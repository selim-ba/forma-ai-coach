# Avatar pipeline: photo → personal MHR avatar (research track)

This is an offline Python pipeline that produces a rigged, animated GLB for the Forma viewer. It runs on your Mac (CPU) and is **not** part of the Next.js app or its deployment.

| Step | Script | Input | Output | Needs a photo |
|---|---|---|---|---|
| 0 | `inspect_mhr.py` | MHR model | `out/mhr_inspect.json` (parameter and joint names, probes) | No |
| 1 | `build_avatar.py` | MHR model (+ optional identity JSON) | rigged GLB with `squat` and `biceps_curl` clips | No |
| 2 | `reconstruct.py` | one photo | `private/<name>/identity.json` (45 shape + scale values) | **Yes** |
| 3 | `build_avatar.py --identity …` | identity JSON | `public/models/avatars/<name>.glb` (git-ignored) | No |

Only the **body shape** is taken from the photo. Its pose, the background and the face expression are discarded.

## Setup (once, on the Mac)

```bash
cd research/avatar-pipeline
brew install uv                     # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt huggingface_hub

hf auth login                       # paste a *read* token from huggingface.co/settings/tokens
hf download facebook/sam-3d-body-dinov3 --local-dir checkpoints/sam-3d-body-dinov3   # several GB
```

`checkpoints/` and `.venv/` are git-ignored. The download includes `assets/mhr_model.pt`, which steps 0, 1 and 3 use.

## Step 2 setup (photo → body shape)

```bash
git clone https://github.com/facebookresearch/sam-3d-body.git vendor/sam-3d-body   # git-ignored
uv pip install -r requirements-sam.txt
```

This runs on the CPU with no detectron2: the whole photo is used as the person's box, so crop it to the person. The first run fetches DINOv3's model *code* from GitHub through `torch.hub`. The weights come from the checkpoint you already downloaded.

```bash
python reconstruct.py private/me/photo.jpg --name me     # → private/me/identity.json
python build_avatar.py --identity private/me/identity.json   # → public/models/avatars/me.glb
# open http://localhost:3000/?avatar=me
```

For a good photo:
- one person, head to toe in frame, standing upright and facing the camera
- arms slightly away from the body
- fitted clothes and a plain background
- camera at about hip height

JPEG and iPhone HEIC both work.

## Privacy

- Photos, identity files and personal GLBs live in `private/` and `public/models/avatars/`, which are both git-ignored. They are never pushed to GitHub or deployed to Vercel.
- Use only photos of people who have agreed, and delete `private/<name>/` when you're done.
- The avatar is an approximate body shape from a single image. It is not a measurement, and not medical or fitness data.

## Licences

- MHR: Apache-2.0. Parts of the GLB writer follow MHR's `web-viewer/exporters.py`.
- SAM 3D Body code and weights: Meta's "SAM License". Read it before any distribution or commercial use. Publications must acknowledge it, and redistributing the weights requires including the licence.

## Roadmap

1. **Multi-photo reconstruction.** SAM 3D Body reads one image at a time, but every result shares the MHR identity space.
   - Shape: run front, side and back photos, then fuse identity and scales with a robust median. Later, refine by fitting silhouettes across all views.
   - Colours: per vertex, sample from the view that sees it most directly, instead of diffusing into unseen areas.
   - Consistency: report the spread between views, and warn when it is too large to trust.
2. **Dumbbells** on MHR avatars, attached to the wrist joints.
3. **In-app flow.** Consented upload, a processing service outside Vercel (CPU is enough: about 25 s inference plus about 1 min bake), short-lived private storage and a delete button.
4. **Validation.** Real photos of consenting people, compared with tape measurements, before claiming any accuracy.
