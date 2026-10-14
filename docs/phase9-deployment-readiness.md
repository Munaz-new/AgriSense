# AgriSense Phase 9: security and deployment readiness

Project title remains **AgriSense: Plant Disease Detection and Health Monitoring Using Hybrid CNN-Transformer Architecture**.

## Release decision

Local Android operation is reported by the project owner to pass camera capture, image validation, plant suitability, tomato analysis, and history persistence. This repository has not been tested on a physical phone during Phase 9. No public deployment was performed.

**Do not expose this API to the public internet yet.** There is no authentication, account identity, or record ownership. Any caller who can reach the API can list/read every plant and observation, create data, upload photos, and fetch photo bytes. `/uploads` is mounted as public static content. CORS and allowed-host checks do not authenticate native apps, scripts, or direct HTTP callers. Adding a shared API key to the mobile bundle would not solve this. A future phase must add a real identity provider/session flow, ownership checks on every journal route, private photo delivery, migrations, and tests for cross-account isolation before launch.

## What the code enforces

- `POST /plants`, plant/history/progression reads, analysis and save routes are unauthenticated. There is no API delete/backup/restore route. Destructive journal deletion and backup are local CLI operations (`python -m backend.delete_plant` and `python -m backend.backup`); protect the host and private backup files.
- `GET /uploads/{uuid}.{ext}` serves stored images without authorization. The upload writer validates supported image bytes, dimensions and a 10 MiB bound, generates UUID filenames, and stores files within the upload directory; request bodies are bounded before multipart spooling. Do not interpret these checks as access control.
- SQL queries use bound parameters. Error responses avoid exception details; diagnostic events avoid filenames, image bytes, notes and record IDs. Configure Uvicorn with `--no-access-log` because its normal request logs can include paths and query strings.
- CORS and `LocalRequestBoundary` constrain browser-origin requests only; calls without an `Origin` header are not blocked. No rate limiting exists. Apply provider/network rate limits after authentication is designed, and monitor upload/inference resource use.
- Local defaults remain local-development friendly. When `AGRISENSE_ENV=production`, startup requires explicit non-wildcard `AGRISENSE_ALLOWED_HOSTS`, exact HTTPS browser CORS origins (or an empty list for native-only use), explicit persistent database/upload paths outside the source tree, and existing absolute model artifact paths. Production also disables `/docs`, `/redoc`, and `/openapi.json`. The `/ready` route returns 503 until SQLite and both real model components are ready; `/health` remains a liveness/capability response.
- These production checks improve configuration hygiene; they do **not** make the unauthenticated routes safe for public traffic. Do not use production mode as a substitute for the missing identity and ownership layer.
- Production mode does not mount `/uploads`, so photo bytes are not publicly served before authorized owner-scoped delivery is implemented. Journal API routes still expose records, so the API remains blocked from public launch.

## Model resource measurements

Measured locally on Python 3.14.7, PyTorch 2.14.0+cu126 (CPU inference), an Intel i7-8550U host, and 8 reported logical CPUs:

| Item | Observed |
|---|---:|
| Tomato checkpoint | 2,607,491 bytes (2.49 MiB) |
| OpenCLIP ViT-B/32 weights used by suitability screening | 605,143,284 bytes (about 577 MiB) |
| Tomato model load | 1.38 s |
| Suitability model load | 3.30 s after tomato load |
| Peak process RSS after both models loaded | about 1,929 MiB |
| Healthy fixture suitability call | 0.16 s |
| Healthy fixture disease prediction | 0.03 s |

These are one local warm run, not a hosting guarantee. Allow operating-system, Python, request, and transient image-processing headroom: 2 GiB is too tight; treat 4 GiB as a minimum host size to validate, with one worker only. The inference lock serializes model use inside a process; extra Uvicorn workers would duplicate both model weights and raise memory use. CPU execution is technically viable, but concurrent-user throughput and a provider's cold-start/runtime have not been benchmarked. Reserve roughly 1 GiB for model artifacts in persistent image/model storage; SQLite plus photos need a separate persistent writable volume whose capacity and backups must match retention policy.

## Local production-like container

The root `Dockerfile` builds a non-root, one-worker API image without copying datasets, databases, private uploads, or model weights. It installs CPU-only PyTorch and torchvision wheels from the official PyTorch CPU index, rather than carrying CUDA libraries into a CPU service. The model checkpoint and OpenCLIP weights are read-only runtime mounts. `/data` must be a durable writable volume. The container serves on port 8000 behind a TLS-terminating ingress; the ingress must set the expected `Host`, preserve request size/time limits, and must not forward untrusted client identity headers. Use `/ready` for traffic readiness and configure the ingress timeout above measured worst-case inference time.

Example, after placing the model artifacts in a protected local directory and creating a persistent data directory owned by UID 10001. This is a local command only; it does not deploy anything:

```sh
docker build -t agrisense-api:local .
mkdir -p /srv/agrisense/data /srv/agrisense/models
sudo chown -R 10001:10001 /srv/agrisense/data
docker run --rm --name agrisense-api \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 127.0.0.1:8000:8000 \
  -v /srv/agrisense/data:/data:rw \
  -v /srv/agrisense/models:/models:ro \
  -e AGRISENSE_ENV=production \
  -e AGRISENSE_ALLOWED_HOSTS=localhost,127.0.0.1 \
  -e AGRISENSE_CORS_ORIGINS= \
  -e AGRISENSE_DB_PATH=/data/agrisense.db \
  -e AGRISENSE_UPLOAD_DIR=/data/uploads \
  -e AGRISENSE_CHECKPOINT_PATH=/models/tomato-best.pt \
  -e AGRISENSE_PLANT_VERIFIER_WEIGHTS=/models/open_clip_model.safetensors \
  agrisense-api:local
curl --fail http://127.0.0.1:8000/ready
```

This loopback-only smoke setup is intentionally not a public service. The image may require a first build with package registry access; base-image and Python dependency reproducibility still need lockfile/digest review. The user should separately test the built image, durable-volume restart/restore, and HTTPS ingress before any deployment decision.

The existing app saves SQLite at `database/agrisense.db` and photos at `backend/uploads` by default, which survive a local restart but are ephemeral on most hosting filesystems. Configure both paths under the same persistent single-instance volume (as in `/data`) and include both in verified private backups. Do not use shared SQLite/upload paths across replicas. For multi-instance scale or high availability, migrate the journal to a managed database and images to private object storage, then add per-user ownership and signed/authorized image delivery.

## Hosting fit (checked 2026-10-14)

- Render documents `1c-2g` as 1 CPU/2 GB RAM and `1c-4g` as 1 CPU/4 GB; current listed price for `1c-4g` is $55/month. The 2 GB tier is below this process's measured peak. Render disks persist under the mount path, but disk-backed services are single-instance and cannot scale horizontally; deploys briefly stop the old instance, and daily snapshots are retained at least seven days. This is the least-complex fit to evaluate if a single-instance disk-backed service is acceptable, but its disk and current auth blocker remain material tradeoffs. See [Render plans and pricing](https://render.com/docs/compute-plans), [Render pricing](https://render.com/pricing), [Render disks](https://render.com/docs/disks), and [Render health checks](https://render.com/docs/health-checks).
- Fly.io documents persistent volumes at $0.15/GB-month and snapshots at $0.08/GB-month (first 10 GB of snapshots free monthly) and bills compute by region and machine size. Its October 2026 page lists a 2 GB shared-cpu-8x at $17.55/month; that RAM tier is also too tight. RAM beyond the listed preset is priced separately, and actual CPU and regional pricing should be checked in the calculator before a purchase. Volumes are machine-local, so plan one instance or redesign persistence before scaling. See [Fly pricing](https://fly.io/pricing-update/) and [Fly resource pricing](https://fly.io/docs/about/pricing/).
- Do not deploy this journal to a stateless/ephemeral free tier: SQLite and photos would be lost at restart/replacement. Any eventual quote must include enough RAM (start tests at 4 GiB), a single-writer persistent data strategy, private backup storage, transfer costs, and HTTPS ingress.

No provider account was created, hosting was not purchased, and prices/features can change; recheck official pricing before making a deployment decision.

## Verification record (2026-10-14)

- Backend suite: 153 passed, 5 skipped. Model inference/pipeline checks: 46 passed. Frontend: 124 passed; TypeScript check and Expo web and Android exports passed.
- `backend.smoke_local --real-model` passed real suitability acceptance, non-plant rejection, disease prediction, saved history, restart persistence and private backup/restore with disposable local fixtures. It returned an experimental `Bacterial_spot` class on its healthy-leaf fixture (uncalibrated score about 99.65; severity unavailable); this is an example of why the output is not a validated diagnosis or a correctness estimate.
- The container image was **not built**: this workspace could not access the Docker daemon socket, including when retried with elevated command permissions. The Dockerfile and ignore rules therefore still need a daemon-enabled build and runtime test.
- Phase 9 did not repeat a physical-device test. The earlier five Android checks are the owner's report. There was no public-cloud test.

## Mobile API configuration

`frontend/src/api.ts` reads the public Expo setting `EXPO_PUBLIC_API_URL`, rejects localhost on native Android/iOS, and accepts HTTPS URLs. For a production build, set `EXPO_PUBLIC_API_URL=https://<your-authenticated-api-host>` in that build's Expo environment; it is a public bundled URL, never a secret. Keep the current ignored `frontend/.env` for laptop/LAN development. Do not commit actual `.env` files or put API credentials/tokens in Expo public variables. The API host must be the later authenticated service; the current API is not safe to expose.

## Later deployment checklist

1. Design identity/session authentication and migrate all plant/observation records to explicit owners; enforce ownership consistently and add cross-user access-denial tests.
2. Make photo access private and authorized; verify backups, restore drills, retention/deletion policy, and encryption/key management.
3. Add a rate limiter at a trusted edge or application layer and define upload/inference concurrency and abuse budgets.
4. Build the container without mounting development caches, run it at 4 GiB or more with representative concurrency, and record cold start, peak RSS, CPU latency, and disk growth.
5. Validate provider health-check hostname behavior, TLS, persistent volume behavior across redeploy/replacement, backup restore, alerting, and sanitized logs.
6. Set the mobile build's public HTTPS API URL only after those checks pass. Retest the owner-reported five-step Android workflow against the authenticated HTTPS deployment.
