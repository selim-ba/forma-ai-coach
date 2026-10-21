"""Shared helpers for loading the MHR TorchScript model (CPU only)."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent

# Where to look for mhr_model.pt, in order. The SAM 3D Body checkpoint ships one
# (checkpoints/sam-3d-body-dinov3/assets/mhr_model.pt); the public MHR release does too.
CANDIDATES = [
    os.environ.get("MHR_MODEL_PATH", ""),
    str(HERE / "checkpoints/sam-3d-body-dinov3/assets/mhr_model.pt"),
    str(HERE / "checkpoints/mhr_model.pt"),
]


def find_model_path() -> Path:
    for candidate in CANDIDATES:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit(
        "mhr_model.pt not found. Download the SAM 3D Body checkpoint into "
        "research/avatar-pipeline/checkpoints/ (see README.md) or set MHR_MODEL_PATH."
    )


class MHRModel:
    """Thin wrapper around the official MHR TorchScript model (units: centimetres, +Y up)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or find_model_path()
        self.model = torch.jit.load(str(self.path), map_location="cpu").eval()
        names = list(self.model.get_parameter_names())
        self.identity_count = int(self.model.get_num_identity_blendshapes())
        self.pose_names: list[str] = names[: -self.identity_count] if self.identity_count else names
        self.pose_limits = self.model.get_parameter_limits().detach().cpu().numpy()[: len(self.pose_names)]
        self.joint_names: list[str] = list(self.model.get_joint_names())
        self.joint_parents = np.asarray(
            [int(v) for v in self.model.character_torch.skeleton.joint_parents], dtype=np.int32
        )
        self.faces = self.model.character_torch.mesh.faces.detach().cpu().numpy().astype(np.uint32)
        idx, w = self.model.get_lbsw()
        self.lbs_indices = idx.detach().cpu().numpy()
        self.lbs_weights = w.detach().cpu().numpy().astype(np.float32)

    def index(self, name: str) -> int:
        return self.pose_names.index(name)

    def evaluate(
        self,
        pose: np.ndarray | None = None,
        identity: np.ndarray | None = None,
        correctives: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (vertices [V,3] cm, skeleton_state [J,8] = tx,ty,tz,qx,qy,qz,qw,scale)."""
        pose = np.zeros(len(self.pose_names), np.float32) if pose is None else pose.astype(np.float32)
        identity = np.zeros(self.identity_count, np.float32) if identity is None else identity.astype(np.float32)
        with torch.inference_mode():
            verts, skel = self.model(
                identity_coeffs=torch.from_numpy(identity[None].copy()),
                model_parameters=torch.from_numpy(pose[None].copy()),
                face_expr_coeffs=torch.zeros(1, 72),
                apply_correctives=correctives,
            )
        return verts[0].numpy().astype(np.float64), skel[0].numpy().astype(np.float64)
