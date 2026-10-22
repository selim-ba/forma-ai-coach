# Avatar pipeline: photo → personal MHR avatar (research track)

This is an offline Python pipeline that produces a rigged, animated GLB for the Forma viewer. It runs on your Mac (CPU) and is **not** part of the Next.js app or its deployment.

| Step | Script | Input | Output | Needs a photo |
|---|---|---|---|---|
| 0 | `inspect_mhr.py` | MHR model | `out/mhr_inspect.json` (parameter and joint names, probes) | No |
| 1 | `build_avatar.py` | MHR model (+ optional identity JSON) | rigged GLB with the five exercise clips (`squat`, `biceps_curl`, `shoulder_press`, `romanian_deadlift`, `split_squat`) | No |
| 2 | `reconstruct.py` | one or more photos | `private/<name>/`: `identity.json` (45 shape + scale values), colours, photo crops for the texture | **Yes** |
| 3 | `build_avatar.py --identity …` | identity JSON | `public/models/avatars/<name>.glb` (git-ignored) | No |

From the photos the avatar takes its **body shape** and its **look**: the photos are projected onto the body as a texture (`texture.py`; the face always comes from the front photo, so seams fall on the sides of the head and body), and the hairline and hair colour come from the photo colours (`hair.py`). The pose and the background are discarded. The generic body gets a template short haircut.

Seams between photos are least visible when the photos are taken one after another, in the same light, at the same distance. Long hair can't be represented yet (the hair is the scalp pushed outwards).

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
python reconstruct.py private/me/front.jpg private/me/side.jpg private/me/back.jpg --name me   # → private/me/identity.json (1+ photos)
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

- Photos, photo crops (`view_<i>.jpg`), identity files and personal GLBs live in `private/` and `public/models/avatars/`, which are both git-ignored. They are never pushed to GitHub or deployed to Vercel. A personal GLB **contains the photo texture**: treat it like the photos themselves.
- Use only photos of people who have agreed, and delete `private/<name>/` when you're done.
- The avatar is an approximate body shape from a few images. It is not a measurement, and not medical or fitness data.

## Licences

- MHR: Apache-2.0. Parts of the GLB writer follow MHR's `web-viewer/exporters.py`.
- SAM 3D Body code and weights: Meta's "SAM License". Read it before any distribution or commercial use. Publications must acknowledge it, and redistributing the weights requires including the licence.

## Roadmap

1. ~~**Multi-photo reconstruction.**~~ Done. `reconstruct.py front side back …` fuses the shape with a median, reports the height spread, colours each vertex from the view that sees it most head-on, and rejects backdrop and edge samples. Areas no photo sees well borrow their left/right mirror twin's colour. Still open: refining the shape by fitting silhouettes across views, and a fourth photo for the other profile.
2. ~~**Dumbbells, hair, photo texture.**~~ Done. Still open: blending photos across seams (two UV sets and a custom shader), a separate mesh for long hair.
3. **In-app flow.** Consented upload, a processing service outside Vercel (CPU is enough: about 25 s inference plus about 1 min bake), short-lived private storage and a delete button.
4. **Validation.** Real photos of consenting people, compared with tape measurements, before claiming any accuracy.
