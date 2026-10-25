"""Steps 1 and 3: bake an MHR body into a rigged, animated GLB for the Forma viewer.

Clips: squat, biceps_curl, shoulder_press, romanian_deadlift, split_squat, kettlebell_swing,
lateral_raise.

    python build_avatar.py                                   # generic MHR body
    python build_avatar.py --identity private/me/identity.json --name me

Output: public/models/mhr-generic.glb (generic) or public/models/avatars/<name>.glb
(personal, git-ignored), plus a .meta.json QA report next to it.

The motions are the same exercises as the Forma mannequin (src/lib/avatar/motions.ts):
identical timing and phase markers, re-expressed as MHR joint parameters.
Directions were taken from out/mhr_inspect.json probes: positive *_bend flexes
knees/elbows/spine/neck; negative *_upleg_rz flexes the hip; positive *_uparm_rz
raises the arm forward; positive *_uparm_ry raises it sideways; positive root_rx
pitches the whole body forward. Left/right parameters share signs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

from glb_writer import ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER, GLB
from hair import GENERIC_HAIR_SRGB, add_hair, head_weight, srgb_to_linear
import texture
from appearance import mirror_map
from clothes import FEMALE, dress, extents_from_photo, garment_texture
from mhr_common import HERE, MHRModel

REPO = HERE.parent.parent
# Body shape of the default (generic) avatar: a lean, athletic build. Taken from AI-generated
# test photos (not a real person); without it the generic body is MHR's average, which reads heavy.
GENERIC_BODY = HERE / "generic_body.json"
GENERIC_BODY_FEMALE = HERE / "generic_body_female.json"  # same idea, from AI-generated photos of a woman
FPS, DURATION = 30, 4.0
D = math.radians

# Same easing keys and markers as src/lib/avatar/motions.ts (the catalog depends on them).
TIMELINES = {
    "squat": {"keys": [(0, 0), (0.3, 0), (1.8, 1), (2.2, 1), (3.7, 0), (4, 0)],
              "markers": {"start": 0, "middle": 1.05 / 4, "bottom": 2.0 / 4}},
    "biceps_curl": {"keys": [(0, 0), (0.3, 0), (1.5, 1), (1.9, 1), (3.7, 0), (4, 0)],
                    "markers": {"start": 0, "middle": 0.9 / 4, "top": 1.7 / 4}},
    # Same rhythm as the curl: 1.2 s press, 0.4 s lockout, 1.8 s lowering.
    "shoulder_press": {"keys": [(0, 0), (0.3, 0), (1.5, 1), (1.9, 1), (3.7, 0), (4, 0)],
                       "markers": {"start": 0, "middle": 0.9 / 4, "top": 1.7 / 4}},
    # Same rhythm as the squat: 1.5 s down, 0.4 s hold, 1.5 s up.
    "romanian_deadlift": {"keys": [(0, 0), (0.3, 0), (1.8, 1), (2.2, 1), (3.7, 0), (4, 0)],
                          "markers": {"start": 0, "middle": 1.05 / 4, "bottom": 2.0 / 4}},
    "split_squat": {"keys": [(0, 0), (0.3, 0), (1.8, 1), (2.2, 1), (3.7, 0), (4, 0)],
                    "markers": {"start": 0, "middle": 1.05 / 4, "bottom": 2.0 / 4}},
    # Two curves: hinge depth (keys) and the arms' angle from vertical (arm_keys, x 90°).
    # Stand, hike back between the legs, snap up to chest height, swing back, stand up.
    "kettlebell_swing": {"keys": [(0, 0), (0.3, 0), (1.2, 1), (2.2, 0), (3.2, 1), (4, 0)],
                         "arm_keys": [(0, 0.25), (0.3, 0.25), (1.2, -0.12), (2.2, 1.0), (3.2, -0.12), (4, 0.25)],
                         "markers": {"start": 0, "bottom": 1.2 / 4, "top": 2.2 / 4}},
    "lateral_raise": {"keys": [(0, 0), (0.3, 0), (1.5, 1), (1.9, 1), (3.7, 0), (4, 0)],
                      "markers": {"start": 0, "middle": 0.9 / 4, "top": 1.7 / 4}},
}

# Split squat stance (metres, relative to the rest ankles): left foot forward, right foot back
# with the heel raised. The feet stay put for the whole clip.
SPLIT_FRONT, SPLIT_BACK, SPLIT_HEEL = 0.36, 0.42, 0.07

# Tunables (radians). Iterate on these with the viewer.
ARM_DOWN_RY = -0.55          # bring the A-pose arms down towards the body
ELBOW_REST = -0.40           # rest elbow is ~35° bent in the A-pose; -0.40 ≈ 12° total flexion
ELBOW_CURL_TOP = 1.83        # ≈ 140° total flexion at the top of the curl


def ease(x: float) -> float:
    return -(math.cos(math.pi * x) - 1) / 2


def sample(keys, t: float) -> float:
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            x = 1.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * ease(x)
    return keys[-1][1]


def both(d: dict, name: str, value: float) -> None:
    d[f"l_{name}"] = value
    d[f"r_{name}"] = value


def squat_pose(s: float, twist: float) -> dict:
    """Beginner bodyweight squat; s = depth 0..1 (same world targets as the mannequin)."""
    d = {"root_rx": D(34) * s, "spine_bend0": D(4) * s, "neck_bend": D(-22) * s, "head_bend": D(-8) * s}
    both(d, "upleg_rz", -D(112) * s)      # hip flexion relative to the pitched pelvis
    both(d, "knee_bend", D(112) * s)
    both(d, "foot_bend", -D(34) * s)      # dorsiflexion keeps the foot flat
    both(d, "uparm_ry", ARM_DOWN_RY)            # seed; solved by solve_arms()
    both(d, "uparm_rz", min(1.95, D(120) * s))  # arms reach forward for balance
    both(d, "elbow_bend", ELBOW_REST)           # seed; solved by solve_arms()
    both(d, "lowarm_twist", twist)
    return d


def curl_pose(c: float, twist: float) -> dict:
    """Standing dumbbell curl; c = 0 extended .. 1 top. Upper arms stay by the sides."""
    d: dict = {}
    both(d, "uparm_ry", ARM_DOWN_RY)        # seeds; all four arm values are solved by solve_arms()
    both(d, "uparm_rz", 0.05 + 0.10 * c)
    both(d, "elbow_bend", ELBOW_REST + (ELBOW_CURL_TOP - ELBOW_REST) * c)
    both(d, "lowarm_twist", twist)
    return d


def press_pose(p: float, twist: float) -> dict:
    """Standing dumbbell shoulder press; p = 0 rack (dumbbells at shoulder height) .. 1 overhead."""
    d: dict = {}
    both(d, "clavicle_ry", 0.22 * p)        # shoulder blades rotate up as the arms go overhead
    both(d, "uparm_ry", 0.6 + 0.5 * p)      # seeds; the arm values are solved by solve_arms()
    both(d, "uparm_rz", 0.3 + 0.6 * p)
    both(d, "elbow_bend", 1.5 * (1 - p))
    both(d, "lowarm_twist", twist)
    return d


def rdl_pose(s: float, twist: float) -> dict:
    """Dumbbell Romanian deadlift; s = 0 standing .. 1 bottom. Hip hinge with a flat back:
    the torso pitches 55°, knees stay soft (18°), shins nearly vertical, head in line."""
    pitch = D(55) * s
    d = {"root_rx": pitch, "spine_bend0": D(-2) * s, "neck_bend": D(-10) * s, "head_bend": D(-4) * s}
    both(d, "upleg_rz", -(pitch + D(12) * s))   # thighs end 12° forward of vertical (hips back)
    both(d, "knee_bend", D(18) * s)
    both(d, "foot_bend", -D(6) * s)             # keeps the feet flat
    both(d, "uparm_ry", ARM_DOWN_RY)            # seeds; solved by solve_arms()
    both(d, "uparm_rz", 0.05 + 0.5 * s)
    both(d, "elbow_bend", ELBOW_REST)
    both(d, "lowarm_twist", twist)
    return d


def split_pose(s: float, twist: float) -> dict:
    """Split squat (static lunge); s = 0 top .. 1 bottom. Legs and pelvis are solved by
    solve_split(); these are only seeds. Torso nearly upright, arms hanging."""
    d = {"root_rx": D(4) * s, "l_upleg_rz": -0.35 - 1.2 * s, "l_knee_bend": 0.15 + 1.4 * s, "l_foot_bend": -0.1,
         "r_upleg_rz": 0.35 - 0.3 * s, "r_knee_bend": 0.3 + 1.2 * s, "r_foot_bend": 0.5}
    both(d, "uparm_ry", ARM_DOWN_RY)
    both(d, "uparm_rz", 0.05)
    both(d, "elbow_bend", ELBOW_REST)
    both(d, "lowarm_twist", twist)
    return d


def swing_pose(h: float, twist: float) -> dict:
    """Kettlebell swing body; h = hinge depth 0 (standing tall) .. 1 (back-swing). Arms are solved."""
    pitch = D(50) * h
    d = {"root_rx": pitch, "spine_bend0": D(-2) * h, "neck_bend": D(-14) * h, "head_bend": D(-4) * h}
    both(d, "upleg_rz", -(pitch + D(25) * h))
    both(d, "knee_bend", D(30) * h)
    both(d, "foot_bend", -D(5) * h)            # = -(pitch - hip flexion + knee): feet flat
    both(d, "uparm_ry", ARM_DOWN_RY + 0.1)
    both(d, "uparm_rz", 0.1)
    both(d, "elbow_bend", ELBOW_REST)
    both(d, "lowarm_twist", twist)
    return d


def raise_pose(p: float, twist: float) -> dict:
    """Lateral raise; p = 0 arms by the sides .. 1 at shoulder height. Arms are solved."""
    d: dict = {}
    both(d, "clavicle_ry", 0.06 * p)
    both(d, "uparm_ry", ARM_DOWN_RY + 1.4 * p)
    both(d, "uparm_rz", 0.05 + 0.3 * p)
    both(d, "elbow_bend", ELBOW_REST + 0.2)
    both(d, "lowarm_twist", twist)
    return d


POSES = {"squat": squat_pose, "biceps_curl": curl_pose, "shoulder_press": press_pose,
         "romanian_deadlift": rdl_pose, "split_squat": split_pose,
         "kettlebell_swing": swing_pose, "lateral_raise": raise_pose}


def cylinder(center: np.ndarray, axis: np.ndarray, radius: float, length: float, segments: int = 20):
    """Closed cylinder as (positions, normals, triangle indices); flat caps, smooth sides."""
    axis = axis / np.linalg.norm(axis)
    ref = np.array([0.0, 1.0, 0.0]) if abs(axis[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    a = np.cross(axis, ref)
    a /= np.linalg.norm(a)
    b = np.cross(axis, a)
    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring = np.cos(ang)[:, None] * a + np.sin(ang)[:, None] * b
    lo, hi = center - axis * length / 2, center + axis * length / 2
    pos, nrm, tris = [], [], []
    # sides
    pos += [lo + radius * ring, hi + radius * ring]
    nrm += [ring, ring]
    for i in range(segments):
        j = (i + 1) % segments
        tris += [[i, j, segments + i], [j, segments + j, segments + i]]
    # caps
    for end, sign in ((lo, -1.0), (hi, 1.0)):
        base = sum(len(p_) for p_ in pos)
        pos += [end[None, :], end + radius * ring]
        nrm += [np.repeat(sign * axis[None, :], segments + 1, axis=0)]
        for i in range(segments):
            j = (i + 1) % segments
            tris.append([base, base + 1 + i, base + 1 + j] if sign > 0 else [base, base + 1 + j, base + 1 + i])
    return np.concatenate(pos), np.concatenate(nrm), np.asarray(tris, np.int64)


def dumbbell(center: np.ndarray, axis: np.ndarray):
    """A light dumbbell: 14 cm handle, two 9 cm-diameter plates clear of a ~9 cm-wide hand."""
    axis = axis / np.linalg.norm(axis)
    parts = [cylinder(center, axis, 0.015, 0.16),
             cylinder(center + axis * 0.065, axis, 0.045, 0.03),
             cylinder(center - axis * 0.065, axis, 0.045, 0.03)]
    pos, nrm, tris, off = [], [], [], 0
    for p_, n_, t_ in parts:
        pos.append(p_)
        nrm.append(n_)
        tris.append(t_ + off)
        off += len(p_)
    return np.concatenate(pos), np.concatenate(nrm), np.concatenate(tris)


def kettlebell(handle: np.ndarray, down: np.ndarray, across: np.ndarray, radius: float = 0.085):
    """A kettlebell whose handle (a torus in the down/across plane) is centred on `handle`
    and whose bell hangs below it along `down`. Returns (positions, normals, triangles)."""
    down = down / np.linalg.norm(down)
    across = across - down * np.dot(across, down)
    across /= np.linalg.norm(across)
    third = np.cross(down, across)
    center = handle + down * (radius + 0.05)
    pos, nrm, tris = [], [], []
    # bell: UV sphere
    rings, segs = 14, 24
    for i in range(rings + 1):
        th = math.pi * i / rings
        for k in range(segs):
            ph = 2 * math.pi * k / segs
            n = math.cos(th) * -down + math.sin(th) * (math.cos(ph) * across + math.sin(ph) * third)
            pos.append(center + radius * n)
            nrm.append(n)
    for i in range(rings):
        for k in range(segs):
            a, b = i * segs + k, i * segs + (k + 1) % segs
            c, d = a + segs, b + segs
            tris += [[a, c, b], [b, c, d]]
    # handle: torus around `third`, centred between the hands
    base = len(pos)
    R, r, n_major, n_minor = 0.065, 0.012, 28, 10
    for i in range(n_major):
        u = 2 * math.pi * i / n_major
        ring_dir = math.cos(u) * across + math.sin(u) * -down
        ring_c = handle + down * 0.035 + R * ring_dir
        for k in range(n_minor):
            v = 2 * math.pi * k / n_minor
            n = math.cos(v) * ring_dir + math.sin(v) * third
            pos.append(ring_c + r * n)
            nrm.append(n)
    for i in range(n_major):
        for k in range(n_minor):
            a = base + i * n_minor + k
            b = base + i * n_minor + (k + 1) % n_minor
            c = base + ((i + 1) % n_major) * n_minor + k
            d = base + ((i + 1) % n_major) * n_minor + (k + 1) % n_minor
            tris += [[a, b, c], [b, d, c]]
    return np.asarray(pos), np.asarray(nrm), np.asarray(tris, np.int64)


def ponytail(root: np.ndarray):
    """A ponytail hanging from `root` (back of the head, rest pose, metres): a tapered tube
    along a gentle S-curve, closed at the tip. Returns (positions, normals, triangles)."""
    ctrl = [root, root + np.array([0.0, 0.012, -0.06]), root + np.array([0.0, -0.08, -0.09]),
            root + np.array([0.0, -0.215, -0.06])]
    n_ring, n_seg = 16, 24
    s = np.linspace(0, 1, n_seg)
    b = [(1 - s) ** 3, 3 * s * (1 - s) ** 2, 3 * s ** 2 * (1 - s), s ** 3]
    pts = sum(bi[:, None] * c for bi, c in zip(b, ctrl))
    radius = np.interp(s, [0, 0.08, 0.25, 0.65, 0.9, 1], [0.014, 0.017, 0.031, 0.024, 0.012, 0.003])
    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    side = np.array([1.0, 0.0, 0.0])
    pos, nrm, tris = [], [], []
    for i in range(n_seg):
        nvec = np.cross(tang[i], side)
        nvec /= np.linalg.norm(nvec)
        for k in range(n_ring):
            a = 2 * np.pi * k / n_ring
            d = np.cos(a) * side + np.sin(a) * nvec
            pos.append(pts[i] + radius[i] * d)
            nrm.append(d)
    for i in range(n_seg - 1):
        for k in range(n_ring):
            a0, a1 = i * n_ring + k, i * n_ring + (k + 1) % n_ring
            b0, b1 = a0 + n_ring, a1 + n_ring
            tris += [[a0, b0, a1], [a1, b0, b1]]
    tip = len(pos)
    pos.append(pts[-1] + tang[-1] * 0.004)
    nrm.append(tang[-1])
    last = (n_seg - 1) * n_ring
    tris += [[last + k, tip, last + (k + 1) % n_ring] for k in range(n_ring)]
    return np.asarray(pos), np.asarray(nrm), np.asarray(tris, np.int64)


# --------------------------------------------------------------------------- math
def quat_to_mat(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def mat_to_quat(m: np.ndarray) -> np.ndarray:
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def locals_from_state(state: np.ndarray, parents: np.ndarray):
    """skeleton_state (metres) -> per-joint local (t, q, s) relative to the parent joint."""
    n = len(parents)
    R = np.stack([quat_to_mat(state[j, 3:7]) for j in range(n)])
    T, S = state[:, :3], state[:, 7]
    lt, lq, ls = np.zeros((n, 3)), np.zeros((n, 4)), np.zeros(n)
    for j in range(n):
        p = parents[j]
        if p < 0:
            lt[j], lq[j], ls[j] = T[j], mat_to_quat(R[j]), S[j]
        else:
            lt[j] = R[p].T @ (T[j] - T[p]) / S[p]
            lq[j] = mat_to_quat(R[p].T @ R[j])
            ls[j] = S[j] / S[p]
    return lt, lq, ls, R


# --------------------------------------------------------------------------- build
def build(identity_path: Path | None, out_path: Path, use_texture: bool = True, mhr: MHRModel | None = None,
          log=print, generic_body: Path | None = GENERIC_BODY, hairstyle: str = "short",
          female: bool = False) -> dict:
    """Bake the generic body (identity_path=None) or a personal one into out_path (+ .meta.json).

    Personal avatars read appearance.npz / texture_views.npz / view_*.jpg next to the identity
    file. Returns the metadata written to the .meta.json file.
    """
    print = log  # noqa: A001 — every progress line goes to the caller's logger
    m = mhr or MHRModel()
    P = len(m.pose_names)
    base = np.zeros(P, np.float32)
    identity = np.zeros(m.identity_count, np.float32)
    personal = identity_path is not None
    shape_file = identity_path if personal else (generic_body if generic_body and generic_body.is_file() else None)
    if shape_file is not None:
        data = json.loads(shape_file.read_text())
        identity = np.asarray(data["identity"], np.float32)
        for name, value in data.get("scales", {}).items():
            base[m.index(name)] = value
        if not personal:
            print(f"  generic body shape from {shape_file.name}")

    idx = {n: i for i, n in enumerate(m.joint_names)}
    ankles = [idx["l_talocrural"], idx["r_talocrural"]]

    def evaluate(pose_dict: dict, root_t=np.zeros(3)):
        pose = base.copy()
        for k, v in pose_dict.items():
            pose[m.index(k)] = v
        pose[m.index("root_tx")] += root_t[0] * 10  # metres -> root_t* units (1 unit = 10 cm)
        pose[m.index("root_ty")] += root_t[1] * 10
        pose[m.index("root_tz")] += root_t[2] * 10
        v, s = m.evaluate(pose, identity)
        return v / 100.0, np.concatenate([s[:, :3] / 100.0, s[:, 3:]], axis=1)

    # Bind pose: zero pose (A-pose) snapped to the floor.
    v0, s0 = evaluate({})
    base[m.index("root_ty")] += -float(v0[:, 1].min()) * 10  # metres -> 10 cm units
    v0, s0 = evaluate({})
    rest_ankles = s0[ankles, :3].copy()

    # Clothes (generic body): reshape the rest mesh into a T-shirt and shorts that drape like
    # fabric, before anything measures the body, so clearances account for the garments.
    garment_fields, clothes_info = None, None
    joints_rest = {n: s0[i, :3] for i, n in enumerate(m.joint_names)}
    if not personal:
        v0, _garment_label, clothes_info, garment_fields = dress(v0, m.faces.astype(np.int64), joints_rest,
                                                                 FEMALE if female else None)
        print(f"  clothes: {clothes_info}")
    elif (identity_path.parent / "appearance.npz").is_file():
        # Photo avatars: the garments' shape follows what the person wore (sleeve and leg
        # lengths read from the photo colours); the photo texture still paints them.
        z = np.load(identity_path.parent / "appearance.npz")
        if len(z["colors"]) == len(v0):
            ext, ext_info = extents_from_photo(v0, joints_rest, z["colors"].astype(np.float64) / 255.0, z["visible"])
            if ext:
                cut = {**(FEMALE if female else {}), **ext, "hem_ease": 0.004}
                v0, _garment_label, clothes_info, _fields = dress(v0, m.faces.astype(np.int64), joints_rest, cut)
                clothes_info = {**clothes_info, "fromPhoto": ext_info}
                print(f"  clothes from the photos: {clothes_info}")
            else:
                print(f"  clothes: not enough of the body seen to shape garments ({ext_info})")

    # Solve forearm twist so the palms face forward at the curl's start (supinated grip).
    fingers = {side: [idx[f"{side}_wrist"], idx[f"{side}_middle1"], idx[f"{side}_index1"], idx[f"{side}_pinky1"]]
               for side in ("l", "r")}

    def palm_normal(state: np.ndarray, side: str) -> np.ndarray:
        """Unit vector pointing out of the palm (anatomical position: +Z, forward)."""
        w, mid, ind, pin = fingers[side]
        a, b = state[mid, :3] - state[w, :3], state[ind, :3] - state[pin, :3]
        n = np.cross(a, b) if side == "l" else np.cross(b, a)
        return n / (np.linalg.norm(n) + 1e-9)

    def palm_forwardness(state: np.ndarray) -> float:
        return float(np.mean([palm_normal(state, side)[2] for side in ("l", "r")]))


    def arm_points(state: np.ndarray, side: str):
        return (state[idx[f"{side}_uparm"], :3], state[idx[f"{side}_lowarm"], :3], state[idx[f"{side}_wrist"], :3])

    def flexion(sh, el, wr) -> float:
        u, f = el - sh, wr - el
        return math.acos(float(np.clip(np.dot(u, f) / (np.linalg.norm(u) * np.linalg.norm(f) + 1e-12), -1, 1)))

    def solve_arms(pose: dict, unknowns: list[str], residual, iterations: int = 8, limits: dict | None = None) -> dict:
        """Gauss-Newton on per-arm parameters (both arms at once; arms are independent).

        residual(state, side) -> np.ndarray of goal errors for that arm. Unknown names are
        given without the l_/r_ prefix; the numerical Jacobian is block-diagonal per side.
        """
        pose = dict(pose)

        def err(p_):
            _, st_ = evaluate(p_)
            return {side: residual(st_, side) for side in ("l", "r")}

        r = err(pose)
        for _ in range(iterations):
            if max(np.abs(v).max() for v in r.values()) < 1e-3:
                break
            _, st = evaluate(pose)
            J = {side: np.zeros((len(r[side]), len(unknowns))) for side in ("l", "r")}
            for k, u in enumerate(unknowns):
                trial = dict(pose)
                for side in ("l", "r"):
                    trial[f"{side}_{u}"] = pose.get(f"{side}_{u}", 0.0) + 1e-3
                _, st2 = evaluate(trial)
                for side in ("l", "r"):
                    J[side][:, k] = (residual(st2, side) - r[side]) / 1e-3
            steps = {side: np.clip(np.linalg.lstsq(J[side], -r[side], rcond=None)[0], -0.3, 0.3) for side in ("l", "r")}
            scale = 1.0
            for _attempt in range(5):  # backtracking: never accept a step that makes things worse
                trial = dict(pose)
                for side in ("l", "r"):
                    for k, u in enumerate(unknowns):
                        name = f"{side}_{u}"
                        lo, hi = (limits or {}).get(u, m.pose_limits[m.index(name)])
                        trial[name] = float(np.clip(pose.get(name, 0.0) + scale * steps[side][k], lo, hi))
                r_trial = err(trial)
                if sum(float(v @ v) for v in r_trial.values()) < sum(float(v @ v) for v in r.values()):
                    pose, r = trial, r_trial
                    break
                scale *= 0.5
            else:
                # Every step made things worse: usually a parameter pushed into its joint limit.
                # Freeze the parameters at a limit that the step pushes into and solve for the rest.
                trial = dict(pose)
                for side in ("l", "r"):
                    free = np.ones(len(unknowns), bool)
                    for k, u in enumerate(unknowns):
                        lo, hi = (limits or {}).get(u, m.pose_limits[m.index(f"{side}_{u}")])
                        v_ = pose.get(f"{side}_{u}", 0.0)
                        if (v_ <= lo + 1e-4 and steps[side][k] < 0) or (v_ >= hi - 1e-4 and steps[side][k] > 0):
                            free[k] = False
                    step = np.zeros(len(unknowns))
                    if free.any():
                        step[free] = np.clip(np.linalg.lstsq(J[side][:, free], -r[side], rcond=None)[0], -0.3, 0.3)
                    for k, u in enumerate(unknowns):
                        name = f"{side}_{u}"
                        lo, hi = (limits or {}).get(u, m.pose_limits[m.index(name)])
                        trial[name] = float(np.clip(pose.get(name, 0.0) + 0.5 * step[k], lo, hi))
                r_trial = err(trial)
                if sum(float(v @ v) for v in r_trial.values()) < sum(float(v @ v) for v in r.values()):
                    pose, r = trial, r_trial
                    continue
                break
        solve_arms.last_error = max(float(np.abs(v).max()) for v in r.values())  # type: ignore[attr-defined]
        return pose

    SIGN = {"l": 1.0, "r": -1.0}  # +x is outward for the left arm, -x for the right arm

    def curl_goals(c: float, solve_twist: bool = False):
        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            sg = SIGN[side]
            rows = [
                sg * (el[0] - sh[0]) - 0.05,          # elbow just outside the shoulder line, clear of the torso
                (el[2] - sh[2]) - (0.02 + 0.05 * c),  # elbow drifts only slightly forward
                flexion(sh, el, wr) - D(12 + 113 * c),  # 12° (extended) -> 125° (top, hands ~shoulder height)
            ]
            if solve_twist:
                rows.append(sg * (wr[0] - el[0]))     # hand in front of the elbow: fixes the humerus twist
            return np.array(rows)
        unknowns = ["uparm_ry", "uparm_rz", "elbow_bend"] + (["uparm_twist"] if solve_twist else [])
        return unknowns, residual

    def squat_goals(s: float, hang_offset: float):
        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            return np.array([
                SIGN[side] * (wr[0] - sh[0]) - hang_offset * (1 - s),  # parallel arms at depth
                flexion(sh, el, wr) - D(10),
            ])
        return ["uparm_ry", "elbow_bend"], residual

    def plant_feet(pose: dict, iterations: int = 4, widen: float = 0.0) -> dict:
        """Hip ab/adduction correction so each ankle keeps its rest X (no sideways foot slide).

        MHR's rest legs are slightly abducted, so pure hip flexion swings the feet outwards.
        Small Newton steps on *_upleg_ry with a numerical derivative remove that drift.
        """
        pose = dict(pose)
        for _ in range(iterations):
            _, s = evaluate(pose)
            done = True
            for k, side in enumerate(("l", "r")):
                name = f"{side}_upleg_ry"
                err = s[ankles[k], 0] - (rest_ankles[k, 0] + (widen if side == "l" else -widen))
                if abs(err) < 2e-4:
                    continue
                done = False
                trial = dict(pose)
                trial[name] = pose.get(name, 0.0) + 0.02
                _, s2 = evaluate(trial)
                slope = (s2[ankles[k], 0] - s[ankles[k], 0]) / 0.02
                if abs(slope) > 1e-4:
                    pose[name] = float(np.clip(pose.get(name, 0.0) - err / slope, -1.6, 0.6))
            if done:
                break
        return pose

    # Curl setup: (1) solve the TOP pose to find the humerus twist that keeps the curl in a
    # sagittal plane, freeze it; (2) solve the start pose; (3) pick the forearm twist that turns
    # the palms forward there. The squat reuses that forearm twist.
    u_top, r_top = curl_goals(1.0, solve_twist=True)
    top_pose = solve_arms(curl_pose(1.0, 0.0), u_top, r_top, iterations=25)
    print(f"  curl top solve error {solve_arms.last_error:.4f}")
    humerus_twist = {side: top_pose.get(f"{side}_uparm_twist", 0.0) for side in ("l", "r")}

    def with_humerus_twist(pose: dict) -> dict:
        return {**pose, "l_uparm_twist": humerus_twist["l"], "r_uparm_twist": humerus_twist["r"]}

    u0, r0 = curl_goals(0.0)
    start_pose = solve_arms(with_humerus_twist({**curl_pose(0.0, 0.0), **{k: v for k, v in top_pose.items() if "uparm" in k}}), u0, r0, iterations=25)
    twists = np.linspace(-2.2, 1.0, 81)
    scores = [palm_forwardness(evaluate({**start_pose, "l_lowarm_twist": t, "r_lowarm_twist": t})[1]) for t in twists]
    twist = float(twists[int(np.argmax(scores))])
    start_pose = {**start_pose, "l_lowarm_twist": twist, "r_lowarm_twist": twist}
    _, st_start = evaluate(start_pose)
    print(f"  curl start: solve error {solve_arms.last_error:.4f}, palm forwardness {palm_forwardness(st_start):.2f} "
          f"(1 = straight ahead), humerus twist {humerus_twist['l']:.2f}, forearm twist {twist:.2f}")
    sh_l, el_l, wr_l = arm_points(st_start, "l")
    hang_offset = float(wr_l[0] - sh_l[0])  # how far the hanging hand sits outside the shoulder
    arm_len = float(np.linalg.norm(el_l - sh_l) + np.linalg.norm(wr_l - el_l))

    # ---------------------------------------------------------------- shoulder press
    # Rack: wrists 4 cm above and 16 cm outside the shoulder joints, a little forward, elbows
    # under the wrists and slightly forward. Top: arms almost straight overhead.
    PRESS_LIMITS = {"uparm_ry": (-1.0, 2.9), "uparm_rz": (-1.2, 3.0)}  # overhead needs more than the model's defaults

    def press_goals(p: float):
        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            sg = SIGN[side]
            return np.array([
                sg * (wr[0] - sh[0]) - (0.16 - 0.10 * p),
                (wr[1] - sh[1]) - (0.04 + (0.95 * arm_len - 0.04) * p),
                (wr[2] - sh[2]) - (0.05 - 0.03 * p),
                (el[2] - sh[2]) - 0.06 * (1 - p),
            ])
        return ["uparm_ry", "uparm_rz", "elbow_bend", "uparm_twist"], residual

    u_ps, r_ps = press_goals(0.0)
    press_start = solve_arms(press_pose(0.0, 0.0), u_ps, r_ps, iterations=40, limits=PRESS_LIMITS)
    press_err = solve_arms.last_error
    scores = [palm_forwardness(evaluate({**press_start, "l_lowarm_twist": t, "r_lowarm_twist": t})[1]) for t in twists]
    press_twist = float(twists[int(np.argmax(scores))])
    press_start = {**press_start, "l_lowarm_twist": press_twist, "r_lowarm_twist": press_twist}
    walk = dict(press_start)  # follow the press upwards from the rack, as the bake does
    for p_ in np.linspace(0.1, 1.0, 10):
        u_pt, r_pt = press_goals(float(p_))
        walk = solve_arms({**walk, **{k: v for k, v in press_pose(float(p_), press_twist).items() if "clavicle" in k}},
                          u_pt, r_pt, iterations=25, limits=PRESS_LIMITS)
    print(f"  press: rack solve error {press_err:.4f}, top solve error {solve_arms.last_error:.4f}, "
          f"palm forwardness {max(scores):.2f}, forearm twist {press_twist:.2f}")

    # ---------------------------------------------------------------- Romanian deadlift
    # Arms hang straight down from the shoulders, hands just in front of the thighs, palms
    # facing the body (pronated grip).
    # Leg "front surface" model: how far the thigh and shin stick out in front of their bone
    # axis (measured on the rest mesh), so the dumbbells can be kept just in front of the legs.
    def leg_radius(side: str, a: str, b: str) -> float:
        pa, pb = s0[idx[f"{side}_{a}"], :3], s0[idx[f"{side}_{b}"], :3]
        mid = (pa + pb) / 2
        near = (np.abs(v0[:, 1] - mid[1]) < 0.02) & (np.abs(v0[:, 0] - mid[0]) < 0.07)
        return float(v0[near, 2].max() - mid[2]) if near.any() else 0.07

    LEG_SEGMENTS = {side: [("upleg", "lowleg", leg_radius(side, "upleg", "lowleg")),
                           ("lowleg", "talocrural", leg_radius(side, "lowleg", "talocrural"))] for side in ("l", "r")}
    DUMBBELL_CLEARANCE = 0.09  # palm → far edge of the plates (3.5 cm offset + 4.5 cm radius) + 1 cm

    def leg_front_z(st, side: str, y: float) -> float:
        front = -np.inf
        for a, b, r in LEG_SEGMENTS[side]:
            pa, pb = st[idx[f"{side}_{a}"], :3], st[idx[f"{side}_{b}"], :3]
            lo, hi = min(pa[1], pb[1]), max(pa[1], pb[1])
            if lo <= y <= hi and hi - lo > 1e-6:
                p = pa + (y - pa[1]) / (pb[1] - pa[1]) * (pb - pa)
                front = max(front, p[2] + r)
        return front

    # ---------------------------------------------------------------- body-surface clearance
    # Front-surface depth map of the torso + legs (no arms) in the rest pose: for each 1 cm
    # (x, y) cell, the largest z (front-most skin). Arm points are mapped into the rest pose
    # through the torso frame (so it follows the hinge) and must stay in front of the skin.
    arm_words = ("uparm", "lowarm", "wrist", "hand", "thumb", "index", "middle", "ring", "pinky")
    arm_joint_ids = [i for i, n in enumerate(m.joint_names) if any(w in n for w in arm_words)]
    arm_w = (m.lbs_weights * np.isin(m.lbs_indices, arm_joint_ids)).sum(1)
    trunk = v0[arm_w < 0.2]
    GX0, GY0, CELL = -0.45, 0.0, 0.01
    front_map = np.full((91, 200), -np.inf)
    back_map = np.full((91, 200), np.inf)
    gx = np.clip(((trunk[:, 0] - GX0) / CELL).astype(int), 0, 90)
    gy = np.clip(((trunk[:, 1] - GY0) / CELL).astype(int), 0, 199)
    np.maximum.at(front_map, (gx, gy), trunk[:, 2])
    np.minimum.at(back_map, (gx, gy), trunk[:, 2])
    # close one-cell holes between vertices
    pf, pb = np.pad(front_map, 1, constant_values=-np.inf), np.pad(back_map, 1, constant_values=np.inf)
    front_map = np.max([pf[1 + dx:92 + dx, 1 + dy:201 + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)], axis=0)
    back_map = np.min([pb[1 + dx:92 + dx, 1 + dy:201 + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)], axis=0)

    def frame_of(st):
        hips = (st[idx["l_upleg"], :3] + st[idx["r_upleg"], :3]) / 2
        up = st[idx["c_neck"], :3] - hips
        up /= np.linalg.norm(up)
        left = st[idx["l_upleg"], :3] - st[idx["r_upleg"], :3]
        left -= up * np.dot(left, up)
        left /= np.linalg.norm(left)
        return hips, np.stack([left, up, np.cross(left, up)])  # rows: x, y, z axes

    rest_hips, rest_axes = frame_of(s0)

    def skin_penetration(st, side: str) -> float:
        """How far (m) the forearm, hand and dumbbell are inside the trunk, measured to its front
        skin plus a margin (0 when clear). Points beside or behind the trunk don't count."""
        hips, axes = frame_of(st)
        sh, el, wr = arm_points(st, side)
        hand = wr + 0.08 * (wr - el) / (np.linalg.norm(wr - el) + 1e-9)
        pts = [(el + f * (wr - el), 0.04) for f in (0.33, 0.66)] + [(wr, 0.09), (hand, 0.085)]
        worst = 0.0
        for p, margin in pts:
            q = rest_hips + rest_axes.T @ (axes @ (p - hips))  # same place relative to the torso, at rest
            ix, iy = int((q[0] - GX0) / CELL), int((q[1] - GY0) / CELL)
            if 0 <= ix <= 90 and 0 <= iy <= 199 and back_map[ix, iy] < q[2] < front_map[ix, iy] + margin:
                worst = max(worst, front_map[ix, iy] + margin - q[2])
        return worst

    def rdl_goals(s_: float):
        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            hang = sh[2] + 0.12 * (1 - s_) + 0.03 * s_            # in front of the thighs, then vertical
            z_goal = max(hang, leg_front_z(st, side, wr[1]) + DUMBBELL_CLEARANCE)  # never into the legs
            z_goal = max(z_goal, wr[2] + skin_penetration(st, side))             # nor into the hips/belly
            return np.array([
                SIGN[side] * (wr[0] - sh[0]) + 0.08,               # hands in front of the thighs, inside the shoulders
                wr[2] - z_goal,
                flexion(sh, el, wr) - D(8),
            ])
        return ["uparm_ry", "uparm_rz", "elbow_bend"], residual

    u_rd, r_rd = rdl_goals(0.0)
    rdl_start = solve_arms(rdl_pose(0.0, 0.0), u_rd, r_rd, iterations=25)
    # Palms facing the thighs needs inward rotation of the upper arm as well as the forearm.
    best_rdl = (9.0, 0.0, 0.0)
    for ut in np.linspace(-1.5, 1.8, 12):
        for lt in np.linspace(-2.2, 1.0, 17):
            score = palm_forwardness(evaluate({**rdl_start, "l_uparm_twist": ut, "r_uparm_twist": ut,
                                               "l_lowarm_twist": lt, "r_lowarm_twist": lt})[1])
            if score < best_rdl[0]:
                best_rdl = (score, float(ut), float(lt))
    rdl_humerus, rdl_twist = best_rdl[1], best_rdl[2]
    rdl_fixed = {"l_uparm_twist": rdl_humerus, "r_uparm_twist": rdl_humerus,
                 "l_lowarm_twist": rdl_twist, "r_lowarm_twist": rdl_twist}
    rdl_start = solve_arms({**rdl_start, **rdl_fixed}, u_rd, r_rd, iterations=25)
    print(f"  deadlift: start solve error {solve_arms.last_error:.4f}, palm forwardness {best_rdl[0]:.2f} "
          f"(-1 = facing the thighs), humerus twist {rdl_humerus:.2f}, forearm twist {rdl_twist:.2f}")

    # ---------------------------------------------------------------- split squat
    balls = [idx["l_ball"], idx["r_ball"]]
    rest_balls = s0[balls, :3].copy()
    hips, knees = [idx["l_upleg"], idx["r_upleg"]], [idx["l_lowleg"], idx["r_lowleg"]]
    split_targets = [rest_ankles[0] + np.array([0.0, 0.0, SPLIT_FRONT]),
                     rest_ankles[1] + np.array([0.0, SPLIT_HEEL, -SPLIT_BACK])]
    # Balls of the feet: front foot flat; back foot on its ball, heel up, toes still pointing
    # forward (without the z target the solver may point the back foot backwards instead).
    foot_vec = rest_balls[1] - rest_ankles[1]
    foot_len = float(np.hypot(foot_vec[1], foot_vec[2]))
    back_drop = float(-foot_vec[1] + SPLIT_HEEL)
    ball_targets = [rest_balls[0] + np.array([0.0, 0.0, SPLIT_FRONT]),
                    np.array([rest_balls[1][0], rest_balls[1][1],
                              split_targets[1][2] + float(np.sqrt(max(foot_len ** 2 - back_drop ** 2, 1e-6)))])]
    split_unknowns = ["root_ty", "root_tz", "l_upleg_rz", "l_upleg_ry", "l_knee_bend", "l_foot_bend",
                      "r_upleg_rz", "r_upleg_ry", "r_knee_bend", "r_foot_bend"]

    def split_residual(st, s_):
        rows = []
        for k in (0, 1):
            rows += list(st[ankles[k], :3] - split_targets[k])   # ankles exactly on their marks
            rows += [st[balls[k], 1] - ball_targets[k][1],       # balls of both feet on the floor,
                     st[balls[k], 2] - ball_targets[k][2]]       # in front of the ankles
        rows.append(flexion(st[hips[0], :3], st[knees[0], :3], st[ankles[0], :3]) - (D(6) + D(84) * s_))  # front knee
        rows.append(st[idx["root"], 2] - ((split_targets[0][2] + split_targets[1][2]) / 2 + 0.03))  # pelvis between the feet
        return np.array(rows)

    def solve_split(pose: dict, s_: float, iterations: int = 10) -> dict:
        """Gauss-Newton on pelvis height/position and both legs (coupled through the pelvis)."""
        pose = dict(pose)
        pose.setdefault("root_ty", float(base[m.index("root_ty")]))
        pose.setdefault("root_tz", float(base[m.index("root_tz")]))
        for u in split_unknowns:
            pose.setdefault(u, 0.0)

        def err(p_):
            return split_residual(evaluate(p_)[1], s_)

        r = err(pose)
        for _ in range(iterations):
            if np.abs(r).max() < 2e-4:
                break
            J = np.zeros((len(r), len(split_unknowns)))
            for k, u in enumerate(split_unknowns):
                trial = dict(pose)
                trial[u] = pose[u] + 1e-3
                J[:, k] = (err(trial) - r) / 1e-3
            step = np.clip(np.linalg.lstsq(J, -r, rcond=None)[0], -0.3, 0.3)
            scale = 1.0
            for _attempt in range(6):
                trial = {**pose, **{u: pose[u] + scale * step[k] for k, u in enumerate(split_unknowns)}}
                r_trial = err(trial)
                if float(r_trial @ r_trial) < float(r @ r):
                    pose, r = trial, r_trial
                    break
                scale *= 0.5
            else:
                break
        solve_split.last_error = float(np.abs(r).max())  # type: ignore[attr-defined]
        return pose

    split_start = solve_split(split_pose(0.0, 0.0), 0.0, iterations=40)
    split_err = solve_split.last_error
    # Back foot: heel up, so bend the toes back up to the floor. The sign of *_ball_bend is
    # not documented; take whichever keeps the right toes closest to the floor.
    toe_verts = np.flatnonzero((m.lbs_weights * (m.lbs_indices == idx["r_ball"])).sum(1) > 0.5)
    rb = rest_balls[1] - rest_ankles[1]
    _, st_sp = evaluate(split_start)
    cb = st_sp[balls[1], :3] - st_sp[ankles[1], :3]
    foot_pitch = abs(math.atan2(cb[1], abs(cb[2])) - math.atan2(rb[1], abs(rb[2])))
    toe_options = {}
    for sign in (1.0, -1.0):
        lo, hi = m.pose_limits[m.index("r_ball_bend")]
        val = float(np.clip(sign * foot_pitch, lo, hi))
        v_try, _ = evaluate({**split_start, "r_ball_bend": val})
        toe_options[val] = abs(float(v_try[toe_verts, 1].min()))
    split_toe = min(toe_options, key=toe_options.get)
    print(f"  split squat: start solve error {split_err:.4f}, back-foot pitch {math.degrees(foot_pitch):.0f}°, "
          f"toe bend {split_toe:.2f} (toes {min(toe_options.values())*100:.1f} cm from the floor)")

    # ---------------------------------------------------------------- shared helpers (new exercises)
    def torso_frame(st):
        """(hips centre, up, left, forward) of the torso: left = character's left (+x at rest)."""
        hips = (st[idx["l_upleg"], :3] + st[idx["r_upleg"], :3]) / 2
        up = st[idx["c_neck"], :3] - hips
        up /= np.linalg.norm(up)
        left = st[idx["l_upleg"], :3] - st[idx["r_upleg"], :3]
        left -= up * np.dot(left, up)
        left /= np.linalg.norm(left)
        return hips, up, left, np.cross(left, up)

    def inwardness(state: np.ndarray) -> float:
        """1 when both palms face the body's midline (neutral grip)."""
        return float(np.mean([-SIGN[side] * palm_normal(state, side)[0] for side in ("l", "r")]))

    def best_twists(pose: dict, score) -> tuple[float, float, float]:
        """Grid over humerus and forearm twist; returns (score, humerus, forearm) with the highest score."""
        best = (-9.0, 0.0, 0.0)
        for ut in np.linspace(-1.5, 1.8, 12):
            for lt in np.linspace(-2.2, 1.0, 17):
                sc = score(evaluate({**pose, "l_uparm_twist": ut, "r_uparm_twist": ut,
                                     "l_lowarm_twist": lt, "r_lowarm_twist": lt})[1])
                if sc > best[0]:
                    best = (sc, float(ut), float(lt))
        return best

    def fixed_twists(ut: float, lt: float) -> dict:
        return {"l_uparm_twist": ut, "r_uparm_twist": ut, "l_lowarm_twist": lt, "r_lowarm_twist": lt}

    # ---------------------------------------------------------------- lateral raise
    # The arm direction sweeps from 12° to 82° away from vertical, in the scapular plane
    # (25° forward of straight out to the side), elbows softly bent, palms facing in → down.
    def raise_goals(p: float):
        angle = D(12) + (D(82) - D(12)) * p

        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            sg = SIGN[side]
            out = np.array([sg * math.cos(D(25)), 0.0, math.sin(D(25))])
            want = math.sin(angle) * out + math.cos(angle) * np.array([0.0, -1.0, 0.0])
            cur = (wr - sh) / (np.linalg.norm(wr - sh) + 1e-9)
            return np.array([*(cur - want), flexion(sh, el, wr) - D(15)])
        return ["uparm_ry", "uparm_rz", "elbow_bend"], residual

    u_lr, r_lr = raise_goals(0.0)
    raise_start = solve_arms(raise_pose(0.0, 0.0), u_lr, r_lr, iterations=40, limits=PRESS_LIMITS)
    lr_best = best_twists(raise_start, inwardness)
    raise_fixed = fixed_twists(lr_best[1], lr_best[2])
    raise_start = solve_arms({**raise_start, **raise_fixed}, u_lr, r_lr, iterations=25, limits=PRESS_LIMITS)
    walk = dict(raise_start)
    for p_ in np.linspace(0.1, 1.0, 10):
        u_, r_ = raise_goals(float(p_))
        walk = solve_arms({**walk, "l_clavicle_ry": 0.06 * p_, "r_clavicle_ry": 0.06 * p_}, u_, r_, iterations=25,
                          limits=PRESS_LIMITS)
    print(f"  lateral raise: top solve error {solve_arms.last_error:.4f}, palms facing in at the start {lr_best[0]:.2f}")

    # ---------------------------------------------------------------- kettlebell swing
    # Both hands on the handle at the midline; the arms point along a world-space angle from
    # vertical (arm_keys), long and relaxed. Palms face the body, like the deadlift grip.
    def thigh_overlap(st, p: np.ndarray, margin: float) -> float:
        """How far (m) a point is inside either thigh (+ margin); <= 0 when clear."""
        worst = -1.0
        for side in ("l", "r"):
            a, b = st[idx[f"{side}_upleg"], :3], st[idx[f"{side}_lowleg"], :3]
            u = float(np.clip(np.dot(p - a, b - a) / np.dot(b - a, b - a), 0, 1))
            worst = max(worst, LEG_SEGMENTS[side][0][2] + margin - float(np.linalg.norm(p - (a + u * (b - a)))))
        return worst

    def swing_goals(arm_angle: float):
        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            sg = SIGN[side]
            mid = (st[idx["l_uparm"], :3] + st[idx["r_uparm"], :3]) / 2
            # If the hands would be inside a thigh, swing the arms just far enough forward to
            # clear it (bisection, so the target moves smoothly); it always stays within reach.
            def at(a):
                return mid + np.array([sg * 0.035, -math.cos(a) * 0.95 * arm_len, math.sin(a) * 0.95 * arm_len])

            lo = arm_angle
            if thigh_overlap(st, at(lo), 0.025) > 0:
                hi = lo
                while hi < D(100) and thigh_overlap(st, at(hi), 0.025) > 0:
                    hi += D(10)
                for _ in range(14):
                    m_ = (lo + hi) / 2
                    lo, hi = (lo, m_) if thigh_overlap(st, at(m_), 0.025) <= 0 else (m_, hi)
                lo = hi
            target = at(lo)
            pen = skin_penetration(st, side)
            if pen > 0:  # forearms in front of the belly: push forward, then swing back onto the reach sphere
                reach = np.linalg.norm(target - mid)
                pushed = target.copy()
                pushed[2] = max(pushed[2], wr[2] + pen)
                target = mid + (pushed - mid) * (reach / np.linalg.norm(pushed - mid))
            return wr - target
        return ["uparm_ry", "uparm_rz", "elbow_bend"], residual

    u_sw, r_sw = swing_goals(D(90) * sample(TIMELINES["kettlebell_swing"]["arm_keys"], 0.0))
    SWING_LIMITS = {"uparm_ry": (-1.4, 2.9), "uparm_rz": (-1.2, 3.0)}  # hands meet at the midline
    arm_keys_ = [f"{sd}_{u}" for sd in ("l", "r") for u in u_sw]
    starts = {"swing seeds": {}, "deadlift arms": {k: rdl_start[k] for k in arm_keys_ if k in rdl_start}}
    for ry_ in (-0.9, -0.5):
        for rz_ in (0.2, 0.6):
            starts[f"ry {ry_} rz {rz_}"] = {f"{sd}_uparm_ry": ry_ for sd in ("l", "r")} | \
                {f"{sd}_uparm_rz": rz_ for sd in ("l", "r")} | {f"{sd}_elbow_bend": 0.2 for sd in ("l", "r")}
    best_sw = None
    for label_, extra in starts.items():
        cand = solve_arms({**swing_pose(0.0, 0.0), **rdl_fixed, **extra}, u_sw, r_sw, iterations=60, limits=SWING_LIMITS)
        print(f"    swing hold from {label_}: error {solve_arms.last_error:.4f}")
        if best_sw is None or solve_arms.last_error < best_sw[0]:
            best_sw = (solve_arms.last_error, cand)
    swing_err, swing_start = best_sw
    print(f"  swing: hold solve error {swing_err:.4f}")
    if os.environ.get("FORMA_DIAG"):
        _, st_ = evaluate(swing_start)
        for sd in ("l", "r"):
            sh_, el_, wr_ = arm_points(st_, sd)
            print(f"    {sd}: residual {np.round(r_sw(st_, sd), 3)}, shoulder {np.round(sh_, 3)}, wrist {np.round(wr_, 3)}, "
                  f"elbow flexion {math.degrees(flexion(sh_, el_, wr_)):.0f}°, arm length {arm_len:.3f} m")
            for u in u_sw:
                nm = f"{sd}_{u}"
                print(f"      {nm} = {swing_start.get(nm, 0.0):.3f}  limits {SWING_LIMITS.get(u, tuple(np.round(m.pose_limits[m.index(nm)], 3)))}")
        raise SystemExit("FORMA_DIAG: stopped after the swing set-up (nothing written).")

    # Squats start with relaxed arms, palms facing the thighs (the lateral raise's start grip),
    # rather than the curl's palms-forward grip, which reads as a mannequin's A-pose.
    TWISTS = {"squat": lr_best[2], "biceps_curl": twist, "shoulder_press": press_twist,
              "romanian_deadlift": rdl_twist, "split_squat": lr_best[2],
              "kettlebell_swing": rdl_twist, "lateral_raise": lr_best[2]}
    SEEDS = {"shoulder_press": press_start, "romanian_deadlift": rdl_start,
             "lateral_raise": raise_start, "kettlebell_swing": swing_start}
    FIXED = {"romanian_deadlift": rdl_fixed, "kettlebell_swing": rdl_fixed, "lateral_raise": raise_fixed,
             "squat": raise_fixed, "split_squat": raise_fixed}
    LIMITS = {"shoulder_press": PRESS_LIMITS, "lateral_raise": PRESS_LIMITS, "kettlebell_swing": SWING_LIMITS}
    STANCE_WIDEN = {"kettlebell_swing": 0.07}  # metres per foot: a little wider than hip-width

    def goals_for(clip: str, amount: float, t: float):
        if clip == "biceps_curl":
            return curl_goals(amount)
        if clip == "shoulder_press":
            return press_goals(amount)
        if clip == "romanian_deadlift":
            return rdl_goals(amount)
        if clip == "split_squat":
            return squat_goals(0.0, hang_offset)  # arms hang by the sides
        if clip == "lateral_raise":
            return raise_goals(amount)
        if clip == "kettlebell_swing":
            return swing_goals(D(90) * sample(TIMELINES[clip]["arm_keys"], t))
        return squat_goals(amount, hang_offset)

    hold_states: dict = {}  # first-frame skeletons, to place the kettlebells in the hands

    # Bake every clip.
    frames = int(DURATION * FPS) + 1
    times = np.arange(frames, dtype=np.float32) / FPS
    bind_t, bind_q, bind_s, _ = locals_from_state(s0, m.joint_parents)
    clips, report = {}, []
    for clip, tl in TIMELINES.items():
        lt_all, lq_all = [], []
        prev: dict = {}
        prev_legs: dict = {}
        worst_ik, worst_t = 0.0, 0.0
        stance = rest_ankles + np.array([[STANCE_WIDEN.get(clip, 0.0), 0, 0], [-STANCE_WIDEN.get(clip, 0.0), 0, 0]])
        floor_min, floor_max, drift_max, hand_thigh = 1e9, -1e9, 0.0, 1e9
        trunk_overlap = 0.0
        for t in times:
            amount = sample(tl["keys"], float(t))
            pose = POSES[clip](amount, TWISTS[clip])
            if clip == "biceps_curl":
                pose = with_humerus_twist(pose)
            pose = {**pose, **FIXED.get(clip, {})}
            unknowns, residual = goals_for(clip, amount, float(t))
            for u in unknowns:  # warm start from the previous frame (or the pre-solved start pose)
                for side in ("l", "r"):
                    key = f"{side}_{u}"
                    if key in prev:
                        pose[key] = prev[key]
                    elif key in SEEDS.get(clip, {}):
                        pose[key] = SEEDS[clip][key]
            pose = solve_arms(pose, unknowns, residual, limits=LIMITS.get(clip))
            if solve_arms.last_error > 0.005:  # stuck: more iterations, then a restart from the seed
                pose = solve_arms(pose, unknowns, residual, iterations=40, limits=LIMITS.get(clip))
                if solve_arms.last_error > 0.005 and clip in SEEDS:
                    first_err = solve_arms.last_error
                    retry = solve_arms({**pose, **{k: v for k, v in SEEDS[clip].items() if any(k.endswith(u) for u in unknowns)}},
                                       unknowns, residual, iterations=40, limits=LIMITS.get(clip))
                    if solve_arms.last_error < first_err:
                        pose = retry
                    else:
                        solve_arms.last_error = first_err
            if solve_arms.last_error > worst_ik:
                worst_ik, worst_t = solve_arms.last_error, float(t)
            prev = pose
            if clip == "split_squat":
                pose = {**pose, **(prev_legs or {k: split_start[k] for k in split_unknowns}), "r_ball_bend": split_toe}
                pose = solve_split(pose, amount)
                worst_ik = max(worst_ik, solve_split.last_error)
                prev_legs = {k: pose[k] for k in split_unknowns}
                v, s = evaluate(pose)
                drift_max = max(drift_max, float(max(np.abs(s[ankles[k], :3] - split_targets[k]).max() for k in (0, 1))))
            else:
                pose = plant_feet(pose, widen=STANCE_WIDEN.get(clip, 0.0))
                v, s = evaluate(pose)
                delta = (rest_ankles - s[ankles, :3]).mean(0)       # plant the feet (sagittal + height)
                v, s = evaluate(pose, delta)
                drift_max = max(drift_max, float(np.abs(s[ankles, :3] - stance).max()))
            if clip not in hold_states:
                hold_states[clip] = s.copy()
            floor_min, floor_max = min(floor_min, v[:, 1].min()), max(floor_max, v[:, 1].min())
            for side in ("l", "r"):
                trunk_overlap = max(trunk_overlap, skin_penetration(s, side))
                hand = s[idx[f"{side}_wrist"], :3]
                hip, knee = s[idx[f"{side}_upleg"], :3], s[idx[f"{side}_lowleg"], :3]
                u = np.clip(np.dot(hand - hip, knee - hip) / np.dot(knee - hip, knee - hip), 0, 1)
                hand_thigh = min(hand_thigh, float(np.linalg.norm(hand - (hip + u * (knee - hip)))))
            lt, lq, _, _ = locals_from_state(s, m.joint_parents)
            if lq_all:  # keep quaternion signs continuous for clean interpolation
                flip = np.sum(lq * lq_all[-1], axis=1) < 0
                lq[flip] *= -1
            lt_all.append(lt)
            lq_all.append(lq)
        clips[clip] = (np.stack(lt_all), np.stack(lq_all))
        report.append({
            "name": clip, "duration": DURATION, "fps": FPS, "markers": tl["markers"],
            "qa": {"ankleDriftM": round(drift_max, 5), "lowestVertexM": [round(float(floor_min), 4), round(float(floor_max), 4)],
                   "minWristToThighAxisM": round(hand_thigh, 3)},
        })
        print(f"✓ {clip}: drift {drift_max*1000:.1f} mm, floor {floor_min:.3f}..{floor_max:.3f} m, "
              f"wrist–thigh axis ≥ {hand_thigh*100:.1f} cm, hand/forearm clearance short by ≤ {trunk_overlap*100:.1f} cm, "
              f"worst solve error {worst_ik:.4f} at {worst_t:.2f} s")

    # Joints animated in ANY clip get a channel in EVERY clip (no stale poses when switching).
    rot_joints = sorted({j for lt, lq in clips.values() for j in np.flatnonzero(
        np.abs(np.abs(np.einsum("fjk,jk->fj", lq, bind_q)) - 1).max(0) > 1e-5)})
    pos_joints = sorted({j for lt, lq in clips.values() for j in np.flatnonzero(
        np.abs(lt - bind_t[None]).max((0, 2)) > 1e-5)})

    # ---------------------------------------------------------------- mesh + skin
    faces = m.faces.astype(np.uint32)
    normals = np.zeros_like(v0)
    tri = v0[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(normals, faces[:, k], fn)
    front = v0[:, 2] > v0[:, 2].max() - 0.02
    if normals[front, 2].mean() < 0:  # inward-facing winding: flip
        faces = faces[:, [0, 2, 1]]
        normals = -normals
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12

    photo_srgb = None
    if personal and (identity_path.parent / "appearance.npz").is_file():
        photo_srgb = np.load(identity_path.parent / "appearance.npz")["colors"].astype(np.float64) / 255.0
        if len(photo_srgb) != len(v0):
            photo_srgb = None
        else:
            print(f"  using photo colours from {identity_path.parent.name}/appearance.npz")

    # Hair: MHR bodies are bald. Push the scalp out and tint it (see hair.py).
    eye_mid = (s0[idx["l_eye"], :3] + s0[idx["r_eye"], :3]) / 2
    v_bald = v0.copy()  # symmetric rest mesh, for the left/right mirror map
    v0, srgb, hair_info = add_hair(v0.astype(np.float64), normals, faces.astype(np.int64),
                                   head_weight(m.lbs_indices, m.lbs_weights, list(m.joint_names)), eye_mid, photo_srgb)
    print(f"  hair: {hair_info}")
    hair_srgb_for_tail = np.asarray(hair_info.get("hairSRGB", GENERIC_HAIR_SRGB), np.float64)
    normals = np.zeros_like(v0)
    tri = v0[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(normals, faces[:, k], fn)
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    colors = srgb_to_linear(srgb).astype(np.float32)  # glTF vertex colours are linear

    order = np.argsort(m.lbs_weights, axis=1)[:, ::-1][:, :4]
    jidx = np.take_along_axis(m.lbs_indices, order, axis=1).astype(np.uint16)
    jw = np.take_along_axis(m.lbs_weights, order, axis=1)
    jw = (jw / jw.sum(1, keepdims=True)).astype(np.float32)

    g = GLB()
    n_j = len(m.joint_names)
    for j, jn in enumerate(m.joint_names):
        node = {"name": jn, "translation": bind_t[j].tolist(), "rotation": bind_q[j].tolist()}
        if abs(bind_s[j] - 1) > 1e-6:
            node["scale"] = [float(bind_s[j])] * 3
        kids = np.flatnonzero(m.joint_parents == j).tolist()
        if kids:
            node["children"] = kids
        g.doc["nodes"].append(node)
    roots = np.flatnonzero(m.joint_parents < 0).tolist()

    _, _, _, R0 = locals_from_state(s0, m.joint_parents)
    ibm = np.zeros((n_j, 16), np.float32)
    for j in range(n_j):
        M = np.eye(4)
        M[:3, :3] = R0[j] * s0[j, 7]
        M[:3, 3] = s0[j, :3]
        ibm[j] = np.linalg.inv(M).flatten(order="F")

    # Photo texture (personal avatars): split the mesh per photo, see texture.py. Textured
    # vertices get a white colour multiplier; the untextured rest continues the texture's colours.
    tex = None
    if personal and use_texture:
        names = list(m.joint_names)
        upper = [names.index(n) for n in texture.HEAD_NECK_JOINTS if n in names]
        head_neck_w = (m.lbs_weights * np.isin(m.lbs_indices, upper)).sum(1)
        tex = texture.build(faces.astype(np.int64), identity_path.parent, mirror_map(v_bald), head_neck_w)
    pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.8}
    out_v, out_n, out_faces = v0, normals, faces
    if tex is not None:
        vm = tex["vertex_map"]
        out_v, out_n, jidx, jw = v0[vm], normals[vm], jidx[vm], jw[vm]
        colors = srgb_to_linear(tex["fallback_srgb"]).astype(np.float32)
        out_faces = tex["faces"]
        pbr["baseColorTexture"] = {"index": g.texture(tex["jpeg"])}
        print(f"  photo texture: {tex['info']}")
    elif personal and use_texture:
        print("  no texture_views.npz: re-run reconstruct.py to get the sharper photo texture")
    garment_uv = None
    if tex is None and garment_fields is not None:  # crisp garment edges from a tiny texture
        garment_uv, garment_png = garment_texture(garment_fields, srgb_to_linear(np.array([0.93, 0.90, 0.87])))
        pbr["baseColorTexture"] = {"index": g.texture(garment_png, "image/png")}
    g.doc["materials"].append({"name": "Skin", "pbrMetallicRoughness": pbr})
    attrs = {
        "POSITION": g.accessor(out_v.astype(np.float32), "VEC3", ARRAY_BUFFER, minmax=True),
        "NORMAL": g.accessor(out_n.astype(np.float32), "VEC3", ARRAY_BUFFER),
        "JOINTS_0": g.accessor(jidx, "VEC4", ARRAY_BUFFER),
        "WEIGHTS_0": g.accessor(jw, "VEC4", ARRAY_BUFFER),
        "COLOR_0": g.accessor(colors, "VEC3", ARRAY_BUFFER),
    }
    if tex is not None:
        attrs["TEXCOORD_0"] = g.accessor(tex["uv"].astype(np.float32), "VEC2", ARRAY_BUFFER)
    elif garment_uv is not None:
        attrs["TEXCOORD_0"] = g.accessor(garment_uv, "VEC2", ARRAY_BUFFER)
    faces = out_faces
    ind_type = np.uint16 if len(out_v) < 65535 else np.uint32
    g.doc["meshes"].append({"name": "Avatar", "primitives": [{
        "attributes": attrs, "indices": g.accessor(faces.reshape(-1).astype(ind_type), "SCALAR", ELEMENT_ARRAY_BUFFER),
        "material": 0}]})
    g.doc["skins"].append({"joints": list(range(n_j)), "skeleton": roots[0],
                           "inverseBindMatrices": g.accessor(ibm, "MAT4")})
    g.doc["nodes"].append({"name": "Avatar", "mesh": 0, "skin": 0})
    scene_nodes = roots + [len(g.doc["nodes"]) - 1]

    # Props, rigidly attached to the wrist joints. The app shows each prop mesh ("Dumbbells",
    # "KettlebellSwing") only for the exercises that use it.
    g.doc["materials"].append({"name": "Prop", "pbrMetallicRoughness": {
        "baseColorFactor": [0.10, 0.11, 0.12, 1], "metallicFactor": 0.6, "roughnessFactor": 0.35},
        "doubleSided": True})
    db_pos, db_nrm, db_tri, db_joint = [], [], [], []
    for side in ("l", "r"):
        w, mid, ind, pin = fingers[side]
        palm_center = s0[w, :3] + 0.55 * (s0[mid, :3] - s0[w, :3])
        center = palm_center + palm_normal(s0, side) * 0.035   # in front of the palm, inside the grip
        p_, n_, t_ = dumbbell(center, s0[ind, :3] - s0[pin, :3])  # handle runs across the palm
        db_tri.append(t_ + sum(len(x) for x in db_pos))
        db_pos.append(p_)
        db_nrm.append(n_)
        db_joint.append(np.full(len(p_), idx[f"{side}_wrist"], np.uint16))
    db_pos_a = np.concatenate(db_pos).astype(np.float32)
    db_j = np.zeros((len(db_pos_a), 4), np.uint16)
    db_j[:, 0] = np.concatenate(db_joint)
    db_w = np.zeros((len(db_pos_a), 4), np.float32)
    db_w[:, 0] = 1.0
    g.doc["meshes"].append({"name": "Dumbbells", "primitives": [{
        "attributes": {
            "POSITION": g.accessor(db_pos_a, "VEC3", ARRAY_BUFFER, minmax=True),
            "NORMAL": g.accessor(np.concatenate(db_nrm).astype(np.float32), "VEC3", ARRAY_BUFFER),
            "JOINTS_0": g.accessor(db_j, "VEC4", ARRAY_BUFFER),
            "WEIGHTS_0": g.accessor(db_w, "VEC4", ARRAY_BUFFER),
        },
        "indices": g.accessor(np.concatenate(db_tri).reshape(-1).astype(np.uint16), "SCALAR", ELEMENT_ARRAY_BUFFER),
        "material": 1}]})
    g.doc["nodes"].append({"name": "Dumbbells", "mesh": 1, "skin": 0})
    scene_nodes.append(len(g.doc["nodes"]) - 1)

    # Kettlebells: placed between the hands in the exercise's first frame, then expressed in
    # the right wrist's bind frame so the skin carries them (rigidly, with the right hand).
    def wrist_matrix(state: np.ndarray) -> np.ndarray:
        M = np.eye(4)
        M[:3, :3] = quat_to_mat(state[idx["r_wrist"], 3:7]) * state[idx["r_wrist"], 7]  # same as the IBMs
        M[:3, 3] = state[idx["r_wrist"], :3]
        return M

    def palm_mid(state: np.ndarray) -> np.ndarray:
        pts = []
        for side in ("l", "r"):
            w, mid_, _ind, _pin = fingers[side]
            pts.append(state[w, :3] + 0.55 * (state[mid_, :3] - state[w, :3]))
        return (pts[0] + pts[1]) / 2

    def add_kettlebell(name: str, state: np.ndarray, below: np.ndarray) -> None:
        _hips, up, left, fwd = torso_frame(state)
        handle = palm_mid(state)
        p_, n_, t_ = kettlebell(handle, below / np.linalg.norm(below), left)
        to_bind = wrist_matrix(s0) @ np.linalg.inv(wrist_matrix(state))
        p_ = (to_bind[:3, :3] @ p_.T).T + to_bind[:3, 3]
        n_ = (to_bind[:3, :3] @ n_.T).T
        n_ /= np.linalg.norm(n_, axis=1, keepdims=True)
        j_ = np.zeros((len(p_), 4), np.uint16)
        j_[:, 0] = idx["r_wrist"]
        w_ = np.zeros((len(p_), 4), np.float32)
        w_[:, 0] = 1.0
        mesh_index = len(g.doc["meshes"])
        g.doc["meshes"].append({"name": name, "primitives": [{
            "attributes": {
                "POSITION": g.accessor(p_.astype(np.float32), "VEC3", ARRAY_BUFFER, minmax=True),
                "NORMAL": g.accessor(n_.astype(np.float32), "VEC3", ARRAY_BUFFER),
                "JOINTS_0": g.accessor(j_, "VEC4", ARRAY_BUFFER),
                "WEIGHTS_0": g.accessor(w_, "VEC4", ARRAY_BUFFER),
            },
            "indices": g.accessor(t_.reshape(-1).astype(np.uint16), "SCALAR", ELEMENT_ARRAY_BUFFER),
            "material": 1}]})
        g.doc["nodes"].append({"name": name, "mesh": mesh_index, "skin": 0})
        scene_nodes.append(len(g.doc["nodes"]) - 1)

    # Swing: the bell hangs below the hands along the arms.
    ss = hold_states["kettlebell_swing"]
    arm_dir = palm_mid(ss) - (ss[idx["l_uparm"], :3] + ss[idx["r_uparm"], :3]) / 2
    add_kettlebell("KettlebellSwing", ss, arm_dir)

    # Ponytail: a tapered tube tied at the back of the head, rigid with the head joint.
    if hairstyle == "ponytail":
        hw = head_weight(m.lbs_indices, m.lbs_weights, list(m.joint_names))
        band = (hw > 0.9) & (np.abs(v0[:, 1] - (eye_mid[1] + 0.035)) < 0.015) & (np.abs(v0[:, 0] - eye_mid[0]) < 0.03)
        if band.any():
            back = v0[band][np.argmin(v0[band, 2])]
            p_, n_, t_ = ponytail(back + np.array([0.0, 0.012, 0.006]))
            j_ = np.zeros((len(p_), 4), np.uint16)
            j_[:, 0] = idx["c_head"]
            w_ = np.zeros((len(p_), 4), np.float32)
            w_[:, 0] = 1.0
            g.doc["materials"].append({"name": "Hair", "pbrMetallicRoughness": {
                "baseColorFactor": [*srgb_to_linear(hair_srgb_for_tail).tolist(), 1], "metallicFactor": 0,
                "roughnessFactor": 0.6}, "doubleSided": True})
            g.doc["meshes"].append({"name": "Ponytail", "primitives": [{
                "attributes": {
                    "POSITION": g.accessor(p_.astype(np.float32), "VEC3", ARRAY_BUFFER, minmax=True),
                    "NORMAL": g.accessor(n_.astype(np.float32), "VEC3", ARRAY_BUFFER),
                    "JOINTS_0": g.accessor(j_, "VEC4", ARRAY_BUFFER),
                    "WEIGHTS_0": g.accessor(w_, "VEC4", ARRAY_BUFFER),
                },
                "indices": g.accessor(t_.reshape(-1).astype(np.uint16), "SCALAR", ELEMENT_ARRAY_BUFFER),
                "material": len(g.doc["materials"]) - 1}]})
            g.doc["nodes"].append({"name": "Ponytail", "mesh": len(g.doc["meshes"]) - 1, "skin": 0})
            scene_nodes.append(len(g.doc["nodes"]) - 1)
            print("  hair: ponytail")
    g.doc["scenes"][0]["nodes"] = scene_nodes

    for clip, (lt, lq) in clips.items():
        t_acc = g.accessor(times, "SCALAR", minmax=True)
        samplers, channels = [], []
        for j in rot_joints:
            samplers.append({"input": t_acc, "output": g.accessor(lq[:, j].astype(np.float32), "VEC4"), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": int(j), "path": "rotation"}})
        for j in pos_joints:
            samplers.append({"input": t_acc, "output": g.accessor(lt[:, j].astype(np.float32), "VEC3"), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": int(j), "path": "translation"}})
        g.doc["animations"].append({"name": clip, "samplers": samplers, "channels": channels})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(g.to_bytes())
    meta = {
        "generator": "research/avatar-pipeline/build_avatar.py",
        "source": "MHR (Apache-2.0)" + (" + SAM 3D Body identity (SAM License)" if personal else ""),
        "personal": personal, "units": "metres", "up": "+Y", "forward": "+Z",
        "bytes": out_path.stat().st_size, "vertices": int(len(v0)), "joints": n_j,
        "animatedJoints": {"rotation": len(rot_joints), "translation": len(pos_joints)},
        "heightM": round(float(v0[:, 1].max()), 3), "palmTwist": round(twist, 3), "hair": hair_info, "clothes": clothes_info,
        "texture": tex["info"] if tex is not None else None,
        "clips": report,
    }
    out_path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    shown = out_path.relative_to(REPO) if out_path.is_relative_to(REPO) else out_path
    print(f"✓ wrote {shown} ({meta['bytes']/1024:.0f} KiB, height {meta['heightM']} m, "
          f"{len(rot_joints)} rotating joints, palm twist {twist:.2f} rad)")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", type=Path, help="identity.json from reconstruct.py (omit for the generic body)")
    ap.add_argument("--name", default=None, help="output name (default: mhr-generic, or the identity folder name)")
    ap.add_argument("--no-texture", action="store_true", help="per-vertex photo colours only (no photo texture)")
    ap.add_argument("--average-body", action="store_true", help="generic body: MHR's average shape, not generic_body.json")
    ap.add_argument("--body", choices=["male", "female"], default="male",
                    help="generic body: male (mhr-generic) or female (mhr-generic-f, with a ponytail)")
    ap.add_argument("--hair", choices=["short", "ponytail"], default=None, help="hairstyle (default: by --body)")
    args = ap.parse_args()
    personal = args.identity is not None
    female = args.body == "female"
    name = args.name or (args.identity.parent.name if personal else ("mhr-generic-f" if female else "mhr-generic"))
    out_path = REPO / "public/models" / ("avatars" if personal else "") / f"{name}.glb"
    build(args.identity, out_path, use_texture=not args.no_texture,
          generic_body=None if args.average_body else (GENERIC_BODY_FEMALE if female else GENERIC_BODY),
          hairstyle=args.hair or ("ponytail" if female else "short"), female=female)


if __name__ == "__main__":
    main()
