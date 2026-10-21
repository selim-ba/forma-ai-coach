"""Projection, overlay and per-vertex colour sampling for reconstruct.py.

Camera convention (matches SAM 3D Body's visualisation renderer): posed vertices
are in an OpenCV-like camera frame (x right, y down, z forward) after adding
pred_cam_t; u = f*X/Z + W/2, v = f*Y/Z + H/2. This is verified at runtime
against the model's own 2D keypoints.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw


def make_projector(cam_t: np.ndarray, focal: float, width: int, height: int):
    def project(points: np.ndarray):
        p = points + cam_t
        z = np.maximum(p[:, 2], 1e-6)
        return np.stack([focal * p[:, 0] / z + width / 2, focal * p[:, 1] / z + height / 2], axis=1), p[:, 2]
    project.cam_t = cam_t  # type: ignore[attr-defined]  # posed + cam_t = camera-frame position
    return project


def best_projector(person: dict, width: int, height: int):
    """Pick the camera-translation sign convention that best matches the 2D keypoints."""
    cam_t = np.asarray(person["pred_cam_t"], np.float64).reshape(3)
    focal = float(np.asarray(person["focal_length"]).reshape(-1)[0])
    k3 = np.asarray(person["pred_keypoints_3d"], np.float64).reshape(-1, 3)
    k2 = np.asarray(person["pred_keypoints_2d"], np.float64).reshape(-1, np.asarray(person["pred_keypoints_2d"]).shape[-1])[:, :2]
    best = None
    for sx in (1, -1):
        for sy in (1, -1):
            t = cam_t * np.array([sx, sy, 1.0])
            proj = make_projector(t, focal, width, height)
            uv, _ = proj(k3)
            ok = np.isfinite(k2).all(1) & (np.abs(k2).sum(1) > 0)
            err = float(np.median(np.linalg.norm(uv[ok] - k2[ok], axis=1))) if ok.any() else np.inf
            if best is None or err < best[0]:
                best = (err, proj, (sx, sy))
    return best  # (median px error, projector, signs)


def rasterize_ids(uv: np.ndarray, depth: np.ndarray, faces: np.ndarray, width: int, height: int) -> np.ndarray:
    """Painter's-algorithm face-id buffer (0 = background, i+1 = face i)."""
    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    order = np.argsort(-depth[faces].mean(1))  # far to near
    for i in order:
        fid = int(i) + 1
        draw.polygon([tuple(uv[k]) for k in faces[i]], fill=(fid & 255, (fid >> 8) & 255, (fid >> 16) & 255))
    a = np.asarray(img).astype(np.int64)
    return a[:, :, 0] | (a[:, :, 1] << 8) | (a[:, :, 2] << 16)


def overlay_image(rgb: np.ndarray, uv: np.ndarray, depth: np.ndarray, faces: np.ndarray, verts: np.ndarray) -> Image.Image:
    """Original | shaded mesh drawn over the photo, side by side."""
    h, w = rgb.shape[:2]
    base = Image.fromarray(rgb).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    tri = verts[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    shade = np.clip(np.abs(n[:, 2]), 0.25, 1.0)
    for i in np.argsort(-depth[faces].mean(1)):
        g = int(110 + 120 * shade[i])
        draw.polygon([tuple(uv[k]) for k in faces[i]], fill=(g, int(g * 0.75), int(g * 0.55), 150))
    blended = Image.alpha_composite(base, layer).convert("RGB")
    out = Image.new("RGB", (w * 2, h), (0, 0, 0))
    out.paste(Image.fromarray(rgb), (0, 0))
    out.paste(blended, (w, 0))
    return out


def vertex_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    vn = np.zeros_like(verts)
    fn = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]], verts[faces[:, 2]] - verts[faces[:, 0]])
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def background_color(rgb: np.ndarray, border: int = 12):
    """Median colour of the image border, or None if the border isn't a plain backdrop."""
    edge = np.concatenate([rgb[:border].reshape(-1, 3), rgb[-border:].reshape(-1, 3),
                           rgb[:, :border].reshape(-1, 3), rgb[:, -border:].reshape(-1, 3)]).astype(np.float64)
    med = np.median(edge, axis=0)
    spread = np.median(np.linalg.norm(edge - med, axis=1))
    return med if spread < 12 else None


def sample_visible(rgb: np.ndarray, uv: np.ndarray, ids: np.ndarray, faces: np.ndarray, verts_cam: np.ndarray):
    """Per-vertex photo colour and a confidence weight (how directly the camera sees it; 0 = unseen).

    verts_cam must be in the CAMERA frame (posed vertices + pred_cam_t; camera at the origin).
    """
    verts = verts_cam
    h, w = rgb.shape[:2]
    n_v = len(verts)
    visible_faces = np.unique(ids[ids > 0]) - 1
    vis = np.zeros(n_v, bool)
    vis[faces[visible_faces].reshape(-1)] = True
    # Direction from each vertex to the camera (camera at the origin of the posed frame).
    to_cam = -verts / (np.linalg.norm(verts, axis=1, keepdims=True) + 1e-12)
    facing = np.sum(vertex_normals(verts, faces) * to_cam, axis=1)
    if vis.any() and facing[vis].mean() < 0:  # mesh winding is inward: flip the convention
        facing = -facing
    vis &= facing > 0.35  # drop grazing vertices (silhouette edges pick up background)

    # Edge rejection: within a small window around the vertex's pixel there must be no
    # background and no surface clearly closer to the camera (e.g. an arm in front of the
    # torso). Misalignment errors concentrate exactly at those image edges.
    face_depth = verts[faces][:, :, 2].mean(1)
    r = max(3, int(round(0.004 * h)))
    xs = np.clip(np.round(uv[:, 0]).astype(int), 0, w - 1)
    ys = np.clip(np.round(uv[:, 1]).astype(int), 0, h - 1)
    clean = np.ones(n_v, bool)
    for dy in range(-r, r + 1, max(1, r // 2)):
        for dx in range(-r, r + 1, max(1, r // 2)):
            fid = ids[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)]
            near_depth = np.where(fid > 0, face_depth[np.maximum(fid - 1, 0)], -np.inf)
            clean &= (fid > 0) & (near_depth > verts[:, 2] - 0.03)
    vis &= clean
    x = np.clip(np.round(uv[:, 0]).astype(int), 1, w - 2)
    y = np.clip(np.round(uv[:, 1]).astype(int), 1, h - 2)
    patch = np.zeros((n_v, 3))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            patch += rgb[y + dy, x + dx]
    colors = patch / 9.0
    # Reject samples that are really backdrop (misaligned silhouette edges on a plain background).
    bg = background_color(rgb)
    if bg is not None:
        vis &= np.linalg.norm(colors - bg, axis=1) > 22
    weight = np.where(vis, facing, 0.0)
    return colors, weight


def texture_visibility(rgb: np.ndarray, uv: np.ndarray, ids: np.ndarray, faces: np.ndarray, verts_cam: np.ndarray):
    """For the photo texture: (per-face visible flag, per-vertex weight).

    Looser than sample_visible: a triangle only has to be the front-most surface somewhere
    in the photo (id buffer), and a vertex is weighted by how directly the camera sees it,
    unless its pixel is plain backdrop. No edge window, so areas next to the nose, the
    chin or the arms stay textured.
    """
    n_f = len(faces)
    face_visible = np.zeros(n_f, bool)
    face_visible[np.unique(ids[ids > 0]) - 1] = True
    to_cam = -verts_cam / (np.linalg.norm(verts_cam, axis=1, keepdims=True) + 1e-12)
    facing = np.sum(vertex_normals(verts_cam, faces) * to_cam, axis=1)
    seen = np.zeros(len(verts_cam), bool)
    seen[faces[face_visible].reshape(-1)] = True
    if seen.any() and facing[seen].mean() < 0:
        facing = -facing
    weight = np.clip(facing, 0.0, 1.0)
    bg = background_color(rgb)
    if bg is not None:
        h, w = rgb.shape[:2]
        x = np.clip(np.round(uv[:, 0]).astype(int), 0, w - 1)
        y = np.clip(np.round(uv[:, 1]).astype(int), 0, h - 1)
        weight[np.linalg.norm(rgb[y, x].astype(np.float64) - bg, axis=1) <= 22] = 0.0
    return face_visible, weight.astype(np.float32)


def diffuse(colors: np.ndarray, filled: np.ndarray, faces: np.ndarray, iterations: int = 400) -> np.ndarray:
    """Fill unseen vertices by spreading colours across mesh edges."""
    colors, filled = colors.copy(), filled.copy()
    n_v = len(colors)
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    for _ in range(iterations):
        todo = ~filled
        if not todo.any():
            break
        src = filled[e[:, 0]] & todo[e[:, 1]]
        acc = np.zeros((n_v, 3))
        cnt = np.zeros(n_v)
        np.add.at(acc, e[src, 1], colors[e[src, 0]])
        np.add.at(cnt, e[src, 1], 1)
        new = cnt > 0
        colors[new] = acc[new] / cnt[new, None]
        filled |= new
    if (~filled).any():
        colors[~filled] = colors[filled].mean(0) if filled.any() else 200
    return colors


def mirror_map(rest: np.ndarray, chunk: int = 512) -> np.ndarray:
    """Index of each vertex's left/right mirror twin on the (symmetric) rest mesh (x -> -x)."""
    pts = rest.astype(np.float32)
    mirrored = pts * np.array([-1.0, 1.0, 1.0], np.float32)
    sq = (pts ** 2).sum(1)
    out = np.empty(len(pts), np.int64)
    for i in range(0, len(pts), chunk):
        m = mirrored[i:i + chunk]
        d = (m ** 2).sum(1)[:, None] + sq[None, :] - 2.0 * (m @ pts.T)  # squared distances
        out[i:i + chunk] = d.argmin(1)
    return out


def fuse_colors(samples: list[tuple[np.ndarray, np.ndarray]], faces: np.ndarray, mirror: np.ndarray | None = None):
    """Blend per-view colours, strongly favouring the view that sees each vertex most head-on.

    Vertices no photo sees well borrow the colour of their mirror twin when that twin was
    seen clearly; anything still unseen is filled by diffusion across the mesh.
    """
    n_v = len(samples[0][0])
    acc = np.zeros((n_v, 3))
    wsum = np.zeros(n_v)
    best = np.zeros(n_v)
    for colors, weight in samples:
        w = weight ** 4
        acc += colors * w[:, None]
        wsum += w
        best = np.maximum(best, weight)
    seen = wsum > 1e-6
    fused = np.zeros((n_v, 3))
    fused[seen] = acc[seen] / wsum[seen, None]
    if mirror is not None:
        borrow = (best < 0.45) & (best[mirror] >= 0.6)
        fused[borrow] = fused[mirror[borrow]]
        best = np.where(borrow, best[mirror], best)
        seen = seen | borrow
    return np.clip(diffuse(fused, seen, faces), 0, 255).astype(np.uint8), seen


def sample_vertex_colors(rgb, uv, ids, faces, verts):
    """Single-view convenience wrapper."""
    return fuse_colors([sample_visible(rgb, uv, ids, faces, verts)], faces)


def facing_label(verts: np.ndarray, nose_index: int, head_index: int) -> str:
    """Is the person facing the camera, facing away, or side-on? (camera looks along +Z).

    head_index is the back of the head, so nose - back points where the face points.
    """
    d = verts[nose_index] - verts[head_index]
    d /= np.linalg.norm(d) + 1e-12
    if d[2] < -0.5:
        return "front"
    if d[2] > 0.5:
        return "back"
    return "side"
