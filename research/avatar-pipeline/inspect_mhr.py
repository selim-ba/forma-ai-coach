"""Step 0: inspect the MHR model and probe what each pose parameter does.

    python inspect_mhr.py            # writes out/mhr_inspect.json

The JSON lists parameter/joint names, the rest skeleton, and — for every
body pose parameter — which joints move and in which direction when the
parameter is nudged. It contains no personal data (generic body only), and
it is what the motion retargeting in build_avatar.py is written against.
"""
from __future__ import annotations

import json
import time

import numpy as np

from mhr_common import HERE, MHRModel

SKIP_PREFIXES = ("r_thumb", "r_index", "r_middle", "r_ring", "r_pinky",
                 "l_thumb", "l_index", "l_middle", "l_ring", "l_pinky")
DELTA = 0.35  # radians for rotational parameters

started = time.time()
m = MHRModel()
verts0, skel0 = m.evaluate()
rest = skel0[:, :3]

probes = []
for i, name in enumerate(m.pose_names):
    if name.startswith(SKIP_PREFIXES):
        continue
    pose = np.zeros(len(m.pose_names), np.float32)
    lo, hi = m.pose_limits[i]
    delta = DELTA if not name.startswith(("scale_", "root_t")) else 0.1
    pose[i] = float(np.clip(delta, lo, hi)) if hi > lo else delta
    _, skel = m.evaluate(pose)
    disp = skel[:, :3] - rest
    mag = np.linalg.norm(disp, axis=1)
    moved = np.argsort(-mag)[:4]
    probes.append({
        "param": name,
        "index": i,
        "limits": [float(lo), float(hi)],
        "value": float(pose[i]),
        "moved": [
            {"joint": m.joint_names[j], "cm": [round(float(v), 2) for v in disp[j]], "dist": round(float(mag[j]), 2)}
            for j in moved if mag[j] > 0.05
        ],
    })

out = {
    "model": str(m.path.name),
    "counts": {
        "pose_params": len(m.pose_names),
        "identity": m.identity_count,
        "joints": len(m.joint_names),
        "vertices": int(verts0.shape[0]),
        "faces": int(m.faces.shape[0]),
        "lbs_influences_per_vertex": int(m.lbs_indices.shape[1]) if m.lbs_indices.ndim == 2 else None,
    },
    "rest_bbox_cm": {"min": np.round(verts0.min(0), 2).tolist(), "max": np.round(verts0.max(0), 2).tolist()},
    "pose_names": m.pose_names,
    "joints": [
        {"i": j, "name": n, "parent": int(m.joint_parents[j]), "rest_cm": np.round(rest[j], 2).tolist(),
         "scale": round(float(skel0[j, 7]), 4)}
        for j, n in enumerate(m.joint_names)
    ],
    "probes": probes,
}
(HERE / "out").mkdir(exist_ok=True)
path = HERE / "out" / "mhr_inspect.json"
path.write_text(json.dumps(out, indent=1))
print(f"Wrote {path} — {out['counts']} in {time.time() - started:.1f}s")
