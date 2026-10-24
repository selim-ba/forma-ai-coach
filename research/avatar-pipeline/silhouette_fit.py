"""Refine a fused body shape so the posed body matches each photo's outline.

SAM 3D Body regresses the body shape from each photo and reconstruct.py takes the
median. The regressor tends to make bodies too deep (belly and back), which reads as
extra body fat. This step keeps each photo's pose and camera, and adjusts only the
45 MHR shape coefficients so the projected body fits the person's outline:

- The person's outline comes from GrabCut, seeded with the predicted body (no extra
  model, works on a plain or busy background).
- Body pixels outside the outline cost a lot (the body is too big there). Outline
  pixels the body doesn't cover cost little, because clothes and hair add volume.
- A small prior keeps the shape near the regressor's estimate.

Used by reconstruct.py. To re-run only this step on an existing reconstruction:

    python silhouette_fit.py private/<name>

It reads private/<name>/fit_inputs.npz, rewrites identity.json (keeping the old one as
identity.before_fit.json) and writes fit_<i>_<view>.png overlays.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

WORK = 768          # working resolution (longest side) for outlines
W_OVER = 1.0        # body outside the person's outline
W_UNDER = 0.15      # outline not covered by the body (clothes, hair)
PRIOR = 0.02        # pull towards the regressor's shape, per coefficient² (cost is in cm, see View.cost)
STEP = 0.3          # finite-difference step in shape units
ITERATIONS = 10
COMPONENTS = 24     # the leading shape components carry most of the body-shape variation


def similarity(src: np.ndarray, dst: np.ndarray):
    """Least-squares similarity transform (s, R, t) with dst ≈ s·R·src + t (Umeyama)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, sig, vt = np.linalg.svd(b.T @ a / len(src))
    d = np.eye(3)
    if np.linalg.det(u @ vt) < 0:
        d[2, 2] = -1
    r = u @ d @ vt
    s = float(np.trace(np.diag(sig) @ d) / (a ** 2).sum(1).mean())
    return s, r, mu_d - s * r @ mu_s


def person_outline(rgb: np.ndarray, body: np.ndarray, body_height_px: float) -> np.ndarray:
    """Person mask from GrabCut, seeded with the predicted body's silhouette."""
    def grow(m, r):
        r = max(1, int(round(r)))
        return cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))

    def shrink(m, r):
        r = max(1, int(round(r)))
        return cv2.erode(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))

    body = body.astype(np.uint8)
    gc = np.full(body.shape, cv2.GC_BGD, np.uint8)
    gc[grow(body, 0.09 * body_height_px) > 0] = cv2.GC_PR_BGD
    gc[grow(body, 0.015 * body_height_px) > 0] = cv2.GC_PR_FGD
    gc[shrink(body, 0.045 * body_height_px) > 0] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), gc, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    fg = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.uint8)
    # Largest connected piece, holes filled.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n > 1:
        fg = (labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(fg)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled


class View:
    """One photo: its pose and camera stay fixed; only the body shape changes."""

    def __init__(self, mhr, faces, data: dict, correctives: bool):
        self.mhr, self.faces, self.correctives = mhr, faces, correctives
        self.params = data["params"].astype(np.float32)[: len(mhr.pose_names)]
        self.name = str(data["view"])
        h, w = data["size"]
        self.k = WORK / max(h, w)
        self.size = (int(round(h * self.k)), int(round(w * self.k)))
        self.cam_t, self.focal, self.full_size = data["cam_t"], float(data["focal"]), (h, w)
        model_v, _ = mhr.evaluate(self.params, data["shape"], correctives)
        self.s, self.r, self.t = similarity(model_v, data["pred_vertices"])
        fitted = self.s * model_v @ self.r.T + self.t
        self.residual = float(np.sqrt(((fitted - data["pred_vertices"]) ** 2).sum(1).mean()))
        self.rgb = data["rgb"]
        self.offset = np.zeros(2)
        body = self.silhouette(data["pred_vertices"])
        ys = np.flatnonzero(body.any(1))
        self.height_px = float(ys.max() - ys.min()) if len(ys) else 1.0
        self.outline = person_outline(self.rgb, body, self.height_px)
        # The projection can sit a few pixels off the photo: align it before touching the shape.
        best = (-1.0, 0, 0)
        for dy in range(-10, 11):
            for dx in range(-10, 11):
                moved = np.roll(np.roll(body, dy, 0), dx, 1)
                iou = float((moved & self.outline).sum()) / max(1.0, float((moved | self.outline).sum()))
                if iou > best[0]:
                    best = (iou, dx, dy)
        self.offset = np.array([best[1], best[2]], np.float64)
        self.dist_to_outline = cv2.distanceTransform((1 - self.outline).astype(np.uint8), cv2.DIST_L2, 3)
        self.outline_area = max(1, int(self.outline.sum()))
        pv = data["pred_vertices"]
        self.cm_per_px = float(pv[:, 1].max() - pv[:, 1].min()) * 100.0 / self.height_px
        cs, _ = cv2.findContours(self.outline, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        self.perimeter_cm = max(1.0, sum(cv2.arcLength(c, True) for c in cs) * self.cm_per_px)
        self.area_ratio = self.outline_area / max(1, int(body.sum()))

    def vertices(self, shape: np.ndarray) -> np.ndarray:
        v, _ = self.mhr.evaluate(self.params, shape, self.correctives)
        return self.s * v @ self.r.T + self.t

    def project(self, verts: np.ndarray) -> np.ndarray:
        p = verts + self.cam_t
        z = np.maximum(p[:, 2], 1e-6)
        h, w = self.full_size
        uv = np.stack([self.focal * p[:, 0] / z + w / 2, self.focal * p[:, 1] / z + h / 2], axis=1)
        return uv * self.k + self.offset

    def silhouette(self, verts: np.ndarray) -> np.ndarray:
        # One triangle at a time: fillPoly with many overlapping polygons fills by parity (holes).
        tri = np.round(self.project(verts) * 4).astype(np.int32)[self.faces]  # 2 bits of sub-pixel precision
        out = np.zeros(self.size, np.uint8)
        for t in tri:
            cv2.fillConvexPoly(out, t, 1, cv2.LINE_8, 2)
        return out

    def cost(self, shape: np.ndarray) -> tuple[float, float]:
        """(outline cost, IoU) for a shape.

        Each mismatched pixel adds its squared distance to the other outline (cm²) times its
        area; dividing by the outline's length makes a uniform band T cm thick cost T³/3.
        """
        body = self.silhouette(self.vertices(shape))
        over = (body == 1) & (self.outline == 0)
        under = (self.outline == 1) & (body == 0)
        d_over = self.dist_to_outline[over]
        d_under = cv2.distanceTransform((1 - body).astype(np.uint8), cv2.DIST_L2, 3)[under]
        cpp = self.cm_per_px
        c = (W_OVER * ((d_over * cpp) ** 2).sum() + W_UNDER * ((d_under * cpp) ** 2).sum()) * cpp ** 2 / self.perimeter_cm
        inter = float(((body == 1) & (self.outline == 1)).sum())
        iou = inter / max(1.0, float(((body == 1) | (self.outline == 1)).sum()))
        return float(c), iou

    def overlay(self, shape: np.ndarray) -> np.ndarray:
        """Photo with the person's outline (blue) and the fitted body's outline (orange)."""
        img = cv2.cvtColor(self.rgb, cv2.COLOR_RGB2BGR).copy()
        body = self.silhouette(self.vertices(shape))
        for m, col in ((self.outline, (235, 160, 60)), (body, (40, 120, 255))):
            cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(img, cs, -1, col, 2)
        return img


def refine_shape(mhr, faces, views_data: list[dict], shape0: np.ndarray, log=print, out_dir: Path | None = None):
    """Return (refined shape, report). Views whose outline looks unreliable are left out."""
    started = time.time()
    faces = np.asarray(faces, np.int64)
    views, notes = [], []
    corr = None
    for data in views_data:
        if corr is None:  # SAM may or may not apply MHR's pose correctives: use whichever reproduces it
            params = data["params"].astype(np.float32)[: len(mhr.pose_names)]
            res = {}
            for c in (False, True):
                mv, _ = mhr.evaluate(params, data["shape"], c)
                s_, r_, t_ = similarity(mv, data["pred_vertices"])
                res[c] = float(np.sqrt((((s_ * mv @ r_.T + t_) - data["pred_vertices"]) ** 2).sum(1).mean()))
            corr = min(res, key=res.get)
        v = View(mhr, faces, data, corr)
        if v.residual > 0.01:
            notes.append(f"{v.name}: pose not reproduced ({v.residual*100:.1f} cm), skipped")
        elif not 0.75 <= v.area_ratio <= 1.45:
            notes.append(f"{v.name}: outline unreliable (area {v.area_ratio:.2f}× the body), skipped")
        else:
            views.append(v)
    if not views:
        return shape0, {"applied": False, "notes": notes}

    def total(x):
        costs = [v.cost(x) for v in views]
        return sum(c for c, _ in costs) + PRIOR * float(((x - shape0) ** 2).sum()), costs

    x = shape0.astype(np.float64).copy()
    f, costs0 = total(x)
    f0 = f
    for it in range(ITERATIONS):
        grad = np.zeros_like(x)
        for i in range(min(COMPONENTS, len(x))):
            xp = x.copy()
            xp[i] += STEP
            grad[i] = (total(xp)[0] - f) / STEP
        norm = float(np.linalg.norm(grad))
        if norm < 1e-6:
            break
        improved = False
        for length in (1.2, 0.6, 0.3, 0.15):
            cand = x - grad / norm * length
            fc, _ = total(cand)
            if fc < f:
                x, f, improved = cand, fc, True
                break
        if not improved:
            break
    _, costs1 = total(x)
    report = {
        "applied": True,
        "views": [v.name for v in views],
        "offsetsPx": [[int(v.offset[0]), int(v.offset[1])] for v in views],
        "iouBefore": [round(i, 3) for _, i in costs0],
        "iouAfter": [round(i, 3) for _, i in costs1],
        "costBefore": round(f0, 3),
        "costAfter": round(f, 3),
        "shapeChange": round(float(np.linalg.norm(x - shape0)), 3),
        "notes": notes,
    }
    log(f"  outline fit: {len(views)} view(s), IoU "
        f"{', '.join(f'{a:.3f}→{b:.3f}' for a, b in zip(report['iouBefore'], report['iouAfter']))}, "
        f"shape change {report['shapeChange']:.2f}, {time.time() - started:.0f}s")
    for n in notes:
        log(f"  ⚠ outline fit: {n}")
    if out_dir is not None:
        for i, v in enumerate(views, start=1):
            cv2.imwrite(str(out_dir / f"fit_{i}_{v.name}_before.png"), v.overlay(shape0))
            cv2.imwrite(str(out_dir / f"fit_{i}_{v.name}_after.png"), v.overlay(x))
    return x.astype(np.float32), report


def view_inputs(rgb: np.ndarray, person: dict, project, view: str, shape: np.ndarray) -> dict:
    """What refine_shape needs from one photo (also saved to fit_inputs.npz for re-runs)."""
    h, w = rgb.shape[:2]
    k = WORK / max(h, w)
    small = cv2.resize(rgb, (int(round(w * k)), int(round(h * k))), interpolation=cv2.INTER_AREA)
    return {
        "rgb": small,
        "params": np.asarray(person["mhr_model_params"], np.float32).reshape(-1),
        "pred_vertices": np.asarray(person["pred_vertices"], np.float64).reshape(-1, 3),
        "cam_t": np.asarray(project.cam_t, np.float64),
        "focal": float(np.asarray(person["focal_length"]).reshape(-1)[0]),
        "size": np.array([h, w]),
        "view": view,
        "shape": np.asarray(shape, np.float32),
    }


def save_inputs(path: Path, views_data: list[dict], faces: np.ndarray) -> None:
    flat = {"faces": np.asarray(faces, np.int32), "count": np.array(len(views_data))}
    for i, d in enumerate(views_data):
        for key, val in d.items():
            flat[f"{i}_{key}"] = np.asarray(val)
    np.savez_compressed(path, **flat)


def load_inputs(path: Path) -> tuple[list[dict], np.ndarray]:
    z = np.load(path)
    views = []
    for i in range(int(z["count"])):
        d = {key: z[f"{i}_{key}"] for key in ("rgb", "params", "pred_vertices", "cam_t", "focal", "size", "view", "shape")}
        d["focal"] = float(d["focal"])
        d["view"] = str(d["view"])
        views.append(d)
    return views, z["faces"]


def main() -> None:
    from mhr_common import MHRModel

    if len(sys.argv) != 2:
        sys.exit(__doc__)
    folder = Path(sys.argv[1])
    ident_path = folder / "identity.json"
    ident = json.loads(ident_path.read_text())
    backup = folder / "identity.before_fit.json"
    if backup.exists():  # always refit from the regressor's shape, not a previous fit
        ident = {**ident, "identity": json.loads(backup.read_text())["identity"]}
    else:
        backup.write_text(json.dumps(ident, indent=2) + "\n")
    views, faces = load_inputs(folder / "fit_inputs.npz")
    mhr = MHRModel()
    shape, report = refine_shape(mhr, faces, views, np.asarray(ident["identity"], np.float32), out_dir=folder)
    ident["identity"] = [round(float(v), 6) for v in shape]
    ident["outlineFit"] = report
    ident_path.write_text(json.dumps(ident, indent=2) + "\n")
    print(f"✓ wrote {ident_path} (before: {backup.name}); overlays fit_*_before.png / fit_*_after.png")


if __name__ == "__main__":
    main()
