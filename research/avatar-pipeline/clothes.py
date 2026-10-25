"""Garment shapes for the avatar mesh: a T-shirt and shorts that drape like fabric.

MHR bodies are skin-tight. Painting clothes onto them (generic colours, or the photo
texture) gives "leggings and a painted-on shirt". This module reshapes the rest mesh
where the clothes are, so the skinned animation carries the garments for free:

- Shirt body: each horizontal slice is widened to its convex hull (fills the waist curve,
  belly button and spine groove), and below the chest the fabric falls almost straight
  down instead of following the waist in. A little ease is added, more at the hem.
- Sleeves and shorts legs: each slice along the limb is widened to its convex hull plus
  ease that grows towards the hem, so they stand off the arm or thigh like fabric.
- The displacement is smoothed within each garment but never across a hem, so every hem
  keeps a crisp fabric edge.

Returns the dressed vertices and a per-vertex garment label (0 skin, 1 shirt, 2 shorts).
"""
from __future__ import annotations

import numpy as np

NONE, SHIRT, SHORTS = 0, 1, 2
SHIRT_SRGB = np.array([0.22, 0.24, 0.29])   # charcoal-navy T-shirt
SHORTS_SRGB = np.array([0.47, 0.48, 0.51])  # mid-grey shorts

# Garment extents. sleeve_t / shorts_t run along the whole limb: 0..1 is the upper arm or thigh,
# 1..2 the forearm or shin (so 1.9 is a long sleeve or long trousers). hem_ease: extra width at
# the shirt hem (a flare reads well on the generic body; photo avatars keep it small because the
# real hem may be tucked in or elsewhere).
GENERIC = {"sleeve_t": 0.42, "shirt_hem_below_root": 0.06, "shorts_t": 0.48, "hem_ease": 0.012}
ARM = (("uparm", "uparm", "lowarm"), ("forearm", "lowarm", "wrist"))
LEG = (("thigh", "upleg", "lowleg"), ("shin", "lowleg", "talocrural"))


def _segment(p: np.ndarray, a: np.ndarray, b: np.ndarray):
    """Distance from points p to segment ab, and the parameter t (0 at a, 1 at b)."""
    ab = b - a
    t = np.clip((p - a) @ ab / float(ab @ ab), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1), t


def classify(v: np.ndarray, J: dict) -> tuple[np.ndarray, dict]:
    """Body part of each vertex in the rest pose (A-pose), by nearest bone relative to its
    typical radius. Returns (part names array, {part: t along its bone})."""
    segs = {"torso": (J["root"] - np.array([0, 0.08, 0]), J["c_neck"], 0.15),
            "head": (J["c_neck"], J["c_head"] + np.array([0, 0.12, 0]), 0.10)}
    for s in ("l", "r"):
        segs[f"{s}_uparm"] = (J[f"{s}_uparm"], J[f"{s}_lowarm"], 0.05)
        segs[f"{s}_forearm"] = (J[f"{s}_lowarm"], J[f"{s}_wrist"], 0.04)
        segs[f"{s}_hand"] = (J[f"{s}_wrist"], J[f"{s}_wrist"] + 1.6 * (J[f"{s}_wrist"] - J[f"{s}_lowarm"]) / 3, 0.035)
        segs[f"{s}_thigh"] = (J[f"{s}_upleg"], J[f"{s}_lowleg"], 0.075)
        segs[f"{s}_shin"] = (J[f"{s}_lowleg"], J[f"{s}_talocrural"], 0.05)
        segs[f"{s}_foot"] = (J[f"{s}_talocrural"], J[f"{s}_ball"], 0.04)
    names = list(segs)
    score = np.empty((len(v), len(names)))
    ts = {}
    for k, n in enumerate(names):
        a, b, r = segs[n]
        d, t = _segment(v, a, b)
        score[:, k] = d / r
        ts[n] = t
    part = np.array(names, dtype=object)[np.argmin(score, axis=1)]
    return part, ts


def _hull(points: np.ndarray) -> np.ndarray:
    """2D convex hull (counter-clockwise), monotone chain."""
    pts = np.unique(np.round(points, 6), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def _hull_radius(hull: np.ndarray, center: np.ndarray, angles: np.ndarray) -> np.ndarray:
    """Distance from center to the hull boundary along each angle (0 when outside / degenerate)."""
    out = np.zeros(len(angles))
    if len(hull) < 3:
        return out
    d = np.stack([np.cos(angles), np.sin(angles)], 1)
    for i in range(len(hull)):
        a, b = hull[i] - center, hull[(i + 1) % len(hull)] - center
        e = b - a
        den = d[:, 0] * e[1] - d[:, 1] * e[0]
        ok = np.abs(den) > 1e-12
        s = np.where(ok, (a[0] * e[1] - a[1] * e[0]) / np.where(ok, den, 1), -1)   # along the ray
        u = np.where(ok, (a[0] * d[:, 1] - a[1] * d[:, 0]) / np.where(ok, den, 1), -1)  # along the edge
        hit = ok & (s > 0) & (u >= -1e-9) & (u <= 1 + 1e-9)
        out = np.where(hit, np.maximum(out, s), out)
    return out


def _limb_frame(axis: np.ndarray):
    axis = axis / np.linalg.norm(axis)
    ref = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, ref)
    u /= np.linalg.norm(u)
    return axis, u, np.cross(axis, u)


def _drape_limb(v, sel, a, b, ease0, ease1, t_hem, out, t_offset: float = 0.0):
    """Widen a limb garment (sleeve or trouser leg) slice by slice along a→b; t_offset is this
    segment's start along the whole limb (0 upper segment, 1 lower)."""
    axis, u, w = _limb_frame(b - a)
    length = float(np.linalg.norm(b - a))
    rel = v[sel] - a
    along = rel @ axis
    t = along / length
    p2 = np.stack([rel @ u, rel @ w], 1)
    bins = np.floor(t / 0.04).astype(int)
    for bidx in np.unique(bins):
        k = bins == bidx
        if k.sum() < 6:
            continue
        c = p2[k].mean(0)
        ang = np.arctan2(p2[k, 1] - c[1], p2[k, 0] - c[0])
        r = np.linalg.norm(p2[k] - c, axis=1)
        rh = _hull_radius(_hull(p2[k]), c, ang)
        frac = np.clip((t_offset + t[k]) / max(t_hem, 1e-6), 0, 1)
        ease = ease0 + (ease1 - ease0) * frac ** 2
        r_new = np.maximum(r, rh) + ease
        q2 = c + (p2[k] - c) * (r_new / np.maximum(r, 1e-6))[:, None]
        idx = np.flatnonzero(sel)[k]
        out[idx] = a + np.outer(along[k], axis) + np.outer(q2[:, 0], u) + np.outer(q2[:, 1], w)


def _neighbours(faces: np.ndarray, n: int) -> list[np.ndarray]:
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.concatenate([edges, edges[:, ::-1]])
    order = np.argsort(edges[:, 0], kind="stable")
    edges = edges[order]
    starts = np.searchsorted(edges[:, 0], np.arange(n + 1))
    return [np.unique(edges[starts[i]:starts[i + 1], 1]) for i in range(n)]


def dress(v: np.ndarray, faces: np.ndarray, joints: dict, extents: dict | None = None):
    """Return (dressed vertices, garment label per vertex, info). v: rest vertices in metres."""
    ext = {**GENERIC, **(extents or {})}
    part, ts = classify(v, joints)
    root_y = float(joints["root"][1])
    hem_y = root_y - ext["shirt_hem_below_root"]
    is_torso = part == "torso"
    y = v[:, 1]
    # Signed distance (m) to each garment's edge, positive inside: the hems are where these
    # cross zero. Labels come from the signs; the GLB draws crisp edges from the values.
    d_shirt = np.full(len(v), -0.05)
    d_shorts = np.full(len(v), -0.05)
    neck = joints["c_neck"]
    d_axis = np.hypot(v[:, 0] - neck[0], v[:, 2] - neck[2])
    band = (y > neck[1] + 0.015) & (y < neck[1] + 0.045) & (d_axis < 0.09)
    r_neck = float(np.median(d_axis[band])) if band.any() else 0.06
    front = np.clip((v[:, 2] - neck[2]) / max(r_neck, 1e-3), 0, 1)
    rc = r_neck + 0.016                                     # crew neck: a little off the neck
    collar = np.minimum(np.maximum((neck[1] - 0.03 * front) - y, d_axis - rc), (neck[1] + 0.06) - y)
    trunk = np.isin(part, ["torso", "head"])
    d_shirt[trunk] = np.minimum(y - hem_y, collar)[trunk]
    d_shorts[is_torso] = (hem_y + 0.12 - y)[is_torso]
    for s in ("l", "r"):
        for k, (cls, a, b) in enumerate(ARM):
            sel = part == f"{s}_{cls}"
            L = float(np.linalg.norm(joints[f"{s}_{b}"] - joints[f"{s}_{a}"]))
            d_shirt[sel] = ((ext["sleeve_t"] - k - ts[f"{s}_{cls}"]) * L)[sel]
        for k, (cls, a, b) in enumerate(LEG):
            sel = part == f"{s}_{cls}"
            L = float(np.linalg.norm(joints[f"{s}_{b}"] - joints[f"{s}_{a}"]))
            d_shorts[sel] = ((ext["shorts_t"] - k - ts[f"{s}_{cls}"]) * L)[sel]
        th = part == f"{s}_thigh"
        d_shirt[th] = (y - hem_y)[th]
    label = np.zeros(len(v), np.int8)
    label[d_shorts > 0] = SHORTS
    label[d_shirt > 0] = SHIRT
    collar_y = y  # (kept for the slice range below)

    out = v.copy()
    # --- shirt body: convex slices, falling straight from the chest ----------------------
    body = (label == SHIRT) & (np.isin(part, ["torso", "head", "l_thigh", "r_thigh"]))
    cz = float(np.median(v[body & (np.abs(v[:, 1] - (root_y + 0.15)) < 0.03), 2]))
    chest_y = float(joints["c_spine3"][1]) - 0.03
    n_ang = 72
    ang_c = (np.arange(n_ang) + 0.5) / n_ang * 2 * np.pi - np.pi
    ys = np.arange(float(v[body, 1].max()) + 0.01, hem_y - 0.01, -0.01)
    env = None
    slice_r = {}
    for y0 in ys:
        k = body & (v[:, 1] <= y0) & (v[:, 1] > y0 - 0.01)
        if k.sum() < 8:
            continue
        p2 = v[k][:, [0, 2]]
        center = np.array([0.0, cz])
        hr = _hull_radius(_hull(p2), center, ang_c)
        if y0 < chest_y and env is not None:
            hr = np.maximum(hr, env - 0.0025)   # below the chest, fabric tapers at most 2.5 mm per cm
        env = hr
        slice_r[round(y0, 3)] = (k, hr)
    for y0, (k, hr) in slice_r.items():
        p2 = v[k][:, [0, 2]] - np.array([0.0, cz])
        ang = np.arctan2(p2[:, 1], p2[:, 0])
        r = np.linalg.norm(p2, axis=1)
        bin_ = np.clip(((ang + np.pi) / (2 * np.pi) * n_ang).astype(int), 0, n_ang - 1)
        hem_frac = np.clip(1 - (v[k, 1] - hem_y) / 0.07, 0, 1)
        ease = 0.007 + ext["hem_ease"] * hem_frac ** 2
        r_new = np.maximum(r, hr[bin_]) + ease
        scale = r_new / np.maximum(r, 1e-6)
        idx = np.flatnonzero(k)
        out[idx, 0] = p2[:, 0] * scale
        out[idx, 2] = cz + p2[:, 1] * scale

    # --- sleeves and shorts legs -----------------------------------------------------------
    for s in ("l", "r"):
        for k, (cls, a, b) in enumerate(ARM):
            sel = (label == SHIRT) & (part == f"{s}_{cls}")
            _drape_limb(v, sel, joints[f"{s}_{a}"], joints[f"{s}_{b}"], 0.007, 0.016, ext["sleeve_t"], out, k)
        for k, (cls, a, b) in enumerate(LEG):
            sel = (label == SHORTS) & (part == f"{s}_{cls}")
            _drape_limb(v, sel, joints[f"{s}_{a}"], joints[f"{s}_{b}"], 0.010, 0.026, ext["shorts_t"], out, k)
    seat = (label == SHORTS) & is_torso   # pelvis under the shorts: a little ease along the normal
    if seat.any():
        c = np.array([0.0, float(np.median(v[seat, 1])), cz])
        d = v[seat] - c
        d[:, 1] *= 0.3
        out[seat] += 0.010 * d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9)

    # --- smooth the displacement inside each garment, never across a hem ------------------
    disp = out - v
    nbrs = _neighbours(faces, len(v))
    garment = np.flatnonzero(label > 0)
    for _ in range(6):
        new = disp.copy()
        for i in garment:
            nb = nbrs[i]
            nb = nb[label[nb] == label[i]]
            if len(nb):
                new[i] = 0.5 * disp[i] + 0.5 * disp[nb].mean(0)
        disp = new
    # Thin the fabric out towards edges that meet skin (collar, sleeve and leg hems): a full
    # step there makes the triangles bridging it read as teeth. Where the shirt hem lies over
    # the shorts the shirt keeps its thickness so it stays on top.
    own = np.where(label == SHIRT, d_shirt, np.where(label == SHORTS, d_shorts, 0.0))
    over_shorts = (label == SHIRT) & (d_shorts > 0)
    x = np.clip(own / 0.015, 0, 1)
    taper = np.where(over_shorts, 1.0, 0.2 + 0.8 * x * x * (3 - 2 * x))
    disp *= np.where(label > 0, taper, 0.0)[:, None]
    out = v + disp
    info = {"shirtVertices": int((label == SHIRT).sum()), "shortsVertices": int((label == SHORTS).sum()),
            "maxOffsetMm": round(float(np.linalg.norm(disp, axis=1).max()) * 1000, 1),
            "meanOffsetMm": round(float(np.linalg.norm(disp[garment], axis=1).mean()) * 1000, 1) if len(garment) else 0.0}
    info["neckRadiusMm"] = round(r_neck * 1000, 1)
    return out, label, info, np.stack([d_shirt, d_shorts], 1)



EDGE_SPAN = 0.03  # metres of signed distance mapped across the garment texture


def garment_texture(fields: np.ndarray, skin_linear: np.ndarray, size: int = 64):
    """Crisp garment edges with a tiny texture instead of per-vertex colours.

    Each vertex gets UV = (shirt distance, shorts distance) mapped to 0..1 (0.5 = the edge);
    the texture is white on skin and the garment colour (divided by the skin vertex colour,
    since glTF multiplies the two) inside a garment. Interpolated distances cross 0.5 inside
    triangles, so every hem is a straight, sharp line. Returns (uv float32 [V,2], PNG bytes).
    """
    import io

    from PIL import Image

    uv = (0.5 + np.clip(fields / EDGE_SPAN, -0.5, 0.5)).astype(np.float32)

    def to_srgb(c):
        c = np.clip(c, 0, 1)
        return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)

    def to_linear(c):
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    shirt = to_srgb(to_linear(SHIRT_SRGB) / skin_linear)
    shorts = to_srgb(to_linear(SHORTS_SRGB) / skin_linear)
    centers = (np.arange(size) + 0.5) / size
    u, v = np.meshgrid(centers, centers)   # rows: v (shorts), columns: u (shirt)
    img = np.ones((size, size, 3))
    img[v > 0.5] = shorts
    img[u > 0.5] = shirt
    buf = io.BytesIO()
    Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(buf, format="PNG")
    return uv, buf.getvalue()


def extents_from_photo(v: np.ndarray, joints: dict, srgb: np.ndarray, seen: np.ndarray):
    """Where the sleeves and the shorts or trousers end, from the photo colours.

    Skin colour comes from the face. Walking down each arm and leg, the garment ends where
    the limb turns (and stays) skin-coloured. Both sides are averaged. Returns (extents, info);
    extents is empty when the photos don't show enough to decide.
    """
    part, ts = classify(v, joints)
    head = joints["c_head"]
    face = (part == "head") & seen & (v[:, 2] > head[2] + 0.04) & \
        (v[:, 1] > joints["c_neck"][1] + 0.06) & (v[:, 1] < head[1] + 0.03)
    if face.sum() < 30:
        return {}, {"skipped": "face not seen"}
    skin = np.median(srgb[face], 0)

    def skin_like(c):
        lum = c.sum(1) + 1e-6
        chroma = c / lum[:, None] - skin / skin.sum()
        ratio = lum / skin.sum()
        return (np.linalg.norm(chroma, axis=1) < 0.04) & (ratio > 0.5) & (ratio < 1.7)

    def garment_end(chain, side):
        s_all, c_all = [], []
        for k, (cls, _a, _b) in enumerate(chain):
            sel = (part == f"{side}_{cls}") & seen
            s_all.append(k + ts[f"{side}_{cls}"][sel])
            c_all.append(srgb[sel])
        s_v, c_v = np.concatenate(s_all), np.concatenate(c_all)
        if len(s_v) < 40:
            return None
        like = skin_like(c_v)
        edges = np.arange(0.0, 2.0001, 0.1)
        frac = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            k = (s_v >= lo) & (s_v < hi)
            frac.append(float(like[k].mean()) if k.sum() >= 5 else np.nan)
        frac = np.array(frac)
        known = np.flatnonzero(~np.isnan(frac))
        if len(known) < 8:
            return None
        # The garment ends where the first sustained run of skin starts (3 known bins), walking
        # away from the body; socks or a watch further down don't extend it.
        is_skin = frac >= 0.55
        for i, b in enumerate(known):
            run = known[i:i + 3]
            if len(run) == 3 and is_skin[run].all():
                return 0.05 if edges[b] < 0.15 else float(edges[b])
        return 1.9                                       # no bare skin: long sleeve / trousers

    ext, info = {}, {"skinSRGB": np.round(skin / 255.0 if skin.max() > 1 else skin, 3).tolist()}
    for key, chain in (("sleeve_t", ARM), ("shorts_t", LEG)):
        ends = [e for e in (garment_end(chain, side) for side in ("l", "r")) if e is not None]
        if ends:
            ext[key] = round(float(np.mean(ends)), 2)
    info.update(ext)
    return ext, info
