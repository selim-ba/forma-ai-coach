"""Save a body's undressed rest mesh and joints, for tuning clothes.py without a full build.

    python dump_rest.py --body female            # -> out/rest_female.npz
    python dump_rest.py --identity private/x/identity.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from mhr_common import HERE, MHRModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", choices=["male", "female"], default="male")
    ap.add_argument("--identity", type=Path)
    args = ap.parse_args()
    shape_file = args.identity or HERE / ("generic_body_female.json" if args.body == "female" else "generic_body.json")
    data = json.loads(shape_file.read_text())
    m = MHRModel()
    pose = np.zeros(len(m.pose_names), np.float32)
    for name, value in data.get("scales", {}).items():
        pose[m.index(name)] = value
    identity = np.asarray(data["identity"], np.float32)
    v, s = m.evaluate(pose, identity)
    pose[m.index("root_ty")] += -float(v[:, 1].min()) / 10  # cm -> 10 cm units (snap to the floor)
    v, s = m.evaluate(pose, identity)
    name = args.identity.parent.name if args.identity else args.body
    out = HERE / "out" / f"rest_{name}.npz"
    np.savez_compressed(out, v=v / 100.0, joints=s[:, :3] / 100.0, names=np.array(m.joint_names),
                        faces=m.faces.astype(np.int32), lbs_indices=m.lbs_indices, lbs_weights=m.lbs_weights)
    print(f"✓ wrote {out}")


if __name__ == "__main__":
    main()
