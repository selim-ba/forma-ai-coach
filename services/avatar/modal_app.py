"""Forma avatar service on Modal: three photos in, an animated personal avatar (GLB) out.

Runs the same pipeline as the Mac (research/avatar-pipeline): SAM 3D Body (on a GPU if
FORMA_AVATAR_GPU is set, else on CPU) for the body shape and photo texture, then the MHR bake
for the five exercise clips.

    modal deploy services/avatar/modal_app.py      # from the repo root, see services/avatar/README.md

HTTP API (base URL printed by `modal deploy`):
    POST   /avatars                 multipart front, side, back (+ keep=true); header X-Avatar-Token
    GET    /avatars/{id}            {"state": queued|working|done|error, "stage", "message", "warnings", ...}
    GET    /avatars/{id}/model.glb  the avatar (once done)
    DELETE /avatars/{id}            removes the avatar and anything left of the photos
    POST   /warm                    start a worker ahead of time (header X-Avatar-Token)

Privacy: the photos are deleted as soon as the avatar is built (or the build fails). Avatars
are deleted after AVATAR_TTL_HOURS unless created with keep=true (the demo fallback). The
avatar id is a random capability: whoever has it can view or delete that avatar.
"""
# No `from __future__ import annotations`: FastAPI must see real types (UploadFile is imported
# inside api(), so string annotations could not be resolved). Python 3.11 handles `X | None`.

import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

import modal

APP_NAME = "forma-avatar"
DATA = Path("/data")                      # Modal volume: checkpoints/, avatars/<id>/, torch hub cache
AVATARS = DATA / "avatars"
CKPT = DATA / "checkpoints" / "sam-3d-body-dinov3"
PIPELINE = Path("/pipeline")              # research/avatar-pipeline, added to the image
SAM_DIR = Path("/opt/sam-3d-body")
AVATAR_TTL_HOURS = 24
ID_RE = re.compile(r"^r-[0-9a-f]{24}$")
VIEWS = ("front", "side", "back")
MAX_PHOTO_BYTES = 8 * 1024 * 1024

# This file is imported twice: on the Mac (modal deploy) and inside every Modal container,
# where it lives at /root/modal_app.py. Only the Mac has the repo, so don't assume parents[2].
_PARENTS = Path(__file__).resolve().parents
LOCAL_PIPELINE = (_PARENTS[2] if len(_PARENTS) > 2 else Path("/")) / "research" / "avatar-pipeline"

app = modal.App(APP_NAME)
volume = modal.Volume.from_name("forma-avatar-data", create_if_missing=True)
secret = modal.Secret.from_name("forma-avatar")  # AVATAR_TOKEN (shared with the Vercel app)

worker_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch", "torchvision", "numpy>=2,<3", "pytorch-lightning", "opencv-python-headless", "pillow",
        "pillow-heif", "yacs", "omegaconf", "einops", "timm", "roma", "braceexpand", "termcolor", "torchmetrics",
    )
    .run_commands(f"git clone --depth 1 https://github.com/facebookresearch/sam-3d-body {SAM_DIR}")
    .env({"MHR_MODEL_PATH": str(CKPT / "assets" / "mhr_model.pt"), "TORCH_HOME": str(DATA / "torch")})
    .add_local_dir(LOCAL_PIPELINE, str(PIPELINE),
                   ignore=["private", ".venv", "checkpoints", "vendor", "out", "__pycache__", "*.pyc"])
)
web_image = modal.Image.debian_slim(python_version="3.11").pip_install("fastapi[standard]", "python-multipart")


# --------------------------------------------------------------------------- status files
def status_path(avatar_id: str) -> Path:
    return AVATARS / avatar_id / "status.json"


def read_status(avatar_id: str) -> dict | None:
    try:
        return json.loads(status_path(avatar_id).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_status(avatar_id: str, **fields) -> dict:
    current = read_status(avatar_id) or {}
    current.update(fields, updated=time.time())
    path = status_path(avatar_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current))
    tmp.replace(path)
    volume.commit()
    return current


# --------------------------------------------------------------------------- worker
# GPU is optional: `FORMA_AVATAR_GPU=T4 modal deploy ...` needs a payment method on the Modal
# account (the free monthly credit still applies). Without it the worker runs on 8 CPU cores:
# about a minute slower per avatar, no card needed.
WORKER_GPU = os.environ.get("FORMA_AVATAR_GPU") or None


@app.cls(image=worker_image, gpu=WORKER_GPU, cpu=8.0, memory=16384, volumes={str(DATA): volume},
         timeout=15 * 60, scaledown_window=10 * 60)
class Worker:
    @modal.enter()
    def load(self) -> None:
        started = time.time()
        sys.path.insert(0, str(PIPELINE))
        import torch
        from mhr_common import MHRModel
        from reconstruct import load_estimator

        if not (CKPT / "model.ckpt").is_file():
            raise RuntimeError(f"SAM 3D Body checkpoint missing at {CKPT}: upload it (services/avatar/README.md)")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.estimator = load_estimator(SAM_DIR, CKPT, device)
        self.mhr = MHRModel()
        print(f"worker ready on {device} in {time.time() - started:.0f}s")

    @modal.method()
    def ping(self) -> str:
        return "ready"

    @modal.method()
    def run(self, avatar_id: str) -> None:
        from build_avatar import build
        from reconstruct import ReconstructionError, reconstruct

        folder = AVATARS / avatar_id
        photos = folder / "photos"
        work = folder / "work"
        volume.reload()
        log_lines: list[str] = []

        def log(line: str) -> None:
            print(f"[{avatar_id}] {line}")
            log_lines.append(line)

        try:
            write_status(avatar_id, state="working", stage="shape", message="Reading your body shape from the photos…")
            started = time.time()
            ordered = [photos / f"{v}.jpg" for v in VIEWS if (photos / f"{v}.jpg").is_file()]
            identity = reconstruct(self.estimator, self.mhr, ordered, work, overlays=False, log=log)
            write_status(avatar_id, stage="build", message="Animating your avatar…",
                         warnings=identity.get("warnings", []), views=identity.get("views", []),
                         heightM=identity.get("estimatedHeightM"))
            build(work / "identity.json", folder / "model.glb", use_texture=True, mhr=self.mhr, log=log)
            write_status(avatar_id, state="done", stage="done", message="Your avatar is ready.",
                         seconds=round(time.time() - started))
        except ReconstructionError as e:
            write_status(avatar_id, state="error", stage="error", message=str(e))
        except Exception as e:  # noqa: BLE001 — report every failure to the app
            print(f"[{avatar_id}] failed: {e!r}")
            write_status(avatar_id, state="error", stage="error",
                         message="Something went wrong while building the avatar. Please try again.")
        finally:
            # Privacy: photos and photo-derived intermediates go as soon as the job ends.
            shutil.rmtree(photos, ignore_errors=True)
            shutil.rmtree(work, ignore_errors=True)
            (folder / "model.meta.json").unlink(missing_ok=True)
            volume.commit()


# --------------------------------------------------------------------------- HTTP API
@app.function(image=web_image, volumes={str(DATA): volume}, secrets=[secret], timeout=120)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def api():
    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse

    web = FastAPI(title="Forma avatar service")
    # Reads and deletes are by unguessable id and may come straight from the phone.
    # Creating an avatar needs the shared token, which only the Forma server holds.
    web.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "DELETE"], allow_headers=["*"])

    from fastapi import Request
    from fastapi.responses import JSONResponse

    @web.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception):
        import traceback
        traceback.print_exception(exc)
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    def check_token(token: str | None) -> None:
        expected = os.environ.get("AVATAR_TOKEN", "")
        if not expected or not token or not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    def check_id(avatar_id: str) -> None:
        if not ID_RE.fullmatch(avatar_id):
            raise HTTPException(status_code=404, detail="not found")

    @web.get("/health")
    def health():
        return {"ok": True}

    @web.post("/warm")
    def warm(x_avatar_token: str | None = Header(default=None)):
        check_token(x_avatar_token)
        Worker().ping.spawn()
        return {"ok": True}

    # Plain `def` (not async): FastAPI runs it in a thread pool, so the blocking Modal calls
    # below (volume commit, spawning the worker) never stall the event loop.
    @web.post("/avatars")
    def create(
        front: UploadFile = File(...),
        side: UploadFile = File(...),
        back: UploadFile = File(...),
        keep: bool = Form(False),
        x_avatar_token: str | None = Header(default=None),
    ):
        check_token(x_avatar_token)
        avatar_id = "r-" + secrets.token_hex(12)
        folder = AVATARS / avatar_id / "photos"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for view, upload in zip(VIEWS, (front, side, back)):
                data = upload.file.read()
                if not data or len(data) > MAX_PHOTO_BYTES:
                    shutil.rmtree(AVATARS / avatar_id, ignore_errors=True)
                    raise HTTPException(status_code=413, detail=f"{view} photo is empty or too large")
                (folder / f"{view}.jpg").write_bytes(data)
            write_status(avatar_id, state="queued", stage="queued", message="Waiting for a worker…",
                         created=time.time(), keep=bool(keep), warnings=[])
            Worker().run.spawn(avatar_id)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — the caller holds the token; give it the cause
            import traceback
            traceback.print_exc()
            shutil.rmtree(AVATARS / avatar_id, ignore_errors=True)
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e
        print(f"[{avatar_id}] queued (keep={bool(keep)})")
        return {"id": avatar_id}

    @web.get("/avatars/{avatar_id}")
    def status(avatar_id: str):
        check_id(avatar_id)
        volume.reload()
        st = read_status(avatar_id)
        if st is None:
            raise HTTPException(status_code=404, detail="not found")
        expires = None if st.get("keep") else st.get("created", 0) + AVATAR_TTL_HOURS * 3600
        return {k: st.get(k) for k in ("state", "stage", "message", "warnings", "views", "heightM", "seconds")} | {
            "id": avatar_id, "expires": expires}

    @web.get("/avatars/{avatar_id}/model.glb")
    def model(avatar_id: str):
        check_id(avatar_id)
        path = AVATARS / avatar_id / "model.glb"
        if not path.is_file():
            volume.reload()
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type="model/gltf-binary",
                            headers={"Cache-Control": "private, max-age=300"})

    @web.delete("/avatars/{avatar_id}")
    def delete(avatar_id: str):
        check_id(avatar_id)
        volume.reload()
        shutil.rmtree(AVATARS / avatar_id, ignore_errors=True)
        volume.commit()
        return {"deleted": True}

    return web


# --------------------------------------------------------------------------- housekeeping
@app.function(image=web_image, volumes={str(DATA): volume}, schedule=modal.Period(hours=1))
def cleanup() -> None:
    """Delete avatars older than AVATAR_TTL_HOURS (except keep=true) and stray jobs."""
    volume.reload()
    if not AVATARS.is_dir():
        return
    now = time.time()
    removed = 0
    for folder in AVATARS.iterdir():
        st = read_status(folder.name) or {}
        created = st.get("created") or folder.stat().st_mtime
        if st.get("keep") and st.get("state") == "done":
            continue
        if now - created > AVATAR_TTL_HOURS * 3600:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    if removed:
        volume.commit()
    print(f"cleanup: removed {removed} avatar(s)")
