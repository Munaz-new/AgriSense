# Phase 5 — model-independent records and progression readiness

Status: **READY for review of the model-independent implementation.** Real model
analysis, severity measurement and real health progression remain unavailable.
No Phase 4B work, training, deployment, dataset modification or Git checkpoint was
performed. This report describes software behavior and tests, not model performance.

## Baseline and preserved work

Started from a clean `main` at Phase 4A commit
`9b4374ee332ef4cdbad920311aa6aebd261669dd`. HEAD and the index remain unchanged.
All files under `model/`, including the training pipeline, configs, tests and
Phase 3/4 readiness reports, remain unchanged. Model regression tests use the
existing synthetic fixtures without optimizer updates or trained checkpoints.
No original dataset images were accessed by this implementation or its checks.
Temporary image fixtures are software tests, not a generated research dataset.

SHA-256 checks before and after implementation confirm unchanged existing:

- `database/agrisense.db` (the user's database was not migrated or opened by the app).
- `model/data/tomato_splits.json`.
- `model/reports/tomato_phase3a_audit.json`.
- `model/reports/tomato_phase3b_sanity.json`.
- `model/configs/tomato.local.json`.

No checkpoint directory was created. No new dependency, CUDA installation or GPU
environment was introduced. Web export files are local artifacts under `/tmp`,
not a deployment or proposed commit content.

## Completed implementation

### 1. Record and analysis contracts

Observations now have optional disease, confidence, severity and predictor values.
`analysis_status` is `not_requested`, `completed`, or `legacy_unknown`.
Record-only rows have `not_requested`, `is_mock=false` and null analysis values;
`is_mock=false` alone is not a claim that analysis occurred. SQLite enforces this
record-only invariant. The separate `Prediction` interface remains compatible with
the future image-only trained adapter.

`/health` exposes record-only capability and explicitly reports validated disease
analysis, severity measurement and health progression unavailable. These flags
remain false even when a custom predictor is injected: custom injection is not
proof of validation. Future activation needs an explicit integration change.

The existing mock and analyzed endpoints remain for legacy compatibility and
software tests. Their numeric outputs are explicitly synthetic, not model results.
The Phase 5 UI never calls `/predict` or the analyzed-save endpoint.

### 2. Versioned, preserving database migration

A transaction with `BEGIN IMMEDIATE` upgrades recognized pre-Phase-5 schemas to
`PRAGMA user_version=1`, including databases whose severity was previously NOT NULL
or already nullable. Existing original fields, IDs and image paths are copied
unchanged; no old observation times, crop identities, hashes or provenance are
inferred. Older records receive `legacy_unknown`; other new metadata stays null.
Future/unrecognized schemas are rejected with the transaction rolled back.
Repeated initialization is idempotent. Foreign keys and indexes are retained.

New metadata supports manually supplied crop identity, observation time, leaf/site
reference, notes, image hash, request identity, duplicate reference, checkpoint
identity, and severity source/method/version/scale. A future explicitly constructed
trained adapter records a SHA-256 identity of its actual checkpoint after guarded
loading; no artifact identity or model weights are invented now.

Only disposable databases were migrated during verification. The installed local
application database will migrate on its next startup. Back it up before that
upgrade if it contains valued records.

### 3. Record-only saving and retries

`POST /plants/{plant_id}/records` validates the actual image bytes and environmental
fields and persists the photo/context without calling any predictor. Optional
observation times must be timezone-qualified and not future; they normalize to UTC.
Save time remains separate. Missing observation time stays null.

The required request ID is unique per plant. An immediate transaction serializes
concurrent attempts; same-content retries return the original record (HTTP 200),
new records return 201, and changed content using the same ID returns 409. Changes
to bytes or metadata are detected. Database failures roll back the row and clean up
the newly written image. Exclusive file creation protects existing images.

Newly recorded identical image bytes within the same plant are retained and flagged
with `duplicate_of`. No images are deleted as duplicates. This does not recognize
near-duplicates, prove distinct leaves, or retroactively hash old uploads. A reused
request ID on a different plant cannot expose the first plant's record.

### 4. Scientifically limited progression

`GET /plants/{plant_id}/progression?tracking_ref=...` returns a status, reason,
message, candidate record IDs/times, nullable delta, and policy/provenance fields.
History is ordered by `COALESCE(observed_at, created_at)`, then save time and ID;
unknown observation times are explicitly labelled and cannot establish eligibility.

Comparisons use the last two records of the requested leaf/site series. They never
skip an ineligible newest record to produce a favorable older comparison. Guards
reject too few records, unspecified reference, different plants, mock values,
missing/invalid severity, unknown/equal/reversed observation times, reused or
unidentified image evidence, differing disease context, measurement provenance,
or model versions. A user-entered reference alone does not prove comparability.

There is **no approved severity policy configured in the API** and no request field
can enable one. Consequently, current real endpoints return only `unavailable` or
`insufficient_data`, with null delta and policy version. Record-only observations
normally lack severity; the classifier prepared in Phase 4A also lacks a severity
head. Confidence, disease labels, healthy labels, and environment are never used
as severity proxies or recovery evidence.

The pure comparison module has a future explicit-policy interface. It compares
latest minus previous severity against a policy tolerance only after eligibility
checks. Direction labels and tolerance boundaries are tested using clearly named
mathematical fixtures, not scientific thresholds or real measurements. No tolerance
ships as a production default. Enabling real progression needs separately validated
measurement data and comparison policy, beyond Phase 4B disease classification.

### 5. Frontend and history

The existing screen structure and styling remain. Users can create a named physical
plant, optionally specify its crop, validate a photo, enter context/notes/time/leaf
reference, and save without analysis. The result/history explicitly show disease
not assessed, confidence unavailable, and severity not measured. Stored demo values
remain labelled synthetic and never become a real health comparison.

History is newest-first; the dashboard presents chronological records and the
server's comparison availability, replacing the unsupported first-to-latest severity
subtraction. Missing severity is never rendered as zero. Stored observation/save
times are distinguished, and exact-image reuse is disclosed.

Pending saves retain their request ID. Inputs and plant switching are locked while
a save is uncertain. Users can check history, return to the pending form, retry with
the same ID, or discard the form after reviewing history. Discarding does not delete
a saved row. Drafts are memory-only and do not survive app restart; there is no
offline queue. A new submission after restart needs a history check. The legacy
analyzed-save endpoint retains its original non-idempotent behavior.

### 6. Validation and documentation

All automated backend data is stored under temporary test directories. TestClient
uses the established outside-sandbox workaround, with the default app's database
and upload environment paths also redirected to `/tmp/agrisense-phase5-check/`.
No real application server was launched against the user's database.

Final results:

- Backend: **89 passed, 2 warnings in 3.19s**.
- Model regressions: **109 passed in 5.41s**; model source remained unchanged after this run.
- Frontend contracts: **8 passed, 0 failed**, 642.052535 ms in the final run.
- TypeScript: `npm run typecheck` passed, exit 0.
- Final web export: passed, 215 modules, 410 KB JS bundle, Metro 669 ms; exported to
  `/tmp/agrisense-phase5-web-final`.
- Backend and model `pip check`: both `No broken requirements found`, exit 0.
- Git whitespace and untracked-file whitespace checks passed.
- Preservation hashes, unchanged model tree, absent checkpoints, unchanged HEAD and
  empty index checks passed.

Tests cover old/fresh/unknown/future migrations, preservation and rollback,
record-only predictor isolation, unavailable capability flags, null fields,
request replay/conflicts, parallel retries, plant isolation, chronological history,
image reuse, invalid fields/images, restart persistence, file collision protection,
write/insert failure cleanup, progression eligibility/policy boundaries, null-safe
UI labels, date validation, request identity and record-only API transport.

Full check execution ledger (including earlier passes and diagnostics):

1. `git status`, baseline refs/source inspection: clean Phase 4A baseline.
2. `PYTHONDONTWRITEBYTECODE=1 AGRISENSE_DB_PATH=/tmp/agrisense-phase5-check/app.db AGRISENSE_UPLOAD_DIR=/tmp/agrisense-phase5-check/uploads .venv/bin/python -m pytest -q -p no:cacheprovider`
   from `backend/`: initial **87 passed, 2 warnings in 3.43s**; after final provenance
   and rollback additions, **89 passed, 2 warnings in 3.19s**.
3. `PYTHONDONTWRITEBYTECODE=1 model/.venv/bin/python -m pytest model/tests -q -p no:cacheprovider`:
   **109 passed in 5.41s**. No training or evaluation CLI was run.
4. `npm run typecheck`: passed before and after the final frontend edits.
5. Initial `npm test` using Node's default subprocess isolation: exit 0, reported
   **one passing file-level test**. A repeat with `--test-reporter=spec` likewise
   reported one file; these were not counted as eight verified individual cases.
6. `node --experimental-strip-types tests/recordState.test.mjs`: direct execution
   confirmed **6 passed**, 16.817277 ms.
7. Diagnostic `node --experimental-strip-types --test --test-isolation=none --test-reporter=spec tests/recordState.test.mjs`:
   exit **9**, unsupported flag in installed Node 22. `node --help` identified the
   supported `--experimental-test-isolation=none` spelling; the script was corrected.
8. Corrected `npm test`: **6 passed** in 59.083616 ms; after adding API transport
   tests, final **8 passed** in 642.052535 ms. No unresolved test failure.
9. `CI=1 EXPO_OFFLINE=1 ./node_modules/.bin/expo export --platform web --output-dir /tmp/agrisense-phase5-web`:
   initial export passed, 215 modules, 410 KB bundle, Metro 7,238 ms.
   Same command with output `/tmp/agrisense-phase5-web-final`: final export passed.
10. `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m pip check` and
    `PYTHONDONTWRITEBYTECODE=1 model/.venv/bin/python -m pip check`: both passed.
11. Repeated `git diff --check`, source/metadata preservation checks, and final
    status/index/HEAD checks: passed.

Non-failing warnings: existing Starlette httpx TestClient and AnyIO BlockingPortal
deprecations; non-writable pip cache; Node's inferred ES module mode for the tested
TypeScript helper; Metro's FORCE_COLOR/NO_COLOR conflict. No packages were changed
to suppress warnings. There was no browser/native camera walkthrough, native build,
real checkpoint load, real inference, severity validation or evaluation run.

## Remaining gates

- Phase 4B: trained/evaluated tomato checkpoint and real inference verification.
- Subsequent explicit integration: scope checks, enabled capabilities/model workflow,
  checkpoint provenance and operational validation. Nothing auto-activates.
- Confidence calibration requires validation evidence; softmax is not accuracy.
- Severity measurement, a scientifically supported comparison tolerance, and real
  longitudinal health interpretation need separate data/method validation. A Phase
  4B class label or healthy prediction cannot replace them.
- Semantic plant/non-plant suitability and other crops need separately evaluated
  capabilities.
- Local file storage and SQLite are not one crash-atomic transaction: ordinary
  exceptions are cleaned up, but process/power loss can leave an orphan upload.
  No destructive cleanup process is introduced. Existing local-only deployment
  scope and absence of authentication are unchanged.

## Files changed for review

Modified:

- `README.md`
- `backend/app/database.py`
- `backend/app/main.py`
- `backend/app/prediction.py`
- `backend/tests/test_model_readiness.py`
- `frontend/App.tsx`
- `frontend/package.json`
- `frontend/src/api.ts`

Added:

- `PHASE5_READINESS.md`
- `backend/app/progression.py`
- `backend/app/records.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_observation_records.py`
- `backend/tests/test_progression.py`
- `frontend/src/recordState.ts`
- `frontend/tests/api.test.mjs`
- `frontend/tests/recordState.test.mjs`

Total: 17 files (8 modified, 9 added). No staging, commit, push, dataset work,
training, weights, CUDA environment, deployment or Phase 4B work occurred.
