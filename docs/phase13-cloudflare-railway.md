# Phase 13 — Cloudflare Pages + Railway demo deployment

Prepared 2026-10-14. **Not deployed. Stop before creating resources, accepting a paid plan, uploading weights/private records, or enabling public networking.** Those actions need the owner's explicit approval. A GitHub push is a separate approval and must not accidentally trigger an already connected cloud deployment.

This is one shared college-demo journal. Every invited demonstrator can read all demo records/photos and add observations or change crop labels. It has no separate accounts/record ownership and is unsuitable for unrelated users. Approve the roster and the actual records to share before uploading anything.

## Findings and current gates

- Repository: `https://github.com/Munaz-new/AgriSense.git`; local branch `main`; remote main verified at `91c64f9b5c61a8f0e1cb2604ff16000475fcb050` during preparation. Existing untracked tomato research files and `frontend/android/` are unrelated and excluded from staging.
- Existing `database/agrisense.db`: schema 3, integrity OK, **4 plants / 11 observations**. All 11 referenced photos exist. The whole upload directory is approximately 7 MiB. Preserve this journal unless the owner explicitly chooses a different reviewed demo copy.
- The real trained checkpoint and screening weights exist locally, are ignored by Git, and are absent from the image/build context. No private dataset is needed on Railway.
- Docker client exists, but the daemon socket is inaccessible even outside the sandbox; `sudo -n docker version` requires a password. **An actual image build and container boot remain unverified and block launch.** Application tests and the real-model smoke below are not substitutes for this check.
- Preferred frontend hostname: **`agrisense.pages.dev`**, subject to availability. No Pages project or custom domain has been created. Its availability/reservation, Railway hostname, Cloudflare team issuer, production Access application AUD, invited email roster, cloud spend approval and cloud upload approval are still required. The owner reports Wrangler CLI is already authenticated. Do not create a new login/token or modify the existing **`family-house-viewer` Worker**. If the preferred name is unavailable, propose `agrisense-munaz.pages.dev` and obtain the owner’s choice before creating anything.
- No Railway/Cloudflare account was modified and no cloud resources, public endpoint, or model/data upload was created.

## Access design

Browser → Cloudflare Access sign-in → Pages static Expo app → same-origin `/api/*` Pages Function → Railway HTTPS API → SQLite/photos/models on one volume.

The Pages Function forwards only the signed `Cf-Access-Jwt-Assertion` and selected content/origin headers. It strips browser cookies, authorization headers and forwarded-host headers. Railway verifies the RSA signature against the fixed team's cached JWKS endpoint, issuer, production application audience, expiry, issued-at time, subject and explicit email allowlist. The header's mere presence or an email header is never sufficient. Key-fetch/verification failure denies access. Missing production auth configuration fails startup. The Railway environment cannot fall back to unauthenticated development mode.

Records, uploads, inference, validation and writes require identity. `/ready` is the sole unauthenticated data-free readiness route; valid CORS preflights can also return without identity. `/health` requires identity. Docs/OpenAPI are disabled. There are no HTTP delete, backup, restore or administrative routes. Photo and API responses use `no-store`. Existing upload byte limits and one inference lock remain; Uvicorn allows at most 16 concurrent connections/tasks. Configure short Access sessions (for example one hour), a small invited roster, billing alerts and provider resource limits. There is no application rate limiter; authenticated users can consume the demo's inference/storage budget. This is an explicit limitation for a controlled demo, not public-service abuse protection.

Protect the **production** Pages hostname, not just preview deployments. Disable preview deployments for this demo, keep the preview Access policy, and omit backend runtime bindings from preview environments. The proxy additionally refuses hostnames other than the configured production origin. If adding a custom domain, protect that exact domain too and select its production Access AUD consistently. A copied still-valid JWT is a bearer credential; use Access logout/revocation and remove the email from Railway's allowlist to revoke access. Do not log JWTs or send them in URLs.

The same-origin proxy avoids cross-site Access-cookie and private-image problems. Native Android builds continue to use local development settings; this phase does not add a native Cloudflare Access login flow. Do not point an APK at the new demo and assume authentication works.

## Exact Railway settings

| Setting | Value |
| --- | --- |
| Repository / branch | `Munaz-new/AgriSense` / approved `main` commit |
| Root directory / build context | repository root `/` (not `backend/`) |
| Builder | Dockerfile |
| Dockerfile | `Dockerfile` |
| Build | Railway builds the root Dockerfile; local equivalent `docker build -t agrisense-api:phase13 .` |
| Start override | leave empty to use image CMD; equivalent `python -m backend.serve` |
| Listener | `0.0.0.0`, integer `$PORT` injected by Railway; local fallback `8000` |
| Workers / replicas | 1 / 1; no horizontal scaling |
| Readiness | `/ready`, timeout 300 seconds |
| Restart | on failure, maximum 3 retries |
| Persistent volume | mount exactly `/data` |
| Runtime user | set `RAILWAY_RUN_UID=0`; entry point claims only application directories and drops to UID/GID 10001 before model loading/HTTP |
| CPU/memory | recommend 2 vCPU and at least 4 GiB RAM; validate real cold-start/latency there |
| Volume capacity | recommend 5 GiB initially; weights consume about 580 MiB, then journal/photos/cache/backups grow |

The prior measured peak was about 1,929 MiB RSS before request headroom, so a 2 GiB service is too tight. One CPU may function but was not benchmarked on Railway; two CPUs and `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2` are the practical starting configuration. No GPU is required. Do not assume the default/free plan has the required limits. Review current dashboard prices, set a spend limit/alert and approve charges before creating anything.

`railway.json` contains the Docker builder, one replica, readiness and restart settings. Do not use a pre-deploy command for volume provisioning: Railway mounts the volume at runtime, not build/pre-deploy time. Attached-volume deployments have a brief interruption and are not a zero-downtime scaling design. [Railway volumes](https://docs.railway.com/volumes), [configuration reference](https://docs.railway.com/config-as-code/reference).

Copy the **template** in `deploy/railway.env.example` to Railway Variables, replacing every `REPLACE_...` value. Set:

```text
AGRISENSE_ALLOWED_HOSTS=<actual-api-host>.up.railway.app,healthcheck.railway.app,127.0.0.1
AGRISENSE_CORS_ORIGINS=https://agrisense.pages.dev
AGRISENSE_ACCESS_ISSUER=https://<actual-team>.cloudflareaccess.com
AGRISENSE_ACCESS_AUD=<production-frontend-access-application-AUD>
AGRISENSE_DEMO_EMAILS=<comma-separated-explicit-invited-emails>
```

No wildcard, URL path, trailing slash or preview wildcard belongs in CORS. `healthcheck.railway.app` is required for Railway probes; `127.0.0.1` is for the container HEALTHCHECK. Railway supplies `PORT`, `RAILWAY_ENVIRONMENT_ID` and `RAILWAY_VOLUME_MOUNT_PATH`; do not fake the mount variable to bypass checks. [Railway health checks](https://docs.railway.com/deployments/healthchecks).

## Model delivery — approval required

These are the exact verified local artifacts:

| Artifact | Local source | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Trained tomato Hybrid CNN–Transformer | `model/checkpoints/tomato_gpu_epoch5_retry2/best.pt` | 2,607,491 | `18372991aaf467e5aea4c5d1f3c9b4c6e8a17ef3a6586758c4644572c4f43b9c` |
| OpenCLIP ViT-B/32 OpenAI screening weights | `~/.cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai/snapshots/a6f597a30f7b82c51704746581f9a4e41421e878/open_clip_model.safetensors` | 605,143,284 | `e6d1bd7789aa45192b3bf90570a789b478bae1b74ebcce7eddd908e83a2b7c31` |

After approval, copy only these files into a private local seed directory as `models/tomato-best.pt` and `models/open_clip_model.safetensors`, dereferencing the local Hugging Face cache symlink. Upload the two explicit files/directories to the Railway volume using the authenticated Railway volume file manager/CLI. This avoids a public bucket, presigned URL, Git LFS or checkpoint in the Docker build. There is no automatic model downloader. Verify checksums on both ends. The SHA-256 variables are pinned to these artifacts; guarded model loading also checks trained metadata, completed optimization, architecture, class mapping, preprocessing and finite tensors. Failed checks/load abort production startup; no mock/untrained fallback exists.

`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` prevent ancillary hub downloads. Runtime caches belong under `/data/cache`; the tokenizer assets already come with the installed package. Training datasets, split manifests, evaluation images, `.aws`, credentials and research directories are never part of this transfer. [Railway volume file commands](https://docs.railway.com/cli/volume).

## Preserve database, photos and runtime files

Final volume layout:

```text
/data/journal/agrisense.db       SQLite plus any SQLite sidecar files
/data/uploads/                  original referenced photos, then new demo photos
/data/models/tomato-best.pt
/data/models/open_clip_model.safetensors
/data/cache/                    optional runtime caches
```

Startup requires an existing schema-3 database, its photo directory, SQLite integrity, valid photo references and hashes where recorded. It never initializes/migrates a production database. Runtime connections also refuse to create a missing database. Missing data, missing volume, hash mismatch or incompatible schema stops readiness/startup. Model files are read by the application; no training or weight updates occur.

After approval and before uploading, stop local journal writes and create a private, consistent backup outside the repository. `backend.backup` uses SQLite's backup API and includes referenced photos, records JSON and a checksum manifest. Do not copy an actively written `.db` alone. Example local preparation (replace `/PRIVATE/phase13` with a private operator-owned directory):

```sh
mkdir -m 700 /PRIVATE/phase13
backend/.venv/bin/python -m backend.backup \
  --database database/agrisense.db --uploads backend/uploads \
  --output /PRIVATE/phase13/demo-backup.zip
mkdir -m 700 /PRIVATE/phase13/volume
backend/.venv/bin/python -m backend.restore_demo \
  --archive /PRIVATE/phase13/demo-backup.zip --volume /PRIVATE/phase13/volume
mkdir -m 700 /PRIVATE/phase13/volume/models
cp --dereference model/checkpoints/tomato_gpu_epoch5_retry2/best.pt /PRIVATE/phase13/volume/models/tomato-best.pt
cp --dereference ~/.cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai/snapshots/a6f597a30f7b82c51704746581f9a4e41421e878/open_clip_model.safetensors /PRIVATE/phase13/volume/models/open_clip_model.safetensors
```

The restore tool validates the archive and journal and refuses to overwrite either destination directory. Review counts (expected 4 plants/11 observations at this inspection), references and hashes in the restored local copy. An interrupted restore leaves a fail-closed partial directory; inspect it rather than overwriting it. No empty-demo initialization is provided.

Once the approved Railway project, service and empty volume are selected, authenticate with the Railway CLI and verify `railway status`. Upload **only** the prepared journal, uploads and models directories to that volume, with the API stopped. Remote paths below are relative to the volume root (`/` means `/data` in the container):

```sh
railway volume files --volume <volume-id> list /
railway volume files --volume <volume-id> upload /PRIVATE/phase13/volume/journal /journal
railway volume files --volume <volume-id> upload /PRIVATE/phase13/volume/uploads /uploads
railway volume files --volume <volume-id> upload /PRIVATE/phase13/volume/models /models
```

Inspect the remote tree to ensure no extra `journal/journal` or `models/models` nesting. Do not replace data on a volume already used for demos. The startup entry point handles root-owned upload permissions and drops privileges. Validate actual provider file-transfer and UID behavior during the pending container/cloud smoke tests. `railway run` executes locally and is **not** a remote data/restore command.

Enable Railway volume backups and retain a separate private journal export after demonstrations. Download backups to private storage; never commit them. A restart/redeploy must retain the same volume. Test a backup restore to a separate empty location, compare counts/hashes and only then consider a restore onto service storage with writes stopped. SQLite/photo backups contain private data and are not encrypted by `backend.backup`; protect their storage/access. Source code rollback does not roll back volume data. Pause writes before a schema-changing update and preserve a verified backup.

## Exact Cloudflare Pages settings

| Setting | Value |
| --- | --- |
| Project type | Pages with Git integration (not a Workers app, not dashboard drag-and-drop) |
| Repository / production branch | `Munaz-new/AgriSense` / approved `main` |
| Framework preset | None |
| Root directory | `frontend` |
| Build command | `npm ci && npm run build:pages` |
| Build output directory | `dist` (relative to frontend root) |
| Node build variable | `NODE_VERSION=22.23.2` |
| Public build variable | `EXPO_PUBLIC_API_URL=https://agrisense.pages.dev/api` |
| Function runtime variable | `AGRISENSE_FRONTEND_ORIGIN=https://agrisense.pages.dev` |
| Function runtime variable | `AGRISENSE_BACKEND_ORIGIN=https://<actual-api-host>.up.railway.app` |
| Functions compatibility date | `2026-10-14` |
| Functions exhaustion behavior | Fail closed |
| Automatic/preview deployment | disable while configuring; no production bindings in previews |

The browser's production API URL is the public HTTPS Pages `/api` endpoint. The Railway origin remains server-side proxy configuration. No backend secret, Access service token, email roster or private checkpoint URL belongs in `EXPO_PUBLIC_*`. Changing the public URL requires a rebuild. The build script rejects HTTP/localhost/credential URLs, disables `.env` loading, clears Metro's cache and verifies the exported JS contains the configured API URL. An observed stale cached URL during preparation prompted this safeguard. The ignored local `frontend/.env` remains intact.

The app is a React state-driven SPA, without Expo Router/deep-link screen routes. `web.output=single` exports `index.html` and static JS. Cloudflare serves the SPA for unknown paths when no root `404.html` exists; do not add a catch-all redirect that could mask `/api`. A refresh boots the app and reloads history; it does not promise to retain the selected screen. Existing draft behavior is unchanged. `_routes.json` invokes the Function only for `/api` and `/api/*`. `functions/` remains in the frontend project root, outside `dist`; Git integration compiles it. Dashboard drag-and-drop does not deploy this Functions directory. [Pages serving behavior](https://developers.cloudflare.com/pages/configuration/serving-pages/), [Functions setup](https://developers.cloudflare.com/pages/functions/get-started/), [Pages known issues](https://developers.cloudflare.com/pages/platform/known-issues/).

`_headers` allows `camera=(self)` and disables microphone/geolocation; use the app as a top-level HTTPS page. Automated browser-camera tests cover permission denial, cancellation and cleanup; tests also verify multipart bytes through the proxy. **Real HTTPS camera permission, capture/upload, refreshed images, device routing and Access sessions still require a browser/device smoke after approved deployment.** No hosted browser success is claimed.

## Dashboard order — perform only after approval

1. **Local Docker gate first:** obtain operator access to the Docker daemon; build with repository root context. Start the image with only disposable restored data and read-only real model mounts, 4 GiB memory, a nondefault `PORT`, one worker and loopback-only published port. Check `/ready`, signed identity access, direct unauthenticated denial, genuine model output, and persistence after container replacement. Do not use the original database as the writable mount. See the local smoke command below.
2. **Cloudflare:** Workers & Pages → Create → Pages → Connect Git; select repository/main and the settings above. Disable automatic/preview deployment while configuring. Request the project name `agrisense` only after approval and availability confirmation; if it is unavailable, stop and propose an alternative before creating another project. Update every frontend-origin/API setting together if the owner selects an alternative. Do not publish usable backend bindings until Access is configured.
3. **Production Access:** Pages project → Settings → General → Enable access policy. Manage the created preview application in Zero Trust → Access controls → Applications → Configure; remove the wildcard from its public hostname to protect the exact production `<project>.pages.dev`. Then re-enable the preview policy so both production and wildcard preview hosts are protected. Add only the approved email roster, a short session duration and an appropriate login method; no Everyone/Bypass policy. Copy the production application's AUD and team issuer. For a custom domain, create/protect its exact hostname too. [Cloudflare's production-versus-preview procedure](https://developers.cloudflare.com/pages/platform/known-issues/#enable-access-on-your-pagesdev-domain).
4. **Railway:** create the approved project/service, select GitHub repository/main, root `/`, Dockerfile builder and `railway.json`. Keep public networking off and automatic deploys off. Configure approved resources, spend controls, one replica and a `/data` volume. Enter the completed variable template including production Access issuer/AUD/roster. Any early deployment without assets/configuration must fail closed; do not relax startup checks to make it green.
5. **Data transfer:** prepare/verify the offline seed described above and upload only those three directories through the authenticated Railway volume manager. Verify the remote paths, hashes, counts and volume association. No source dataset upload is authorized by this runbook.
6. **Railway start:** deploy the reviewed commit with the completed settings. Check sanitized startup stages, both models, UID 10001, `/ready`, memory, CPU and volume usage. Approve/enable the Railway HTTPS domain only after authentication has passed the local gate. Add its exact hostname to allowed hosts; retain `healthcheck.railway.app`. Ensure the generated domain targets Railway's injected `PORT`. Redeploy if variables changed.
7. **Pages finish:** set both Function runtime origins, the exact public build API URL and Fail closed under Settings → Runtime. Build/deploy the approved commit. The production Access app's AUD must be the one configured in Railway; previews must remain unable to proxy into this journal.
8. **Acceptance:** in an incognito browser, require Access sign-in; reject an uninvited account. Direct unauthenticated Railway calls to `/plants`, a known photo and inference must return 401 (only `/ready` is public). With an invited account, create a clearly marked demo plant, upload/capture a nonprivate leaf image, analyze, revisit history/photo, refresh and reopen the page. Check a random SPA URL, expired-login recovery and denied camera permission with gallery fallback. Confirm an unauthorized-origin PATCH preflight fails.
9. **Persistence/recovery:** record demo counts, redeploy/restart the same service, then confirm records/photos/model identity persist. Restore a verified backup to separate storage. Check no logs contain credentials, photos, notes or JWTs. Record actual cold-start duration/RSS and browser/device results. Only after acceptance should you choose whether to enable automatic deployments; any later push would then be a deployment action.

Example local container smoke after Docker access is repaired and a disposable seed is ready (set the issuer/AUD/roster in a private env file copied from the template; remove `RAILWAY_RUN_UID`, use local allowed host `127.0.0.1`, and set model paths to `/models/...`):

```sh
docker build -t agrisense-api:phase13 .
# Give UID 10001 read/write access to the DISPOSABLE journal/uploads; real model files stay read-only.
docker run --rm --name agrisense-phase13-check --memory=4g --cpus=2 \
  -p 127.0.0.1:18080:9217 -e PORT=9217 \
  --env-file /PRIVATE/phase13/container.env \
  --mount type=bind,src=/PRIVATE/phase13/volume,dst=/data \
  --mount type=bind,src=/PRIVATE/phase13/volume/models,dst=/models,readonly \
  agrisense-api:phase13
curl --fail http://127.0.0.1:18080/ready
```

## Verification evidence

- Backend suite: **172 passed, 5 skipped**, including volume permissions, privilege drop, Railway production-mode enforcement and runtime database loss. Skips require PyTorch/OpenCLIP in the lightweight backend environment. Starlette/httpx emits two existing deprecation warnings.
- Frontend: **139 passed**, TypeScript passed. Includes proxy auth/origin rejection, multipart preservation, private photo forwarding, session-expiry and redirect/error handling, plus existing camera, gallery, upload and journal tests.
- Expo production web export: passed, about 496 kB JS. Built with the preferred HTTPS `https://agrisense.pages.dev/api`; this is the selected preference, not a reserved or live deployment. `index.html`, `_headers`, `_routes.json` are present; there is no root `404.html`.
- Existing model inference/training contract tests: **56 passed**; these are software tests with disposable models/data and do not retrain or modify the real checkpoint.
- Real local production smoke: both original weight files loaded, `/ready` returned 200, anonymous journal read returned 401, signed synthetic test identity obtained an actual `is_mock=false` prediction from the existing healthy-leaf fixture. Startup plus prediction took about **7.2 seconds** on this workstation (not a cloud benchmark).
- Actual journal backup/restore smoke: copied **4 plants and 11 observations / 11 referenced photos** to temporary storage, verified restored data and model startup, then removed temporary copies. Source SQLite and every source photo hash remained unchanged. No private rows/photos were printed or uploaded.
- Docker build/run, real Railway volume/UID behavior, actual Access/JWKS network integration, Cloudflare-hosted refresh/camera/upload and physical device testing: **pending**, not claimed as passed.

The backend smoke used a locally generated test signing key, not a real Cloudflare identity or service credential. Cloudflare's documented [JWT validation flow](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/) was used for the production verifier design. Production JWKS is fetched only from the configured team domain and requires outbound HTTPS; no key/token from a request can select another key server.

## Git handoff

Stage only the explicitly reviewed deployment source, tests and documents. Never `git add -A`. Do not stage unrelated research or Android files, `.aws`, credentials, `.env`, local seed/backup directories, SQLite, photos, datasets, weights or generated `dist`.

The owner explicitly authorized committing and pushing the safe deployment changes to verified `origin/main`. The verified base commit is `91c64f9`; 28 reviewed deployment files were staged. The final handoff reports the resulting commit and push status. Cloud creation, charges, artifact/data upload and publishing remain separately unapproved. No force push. The owner confirmed no AgriSense Pages project exists; do not modify the existing `family-house-viewer` Worker.
