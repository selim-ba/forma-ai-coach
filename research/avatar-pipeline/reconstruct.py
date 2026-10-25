"""Step 2: one or more photos -> approximate MHR body shape (identity + proportions). No pose is kept.

    python reconstruct.py private/me/front.jpg --name me
    python reconstruct.py private/me/front.png private/me/side.png private/me/back.png --name me

With several photos of the same person (front / side / back, same outfit and
distance), the body shape is the median across photos and each vertex is
coloured from the photo that sees it most directly.

Writes private/<name>/identity.json, appearance.npz and, for the photo texture,
texture_views.npz plus a cropped copy of each photo (view_<i>.jpg). The whole
private/ folder is git-ignored; delete private/<name>/ to remove everything.
Then build the avatar with:  python build_avatar.py --identity private/<name>/identity.json

Photo tips: one person, whole body visible head to toe, standing upright, facing
the camera, arms slightly away from the body, fitted clothes, plain background,
camera at about hip height. Crop so the person fills most of the frame.

Runs SAM 3D Body (Meta, SAM License) on the CPU. The human detector (detectron2)
is skipped: the whole image is used as the person's box, so crop accordingly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch

from appearance import (best_projector, facing_label, fuse_colors, mirror_map, overlay_image, rasterize_ids,
                        sample_visible, texture_visibility)
from mhr_common import HERE, MHRModel
from silhouette_fit import refine_shape, save_inputs, view_inputs

SAM_DIR_DEFAULT = HERE / "vendor" / "sam-3d-body"
CKPT_DIR_DEFAULT = HERE / "checkpoints" / "sam-3d-body-dinov3"


def cpu_shim() -> None:
    """SAM 3D Body hard-codes .cuda() in a few places; redirect to CPU when no GPU exists."""
    if torch.cuda.is_available():
        return
    torch.Tensor.cuda = lambda self, *a, **k: self  # type: ignore[method-assign]
    torch.nn.Module.cuda = lambda self, *a, **k: self  # type: ignore[method-assign]
    original_to = torch.Tensor.to

    def to(self, *args, **kwargs):
        def fix(v):
            if isinstance(v, str) and v.startswith("cuda"):
                return "cpu"
            if isinstance(v, torch.device) and v.type == "cuda":
                return torch.device("cpu")
            return v
        return original_to(self, *[fix(a) for a in args], **{k: fix(v) for k, v in kwargs.items()})

    torch.Tensor.to = to  # type: ignore[method-assign]


def load_image(path: Path):
    """(RGB uint8 array for SAM, at most 1600 px; full-resolution PIL image for the texture).

    SAM3DBodyEstimator expects RGB arrays. EXIF rotation is honoured; HEIC is ok.
    """
    from PIL import Image, ImageOps
    try:
        import pillow_heif  # noqa: F401
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    full = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img = full
    longest = max(img.size)
    if longest > 1600:  # plenty for body shape; keeps CPU time down
        img = img.resize((round(img.width * 1600 / longest), round(img.height * 1600 / longest)))
    return np.ascontiguousarray(np.asarray(img)), full


def save_texture_view(full, uv: np.ndarray, weight: np.ndarray, small_size: tuple[int, int], path: Path,
                      max_side: int = 2048):
    """Crop the photo around the visible body; return vertex coordinates in the crop's pixels."""
    sx, sy = full.width / small_size[0], full.height / small_size[1]
    uv_full = uv * np.array([sx, sy])
    seen = uv_full[weight > 0] if (weight > 0).any() else uv_full
    lo, hi = seen.min(0), seen.max(0)
    pad = 0.03 * (hi - lo).max()
    x0, y0 = (int(max(0, v)) for v in np.floor(lo - pad))
    x1, y1 = int(min(full.width, np.ceil(hi[0] + pad))), int(min(full.height, np.ceil(hi[1] + pad)))
    crop = full.crop((x0, y0, x1, y1))
    k = min(1.0, max_side / max(crop.size))
    if k < 1.0:
        crop = crop.resize((round(crop.width * k), round(crop.height * k)))
    crop.save(path, quality=92)
    return ((uv_full - np.array([x0, y0])) * k).astype(np.float32), crop.size


class ReconstructionError(Exception):
    """A problem with the photos themselves; the message is safe to show to the person."""


def load_estimator(sam_dir: Path = SAM_DIR_DEFAULT, checkpoint_dir: Path = CKPT_DIR_DEFAULT, device: str = "cpu"):
    """Load SAM 3D Body once (about 10 s); reuse the estimator for every reconstruction."""
    if not (sam_dir / "sam_3d_body").is_dir():
        raise SystemExit(f"SAM 3D Body code not found at {sam_dir}. See README.md, step 2 setup.")
    if device == "cpu":
        cpu_shim()
    if str(sam_dir) not in sys.path:
        sys.path.insert(0, str(sam_dir))
    from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body  # noqa: E402

    model, cfg = load_sam_3d_body(
        checkpoint_path=str(checkpoint_dir / "model.ckpt"),
        mhr_path=str(checkpoint_dir / "assets" / "mhr_model.pt"),
        device=device,
    )
    return SAM3DBodyEstimator(sam_3d_body_model=model, model_cfg=cfg)


def reconstruct(estimator, mhr: MHRModel, photos: list[Path], out_dir: Path, overlays: bool = True, log=print,
                fit_outline: bool = False) -> dict:
    """Photos of one person -> identity.json, appearance.npz, texture_views.npz and view crops in out_dir.

    Returns the identity record (also written to out_dir/identity.json), including any
    "warnings". Raises ReconstructionError when no usable person is found.
    """
    first_scale = mhr.pose_names.index("scale_eye_width")
    scale_names = mhr.pose_names[first_scale:]

    # Landmark vertices on the generic rest mesh, to tell front / side / back views apart.
    rest, _ = mhr.evaluate()
    head = np.flatnonzero(rest[:, 1] > rest[:, 1].max() - 18)  # top ~18 cm
    nose_index = int(head[np.argmax(rest[head, 2])])
    head_index = int(head[np.argmin(rest[head, 2])])  # back of the head: nose - back = facing direction

    out_dir.mkdir(parents=True, exist_ok=True)
    faces = np.asarray(estimator.faces, np.int64)
    shapes, scale_sets, heights, samples, views, tex_views, fit_views = [], [], [], [], [], [], []

    def height_of(shape, scales):
        pose = np.zeros(len(mhr.pose_names), np.float32)
        pose[first_scale:] = scales
        verts, _ = mhr.evaluate(pose, shape)
        return float(verts[:, 1].max() - verts[:, 1].min()) / 100

    skipped = []
    for i, photo in enumerate(photos, start=1):
        img, full = load_image(photo)
        h, w = img.shape[:2]
        started = time.time()
        outputs = estimator.process_one_image(img, bboxes=np.array([[0, 0, w, h]], np.float32), inference_type="body")
        if not outputs:
            log(f"  ✗ {photo.name}: no person found, skipped")
            skipped.append(i)
            continue
        person = outputs[0]
        shape = np.asarray(person["shape_params"], np.float32).reshape(-1)
        scales = np.asarray(person["mhr_model_params"], np.float32).reshape(-1)[first_scale:first_scale + len(scale_names)]
        if shape.shape[0] != mhr.identity_count or len(scales) != len(scale_names):
            raise RuntimeError(f"Unexpected output sizes: shape {shape.shape}, scales {scales.shape}")

        posed = np.asarray(person["pred_vertices"], np.float64).reshape(-1, 3)
        err, project, _signs = best_projector(person, w, h)
        uv, depth = project(posed)
        view = facing_label(posed, nose_index, head_index)
        if overlays:
            overlay_image(img, uv, depth, faces, posed).save(out_dir / f"overlay_{i}_{view}.png")
        ids = rasterize_ids(uv, depth, faces, w, h)
        colors, weight = sample_visible(img, uv, ids, faces, posed + project.cam_t)
        face_visible, tex_weight = texture_visibility(img, uv, ids, faces, posed + project.cam_t)

        tex_uv, tex_size = save_texture_view(full, uv, tex_weight, (w, h), out_dir / f"view_{len(shapes) + 1}.jpg")
        tex_views.append({"uv": tex_uv, "weight": weight.astype(np.float32), "tex_weight": tex_weight,
                          "face_visible": face_visible, "colors": colors.astype(np.float32), "size": tex_size})

        fit_views.append(view_inputs(img, person, project, view, shape))
        shapes.append(shape)
        scale_sets.append(scales)
        heights.append(height_of(shape, scales))
        samples.append((colors, weight))
        views.append(view)
        log(f"  {photo.name}: {view} view, height {heights[-1]:.2f} m, keypoint fit {err:.1f}px, "
            f"{(weight > 0).mean()*100:.0f}% of vertices seen, {time.time() - started:.0f}s")

    if not shapes:
        raise ReconstructionError("No person found in the photos. Take full-body photos, head to toe, "
                                  "with the person filling most of the frame.")

    # Fuse: element-wise median is robust to one bad view.
    shape = np.median(np.stack(shapes), axis=0)
    scales = np.median(np.stack(scale_sets), axis=0)
    regressed_shape = shape.copy()
    fit_report = {"applied": False, "notes": ["turned off"]}
    if fit_outline:
        # The regressor makes bodies too deep (reads as extra body fat): fit the outlines.
        save_inputs(out_dir / "fit_inputs.npz", fit_views, faces)
        try:
            shape, fit_report = refine_shape(mhr, faces, fit_views, shape, log=log,
                                             out_dir=out_dir if overlays else None)
        except Exception as e:  # never lose the avatar over the refinement
            fit_report = {"applied": False, "notes": [f"failed: {e}"]}
            log(f"  ⚠ outline fit failed, keeping the regressed shape: {e}")
    height = height_of(shape, scales)
    spread = (max(heights) - min(heights)) if len(heights) > 1 else 0.0
    shape_dist = [float(np.linalg.norm(s_ - shape)) for s_ in shapes]
    colors, seen = fuse_colors(samples, faces, mirror_map(rest / 100.0))
    np.savez_compressed(out_dir / "appearance.npz", colors=colors, visible=seen)
    tex = {"views": np.array(views)}
    for k_, tv in enumerate(tex_views, start=1):
        tex.update({f"uv_{k_}": tv["uv"], f"weight_{k_}": tv["weight"], f"colors_{k_}": tv["colors"],
                    f"tex_weight_{k_}": tv["tex_weight"], f"face_visible_{k_}": tv["face_visible"],
                    f"size_{k_}": np.array(tv["size"])})
    np.savez_compressed(out_dir / "texture_views.npz", **tex)
    for stale in out_dir.glob("view_*.jpg"):  # a previous run with more photos
        if int(stale.stem.split("_")[1]) > len(tex_views):
            stale.unlink()

    warnings = []
    if skipped:
        warnings.append(f"No person found in photo {', '.join(map(str, skipped))}; it was skipped.")
    if len(shapes) > 1 and (spread > 0.06 or max(shape_dist) > 2.0):
        warnings.append("The photos disagree noticeably: check they show the same person, outfit and distance.")
    if views.count("front") > 1 or ("back" not in views and len(views) >= 3):
        warnings.append("Expected one front, one side and one back photo.")

    out = {
        "identity": [round(float(v), 6) for v in shape],
        "scales": {n: round(float(v), 6) for n, v in zip(scale_names, scales)},
        "estimatedHeightM": round(height, 3),
        "views": views,
        "perViewHeightM": [round(x, 3) for x in heights],
        "perViewShapeDistance": [round(x, 3) for x in shape_dist],
        "regressedIdentity": [round(float(v), 6) for v in regressed_shape],
        "outlineFit": fit_report,
        "warnings": warnings,
        "source": f"SAM 3D Body (facebook/sam-3d-body-dinov3, SAM License), {len(shapes)} photo(s), body decoder, median fusion"
                  + (", outline fit" if fit_report.get("applied") else ""),
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "note": "Approximate body shape from photos. Not a measurement. Delete this folder to remove it.",
    }
    (out_dir / "identity.json").write_text(json.dumps(out, indent=2) + "\n")

    log(f"✓ identity from {len(shapes)} photo(s) ({', '.join(views)}), fused height {height:.2f} m, "
        f"{seen.mean()*100:.0f}% of the body seen in at least one photo")
    if len(shapes) > 1:
        log(f"  consistency: heights {min(heights):.2f}–{max(heights):.2f} m (spread {spread*100:.0f} cm), "
            f"shape distance to fused {', '.join(f'{d:.2f}' for d in shape_dist)}")
    for w_ in warnings:
        log(f"  ⚠ {w_}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", type=Path, nargs="+", help="one or more photos of the same person")
    ap.add_argument("--name", required=True, help="lowercase letters, digits and dashes, e.g. 'me'")
    ap.add_argument("--sam-dir", type=Path, default=SAM_DIR_DEFAULT, help="clone of facebookresearch/sam-3d-body")
    ap.add_argument("--checkpoint-dir", type=Path, default=CKPT_DIR_DEFAULT)
    ap.add_argument("--fit", action="store_true",
                    help="experimental: refine the body shape to the photo outlines (silhouette_fit.py)")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9-]{1,40}", args.name):
        sys.exit("--name must be lowercase letters, digits or dashes (it becomes ?avatar=<name>).")
    started = time.time()
    estimator = load_estimator(args.sam_dir, args.checkpoint_dir, "cuda" if torch.cuda.is_available() else "cpu")
    print(f"  model loaded in {time.time() - started:.0f}s")
    out_dir = HERE / "private" / args.name
    try:
        reconstruct(estimator, MHRModel(), args.photos, out_dir, fit_outline=args.fit)
    except ReconstructionError as e:
        sys.exit(str(e))
    path = out_dir / "identity.json"
    print(f"✓ wrote {path.relative_to(HERE)}")
    print(f"  next: python build_avatar.py --identity {path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
