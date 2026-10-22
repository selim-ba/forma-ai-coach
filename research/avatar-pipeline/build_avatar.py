"""Steps 1 and 3: bake an MHR body into a rigged, animated GLB for the Forma viewer.

Clips: squat, biceps_curl, shoulder_press, romanian_deadlift, split_squat.

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
from pathlib import Path

import numpy as np

from glb_writer import ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER, GLB
from hair import add_hair, head_weight, srgb_to_linear
import texture
from appearance import mirror_map
from mhr_common import HERE, MHRModel

REPO = HERE.parent.parent
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


POSES = {"squat": squat_pose, "biceps_curl": curl_pose, "shoulder_press": press_pose,
         "romanian_deadlift": rdl_pose, "split_squat": split_pose}


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
          log=print) -> dict:
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
    if personal:
        data = json.loads(identity_path.read_text())
        identity = np.asarray(data["identity"], np.float32)
        for name, value in data.get("scales", {}).items():
            base[m.index(name)] = value

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

    def plant_feet(pose: dict, iterations: int = 4) -> dict:
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
                err = s[ankles[k], 0] - rest_ankles[k, 0]
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
    def rdl_goals(s_: float):
        def residual(st, side):
            sh, el, wr = arm_points(st, side)
            return np.array([
                SIGN[side] * (wr[0] - sh[0]) + 0.08,           # hands in front of the thighs, inside the shoulders
                (wr[2] - sh[2]) - (0.12 * (1 - s_) + 0.03 * s_),  # in front of the thighs, then vertical
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

    TWISTS = {"squat": twist, "biceps_curl": twist, "shoulder_press": press_twist,
              "romanian_deadlift": rdl_twist, "split_squat": 0.0}
    SEEDS = {"shoulder_press": press_start, "romanian_deadlift": rdl_start}

    def goals_for(clip: str, amount: float):
        if clip == "biceps_curl":
            return curl_goals(amount)
        if clip == "shoulder_press":
            return press_goals(amount)
        if clip == "romanian_deadlift":
            return rdl_goals(amount)
        if clip == "split_squat":
            return squat_goals(0.0, hang_offset)  # arms hang by the sides
        return squat_goals(amount, hang_offset)

    # Bake every clip.
    frames = int(DURATION * FPS) + 1
    times = np.arange(frames, dtype=np.float32) / FPS
    bind_t, bind_q, bind_s, _ = locals_from_state(s0, m.joint_parents)
    clips, report = {}, []
    for clip, tl in TIMELINES.items():
        lt_all, lq_all = [], []
        prev: dict = {}
        prev_legs: dict = {}
        worst_ik = 0.0
        floor_min, floor_max, drift_max, hand_thigh = 1e9, -1e9, 0.0, 1e9
        for t in times:
            amount = sample(tl["keys"], float(t))
            pose = POSES[clip](amount, TWISTS[clip])
            if clip == "biceps_curl":
                pose = with_humerus_twist(pose)
            if clip == "romanian_deadlift":
                pose = {**pose, **rdl_fixed}
            unknowns, residual = goals_for(clip, amount)
            for u in unknowns:  # warm start from the previous frame (or the pre-solved start pose)
                for side in ("l", "r"):
                    key = f"{side}_{u}"
                    if key in prev:
                        pose[key] = prev[key]
                    elif key in SEEDS.get(clip, {}):
                        pose[key] = SEEDS[clip][key]
            pose = solve_arms(pose, unknowns, residual, limits=PRESS_LIMITS if clip == "shoulder_press" else None)
            worst_ik = max(worst_ik, solve_arms.last_error)
            prev = pose
            if clip == "split_squat":
                pose = {**pose, **(prev_legs or {k: split_start[k] for k in split_unknowns}), "r_ball_bend": split_toe}
                pose = solve_split(pose, amount)
                worst_ik = max(worst_ik, solve_split.last_error)
                prev_legs = {k: pose[k] for k in split_unknowns}
                v, s = evaluate(pose)
                drift_max = max(drift_max, float(max(np.abs(s[ankles[k], :3] - split_targets[k]).max() for k in (0, 1))))
            else:
                pose = plant_feet(pose)
                v, s = evaluate(pose)
                delta = (rest_ankles - s[ankles, :3]).mean(0)       # plant the feet (sagittal + height)
                v, s = evaluate(pose, delta)
                drift_max = max(drift_max, float(np.abs(s[ankles, :3] - rest_ankles).max()))
            floor_min, floor_max = min(floor_min, v[:, 1].min()), max(floor_max, v[:, 1].min())
            for side in ("l", "r"):
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
              f"wrist–thigh axis ≥ {hand_thigh*100:.1f} cm, worst solve error {worst_ik:.4f}")

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
    faces = out_faces
    ind_type = np.uint16 if len(out_v) < 65535 else np.uint32
    g.doc["meshes"].append({"name": "Avatar", "primitives": [{
        "attributes": attrs, "indices": g.accessor(faces.reshape(-1).astype(ind_type), "SCALAR", ELEMENT_ARRAY_BUFFER),
        "material": 0}]})
    g.doc["skins"].append({"joints": list(range(n_j)), "skeleton": roots[0],
                           "inverseBindMatrices": g.accessor(ibm, "MAT4")})
    g.doc["nodes"].append({"name": "Avatar", "mesh": 0, "skin": 0})
    scene_nodes = roots + [len(g.doc["nodes"]) - 1]

    # Dumbbells, rigidly attached to each wrist joint. The app shows the mesh named
    # "Dumbbells" only for exercises with the dumbbell prop (the biceps curl).
    g.doc["materials"].append({"name": "Prop", "pbrMetallicRoughness": {
        "baseColorFactor": [0.10, 0.11, 0.12, 1], "metallicFactor": 0.6, "roughnessFactor": 0.35}})
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
        "heightM": round(float(v0[:, 1].max()), 3), "palmTwist": round(twist, 3), "hair": hair_info,
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
    args = ap.parse_args()
    personal = args.identity is not None
    name = args.name or (args.identity.parent.name if personal else "mhr-generic")
    out_path = REPO / "public/models" / ("avatars" if personal else "") / f"{name}.glb"
    build(args.identity, out_path, use_texture=not args.no_texture)


if __name__ == "__main__":
    main()
