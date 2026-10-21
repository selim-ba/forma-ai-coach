"""Steps 1 and 3: bake an MHR body into a rigged, animated GLB for the Forma viewer.

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
}

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


POSES = {"squat": squat_pose, "biceps_curl": curl_pose}


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
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", type=Path, help="identity.json from reconstruct.py (omit for the generic body)")
    ap.add_argument("--name", default=None, help="output name (default: mhr-generic, or the identity folder name)")
    ap.add_argument("--no-texture", action="store_true", help="per-vertex photo colours only (no photo texture)")
    args = ap.parse_args()

    m = MHRModel()
    P = len(m.pose_names)
    base = np.zeros(P, np.float32)
    identity = np.zeros(m.identity_count, np.float32)
    personal = args.identity is not None
    if personal:
        data = json.loads(args.identity.read_text())
        identity = np.asarray(data["identity"], np.float32)
        for name, value in data.get("scales", {}).items():
            base[m.index(name)] = value
    name = args.name or (args.identity.parent.name if personal else "mhr-generic")
    out_path = REPO / "public/models" / ("avatars" if personal else "") / f"{name}.glb"

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

    def solve_arms(pose: dict, unknowns: list[str], residual, iterations: int = 8) -> dict:
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
                        lo, hi = m.pose_limits[m.index(name)]
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
    sh_l, _, wr_l = arm_points(st_start, "l")
    hang_offset = float(wr_l[0] - sh_l[0])  # how far the hanging hand sits outside the shoulder

    # Bake both clips.
    frames = int(DURATION * FPS) + 1
    times = np.arange(frames, dtype=np.float32) / FPS
    bind_t, bind_q, bind_s, _ = locals_from_state(s0, m.joint_parents)
    clips, report = {}, []
    for clip, tl in TIMELINES.items():
        lt_all, lq_all = [], []
        prev: dict = {}
        worst_ik = 0.0
        floor_min, floor_max, drift_max, hand_thigh = 1e9, -1e9, 0.0, 1e9
        for t in times:
            amount = sample(tl["keys"], float(t))
            pose = POSES[clip](amount, twist)
            if clip == "biceps_curl":
                pose = with_humerus_twist(pose)
            unknowns, residual = curl_goals(amount) if clip == "biceps_curl" else squat_goals(amount, hang_offset)
            for u in unknowns:  # warm start from the previous frame
                for side in ("l", "r"):
                    if f"{side}_{u}" in prev:
                        pose[f"{side}_{u}"] = prev[f"{side}_{u}"]
            pose = solve_arms(pose, unknowns, residual)
            worst_ik = max(worst_ik, solve_arms.last_error)
            prev = pose
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
              f"wrist–thigh axis ≥ {hand_thigh*100:.1f} cm, worst arm-solve error {worst_ik:.4f}")

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
    if personal and (args.identity.parent / "appearance.npz").is_file():
        photo_srgb = np.load(args.identity.parent / "appearance.npz")["colors"].astype(np.float64) / 255.0
        if len(photo_srgb) != len(v0):
            photo_srgb = None
        else:
            print(f"  using photo colours from {args.identity.parent.name}/appearance.npz")

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
    if personal and not args.no_texture:
        tex = texture.build(faces.astype(np.int64), args.identity.parent, mirror_map(v_bald))
    pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.8}
    out_v, out_n, out_faces = v0, normals, faces
    if tex is not None:
        vm = tex["vertex_map"]
        out_v, out_n, jidx, jw = v0[vm], normals[vm], jidx[vm], jw[vm]
        colors = srgb_to_linear(tex["fallback_srgb"]).astype(np.float32)
        out_faces = tex["faces"]
        pbr["baseColorTexture"] = {"index": g.texture(tex["jpeg"])}
        print(f"  photo texture: {tex['info']}")
    elif personal and not args.no_texture:
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
    print(f"✓ wrote {out_path.relative_to(REPO)} ({meta['bytes']/1024:.0f} KiB, height {meta['heightM']} m, "
          f"{len(rot_joints)} rotating joints, palm twist {twist:.2f} rad)")


if __name__ == "__main__":
    main()
