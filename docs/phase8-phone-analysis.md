# Phase 8 — native phone analysis diagnosis and verification

Project title: **AgriSense: Plant Disease Detection and Health Monitoring Using Hybrid CNN-Transformer Architecture**

Baseline: `c6aa207`. Investigation and automated checks: October 14, 2026.
**Physical Android camera-to-analysis remains unverified.** No failing phone photo,
phone log or active Expo environment override was supplied during this investigation.

## Findings before changes

- The local, ignored `frontend/.env` sets `EXPO_PUBLIC_API_URL=http://localhost:8000`.
  The tracked example and API fallback also used localhost. That address refers to
  the phone in Expo Go, so this configuration cannot reach the laptop backend.
  A shell override could explain why a particular phone session reached screening;
  the exact cause of that session's rejection remains unknown.
- URI-backed native multipart construction was already correct. It did not set a
  manual multipart Content-Type/boundary. However, it trusted picker metadata without
  checking whether the cached file still existed, and defaulted missing MIME/name
  to JPEG even when the format was unknown.
- Screening failures inside analysis were flattened to a generic prediction-service
  failure. Structured errors other than the three screening codes lost their message
  in the client. Network failures did not identify the failing endpoint, and every
  timeout suggested a possible save, including preview-only checks.
- Camera quality 0.85 compresses without imposing a pixel limit. Large native photos
  can still exceed the existing 10 MB / 24 MP / 8192-per-side limits. Minimum resolution
  is 224 by 224. These limits remain enforced; HEIC, corrupt files and animations are
  not relabeled as supported images. There is no new automatic resize or conversion.
- Both screening and disease preprocessing already apply EXIF orientation and RGB
  conversion. Disease preprocessing uses the checkpoint's established resize and
  normalization. These operations and the model weights remain unchanged.
- The gate compares two CLIP views against plant and unrelated prompts. Both margins
  must be at least 0.02 for acceptance, or at most -0.02 for non-plant rejection;
  otherwise it abstains. This is **not a species or calibrated image-quality model**.
  It cannot reliably distinguish a non-tomato leaf or quantify blur. Explicit crop
  metadata restricts analysis to plants the user identifies as tomato; changing that
  metadata does not establish the species in the photo.

## Changes and workflow

Native requests now reject a loopback API address with precise Expo restart guidance.
Scan displays the configured backend address. A stale but syntactically valid LAN IP
cannot be detected offline: connection errors direct the user to open `/health` on
the phone and check Wi-Fi, the current laptop IP, firewall and backend bind address.
The ignored local `.env` is not committed or silently replaced with a guessed IP.

`expo-file-system` 57.0.7 (already part of the installed Expo dependency tree) is now
a direct dependency. Before each native upload, the app checks the actual file's
existence and size, accepts file/content URIs, and preserves or derives MIME and
filename metadata. Unknown bytes use an octet-stream type rather than pretending to
be JPEG. The backend remains authoritative and decodes bytes independently of names.

Permission → capture → preview/retake is unchanged. **Use photo** uploads for file
validation and then plant screening. **Analyze tomato leaf and save** uploads again,
rechecks suitability, runs the real hybrid model, and saves atomically. Results show
the server's class, uncalibrated model confidence, experimental-output warning and
severity availability. Current real severity is null: **Severity not measured**.
History uses the saved server record. Replaying the same request ID avoids a duplicate.

File/size errors, upload failures, unreachable backend, 30-second timeouts, non-plant
rejection, uncertain suitability, unsupported crop metadata, unavailable screening,
unavailable model and inference failure have distinct explanations. Scan provides
**Retry photo checks**, connection refresh and the existing **Retry analysis and save**.
An uncertain save retains its request ID; check history before retrying or discarding.
No failed analysis creates a disease result. Native drafts remain session-only.

Backend image decoding now runs in the threadpool instead of blocking the async event
loop. Sanitized request IDs, byte counts, stages, screening margins and durations make
the failure boundary visible. Development Expo logs show a redacted route, response
status and correlation reference. Neither diagnostic stream logs images, filenames,
notes, plant IDs, model paths or raw exception messages. Startup/model libraries may
produce their own logs; use the filtering instructions below before sharing.

## Evidence and limits

Baseline checks passed before code changes: 94 frontend tests, TypeScript and 41 focused
backend tests including real local CLIP/checkpoint integration.

Post-change checks:

- 116 frontend tests passed, zero skipped: native URI/MIME payloads, local file
  availability, loopback rejection, upload/network/HTTP errors, abort timer, retry
  identity, non-plant rejection, result rendering and saved history.
- TypeScript check passed.
- 99 focused backend tests passed, zero skipped, including real screening/checkpoint,
  corrupt/oversized file rejection, non-plant abstention, failed inference with no
  persistence, retry, SQLite history and sanitized diagnostics.
- 24 model inference tests passed, zero skipped, including orientation preprocessing,
  class mapping and invalid-output rejection.
- Android and web Expo exports passed. Exported bundles are not an APK or device test.
- A real Uvicorn HTTP smoke test on localhost, with a disposable database and uploads
  under `/tmp`, passed validation → screening → `Bacterial_spot` inference → save →
  replay (HTTP 200) → history. A logo returned `non_plant_image` (422), leaving one
  history row. It used an extensionless filename and octet-stream MIME to verify
  byte-based decoding over actual multipart HTTP. The test server was stopped.
- Real integration accepts an additional 2048 × 2048 JPEG at quality 85 with EXIF
  orientation 6, then predicts, saves, serves the same bytes and safely replays it.
  It is a transformed fixture, **not a camera capture**.

Existing fixtures with the unchanged local models:

- Bacterial-spot tomato: plant margins 0.05074 / 0.05277; class `Bacterial_spot`,
  uncalibrated score 99.65036%, severity null; screening plus inference about 0.718 s.
- Healthy tomato: margins 0.04282 / 0.04347; class `healthy`, uncalibrated score
  99.99989%, severity null; screening plus inference about 0.485 s.
- Logo: margins -0.11306 / -0.14278; `non_plant_image`; no disease inference or
  analyzed observation. The generated document fixture is also rejected in integration.

These are fixed regression examples, not an accuracy estimate or a promise that a
genuine field photo will pass. False rejection cannot be measured without the failing
photo or representative labeled field evidence. The 0.02 threshold, prompts and
two-view acceptance rule were not changed. No retraining, external evaluation, full
research suite, APK build or physical-device test was performed.

## Start the backend and Expo Go

Use compatible Expo Go for this repository's SDK 57. Phone and laptop must share a
reachable LAN. Identify the laptop's Wi-Fi IPv4 address (not loopback, Docker or VPN):

```bash
ip -4 addr show scope global
```

Terminal 1, retaining the existing journal:

```bash
cd /home/munaz/Projects/AgriSense
OMP_NUM_THREADS=4 model/.venv/bin/python -m uvicorn backend.app.main:app \
  --host 0.0.0.0 --port 8000 --workers 1 --no-access-log \
  2>&1 | tee /tmp/agrisense-phase8-backend.log
```

Wait for `AgriSense startup state=ready ... tomato_analysis=True`. A false value
requires fixing checkpoint/screening startup, not weakening validation. The local
weights must already be present; startup does not download a replacement.

Terminal 2 (the prompt takes your actual laptop IP, overriding the ignored `.env`):

```bash
cd /home/munaz/Projects/AgriSense/frontend
read -r -p 'Laptop Wi-Fi IPv4 address: ' AGRISENSE_LAN_IP
EXPO_PUBLIC_API_URL="http://${AGRISENSE_LAN_IP}:8000" npm start -- --lan --clear
```

Open `http://YOUR_LAPTOP_IP:8000/health` in the phone browser first. Verify both
`tomato_analysis` and `plant_content_screening` are true. If it does not open, resolve
LAN isolation/firewall/bind address first; an Expo tunnel does not tunnel FastAPI.
Scan the Expo QR code. Check that Scan shows the same backend address. Restart Expo
and reload Expo Go whenever the IP/env changes. Native requests do not require CORS.

## Physical reproduction and sanitized logs

1. Select/create a plant known to be tomato. Take a close, well-lit photo of one leaf;
   allow camera access and confirm that the preview is the photo just captured.
2. Use photo, then analyze and save. Record which action fails and its exact message.
   Success must show a real class, model score, experimental warning, unavailable
   severity and one saved history entry with the same photo.
3. Repeat with a clearly unrelated document/logo. It should be rejected or abstain,
   with no disease result and no analyzed history entry. A false acceptance is a
   screening-model failure to investigate, not evidence that the object is tomato.
4. Stop the backend, retry a check, restart it and refresh connection status. For a
   failed/timeout save, check history and retry the same submission; verify one row.
   Retake/cancel, denied permission, gallery and Android background/resume still
   need physical checks. OS process death can lose the session-only native draft.
5. In Expo's React Native DevTools console (press `j` in the Expo terminal), filter
   for `[AgriSense request]`. Copy only those entries around the failing action,
   along with its displayed error. Record phone model, Android/Expo Go versions and
   the Git commit. Avoid sharing full console dumps or personal image/record data.
6. Extract the matching backend diagnostics:

   ```bash
   rg 'AgriSense (startup|request=)' /tmp/agrisense-phase8-backend.log \
     > /tmp/agrisense-phase8-sanitized.log
   ```

   A response reference in Expo matches `request=...` in FastAPI. If there is no
   matching backend request, investigate address/connectivity/local upload. If bytes
   arrived, inspect validation, screening margins and inference stages. Uncertain
   suitability is not proof of an unsupported species or measured blur. Review the
   filtered log before sharing; do not send `.env`, credentials, `.aws`, databases,
   photos or model files. A genuinely valid rejected tomato photo requires further
   model investigation; never force it through or relabel it as accepted.

## Reproduce automated checks

From the repository root (FastAPI tests require local socket access):

```bash
npm --prefix frontend test
npm --prefix frontend run typecheck
(cd backend && OMP_NUM_THREADS=4 /home/munaz/Projects/AgriSense/model/.venv/bin/python \
  -m pytest -q -rs tests/test_plant_suitability.py tests/test_real_integration.py \
  tests/test_image_validation.py tests/test_observation_records.py \
  tests/test_request_limits.py tests/test_startup.py tests/test_api.py)
OMP_NUM_THREADS=4 model/.venv/bin/python -m pytest -q -rs model/tests/test_inference.py
(cd frontend && CI=1 EXPO_OFFLINE=1 npx --no-install expo export \
  --platform android --platform web --output-dir /tmp/agrisense-phase8-export)
```

Only the reviewed application/configuration/test files and this runbook belong in
the Phase 8 commit. Existing untracked research documents, datasets, model weights,
external evaluation files, secrets and `.aws` are excluded.
