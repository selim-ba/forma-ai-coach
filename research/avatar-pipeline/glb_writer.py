"""Minimal glTF 2.0 binary (GLB) writer for one skinned mesh + animation clips.

Kept dependency-free (numpy only). The skin layout (4 influences per vertex,
inverse bind matrices from the rest skeleton) follows the approach of MHR's
web-viewer/exporters.py (Apache-2.0).
"""
from __future__ import annotations

import json
import struct

import numpy as np

FLOAT, USHORT, UINT = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


class GLB:
    def __init__(self) -> None:
        self.bin = bytearray()
        self.doc: dict = {
            "asset": {"version": "2.0", "generator": "forma avatar-pipeline"},
            "buffers": [], "bufferViews": [], "accessors": [],
            "nodes": [], "meshes": [], "skins": [], "materials": [], "animations": [],
            "scenes": [{"nodes": []}], "scene": 0,
        }

    def _view(self, data: bytes, target: int | None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            view["target"] = target
        self.bin.extend(data)
        self.doc["bufferViews"].append(view)
        return len(self.doc["bufferViews"]) - 1

    def accessor(self, array: np.ndarray, kind: str, target: int | None = None, minmax: bool = False) -> int:
        dtype = {np.float32: FLOAT, np.uint16: USHORT, np.uint32: UINT}[array.dtype.type]
        array = np.ascontiguousarray(array)
        view = self._view(array.tobytes(), target)
        count = array.shape[0]
        acc = {"bufferView": view, "componentType": dtype, "count": int(count), "type": kind}
        if minmax:
            flat = array.reshape(count, -1)
            acc["min"] = [float(v) for v in flat.min(0)]
            acc["max"] = [float(v) for v in flat.max(0)]
        self.doc["accessors"].append(acc)
        return len(self.doc["accessors"]) - 1

    def texture(self, data: bytes, mime: str = "image/jpeg") -> int:
        """Embed an image; returns the texture index (linear filtering with mipmaps, clamped)."""
        view = self._view(data, None)
        self.doc.setdefault("images", []).append({"bufferView": view, "mimeType": mime})
        self.doc.setdefault("samplers", []).append({"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071})
        self.doc.setdefault("textures", []).append({"sampler": len(self.doc["samplers"]) - 1,
                                                    "source": len(self.doc["images"]) - 1})
        return len(self.doc["textures"]) - 1

    def to_bytes(self) -> bytes:
        while len(self.bin) % 4:
            self.bin.append(0)
        self.doc["buffers"] = [{"byteLength": len(self.bin)}]
        doc = {k: v for k, v in self.doc.items() if v != []}
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * ((4 - len(js) % 4) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        return (
            struct.pack("<III", 0x46546C67, 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin)
        )
