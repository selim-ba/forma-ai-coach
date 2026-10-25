"""Create an avatar on the deployed Modal service from the Mac (test it, or make the demo fallback).

    python services/avatar/create_avatar.py front.jpg side.jpg back.jpg            # expires after 24 h
    python services/avatar/create_avatar.py front.jpg side.jpg back.jpg --keep     # kept: the demo fallback
    (add --body female for the women's cut and a ponytail)

Reads AVATAR_SERVICE_URL and AVATAR_TOKEN from the environment or from .env.local at the
repo root. Photos are resized to 2048 px JPEG first, exactly like the app does. Prints the
avatar link for the live site when done. Standard library + Pillow only.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = "https://forma-ai-coach-nine.vercel.app"


def env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env_file = REPO / ".env.local"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"')
    sys.exit(f"{name} is not set (environment or .env.local)")


def jpeg(path: Path, max_side: int = 2048) -> bytes:
    from PIL import Image, ImageOps
    try:
        import pillow_heif  # noqa: F401
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def multipart(fields: dict[str, str], files: dict[str, bytes]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, data in files.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.jpg"\r\n'
                  f"Content-Type: image/jpeg\r\n\r\n".encode())
        out.write(data)
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("front", type=Path)
    ap.add_argument("side", type=Path)
    ap.add_argument("back", type=Path)
    ap.add_argument("--keep", action="store_true", help="never auto-delete (the demo fallback avatar)")
    ap.add_argument("--body", choices=["male", "female"], default="male", help="hair and clothing cut")
    args = ap.parse_args()

    base = env("AVATAR_SERVICE_URL").rstrip("/")
    body, ctype = multipart({"keep": "true" if args.keep else "false", "body": args.body},
                            {"front": jpeg(args.front), "side": jpeg(args.side), "back": jpeg(args.back)})
    req = urllib.request.Request(f"{base}/avatars", data=body, method="POST",
                                 headers={"Content-Type": ctype, "X-Avatar-Token": env("AVATAR_TOKEN")})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            avatar_id = json.load(r)["id"]
    except urllib.error.HTTPError as e:
        sys.exit(f"upload failed: HTTP {e.code} {e.read().decode()[:300]}")
    print(f"uploaded, id {avatar_id}")

    started, last = time.time(), ""
    while True:
        with urllib.request.urlopen(f"{base}/avatars/{avatar_id}", timeout=30) as r:
            st = json.load(r)
        line = f"{st['state']}: {st.get('message', '')}"
        if line != last:
            print(f"  {time.time() - started:5.0f}s  {line}")
            last = line
        if st["state"] in ("done", "error"):
            break
        time.sleep(3)
    for w in st.get("warnings") or []:
        print(f"  ⚠ {w}")
    if st["state"] == "done":
        print(f"✓ ready in {time.time() - started:.0f}s{' (kept)' if args.keep else ' (deleted after 24 h)'}")
        print(f"  {SITE}/?avatar={avatar_id}")
        print(f"  local dev: http://localhost:3000/?avatar={avatar_id}")


if __name__ == "__main__":
    main()
