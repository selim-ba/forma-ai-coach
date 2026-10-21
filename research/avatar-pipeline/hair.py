"""Short-hair cap for MHR avatars (MHR bodies are bald).

The scalp is pushed outwards along its normals (fuller on the crown, short at the sides)
and tinted with a hair colour. Where the hair stops is decided by:

- the generic body: a template hairline (forehead, slightly receding temples, sideburns
  in front of the ears, nape at the back), defined in angles around the head centre;
- a photo avatar: the photo colours themselves, i.e. vertices whose colour is closer to
  the crown colour than to the face colour, inside a generous version of the template.
  When hair and skin colours are indistinguishable (bald, or very fair hair) nothing is
  added, rather than guessing a hairline.

Long hair cannot be represented by moving scalp vertices; that would need a separate mesh.
"""
from __future__ import annotations

import numpy as np

HEAD_JOINTS = ("c_head", "c_head_null", "c_jaw", "c_jaw_null", "l_eye", "r_eye", "l_eye_null", "r_eye_null")
GENERIC_HAIR_SRGB = np.array([0.22, 0.17, 0.14])


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def head_weight(lbs_indices: np.ndarray, lbs_weights: np.ndarray, joint_names: list[str]) -> np.ndarray:
    """How much each vertex follows the head (0..1)."""
    ids = [joint_names.index(n) for n in HEAD_JOINTS if n in joint_names]
    return (lbs_weights * np.isin(lbs_indices, ids)).sum(1)


def _edges(faces: np.ndarray) -> np.ndarray:
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    return np.concatenate([e, e[:, ::-1]])


def smooth(x: np.ndarray, faces: np.ndarray, iterations: int) -> np.ndarray:
    """Average a per-vertex scalar with its 1-ring neighbours, `iterations` times."""
    e = _edges(faces)
    deg = np.bincount(e[:, 1], minlength=len(x)).astype(np.float64)
    x = x.astype(np.float64)
    for _ in range(iterations):
        acc = np.bincount(e[:, 1], weights=x[e[:, 0]], minlength=len(x))
        x = 0.5 * x + 0.5 * acc / np.maximum(deg, 1)
    return x


def angles(v: np.ndarray, eye_mid: np.ndarray):
    """Elevation (deg, 0 = eye height) and azimuth (rad, 0 = straight ahead) around the head centre."""
    c = eye_mid + np.array([0.0, 0.005, -0.075])  # cranium centre: just above the eyes, 7.5 cm behind
    d = v - c
    r = np.linalg.norm(d, axis=1) + 1e-9
    return np.degrees(np.arcsin(np.clip(d[:, 1] / r, -1, 1))), np.arctan2(d[:, 0], d[:, 2])


def hairline(phi: np.ndarray, front=34.0, side=12.0, back=-38.0) -> np.ndarray:
    """Lowest elevation (deg) the hair reaches, as a function of azimuth."""
    b = (front - back) / 2
    a = ((front + back) / 2 + side) / 2
    c = ((front + back) / 2 - side) / 2
    e = a + b * np.cos(phi) + c * np.cos(2 * phi)
    ap = np.degrees(np.abs(phi))
    e = e + 5.0 * np.exp(-((ap - 38) / 12) ** 2)    # slightly receding temples
    e = e - 26.0 * np.exp(-((ap - 68) / 6) ** 2)    # sideburns, just in front of the ears
    return e


def add_hair(v: np.ndarray, normals: np.ndarray, faces: np.ndarray, head_w: np.ndarray, eye_mid: np.ndarray,
             srgb: np.ndarray | None):
    """Returns (displaced vertices, sRGB colours 0..1, info dict).

    srgb: per-vertex photo colours (0..1) for a photo avatar, or None for the generic body
    (which then gets a clay skin colour plus GENERIC_HAIR_SRGB).
    """
    elev, phi = angles(v, eye_mid)
    region = smoothstep(0.3, 0.7, head_w)               # never the neck or shoulders
    line = hairline(phi)
    info: dict = {}
    if srgb is None:
        cover = smoothstep(line - 2.5, line + 3.5, elev) * region
        hair = GENERIC_HAIR_SRGB
        out = np.tile(np.array([0.93, 0.90, 0.87]), (len(v), 1))  # = linear (0.86, 0.80, 0.74) clay
        tint = 1.0
        info["source"] = "template"
    else:
        # Generous search zone: down to ~7° below the template at the forehead, ~12° at the back.
        slack = 7.0 + 5.0 * (1 - np.cos(phi)) / 2
        zone = smoothstep(line - slack - 3, line - slack + 3, elev) * region
        crown = (elev > 55) & (head_w > 0.7)
        face = (np.abs(phi) < np.radians(25)) & (elev > -15) & (elev < 5) & (head_w > 0.7)
        hair = np.median(srgb[crown], 0)
        skin = np.median(srgb[face], 0)
        contrast = float(np.linalg.norm(hair - skin))
        info.update(source="photo", hairSRGB=np.round(hair, 3).tolist(), skinSRGB=np.round(skin, 3).tolist(),
                    contrast=round(contrast, 3))
        if contrast < 0.12:  # bald, or hair too close to skin tone to find a hairline: leave as is
            info["skipped"] = "hair and skin colours too similar"
            return v, srgb, info
        d_hair = np.linalg.norm(srgb - hair, axis=1)
        d_skin = np.linalg.norm(srgb - skin, axis=1)
        h = smooth(d_skin / (d_hair + d_skin + 1e-6), faces, 3)
        cover = smoothstep(0.42, 0.62, h) * zone
        out = srgb.copy()
        tint = 0.5  # keep some of the photo's texture, but clean up stray skin-coloured pixels
    volume = smooth(cover, faces, 6) ** 1.5 * region
    thick = 0.005 + 0.015 * smoothstep(20, 70, elev) + 0.004 * np.clip(-np.cos(phi), 0, 1)
    v_out = v + normals * (volume * thick)[:, None]
    out = out * (1 - cover[:, None] * tint) + hair * (cover[:, None] * tint)
    info.update(vertices=int((cover > 0.5).sum()), maxThicknessMm=round(float((volume * thick).max() * 1000), 1))
    return v_out, np.clip(out, 0, 1), info


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
