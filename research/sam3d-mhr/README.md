# SAM 3D Body / MHR research spike (not started)

This is an independent research track. It is **not** part of the MVP runtime. The Node app must never depend on anything in this folder. See "SAM 3D Body / MHR: subsequent research track" in the root README.

Entry criteria: generic-avatar playback and GPT orchestration must already be tested on the iPhone 13.

Integration point: once a personalised GLB animates correctly offline, put it behind an `avatarProvider` interface. It must expose the same clip names and pass `npm run assets:validate`.

Privacy: never commit photos, identity coefficients or reconstructed meshes. `.gitignore` already excludes `research/**/data/` and `research/**/outputs/`.
