"""Photo texture for a personal avatar: each triangle is textured from the photo that sees it best.

reconstruct.py stores, per photo, a crop (view_<i>.jpg) and where every MHR vertex lands
in that crop (texture_views.npz). Here the triangles are split into one group per photo
plus a fallback group for triangles no photo sees well (armpits, inner thighs, soles...).
With a mirror map, each photo also textures the opposite side of the body through the
vertices' left/right twins (a single side photo then covers both sides).
The crops are packed side by side into one atlas; the fallback group keeps the fused
per-vertex colours (COLOR_0) and samples a white patch of the atlas.

Vertices are duplicated where groups meet (one UV per vertex in glTF), so the result is
a list of original-vertex indices plus new faces, UVs and per-vertex colour multipliers.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ATLAS_MAX = 2048          # px; keeps the texture ~16 MB of GPU memory on a phone
MIN_FACE_WEIGHT = 0.30    # how directly a photo must see all 3 corners of a triangle to texture it
WHITE = 16                # px width of the white strip used by the fallback group


def face_adjacency(faces: np.ndarray) -> list[np.ndarray]:
    """Edge-sharing neighbours of each triangle."""
    e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    fid = np.tile(np.arange(len(faces)), 3)
    key = e[:, 0].astype(np.int64) * (faces.max() + 1) + e[:, 1]
    order = np.argsort(key, kind="stable")
    key, fid = key[order], fid[order]
    same = key[1:] == key[:-1]
    a, b = fid[:-1][same], fid[1:][same]
    nbrs: list[list[int]] = [[] for _ in range(len(faces))]
    for x, y in zip(a.tolist(), b.tolist()):
        nbrs[x].append(y)
        nbrs[y].append(x)
    return [np.asarray(n, np.int64) for n in nbrs]


def assign_views(ok: np.ndarray, score: np.ndarray, nbrs: list[np.ndarray], passes: int = 4) -> np.ndarray:
    """Photo per triangle (-1 = fallback), then remove speckle by neighbour majority.

    ok[f, g]: photo g may texture triangle f; among those, the highest score wins.
    """
    label = np.where(ok.any(1), np.where(ok, score, -np.inf).argmax(1), -1)
    n_views = ok.shape[1]
    for _ in range(passes):
        new = label.copy()
        for f, nb in enumerate(nbrs):
            if len(nb) == 0:
                continue
            votes = np.bincount(label[nb] + 1, minlength=n_views + 1)  # index 0 = fallback
            winner = int(votes.argmax()) - 1
            if winner != label[f] and votes.max() >= 2 and (winner == -1 or ok[f, winner]):
                new[f] = winner
        if np.array_equal(new, label):
            break
        label = new
    return label


def mirror_faces(faces: np.ndarray, mirror: np.ndarray) -> np.ndarray:
    """Index of each triangle's mirror twin (the triangle made of the corners' twins)."""
    key = lambda f: np.sort(f, axis=1) @ np.array([1, 1 << 20, 1 << 40], dtype=np.int64)  # noqa: E731
    lookup = {k: i for i, k in enumerate(key(faces.astype(np.int64)).tolist())}
    twins = key(mirror[faces].astype(np.int64)).tolist()
    return np.array([lookup.get(k, i) for i, k in enumerate(twins)], np.int64)


def match_gain(ref: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Per-channel gain that brings `other` photo colours to the reference photo's level."""
    g = np.median(ref, 0) / np.maximum(np.median(other, 0), 1e-3)
    return np.clip(g, 0.8, 1.25)


MIRROR_PENALTY = 0.85     # a real view beats a mirrored one unless it sees the triangle much worse
PRIORITY = {"front": 2.2, "back": 1.4, "side": 1.0}
HEAD_NECK_JOINTS = ("c_head", "c_head_null", "c_jaw", "c_jaw_null", "l_eye", "r_eye", "l_eye_null", "r_eye_null",
                    "c_neck", "c_neck_twist0_proc", "c_neck_twist1_proc")
HEAD_FRONT_MIN = 0.25     # cos of ~75°: how far round the head the front photo is kept


def build(faces: np.ndarray, private_dir: Path, mirror: np.ndarray | None = None,
          head_w: np.ndarray | None = None):
    """Returns None when no texture data exists, else a dict with:
    vertex_map (new -> original vertex), faces (new indices), uv (0..1, glTF: origin top-left),
    textured (bool per new vertex), fallback_srgb (colour multiplier per new vertex: 1 where
    textured, the texture's colours continued across the mesh elsewhere), jpeg (bytes), info.

    head_w (per-vertex head + neck skinning weight, see HEAD_NECK_JOINTS) enables the head rule: on the head the front
    photo wins wherever it sees a triangle at all reasonably (HEAD_FRONT_MIN). Photos taken
    separately never line up perfectly, and a seam across a cheek is far more visible than
    a slightly stretched front photo; this moves it back towards the ear.
    """
    npz = private_dir / "texture_views.npz"
    if not npz.is_file():
        return None
    data = np.load(npz)
    views = [str(v) for v in data["views"]]
    n = len(views)
    crops = [Image.open(private_dir / f"view_{i}.jpg").convert("RGB") for i in range(1, n + 1)]
    uvs = [data[f"uv_{i}"].astype(np.float64) for i in range(1, n + 1)]
    weights = np.stack([data[f"weight_{i}"] for i in range(1, n + 1)], axis=1)  # (V, n)

    colors = [data[f"colors_{i}"].astype(np.float64) for i in range(1, n + 1)]

    # Visibility. Body: the strict per-vertex weights from colour sampling (they reject
    # corners next to an occluding arm, so arm pixels never paint the torso behind it).
    # Head: nothing occludes it in a standing photo, but its tiny triangles fail the strict
    # test around the nose and eyes, so it uses the looser id-buffer visibility instead.
    head_faces = head_w[faces].mean(1) > 0.5 if head_w is not None else np.zeros(len(faces), bool)
    face_w = weights[faces].min(axis=1)  # a triangle is only as visible as its worst corner
    face_w_m = weights[mirror][faces].min(axis=1) if mirror is not None else None
    if "face_visible_1" in data and head_faces.any():  # newer reconstruct.py
        tex_w = np.stack([data[f"tex_weight_{i}"] for i in range(1, n + 1)], axis=1)
        face_vis = np.stack([data[f"face_visible_{i}"] for i in range(1, n + 1)], axis=1)
        for i in range(n):  # sub-pixel triangles: visible when all corners touch a visible one
            seen = np.zeros(int(faces.max()) + 1, bool)
            seen[faces[face_vis[:, i]].reshape(-1)] = True
            face_vis[:, i] |= seen[faces].all(1)
        loose = tex_w[faces].min(axis=1) * face_vis
        face_w[head_faces] = loose[head_faces]
        if mirror is not None:
            loose_m = tex_w[mirror][faces].min(axis=1) * face_vis[mirror_faces(faces, mirror)]
            face_w_m[head_faces] = loose_m[head_faces]
    priority = np.array([PRIORITY.get(v, 1.0) for v in views])
    if mirror is not None:  # pseudo-views n..2n-1: photo i seen through the mirror twins
        face_w = np.concatenate([face_w, face_w_m], axis=1)
        priority = np.concatenate([priority, priority * MIRROR_PENALTY])
    ok = face_w >= MIN_FACE_WEIGHT
    score = face_w * priority[None, :]
    if head_faces.any():
        if "front" in views:
            # The front photo keeps every head triangle it sees reasonably head-on, so the seam
            # with the side photo falls near the ear instead of across the cheek.
            front = views.index("front")
            ok[:, front] |= head_faces & (face_w[:, front] >= 0.12)
            score[head_faces & (face_w[:, front] >= HEAD_FRONT_MIN), front] = 1e3
    label = assign_views(ok, score, face_adjacency(faces))

    # Exposure matching: photos taken separately differ in brightness and white balance.
    # Scale each photo to the reference (front if present) using vertices both see clearly.
    ref = views.index("front") if "front" in views else 0
    gains = []
    for i in range(n):
        both = (weights[:, ref] > 0.3) & (weights[:, i] > 0.3)
        gains.append(match_gain(colors[ref][both], colors[i][both]) if i != ref and both.sum() >= 150
                     else np.ones(3))
    crops = [c if np.allclose(g, 1) else Image.fromarray(np.clip(np.asarray(c, np.float64) * g, 0, 255).astype(np.uint8))
             for c, g in zip(crops, gains)]

    # Atlas: crops side by side (same height), a white strip at the right, scaled to ATLAS_MAX.
    target_h = max(c.height for c in crops)
    scaled = []
    for c, uv in zip(crops, uvs):
        k = target_h / c.height
        scaled.append((c.resize((round(c.width * k), target_h)) if k != 1 else c, uv * k))
    total_w = sum(c.width for c, _ in scaled) + WHITE
    k = min(1.0, ATLAS_MAX / max(total_w, target_h))
    atlas_w, atlas_h = round(total_w * k), round(target_h * k)
    atlas = Image.new("RGB", (atlas_w, atlas_h), (255, 255, 255))
    x = 0
    atlas_uv = []
    for c, uv in scaled:
        w_px = round(c.width * k)
        atlas.paste(c.resize((w_px, atlas_h)), (x, 0))
        atlas_uv.append((uv * k + np.array([x, 0.0])) / np.array([atlas_w, atlas_h]))
        x += w_px
    white_uv = np.array([(atlas_w - WHITE * k / 2) / atlas_w, 0.5])
    buf = io.BytesIO()
    atlas.save(buf, format="JPEG", quality=88, optimize=True)

    # Split vertices per group.
    vertex_map, new_uv, textured, new_faces = [], [], [], np.empty_like(faces)
    count = 0
    n_groups = face_w.shape[1]
    for g in range(-1, n_groups):
        sel = np.flatnonzero(label == g)
        if len(sel) == 0:
            continue
        used = np.unique(faces[sel])
        remap = np.full(faces.max() + 1, -1, np.int64)
        remap[used] = np.arange(len(used)) + count
        new_faces[sel] = remap[faces[sel]]
        vertex_map.append(used)
        if g < 0:
            new_uv.append(np.repeat(white_uv[None], len(used), 0))
        elif g < n:
            new_uv.append(atlas_uv[g][used])
        else:
            new_uv.append(atlas_uv[g - n][mirror[used]])
        textured.append(np.full(len(used), g >= 0))
        count += len(used)
    vertex_map_a, new_uv_a, textured_a = np.concatenate(vertex_map), np.concatenate(new_uv), np.concatenate(textured)

    # Fallback colours: continue the texture's own (blurred) colours into the unseen areas, so
    # there is no brightness jump where a textured region meets an untextured one.
    blurred = np.asarray(atlas.filter(ImageFilter.GaussianBlur(4)), np.float64) / 255.0
    px = np.clip((new_uv_a * [atlas_w, atlas_h]).astype(int), 0, [atlas_w - 1, atlas_h - 1])
    n_v = int(faces.max()) + 1
    acc, cnt = np.zeros((n_v, 3)), np.zeros(n_v)
    tv = np.flatnonzero(textured_a)
    np.add.at(acc, vertex_map_a[tv], blurred[px[tv, 1], px[tv, 0]])
    np.add.at(cnt, vertex_map_a[tv], 1)
    filled = cnt > 0
    base = np.zeros((n_v, 3))
    base[filled] = acc[filled] / cnt[filled, None]
    base = spread(base, filled, faces)
    fallback_srgb = np.where(textured_a[:, None], 1.0, base[vertex_map_a])

    info = {
        "views": views, "atlasPx": [atlas_w, atlas_h], "jpegKiB": round(len(buf.getvalue()) / 1024),
        "facesPerView": {views[g % n] + (" (mirrored)" if g >= n else ""): int((label == g).sum())
                         for g in range(n_groups)},
        "fallbackFaces": int((label < 0).sum()), "vertices": count,
        "headFaces": int(head_faces.sum()),
        "gains": [np.round(g, 2).tolist() for g in gains],
    }
    return {"vertex_map": vertex_map_a, "faces": new_faces, "uv": new_uv_a, "textured": textured_a,
            "fallback_srgb": fallback_srgb, "jpeg": buf.getvalue(), "info": info}


def spread(colors: np.ndarray, filled: np.ndarray, faces: np.ndarray, iterations: int = 300) -> np.ndarray:
    """Fill unfilled vertices by repeatedly averaging filled neighbours across mesh edges."""
    colors, filled = colors.copy(), filled.copy()
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    for _ in range(iterations):
        todo = ~filled
        if not todo.any():
            break
        src = filled[e[:, 0]] & todo[e[:, 1]]
        acc = np.zeros_like(colors)
        cnt = np.zeros(len(colors))
        np.add.at(acc, e[src, 1], colors[e[src, 0]])
        np.add.at(cnt, e[src, 1], 1)
        new = cnt > 0
        colors[new] = acc[new] / cnt[new, None]
        filled |= new
    return colors
