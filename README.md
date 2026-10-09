# AgriSense — controlled tomato-model integration

Expo + React Native + TypeScript, FastAPI, and SQLite. The app supports both
record-only plant journaling and explicit tomato-leaf analysis using the evaluated
Hybrid CNN–Transformer checkpoint. Historical mock observations remain labeled
synthetic; the default prediction path never falls back to mock results.

## Real tomato model

The default artifact is `model/checkpoints/tomato_gpu_epoch5_retry2/best.pt`.
Its held-out TEST evaluation covered 3,719 images: accuracy 82.3071%, macro F1
0.819249, cross-entropy loss 0.553904. These are curated-dataset results, not field
validation. Model scores are uncalibrated. Severity and health progression remain
unavailable. The classifier does not verify that an image depicts a tomato leaf;
other plants and unrelated images can receive a tomato label.

The model loads once per application process during FastAPI startup, on CPU,
using the existing guarded loader and checkpoint preprocessing. Requests reuse
that model in evaluation/inference mode. Inference is serialized in worker
threads, outside the async event loop. Run one server worker for this first local
integration. A missing/incompatible checkpoint or missing model dependency leaves
analysis unavailable while record-only journaling remains usable. Restart the
server after fixing a startup failure; loading is not retried on each scan.

Preprocessing is EXIF transpose, RGB conversion, direct bilinear resize to
224 × 224, float32 pixels divided by 255, CHW layout, and ImageNet normalization
(mean 0.485/0.456/0.406; standard deviation 0.229/0.224/0.225). No augmentation
or cropping is added. The checkpoint's ordered 11-class mapping is authoritative.

`GET /health` exposes `capabilities.tomato_analysis` and
`capabilities.plant_content_screening`; readiness does not establish field accuracy. Choose a plant whose
crop is `tomato` and use **Analyze tomato leaf and save**, or use **Save observation
without analysis** for any crop. A plant's declared crop is not image recognition.

Analysis submits multipart `image`, `request_id`, optional temperature, humidity,
soil type, soil condition and observation time/timezone/reference/notes to
`POST /plants/{plant_id}/observations`. The server validates the image, predicts,
and saves one observation and uploaded photo. Exact request retries return the
same observation (HTTP 200); new saves return HTTP 201. Changed content under an
existing request ID returns HTTP 409. Inference failures return HTTP 503 without
saving. Record-only requests continue to use `/plants/{plant_id}/records`.
`POST /predict` remains a tomato-only, prediction-only endpoint with no persistence.

Real responses include canonical `disease`, `prediction_score` (0–100 uncalibrated
softmax score), `severity: null`, `is_mock: false`, and predictor identity. Saved
observations add `analysis_status: completed`, image hash and checkpoint SHA-256.
The legacy `confidence` response/database column retains the same score for
compatibility; it does not mean calibrated confidence. Severity provenance stays
null. SQLite schema version 3 adds observation timezone and nullable environmental
fields through migrations that preserve existing observations.

The dataset stays outside the repository and is not required for serving.
Checkpoints, manifests, reports, SQLite files and uploads stay Git-ignored.
Earlier phase/readiness documents describe historical states and are not current
model-availability instructions. No automatic retraining or test-set evaluation
runs during application startup or requests.

## Flow

Add/select a physical plant → capture/select photo → technical validation → enter environmental context and optional observation metadata → save without analysis or explicitly analyze a tomato leaf → record / plant history / comparison availability.

Environmental details are stored as context. They are **never passed to the predictor**. No hardware, sensors, sensor APIs, authentication, payments, containers, or cloud services are used.

## What Phase 2A validates

`TechnicalPlantImageValidator` performs real technical checks on the uploaded bytes:

- Non-empty upload, up to 10 MiB (10 × 1024 × 1024 bytes).
- Actual decoded format is JPEG, PNG, or WebP; filename and declared MIME are not trusted.
- Structural integrity and full pixel decoding, including truncated/corrupt-image rejection.
- Each dimension is at least 224 pixels and at most 8192 pixels; total area is at most 24 million pixels. These are explicit MVP input limits, not evidence of plant content or trained-model requirements.
- Still images only; animated images and decompression-bomb images are rejected.

Technical file validation only confirms that the upload decodes as a supported, bounded still image. Tomato analysis then runs a separate local OpenCLIP ViT-B/32 zero-shot suitability check before the existing 11-class disease classifier. The verifier compares two image views against leaf/plant descriptions and unrelated-content descriptions. It accepts clear plant-content evidence, rejects clear unrelated content, and abstains when the comparison is ambiguous. This is not a plant detector with a measured accuracy, and its similarities are not probabilities. It can still miss difficult images or accept unrelated images; use clear close-up leaf photos. A rejected or inconclusive image is never assigned a disease label. Record-only saving remains available without semantic or disease claims.

The suitability weights must be available locally for analysis to be ready. By default the app reads the OpenAI ViT-B/32 weights from the local Hugging Face cache; `AGRISENSE_PLANT_VERIFIER_WEIGHTS` can point to a compatible local OpenCLIP state file. Startup does not download or substitute weights. Health reports plant-content screening readiness separately from technical validation and tomato checkpoint readiness. Treatment guidance remains separate from both image checks and classifier scores.

`PlantImageValidator.validate(image: bytes) -> ValidationResult` remains the technical file-validation boundary. Suitability screening is a separate `PlantContentVerifier` step, so a technical pass never means that the image contains a leaf or that disease analysis succeeded. Scan shows file validation, suitability acceptance/rejection, and disease completion separately. Selecting another photo clears previous checks and results. Explicit image rejection unlocks replacement; ambiguous network/save failures retain the request identity for safe retries. Record-only saving still requires environmental fields and makes no semantic claim.

Every prediction request and save request revalidates its own image bytes. Calling `/predict` or the observation endpoint directly cannot skip validation. A failed validation returns an API error before prediction, image storage, or observation insertion. The validation endpoint itself never predicts or persists anything.

## Prerequisites

- Python 3.11 or newer (tested with 3.14).
- Node.js 22.13 or newer and npm (tested with Node 22.23).
- For the easiest local demo, a desktop browser. For native testing, use an Expo Go version compatible with Expo SDK 57, an Android emulator, or an iOS simulator on macOS.

Run commands from the repository root unless noted. Replace `/path/to/AgriSense`
and `/path/to/tomato-dataset` with your checkout and external dataset locations.

## 1. Backend setup and run

```bash
cd /path/to/AgriSense
# On this workstation model/.venv already contains the evaluated model runtime.
# For a fresh checkout, create it first: python -m venv model/.venv
model/.venv/bin/python -m pip install -r backend/requirements-inference.txt
OMP_NUM_THREADS=4 model/.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`AGRISENSE_CHECKPOINT_PATH` can override the artifact path; relative paths resolve
from the repository root. The checkpoint must be provisioned locally, not committed.
The lightweight `backend/.venv` lacks PyTorch/NumPy on this workstation: use the
combined environment above for real serving. CPU inference also works with the
installed CUDA-enabled PyTorch build. Requirements align NumPy/Pillow with the
evaluated environment; a fresh machine must provision a compatible PyTorch wheel.

Leave this terminal running. Visit:

- Health: http://localhost:8000/health
- Interactive API documentation: http://localhost:8000/docs

SQLite is created automatically at `database/agrisense.db`; uploaded images are written to `backend/uploads/`. Paths default relative to the repository, independent of the working directory. Restarting the backend preserves plants and observations. Both runtime locations are ignored by Git.

Optional shell environment variables: `AGRISENSE_DB_PATH`, `AGRISENSE_UPLOAD_DIR`, and `AGRISENSE_CORS_ORIGINS` (comma-separated frontend origins; defaults to `http://localhost:8081,http://127.0.0.1:8081`). The backend does not automatically load a `.env` file.

## 2. Frontend setup and run

In a second terminal:

```bash
cd /path/to/AgriSense/frontend
npm ci
cp .env.example .env
npm run web
```

Open http://localhost:8081. The checked-in `.env.example` uses:

```dotenv
EXPO_PUBLIC_API_URL=http://localhost:8000
```

To run on a phone, edit `frontend/.env`: replace `localhost` with your computer’s LAN IPv4 address (for example `http://192.168.1.10:8000`). Connect the computer and phone to the same network and allow local connections to ports 8000 and 8081 through your firewall. Then run:

```bash
cd /path/to/AgriSense/frontend
npm start
```

Scan the QR code with compatible Expo Go. `localhost` on a phone points to the phone, not the backend computer. For the standard Android emulator, use `http://10.0.2.2:8000`; an iOS simulator can use `http://localhost:8000`. Restart Expo after changing `.env` (`npx expo start --clear` if needed). Expo public variables are bundled into the app and must never contain secrets.

Camera capture requests permission on native devices. Browser camera/file behavior depends on browser support; photo selection is the reliable desktop path. Images must meet the format, file-size, resolution, and still-image limits above. Convert unsupported HEIC images before uploading if the native picker does not convert them.

For a browser accessed through a LAN hostname/IP instead of localhost, set `AGRISENSE_CORS_ORIGINS` to that exact frontend origin before starting the backend, e.g. `http://192.168.1.10:8081`.

## Record-only walkthrough

1. Add a unique plant name/identifier. Optionally supply its crop name; the app does
   not identify crops from photos or infer species from plant names.
2. Choose **New observation**, select/capture a photo, and **Check file and plant suitability**.
   Record-only saving requires file validation; suitability acceptance is required
   only for **Analyze tomato leaf and save**, which checks suitability again.
3. Enter temperature, humidity, soil type and soil condition for record-only saving;
   these fields are optional for analysis. Photo selection captures observation
   time/timezone automatically, separately from server save time. Leaf/site reference
   and notes are optional. The API still accepts unknown observation time as null.
4. Choose **Save observation without analysis**. No predictor is called. Disease,
   confidence and severity stay null, with explicit unavailable messages.
5. History is newest first; the dashboard is chronological. Ordering uses supplied
   observation time with save time as a labelled fallback. Old records are retained.
6. The comparison panel uses the server's unavailable/insufficient-data result.
   It never derives severity from confidence, disease labels or environmental data.
7. If saving times out, keep the pending form open and check history. **Retry the
   same save** retains its request ID and returns the original saved record. Fields
   remain locked to prevent changing an uncertain submission. Discarding a form
   never deletes a saved observation. Pending forms do not survive app restart;
   inspect history before starting a fresh submission after restarting.

Newly saved identical image bytes for the same plant are flagged as reused evidence,
not deleted. This is exact-byte detection, not near-duplicate or same-leaf recognition;
older records with unknown image hashes are not retroactively matched.


## API contract

| Method | Endpoint | Input / behavior |
| --- | --- | --- |
| GET | `/health` | Predictor readiness plus record-only / technical-validation / plant-screening / tomato-analysis / severity / progression capabilities |
| POST | `/plants` | JSON `name` and optional `crop_name`; returns UUID and UTC save timestamp |
| GET | `/plants` | Plants, newest first |
| GET | `/plants/{plant_id}` | One plant, or 404 |
| POST | `/plants/{plant_id}/observations` | Multipart `image`, `temperature`, `humidity`, `soil_type`, `soil_condition`; revalidates, predicts, and saves; existing Phase 1 contract retained |
| GET | `/plants/{plant_id}/observations` | All records, oldest first by observed time with save-time fallback; unknown plant returns 404 |
| POST | `/plants/{plant_id}/records` | Validated record-only save; image, environmental fields and request ID required; no predictor call |
| GET | `/plants/{plant_id}/progression` | Optional `tracking_ref`; explicit comparison availability and reason; no policy enabled |
| POST | `/validate-image` | Multipart `image` only; technical validation, no prediction or persistence |
| POST | `/check-plant-suitability` | Multipart `image`; technical checks then plant screening, no disease prediction or persistence. Analysis screens the bytes again. |
| POST | `/predict` | Multipart `image` only; revalidate and preview prediction without saving an image or observation |

`POST /records` also accepts optional `observed_at` (timezone required, not future),
`tracking_ref` (up to 100 characters), and `notes` (up to 2,000 characters). Required
`request_id` is 8–100 ASCII letters/digits/underscores/hyphens. A new record returns
201; a same-content retry for the same plant/request ID returns 200 with the original
record; different content with that ID returns 409. No client-supplied prediction
fields are persisted. The existing analyzed-save endpoint retains its previous
behavior and does not gain retry protection in this phase.

Record responses add `analysis_status`, optional observation/provenance metadata,
`request_id`, `image_sha256`, and `duplicate_of`. `not_requested` guarantees null
disease/severity/confidence/predictor values. `legacy_unknown` means older analysis
metadata was not reconstructed. `is_mock=false` alone never means a record was
analyzed. Both frontend and backend contracts now permit absent analysis fields.

Database initialization transactionally migrates known older schemas to
`PRAGMA user_version=1`. Original fields are preserved; new historical fields remain
null/unknown. Future or unrecognized schemas fail without partially migrating.
Back up a valued local database before first running upgraded application code.

Validation success returns HTTP 200 with `is_valid`, `reason`, and `message`:

```json
{
  "is_valid": true,
  "reason": "technical_checks_passed",
  "message": "Technical image checks passed. This does not confirm that the image contains a plant or leaf."
}
```

Validation failures use the same shape inside FastAPI's `detail` field:

```json
{
  "detail": {
    "is_valid": false,
    "reason": "resolution_too_small",
    "message": "Image is too small. Use a photo at least 224 pixels wide and high."
  }
}
```

HTTP 413 means oversized file; 415 means unsupported format or unreadable/corrupted image; 422 covers empty uploads, unsuitable dimensions, animation, or semantic rejection during suitability checking or analysis. A missing multipart `image` field uses FastAPI's normal 422 request-validation error. The frontend displays the server's validation message and clears approval after a validation rejection.

Legacy prediction fields (confidence and any estimated severity use **0–100**, not fractions; `severity` can now be `null` when unavailable):

```json
{
  "disease": "Early Blight",
  "severity": 18,
  "confidence": 91,
  "predictor": "development-mock-v1",
  "is_mock": true
}
```

This is an illustrative response, not a fixed result. A legacy analyzed observation adds `id`, `plant_id`, `image_path`, `created_at` (UTC ISO 8601), and all four environmental fields. The crop name is stored once in the plants table and referenced by `plant_id`. `image_path` is an API-relative URL (`/uploads/<uuid>.png`). Images are served by the backend for local history previews.

Upload examples (replace the plant ID and image path):

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/plants \
  -H 'Content-Type: application/json' -d '{"name":"Tomato"}'
curl -X POST http://localhost:8000/validate-image -F 'image=@/absolute/path/leaf.jpg'
curl -X POST http://localhost:8000/predict -F 'image=@/absolute/path/leaf.jpg'
curl -X POST http://localhost:8000/plants/PLANT_ID/observations \
  -F 'image=@/absolute/path/leaf.jpg' \
  -F 'temperature=27' -F 'humidity=65' \
  -F 'soil_type=Loamy' -F 'soil_condition=Normal'
```

## Structure and replacing the mock

- `frontend/App.tsx`: simple state-based screens and shared UI components.
- `frontend/src/api.ts`: typed API client and native/browser multipart handling.
- `backend/app/main.py`: request validation, API routes, uploads, application factory.
- `backend/app/database.py`: versioned SQLite migrations and transactions.
- `backend/app/records.py`: record-only persistence, request deduplication and exact-image reuse flags.
- `backend/app/progression.py`: comparison eligibility and explicit unavailable states.
- `frontend/src/recordState.ts`: null-safe labels, explicit timestamps and retry identity.
- `backend/app/image_validation.py`: validation interface, technical implementation, result schema, input limits.
- `backend/tests/test_image_validation.py`: validation rejection, side effects, ordering, and future validator boundary tests.
- `backend/app/prediction.py`: `Predictor` interface, response schema, development mock.
- `backend/tests/test_api.py`: isolated integration tests using temporary databases/uploads.

To add the trained Hybrid CNN-Transformer later, implement `predict(image: bytes) -> Prediction` and inject that implementation through `create_app(predictor=...)`. Image decoding/preprocessing/inference belong inside that service. Preserve response names and 0–100 units, set `is_mock=False`, and identify the model in `predictor`. The existing image-only adapter contract is preserved. Phase 5 capability flags deliberately keep validated analysis disabled, including for injected custom predictors; explicit evaluation/approval and a later integration change are required to enable a model workflow. The current UI remains record-only and reads each record’s analysis status and provenance. Keep weights outside Git. Environmental fields remain outside this interface.

## Checks

```bash
cd /path/to/AgriSense/backend
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check

cd /path/to/AgriSense/frontend
npm run typecheck
npm test
CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform web --output-dir /tmp/agrisense-phase5-web
```

Backend tests cover unsupported types, corrupt/truncated images, empty/oversized uploads, dimension bounds, all supported formats, animation, no writes or predictor calls on rejection, validation-before-prediction ordering on every route, replacement-image revalidation, the future semantic validator interface, plant creation, invalid input, missing plants, image validation/limits, prediction-only behavior, observation ordering/isolation, stored image retrieval, restart persistence, and the image-only predictor boundary. Phase 5 adds migration, record-only, retry/concurrency, isolation, provenance and progression-eligibility tests. Frontend checks cover TypeScript, record labels, date validation, retry identity, API transport contracts and web bundling. Node tests use the installed Node 22 experimental type-stripping/test-isolation flags; no new test dependencies are required. Native camera permission/capture should also be exercised on a device using the walkthrough above.

Nothing is deployed. `.env`, virtual environments, node_modules, uploads, SQLite data, model weights, caches, and generated bundles are ignored. Commit `package-lock.json` for reproducible JavaScript dependency installation.

Expo image-picker setup follows the [official Expo documentation](https://docs.expo.dev/versions/latest/sdk/imagepicker/).

## Phase 2B — prepared model pipeline (not trained)

Phase 2B adds runnable **code** for dataset preparation, training, validation, evaluation, and inference. No real dataset, trained weights, accuracy, or model performance results are included. The small tensors/images used by automated tests are temporary software fixtures, not a research dataset. Tests perform no optimizer updates and do not produce completed-training checkpoints.

### Files and architecture

```text
model/
  configs/tomato.json            # All training/data/model paths and hyperparameters
  agrisense_model/
    config.py                   # Config validation and ordered crop-specific classes
    architecture.py             # HybridCNNTransformer
    data.py                     # Folder scanning, split manifests, preprocessing, Dataset
    preparation.py              # Read-only train/valid curation and exclusion audit
    engine.py                   # Training/validation loop and classification metrics
    training.py                 # Preflight, run outputs, best/last checkpoints and resume
    checkpoints.py              # Versioned checkpoint saving and guarded loading
    inference.py                # Image-only checkpoint classifier
  prepare_data.py               # Build/audit split manifest; no image copying
  sanity.py                     # Bounded CPU check: 11 samples, one optimizer step
  train.py                      # Explicit training entry point
  evaluate.py                   # Held-out test evaluation
  infer.py                      # Single-image inference with a trained checkpoint
  requirements.txt
  tests/test_pipeline.py
  tests/test_preparation.py
```

Default architecture (all weights start from scratch; no pretrained downloads):

- **Input:** RGB image resized to 224 × 224, normalized with ImageNet channel mean/std. Normalization constants do not imply pretrained weights.
- **CNN/local branch:** three 3 × 3 convolution blocks (32 → 64 → 128 channels), each with GroupNorm, GELU, and 2 × 2 max pooling; adaptive global average pooling yields 128 local-feature values.
- **Transformer/global branch:** 16 × 16 patch embedding produces 196 tokens of width 128. Learned positional embeddings feed two independent Transformer encoder layers, each with four attention heads, a 512-wide feed-forward layer, GELU, and dropout 0.1. LayerNorm and token mean pooling yield 128 global-feature values.
- **Fusion:** concatenate the two 128-value vectors into 256 values.
- **Classification head:** Linear(256, 128) → GELU → Dropout → Linear(128, number of configured classes), producing logits. Training uses cross-entropy and AdamW, with gradient clipping.
- **Confidence:** the selected class's softmax probability × 100 at inference. It is **uncalibrated model probability**, not a guarantee of correctness or disease diagnosis.
- **Severity:** no severity head or proxy calculation. The real-checkpoint adapter returns `severity: null`. Severity needs appropriate labels and a separately designed/evaluated component; class confidence is never converted to severity.

There is still no plant/non-plant recognition. A crop-specific disease classifier can assign an unrelated image to a tomato class. Real model use must remain limited to its evaluated scope; an unrelated-image rejection strategy needs separate data and evaluation.

### Phase 3A: source images versus generated metadata

The verified source root is an external dataset directory, containing `train/` and
`valid/`, with no test directory. **Source images stay outside Git and are never renamed,
rewritten, deleted, or copied by preparation.** The versioned tomato configuration uses
these 11 exact folder names, in label-index order:

1. `Bacterial_spot`
2. `Early_blight`
3. `Late_blight`
4. `Leaf_Mold`
5. `Septoria_leaf_spot`
6. `Spider_mites Two-spotted_spider_mite`
7. `Target_Spot`
8. `Tomato_Yellow_Leaf_Curl_Virus`
9. `Tomato_mosaic_virus`
10. `healthy`
11. `powdery_mildew`

Class validation, model outputs, manifest labels, and confusion matrices derive their
sizes from the configured ordered class list. `crop_name` identifies the crop; new
potato/pepper configurations can supply their own verified class lists later. No datasets
or placeholder classes for those crops are included. Never infer label order from an
unordered set or silently reuse another crop's mapping.

`--layout train-valid` applies the following versioned policy:

- Verify every supported image and fully decode it; record unreadable files as exclusions.
  Unsupported extensions are recorded as exclusions too. Unexpected split/class folders
  and symlinks fail preparation rather than silently disappearing.
- Hash EXIF-oriented RGB pixels and dimensions. Exclude **all** members of groups with
  conflicting labels, without guessing a corrected diagnosis.
- Preserve cleaned `valid` membership as logical `val`. For same-label overlap, exclude
  training copies and keep the lexicographically first validation path.
- Retain one lexicographically first representative of each remaining exact-image group;
  record every redundant path and the retained path.
- Within each class of cleaned training data, sort paths, shuffle with the configured
  seed (42), and reserve `max(1, floor(N * test_fraction))` unique images as logical test.
  The default `test_fraction=0.15` applies to **clean training**, not all source images.
  Require at least two clean training images and one clean validation image per class.
  Remaining entries are logical train. No physical `test/` folder is created.
- Record per-file source split, label, byte hash, pixel hash when readable, image size,
  exclusion reasons, duplicate/conflict groups, final membership, and count summaries.
  Exclusion categories are mutually exclusive, with conflict exclusion preceding overlap
  and within-split deduplication. Every source file must be accounted for exactly once.

The known source inspection found 25,851 training and 6,684 validation files, including
one corrupt validation image, 396 exact cross-split pairs, and three conflicting-label
groups. Images below the API's 224-pixel minimum remain usable by the training resize
path; they are not silently removed. This difference from upload validation is deliberate
and recorded in the audit.

**Limit:** grouping is exact decoded pixels, not source-leaf identity or perceptual
similarity. No source/augmentation metadata was supplied. The resulting test split is
an internal holdout, not proof of source-independent or field performance. Review
near-duplicates and source provenance before treating later metrics as research results.

Run the read-only preparation calculation, optionally saving a full proposed manifest
and audit outside the source root (the active manifest is not written):

```bash
model/.venv/bin/python -m model.prepare_data \
  --config model/configs/tomato.json \
  --dataset-root /path/to/tomato-dataset \
  --layout train-valid --dry-run \
  --audit-output model/reports/tomato_phase3a_audit.json
```

Output files are never overwritten. For a repeat audit, omit `--audit-output` or choose
another filename. `model/reports/` and `model/data/` are Git-ignored generated metadata,
not the original images. A dry-run audit contains the full proposed manifest but does
not activate it for training.

When ready to materialize the approved manifest, create an ignored local configuration
so **all later commands resolve the same external source root**:

```bash
model/.venv/bin/python - <<'PYCONFIG'
import json
from pathlib import Path
config = json.loads(Path('model/configs/tomato.json').read_text())
config['dataset_path'] = '/path/to/tomato-dataset'
with Path('model/configs/tomato.local.json').open('x') as output:
    json.dump(config, output, indent=2)
PYCONFIG
model/.venv/bin/python -m model.prepare_data \
  --config model/configs/tomato.local.json --layout train-valid
```

The generated active manifest is `model/data/tomato_splits.json` unless overridden.
Manifest loading validates crop/class order, inventory membership and source byte hashes,
selected pixel hashes, validation membership, class coverage, and absence of duplicates.
Changes to source data require a fresh reviewed preparation, not silent re-splitting.
Legacy `unsplit` and complete `train/val/test` (`presplit`) layouts remain available and
strict; the conservative exclusion policy above is explicitly selected by `train-valid`.
`validation_fraction` only applies to the unsplit layout.

### Environment and future commands

The lightweight backend environment remains separate from the PyTorch environment. Activating `backend/.venv` does not activate the model environment. These commands use explicit executables so there is no ambiguity. Run from the repository root. The model environment was checked with Python 3.14 and CPU PyTorch 2.14.0.

Install model dependencies on a fresh checkout (already installed on this workstation):

```bash
cd /path/to/AgriSense
python -m venv model/.venv
model/.venv/bin/python -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
model/.venv/bin/python -m pip install -r model/requirements.txt
```

Use the Phase 3A preparation procedure above; do not run training without separate approval.

### Phase 3B: bounded sanity check

The [readiness report](model/PHASE3B_READINESS.md) records the completed local run.
`model/sanity.py` is the reusable CPU runner derived from that run's preserved local
script. It requires the validated active manifest and original Phase 3A audit,
checks their equality and source integrity, then uses exactly one training image
per class in one batch with one optimizer step. It saves only a local JSON report;
it never saves weights or starts a full epoch. It has no GPU or full-training mode.
Memory measurements are omitted when the platform lacks `resource`, including
Windows; Windows execution itself has not yet been verified.

For a separately approved repeat, from the repository root with the model Python
environment activated (replace local paths as needed):

```bash
python -m model.sanity --config model/configs/tomato.local.json \
  --audit model/reports/tomato_phase3a_audit.json \
  --report model/reports/tomato_sanity.json
```

The runner rejects an existing output or output inside the source dataset. Keep
local configurations, audit/manifest files, and JSON runtime reports ignored. The
versioned `model/configs/tomato.json` provides reusable settings with relative paths.
The new safety/portability tests use temporary fixtures and perform no optimizer
updates. The completed real-data check has not been rerun for checkpoint packaging.

Future training command — **requires separate approval; not executed in Phase 4A**:

```bash
model/.venv/bin/python -m model.train --config model/configs/tomato.local.json --device cpu
```

Default settings in `model/configs/tomato.json`: image size 224, batch size 16, learning rate 0.0003, epochs 30, seed 42, AdamW with weight decay 0.01, and the exact ordered eleven-class tomato list including `powdery_mildew`. SGD is also configurable with momentum (default 0.9). Dataset, manifest, checkpoint, and report paths are configurable. Relative data/output paths resolve from the repository root, not the shell's current directory. An optional `--device cuda` requires separately installing a matching CUDA-enabled PyTorch build and suitable hardware; CPU is the tested setup. Deterministic operations are requested; identical results across devices/PyTorch versions are not guaranteed.

`model.train --check-only` performs read-only manifest/device/output validation and
does not create batches or train. The training CLI supports overrides for dataset
root, epochs, batch size, learning rate, optimizer, weight decay, and checkpoint
path. `model/configs/tomato.windows.example.json` is a portable template; copy it
to an ignored `*.local.json` config and set your own paths. Follow the Phase 4A
report to transfer the existing manifest unchanged rather than resplitting data.

Training validates after each epoch and saves the model with the lowest validation loss at:

```text
model/checkpoints/tomato_hybrid_best.pt
```

Checkpoint format v2 still binds the crop and ordered class mapping with a digest,
preserving Phase 3C inference compatibility. The best checkpoint contains model
weights, configuration, preprocessing version, completed epoch/step counts, measured
validation loss, and manifest digest. Its optimizer-state entry is empty: use the
separate last checkpoint for resume. With the default path, outputs are:

- `model/checkpoints/tomato_hybrid_best.pt`: best validation-loss model.
- `model/checkpoints/tomato_hybrid_best.last.pt`: last completed epoch, optimizer,
  best-model snapshot and resume metadata.
- `model/checkpoints/tomato_hybrid_best.history.json`: measured epoch records.
- `model/checkpoints/tomato_hybrid_best.run.json`: configuration and runtime metadata.

All remain ignored. New runs, including resume, require an unused output prefix
outside the source dataset. `--resume` accepts only a Phase 4A last checkpoint;
`--epochs` is the total target epoch count. Class order, manifest digest, training
settings and recorded runtime must match. The new prefix preserves the old run and
restores its best model even when later epochs do not improve. Only completed
epochs resume; an interrupted partial epoch is repeated. Best/legacy checkpoints
cannot resume. See the Phase 4A report for the proposed Windows commands.

Future evaluation command — **not run against any real dataset/checkpoint yet**:

```bash
model/.venv/bin/python -m model.evaluate --config model/configs/tomato.local.json
```

Evaluation requires the same manifest and class mapping as training, and uses checkpoint preprocessing settings. It writes measured test loss, accuracy, confusion matrix (rows = actual, columns = predicted), per-class precision/recall/F1/support, and macro F1 to `model/reports/tomato_test.json`. Accuracy/precision/recall/F1 are fractions (0–1). Zero-denominator precision/recall/F1 use 0. Do not repeatedly tune against the held-out test set. No such performance report exists yet.

Future single-image inference command:

```bash
model/.venv/bin/python -m model.infer --config model/configs/tomato.local.json --image /absolute/path/leaf.jpg
```

The CLI first applies the existing technical image checks. Checkpoint loading uses `weights_only=True`, strict architecture/state checks, finite weights, training metadata, and preprocessing compatibility. Missing, raw/untrained, or incompatible checkpoints fail with an error; inference never substitutes random weights. Metadata guards prevent accidental use of untrained weights, but do not establish model quality or prove provenance of an arbitrary supplied file. Use only trusted checkpoints produced and evaluated in your own workflow.

### Backend readiness and current safety state

The default `create_app()` **still constructs `MockPredictor`**, even if a checkpoint later appears. `/health` retains this legacy predictor-mode information while reporting validated analysis unavailable. The Phase 5 UI uses record-only capabilities and never calls the mock predictor. Existing synthetic mock severity/confidence are unchanged and are not model performance.

Phase 3C validates inference logits before selecting a class: one finite
floating-point row with exactly the configured number of classes (11 for tomato).
Inference explicitly disables augmentation and shares validation preprocessing.
The future trained adapter translates model runtime/output failures into a generic
HTTP 503 on both preview and save routes, without a mock fallback, image upload,
or observation write. Checkpoint-loading failures still stop adapter construction.
The Phase 5 frontend labels historical mock confidence as synthetic and stored model
confidence as uncalibrated; record-only observations have neither value.

`backend/app/prediction.py` now includes `TrainedTomatoPredictor(checkpoint_path)`, which lazily loads the guarded classifier and implements the existing image-only `predict(bytes) -> Prediction` contract. A future explicit integration can pass this adapter to `create_app(predictor=...)` after dataset/model evaluation and installing model dependencies in the backend environment. It is not activated in Phase 2B, is tomato-only, and never receives environmental fields. Missing checkpoints fail construction; the current default app remains mock without needing PyTorch installed in its environment.

Phase 3C established nullable severity. Phase 5 additionally permits absent disease and confidence for record-only observations, preserves legacy records through a versioned transaction, and displays “Severity not measured” without inventing a zero. Actual model-derived severity remains unavailable.

Datasets, split manifests, virtual environments, checkpoints, training histories, and evaluation reports are Git-ignored. The user supplied the local tomato images; no datasets or weights were downloaded by this workflow. Phase 3A prepared metadata only. Phase 3B subsequently completed one disposable optimizer step, as recorded in the readiness report. No full training or deployment was performed. Review the generated audit and source/collection grouping limitations before authorizing further training.

### Model/backend checks

```bash
cd /path/to/AgriSense
model/.venv/bin/python -m pytest model/tests -q
model/.venv/bin/python -m pip check
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
cd ../frontend
npm run typecheck
npm test
CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform web --output-dir /tmp/agrisense-phase5-web
```

Model tests check configuration, branch connectivity/shapes, deterministic preprocessing, augmentation restricted to training, split isolation/integrity, missing/untrained checkpoint rejection, probability/report arithmetic using explicitly synthetic test doubles, and a validation loop that makes no parameter updates. Backend tests also check mock defaults, absent checkpoint handling, nullable severity persistence, and migration preservation.

Implementation references: [PyTorch TransformerEncoderLayer](https://docs.pytorch.org/docs/stable/generated/torch.nn.TransformerEncoderLayer.html) and [saving/loading state dictionaries](https://docs.pytorch.org/tutorials/beginner/saving_loading_models).

### Verification notes

Phase 3A verification: 44 model tests and 32 backend tests passed, as did both Python
dependency checks. The real dataset dry run retained 31,441 of 32,535 source files:
21,108 train, 6,614 validation, and 3,719 test. It excluded 1 unreadable file, 6 files
from 3 conflicting-label groups, 395 training copies overlapping validation, and 692
within-split redundant copies. No exact pixel duplicates remain in proposed membership.
The full audit is generated locally at `model/reports/tomato_phase3a_audit.json` and is
Git-ignored. No active training manifest, trained checkpoint, or performance metric was
created by this dry run. Near-duplicate/source-leaf leakage remains unverified.


Phase 2B verification: 22 model tests and 32 backend tests passed; model/backend dependency checks, TypeScript, Expo compatibility, web/Android/iOS bundles, and all four model CLI `--help` commands passed. No optimizer updates, real dataset evaluation, trained checkpoints, or performance reports were produced.

Phase 2A passed 29 backend tests, Python dependency checks, TypeScript checking, Expo dependency compatibility checking, and Expo web, Android, and iOS bundling. Native camera interaction and the full UI flow still require a device/browser walkthrough; bundle checks are not end-to-end UI tests. TestClient needed to run outside this workstation’s restricted sandbox because its event-loop thread stalled inside it. Two upstream Starlette test-client deprecation warnings are non-failing.

`npm audit` reports 10 moderate findings in the Expo tooling dependency chain, rooted in the transitive `uuid` package used by `xcode`. Its suggested automatic fix downgrades Expo to SDK 46, so it was not applied. There are no high or critical findings in that audit. Recheck upstream dependency updates before a later production phase.
