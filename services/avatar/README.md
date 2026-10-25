# Avatar service (Modal)

Lets the iPhone app turn three photos into a personal avatar without the Mac. It runs the same pipeline as `research/avatar-pipeline/` on a Modal GPU worker.

```
iPhone ──photos──▶ Vercel /api/avatar ──(token)──▶ Modal  POST /avatars ──▶ GPU worker
   ▲                                                     │   SAM 3D Body → identity + texture
   └──── polls status, downloads model.glb ◀─────────────┘   MHR bake → model.glb (7 clips)
```

- **Cost.** One avatar takes 2–3 minutes of 8 CPU cores, or a bit less with a T4 GPU: a few cents either way. Modal's free plan includes $30 of credit a month. Workers shut down 10 minutes after the last job.
- **Privacy.** Photos are deleted as soon as the avatar is built, or fails. Avatars are deleted after 24 hours unless created with `keep` (the demo fallback). Anyone with an avatar's id can view it, and delete it unless it was kept (deleting a kept avatar needs the service token).
- **Licences.** SAM 3D Body weights are under Meta's SAM License: check its terms before any use beyond a personal demo. MHR is Apache-2.0.

## One-time setup (Mac, `research/avatar-pipeline` environment active)

```bash
uv pip install modal
modal setup                                   # links your Modal account in the browser

# 1. A shared secret between the Forma server and the service
TOKEN=$(openssl rand -hex 24)
modal secret create forma-avatar AVATAR_TOKEN=$TOKEN
echo "AVATAR_TOKEN=$TOKEN"                     # keep it: it also goes into Vercel and .env.local

# 2. Upload the SAM 3D Body checkpoint (several GB, once), from the repo root
modal volume create forma-avatar-data
modal volume put forma-avatar-data research/avatar-pipeline/checkpoints/sam-3d-body-dinov3 /checkpoints/sam-3d-body-dinov3

# 3. Deploy (prints the API URL, e.g. https://<you>--forma-avatar-api.modal.run)
modal deploy services/avatar/modal_app.py                      # CPU worker, no payment method needed
FORMA_AVATAR_GPU=T4 modal deploy services/avatar/modal_app.py  # GPU worker, faster; Modal asks for a card
```

Then set these in `.env.local` and in Vercel (Project → Settings → Environment Variables):

| Variable | Value | Where it's used |
|---|---|---|
| `AVATAR_SERVICE_URL` | the API URL from `modal deploy` | server: forwards the photos |
| `AVATAR_TOKEN` | the token above | server only, never `NEXT_PUBLIC_` |
| `NEXT_PUBLIC_AVATAR_SERVICE_URL` | the same API URL | browser: progress and the avatar file |
| `AVATAR_ACCESS_CODE` | optional short code | the app asks for it before uploading, so strangers can't spend your credit |

## Test from the Mac, and make the demo fallback

```bash
python services/avatar/create_avatar.py research/avatar-pipeline/private/test-b/{front,side,back}.png
python services/avatar/create_avatar.py me-front.jpg me-side.jpg me-back.jpg --keep   # the fallback
```

The script prints the avatar's link, for example `https://forma-ai-coach-nine.vercel.app/?avatar=r-…`. Add the kept one to your iPhone's Home Screen or bookmarks before the demo.

## Operating it

- `modal app logs forma-avatar` shows the worker's progress lines.
- **Before the demo,** open the app's "Create my avatar" screen once. It warms a worker so the first avatar doesn't wait for a cold start of about a minute.
- To delete everything: `modal volume rm forma-avatar-data /avatars -r`.
