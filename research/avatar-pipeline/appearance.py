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


def sample_vertex_colors(rgb: np.ndarray, uv: np.ndarray, ids: np.ndarray, faces: np.ndarray,
                         verts: np.ndarray, camera_dir_z: float = 1.0):
    """Colour each vertex from the photo where it is visible; diffuse into hidden areas."""
    h, w = rgb.shape[:2]
    n_v = len(verts)
    visible_faces = np.unique(ids[ids > 0]) - 1
    vis = np.zeros(n_v, bool)
    vis[faces[visible_faces].reshape(-1)] = True
    # Vertex normals: drop grazing vertices (silhouette edges pick up background).
    vn = np.zeros_like(verts)
    fn = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]], verts[faces[:, 2]] - verts[faces[:, 0]])
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    facing = -vn[:, 2] * camera_dir_z  # camera looks along +Z; outward normals point to -Z when facing it
    if vis.any() and facing[vis].mean() < 0:  # mesh winding is inward: flip the convention
        facing = -facing
    vis &= facing > 0.35
    x = np.clip(np.round(uv[:, 0]).astype(int), 1, w - 2)
    y = np.clip(np.round(uv[:, 1]).astype(int), 1, h - 2)
    patch = np.zeros((n_v, 3))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            patch += rgb[y + dy, x + dx]
    colors = np.zeros((n_v, 3))
    colors[vis] = patch[vis] / 9.0
    filled = vis.copy()

    # Diffuse colours across mesh edges into unseen vertices (back, under arms, top of head).
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    for _ in range(400):
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
    colors[~filled] = colors[filled].mean(0) if filled.any() else 200
    return np.clip(colors, 0, 255).astype(np.uint8), vis
