"""Step 2: one or more photos -> approximate MHR body shape (identity + proportions). No pose is kept.

    python reconstruct.py private/me/front.jpg --name me
    python reconstruct.py private/me/front.png private/me/side.png private/me/back.png --name me

With several photos of the same person (front / side / back, same outfit and
distance), the body shape is the median across photos and each vertex is
coloured from the photo that sees it most directly.

Writes private/<name>/identity.json (git-ignored). The photo itself is NOT copied.
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

from appearance import best_projector, facing_label, fuse_colors, mirror_map, overlay_image, rasterize_ids, sample_visible
from mhr_common import HERE, MHRModel

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


def load_image(path: Path) -> np.ndarray:
    """Load as RGB uint8 (what SAM3DBodyEstimator expects for arrays), honouring EXIF rotation; HEIC ok."""
    from PIL import Image, ImageOps
    try:
        import pillow_heif  # noqa: F401
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    longest = max(img.size)
    if longest > 1600:  # plenty for body shape; keeps CPU time down
        img = img.resize((round(img.width * 1600 / longest), round(img.height * 1600 / longest)))
    return np.ascontiguousarray(np.asarray(img))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", type=Path, nargs="+", help="one or more photos of the same person")
    ap.add_argument("--name", required=True, help="lowercase letters, digits and dashes, e.g. 'selim'")
    ap.add_argument("--sam-dir", type=Path, default=SAM_DIR_DEFAULT, help="clone of facebookresearch/sam-3d-body")
    ap.add_argument("--checkpoint-dir", type=Path, default=CKPT_DIR_DEFAULT)
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9-]{1,40}", args.name):
        sys.exit("--name must be lowercase letters, digits or dashes (it becomes ?avatar=<name>).")
    if not (args.sam_dir / "sam_3d_body").is_dir():
        sys.exit(f"SAM 3D Body code not found at {args.sam_dir}. See README.md, step 2 setup.")

    cpu_shim()
    sys.path.insert(0, str(args.sam_dir))
    from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body  # noqa: E402

    started = time.time()
    model, cfg = load_sam_3d_body(
        checkpoint_path=str(args.checkpoint_dir / "model.ckpt"),
        mhr_path=str(args.checkpoint_dir / "assets" / "mhr_model.pt"),
        device="cpu",
    )
    estimator = SAM3DBodyEstimator(sam_3d_body_model=model, model_cfg=cfg)
    print(f"  model loaded in {time.time() - started:.0f}s")

    mhr = MHRModel()
    first_scale = mhr.pose_names.index("scale_eye_width")
    scale_names = mhr.pose_names[first_scale:]

    # Landmark vertices on the generic rest mesh, to tell front / side / back views apart.
    rest, _ = mhr.evaluate()
    head = np.flatnonzero(rest[:, 1] > rest[:, 1].max() - 18)  # top ~18 cm
    nose_index = int(head[np.argmax(rest[head, 2])])
    head_index = int(head[np.argmin(rest[head, 2])])  # back of the head: nose - back = facing direction

    out_dir = HERE / "private" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    faces = np.asarray(estimator.faces, np.int64)
    shapes, scale_sets, heights, samples, views = [], [], [], [], []

    def height_of(shape, scales):
        pose = np.zeros(len(mhr.pose_names), np.float32)
        pose[first_scale:] = scales
        verts, _ = mhr.evaluate(pose, shape)
        return float(verts[:, 1].max() - verts[:, 1].min()) / 100

    for i, photo in enumerate(args.photos, start=1):
        img = load_image(photo)
        h, w = img.shape[:2]
        started = time.time()
        outputs = estimator.process_one_image(img, bboxes=np.array([[0, 0, w, h]], np.float32), inference_type="body")
        if not outputs:
            print(f"  ✗ {photo.name}: no person found, skipped")
            continue
        person = outputs[0]
        shape = np.asarray(person["shape_params"], np.float32).reshape(-1)
        scales = np.asarray(person["mhr_model_params"], np.float32).reshape(-1)[first_scale:first_scale + len(scale_names)]
        if shape.shape[0] != mhr.identity_count or len(scales) != len(scale_names):
            sys.exit(f"Unexpected output sizes: shape {shape.shape}, scales {scales.shape}")

        posed = np.asarray(person["pred_vertices"], np.float64).reshape(-1, 3)
        err, project, _signs = best_projector(person, w, h)
        uv, depth = project(posed)
        view = facing_label(posed, nose_index, head_index)
        overlay_image(img, uv, depth, faces, posed).save(out_dir / f"overlay_{i}_{view}.png")
        colors, weight = sample_visible(img, uv, rasterize_ids(uv, depth, faces, w, h), faces, posed + project.cam_t)

        shapes.append(shape)
        scale_sets.append(scales)
        heights.append(height_of(shape, scales))
        samples.append((colors, weight))
        views.append(view)
        print(f"  {photo.name}: {view} view, height {heights[-1]:.2f} m, keypoint fit {err:.1f}px, "
              f"{(weight > 0).mean()*100:.0f}% of vertices seen, {time.time() - started:.0f}s")

    if not shapes:
        sys.exit("No person found in any photo. Use full-body photos where the person fills most of the frame.")

    # Fuse: element-wise median is robust to one bad view.
    shape = np.median(np.stack(shapes), axis=0)
    scales = np.median(np.stack(scale_sets), axis=0)
    height = height_of(shape, scales)
    spread = (max(heights) - min(heights)) if len(heights) > 1 else 0.0
    shape_dist = [float(np.linalg.norm(s_ - shape)) for s_ in shapes]
    colors, seen = fuse_colors(samples, faces, mirror_map(rest / 100.0))
    np.savez_compressed(out_dir / "appearance.npz", colors=colors, visible=seen)

    out = {
        "identity": [round(float(v), 6) for v in shape],
        "scales": {n: round(float(v), 6) for n, v in zip(scale_names, scales)},
        "estimatedHeightM": round(height, 3),
        "views": views,
        "perViewHeightM": [round(x, 3) for x in heights],
        "perViewShapeDistance": [round(x, 3) for x in shape_dist],
        "source": f"SAM 3D Body (facebook/sam-3d-body-dinov3, SAM License), {len(shapes)} photo(s), body decoder, median fusion",
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "note": "Approximate body shape from photos. Not a measurement. Delete this folder to remove it.",
    }
    path = out_dir / "identity.json"
    path.write_text(json.dumps(out, indent=2) + "\n")

    print(f"✓ wrote {path.relative_to(HERE)} from {len(shapes)} photo(s) ({', '.join(views)}), "
          f"fused height {height:.2f} m, {seen.mean()*100:.0f}% of the body seen in at least one photo")
    if len(shapes) > 1:
        print(f"  consistency: heights {min(heights):.2f}–{max(heights):.2f} m (spread {spread*100:.0f} cm), "
              f"shape distance to fused {', '.join(f'{d:.2f}' for d in shape_dist)}")
        if spread > 0.06 or max(shape_dist) > 2.0:
            print("  ⚠ the photos disagree noticeably — check they show the same body, outfit and camera distance")
    if views.count("front") > 1 or ("back" not in views and len(views) >= 3):
        print("  ⚠ expected one front, one side and one back view — check the overlay_*.png images")
    print(f"  next: python build_avatar.py --identity {path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
