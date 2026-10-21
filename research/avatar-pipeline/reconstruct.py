"""Step 2: one photo -> approximate MHR body shape (identity + proportions). No pose is kept.

    python reconstruct.py path/to/photo.jpg --name me

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
    ap.add_argument("photo", type=Path)
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

    img = load_image(args.photo)
    h, w = img.shape[:2]
    started = time.time()
    outputs = estimator.process_one_image(img, bboxes=np.array([[0, 0, w, h]], np.float32), inference_type="body")
    print(f"  inference in {time.time() - started:.0f}s")
    if not outputs:
        sys.exit("No person found. Use a full-body photo where the person fills most of the frame.")
    person = outputs[0]

    shape = np.asarray(person["shape_params"], np.float32).reshape(-1)
    model_params = np.asarray(person["mhr_model_params"], np.float32).reshape(-1)
    mhr = MHRModel()
    first_scale = mhr.pose_names.index("scale_eye_width")
    scale_names = mhr.pose_names[first_scale:]
    scales = model_params[first_scale:first_scale + len(scale_names)]
    if shape.shape[0] != mhr.identity_count or len(scales) != len(scale_names):
        sys.exit(f"Unexpected output sizes: shape {shape.shape}, scales {scales.shape}")

    # Sanity check: rest-pose height of this body.
    pose = np.zeros(len(mhr.pose_names), np.float32)
    pose[first_scale:] = scales
    verts, _ = mhr.evaluate(pose, shape)
    height = float(verts[:, 1].max() - verts[:, 1].min()) / 100

    out_dir = HERE / "private" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "identity": [round(float(v), 6) for v in shape],
        "scales": {n: round(float(v), 6) for n, v in zip(scale_names, scales)},
        "estimatedHeightM": round(height, 3),
        "source": "SAM 3D Body (facebook/sam-3d-body-dinov3, SAM License), single photo, body decoder",
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "note": "Approximate body shape from one image. Not a measurement. Delete this folder to remove it.",
    }
    path = out_dir / "identity.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"✓ wrote {path.relative_to(HERE)} — model height {height:.2f} m "
          "(absolute scale from one photo is approximate; proportions are what matter)")
    print(f"  next: python build_avatar.py --identity {path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
