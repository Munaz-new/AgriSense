# Phase 3C: local inference and application integration readiness

**Infrastructure ready for a future trusted checkpoint; real disease inference
remains unavailable and unverified.** No trained checkpoint exists at the configured
path. No training, real-model activation, deployment, commit, or push was performed.

## Starting checkpoint

The working tree was clean at the start. Local `main`, `origin/main`, and a read-only
query of GitHub's `main` all returned
`34af5063c25ef13e1bf6d476dbe38ccad24f85b8` (completed Phase 3B).
That commit and the Phase 3B readiness report remain unchanged. Phase 3C consists
only of uncommitted source, tests, and documentation edits.

## Current application flow

- `backend/app/main.py` creates the default app with `MockPredictor`. No checkpoint
  discovery or environment switch enables the trained adapter automatically.
- `/predict` validates the uploaded image and returns an unsaved mock preview.
- `/plants/{plant_id}/observations` independently validates the image and reruns
  the same predictor before saving. It does not trust the frontend's preview.
- `MockPredictor` always returns Early Blight, with image-hash-based synthetic
  confidence and severity. It performs no plant recognition or disease diagnosis.
- `/health` identifies the default as a development mock. A custom predictor's
  health response only identifies its mode; it does not prove model quality or
  successful inference on an image.
- `frontend/src/api.ts` calls `/validate-image`, `/predict`, and the observation
  save route. Environmental fields are sent on save for storage, never to the model.
- `frontend/App.tsx` shows mock warnings for preview and saved observations and
  supports `severity: null` without drawing a zero-severity chart bar. There is no
  model running in the frontend. Previously the analysis button always said
  “(mock)”; it now follows the service mode. Confidence text distinguishes synthetic
  mock values from uncalibrated future model confidence.

## Model loading and preprocessing

The existing `CropClassifier`/`TomatoClassifier` uses `load_checkpoint`, which loads
onto CPU with `weights_only=True`, validates format/architecture/training metadata,
preprocessing version, crop and ordered class mapping, then checks the model state
strictly and rejects nonfinite weights. The model is set to evaluation mode, and
prediction uses `torch.inference_mode()`. Missing or rejected checkpoints raise;
there is no random-weight or mock fallback.

Directly attempting to construct the classifier at the configured checkpoint path
confirmed `FileNotFoundError`. The architecture itself is executable in existing
synthetic forward-pass tests, but it cannot currently provide trained inference.
Successful loading of real trained weights and real end-to-end inference remain
untested. Metadata is a compatibility guard, not evidence of model quality or
checkpoint provenance; only use a trusted, trained and evaluated artifact.

Both the CLI (`model/infer.py`) and API apply technical image validation before
inference. The low-level classifier assumes that input validation has already run.
The default tomato configuration specifies 224×224 input. Shared preprocessing:

1. Apply EXIF orientation and convert to RGB.
2. Resize to 224×224 with bilinear interpolation for the current configuration.
3. Convert to float32, divide by 255, normalize with channel mean
   `[0.485, 0.456, 0.406]` and standard deviation `[0.229, 0.224, 0.225]`.
4. Add the batch dimension: `[1, 3, 224, 224]`. Inference augmentation is explicitly
   disabled. The checkpoint's configuration supplies the image size when loaded.

The new tests compare inference tensors with the existing validation dataset path,
including EXIF orientation, RGB/grayscale/RGBA inputs, and repeatability. New output
guards require a finite floating-point tensor of shape `[1, num_classes]` before
softmax and label selection. For the tomato model, this is `[1, 11]`.
Softmax confidence is uncalibrated, and severity remains `null` for model inference.

## Verified zero-based class mapping

The versioned config and all eleven logit-to-label routing tests agree:

0. `Bacterial_spot`
1. `Early_blight`
2. `Late_blight`
3. `Leaf_Mold`
4. `Septoria_leaf_spot`
5. `Spider_mites Two-spotted_spider_mite`
6. `Target_Spot`
7. `Tomato_Yellow_Leaf_Curl_Virus`
8. `Tomato_mosaic_virus`
9. `healthy`
10. `powdery_mildew` (Powdery Mildew)

No labels were renamed or reordered. The set includes the healthy class; it has no
non-plant/unknown class. The trained backend adapter passes the expected tomato
configuration to the guarded loader, preventing silent class-map substitution.

## Why unrelated images can pass

`TechnicalPlantImageValidator` checks nonempty data, a 10 MiB size limit, decoded
JPEG/PNG/WebP format, at least 224 pixels per side, at most 8192 pixels per side and
24 million pixels total, a single frame, and successful verification/full decoding.
It does not inspect semantic content. A valid poster, object photo, or solid-color
test image can satisfy every check. The API message and UI already disclose this.

An eleven-class disease classifier will still select a class for unrelated inputs.
The healthy class is not a non-plant category, and softmax alone does not establish
image suitability. This phase adds no color heuristic, unsupported rejection
threshold, or pretend plant detector. Reliable rejection requires a separately
designed and evaluated suitability/OOD approach and representative negative data.

## Changes and verification

- `model/agrisense_model/inference.py`: explicit non-augmented preprocessing and
  logits type, shape, dtype, and finiteness checks.
- `backend/app/prediction.py`: model runtime/output errors become a typed
  unavailable error. No fallback result is returned.
- `backend/app/main.py`: preview and save return a generic HTTP 503 on that error,
  without leaking internal error details, writing uploads, or saving observations.
- `frontend/App.tsx`: mode-aware analysis label, clearer confidence labels, and
  removal of the obsolete Phase 2A banner prefix.
- `model/tests/test_inference.py`: preprocessing, all class indices, malformed
  outputs, missing-checkpoint refusal, and incompatible-loader propagation tests.
- `backend/tests/test_model_readiness.py`: guarded-loader configuration forwarding,
  runtime-error translation, HTTP 503 behavior, no fallback/persistence, and
  validation before prediction. Tests use temporary storage and explicit doubles.
- `README.md` and `model/PHASE3C_READINESS.md`: current status and this report.

**Results:** 77 model tests passed; 37 backend tests passed; both Python dependency
checks passed; frontend TypeScript checking passed; whitespace checks passed.
Backend tests used the established outside-sandbox TestClient workaround. The two
existing Starlette/AnyIO deprecation warnings and model pip-cache warning were
non-failing. No tests failed. A browser/native UI walkthrough was not performed.

New inference tests use in-memory fixed outputs solely to exercise software
contracts. They are not research results or claims of real diagnoses. Existing
checkpoint-rejection tests use temporary invalid/untrained fixtures. No trained
checkpoint, full training, optimizer update, or real-dataset inference was performed
in this phase. No accuracy, precision, recall, F1, or other research metric was made.

## Preserved data and next step

The original tomato dataset was not read, modified, reorganized, or uploaded in
Phase 3C. Phase 3A manifests/audit and Phase 3B local evidence remain untouched.
`.gitignore` is unchanged: local configs, `model/data/`, `model/reports/`,
`model/runs/`, checkpoints/weights, virtual environments, caches, `.env`, credentials,
database files, uploads, frontend dependencies, and build output remain excluded.
Only source/tests and safe Markdown documentation are proposed for later review.

Review and approve Phase 3C first. The next model milestone is a separately approved
Windows environment check, training and evaluation that produces a trusted checkpoint
with this class mapping. Before application activation, test that real artifact
through CLI/API, verify the backend's PyTorch dependencies, and address image
suitability and evaluation scope. This phase does not establish Windows/GPU
readiness, disease accuracy, calibrated confidence, or field performance.

**Stopped for approval. No commit, push, training, deployment, or next phase started.**
