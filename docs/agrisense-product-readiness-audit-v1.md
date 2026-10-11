# AgriSense product readiness audit (v1)

**Audit date:** 2026-10-11

**Scope:** Repository code, README, existing automated tests, and local web export. No application code, model, weights, original dataset, or external evaluation data were changed.

## Architecture reviewed

- **Frontend:** Expo / React Native / TypeScript. `frontend/App.tsx` composes the journal screens; `frontend/src/hooks/useJournal.ts` owns the current session state; `frontend/src/api.ts` sends JSON and multipart requests.
- **Backend:** FastAPI in `backend/app/main.py`, technical image validation in `image_validation.py`, separate CLIP-based suitability screening in `plant_suitability.py`, closed-set model adapter in `prediction.py`, SQLite migrations in `database.py`, and atomic record/image persistence in `records.py`.
- **Model:** Existing 11-class tomato checkpoint and preprocessing in `model/agrisense_model/`. The app loads a real checkpoint when available; failures disable analysis instead of substituting a mock. The classifier does not determine crop identity.
- **Persistence:** Local SQLite records plus image files in the backend upload directory. This is a local, single-service arrangement, not a multi-user account system.

## What works today

| Area | Observed implementation and evidence | Current limit |
|---|---|---|
| Photo capture and selection | Expo ImagePicker paths exist for camera capture (with permission request) and photo-library selection. The scan screen previews a selection. UI tests cover selection and capture behavior. | Browser camera behavior depends on the browser. No physical iOS/Android device test was run in this audit. |
| File and plant checks | Backend validates JPEG/PNG/WebP bytes, size, dimensions, animation, and decodability; the separate suitability route can reject clear unrelated content or abstain. Both prediction and save routes recheck inputs. | File validation is not plant detection. Suitability is a zero-shot CLIP check without a measured accuracy claim and can make mistakes. |
| Tomato analysis | The tomato flow requires a user-declared tomato crop, calls suitability screening and then the ordered 11-class model, and persists completed output. Missing model or screening readiness disables analysis. | The model is closed-set and cannot establish tomato identity. Scores are uncalibrated; the saved severity remains null. This is experimental output, not a validated diagnosis. |
| Uncertainty and unsupported content | UI separates technical validation, suitability, and disease analysis. It explains that tomato identity is not verified, labels real predictions experimental, identifies scores as uncalibrated, and avoids fabricating severity. Conditional treatment guidance is source-linked and carries regional/diagnostic limitations. | No external clinical/agronomic validation was performed. Guidance is not a substitute for diagnosis. |
| Plant records and repeated observations | Users can create plant records, select a physical plant, save a photo with environmental context and notes, and revisit chronological history. SQLite persists records; image writes are rolled back on failed record insertion. Same-request retries are idempotent for record-only and analyzed saves. | Record-only saving requires temperature, humidity, soil type, and soil condition; analysis permits those fields to be absent. Health progression is unavailable because no validated severity measurement/policy is configured. Drafts exist only in frontend memory and do not survive app restart. No edit/delete/export workflow was found. |
| Loading, empty, errors, and offline | The shell shows a busy indicator, error messages, reconnect/refresh actions, and empty states. API calls have a 30-second timeout; ambiguous save retries reuse the pending request ID. | Offline use is not supported: no local journal cache or persistent upload queue exists. Drafts are lost on restart. API availability is shown as unavailable rather than serving stale local history. |
| Responsive UI | Screens share a visual theme, safe-area shell, scrollable content, touch-sized controls, accessibility labels/roles for key controls, and a centered maximum-width layout. Web export succeeds. | Native camera, small-screen keyboard behavior, assistive technology, and accessibility contrast/zoom were not device-tested. The current UI is a single-user journal interface, not a deployment-ready design system. |
| Data privacy and API | Request validation, bounded image decoding, SQLite constraints/migrations, foreign keys, stable request IDs, and generic inference errors are implemented. Local records survive backend restarts. | No authentication or per-user authorization exists. Uploaded files are served from a static `/uploads` mount. CORS is not access control. No TLS termination, encryption/retention policy, account isolation, deletion/export, backup/restore, rate limiting, or production observability is implemented in the reviewed app. Do not expose this local service as a public multi-user service. |
| Deployment | README documents local setup and says the app is not deployed. The web bundle builds locally. No tracked Docker, orchestration, hosting, or CI deployment configuration was found. | A web export is not a deployment. Production hosting, TLS, secrets/configuration, migrations/backups, monitoring, recovery, and native release builds remain unverified. |

## Experimental and research status

- The model’s README-reported held-out metrics are curated-dataset results, not field validation. This audit did not rerun that evaluation or verify the checkpoint’s performance.
- No independent human expert review, labels, or field study were conducted for this audit. The formal independent evaluation protocol remains unchanged; its reviewer and adjudicator requirements are not marked satisfied.
- The four existing external candidates and `labels.csv` were not altered or approved. Their external status remains separate from this repository documentation.
- The AI-assisted exploratory track is described separately in `agrisense-ai-assisted-exploratory-evaluation-track-v1.md`; AI assessments remain provisional and must not be represented as human ground truth.

## Verification run

| Check | Result |
|---|---|
| Frontend Node tests | 45 passed, 0 failed. Node emitted a module-type performance warning for `recordState.ts`. |
| Frontend TypeScript | `npm run typecheck` passed. |
| Frontend web export | `CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform web --output-dir /tmp/agrisense-readiness-web` succeeded. This only verifies bundling. |
| Backend tests (`backend/.venv`) | 111 passed, 5 skipped. The skipped pretrained suitability/model cases could not import PyTorch/OpenCLIP in this lightweight environment. Two Starlette/httpx deprecation warnings were emitted. |
| Model tests (`model/.venv`) | 118 passed. |
| Combined model-environment backend test attempt | Did not complete and was interrupted after it remained silent; it emitted virtual-environment prefix warnings. No conclusion about this invocation’s real-model integration cases is claimed. |

The tests exercise software contracts and test doubles; they do not constitute a production deployment test or expert validation. Native device flows and an end-to-end production service remain untested.

## Prioritized implementation roadmap

### P0 — Let users save an honest record when measurements are unknown

Record-only saving currently requires temperature, humidity, soil type, and soil condition. Permit each field to be unknown and persist it as null instead of prompting users to guess. Keep validation for values they do provide. Make the UI state clearly that these measurements are optional context; none is a model input.

Likely files: `backend/app/main.py` (record endpoint form defaults), `frontend/src/recordState.ts` (record blockers), `frontend/src/screens/ScanScreen.tsx` (optional labels/help), and the existing backend/frontend record tests.

Required tests: submit a record-only photo with all four context values omitted and confirm all are null in the response and after reload; verify each field can independently remain unknown; verify supplied values still enforce range/type validation; ensure tomato analysis retains its current optional-context behavior and no environmental value is fabricated.

### P1 — Make the observation workflow resumable after connectivity loss

Implement a resumable draft queue for the camera/gallery → validation → record-only save or explicit tomato analysis → history workflow. Stage selected media in app-private storage, persist the exact form and request ID, surface queued/sending/saved/failed states, and resume/retry only the same payload after restart or reconnection. Do not imply that a local queued item was saved on the server. Define local data retention and user-controlled discard before persisting photos.

Likely files: `frontend/src/hooks/useJournal.ts`, `frontend/src/api.ts`, `frontend/src/screens/ScanScreen.tsx`, a new `frontend/src/storage/observationDraftStore.ts`, `frontend/tests/useJournal.test.mjs`, and `frontend/tests/api.test.mjs`; add only the platform storage dependency selected for the implementation.

Required tests: draft serialization/restoration; staged-photo availability after app restart; offline queue and reconnect; same request ID/payload on timeout and retry; no duplicate server row after a response is lost; explicit discard; validation/suitability failures do not enter the queue; no display of “saved” until server confirmation. Add device smoke coverage for camera/gallery permission and app background/relaunch on iOS and Android plus web refresh/reconnect.

### P0 release gate — Protect real user data before remote or multi-user launch

Add authenticated identity and ownership checks for plants, records, and uploaded images; protect uploads instead of exposing a public static directory; require HTTPS at the serving boundary; define backup/restore, retention, deletion/export, and operational access policies. CORS configuration alone does not provide these controls. This is a deployment blocker even if local single-user development continues.

### P1 — Make service readiness and operations dependable

Separate liveness from model/screening readiness in API responses; document a supported server topology; bound upload parsing and inference resource use; add structured request correlation and safe operational logs; verify database backup/restore and migration recovery. Current guidance requires one worker for in-process inference serialization.

### P1 — Complete cross-device and accessibility QA

Test real camera permissions/capture, browser and native pickers, keyboard visibility, large text/zoom, screen-reader labels, image failures, slow networks, app backgrounding, and small/large screen layouts. Add end-to-end automation for the complete capture-to-history path where stable.

### P2 — Improve model evidence separately from product engineering

Use the AI-assisted exploratory track only for provisional failure discovery. Any research/performance claim still requires the unchanged formal protocol, real reviewer agreements, a qualified adjudicator, source/overlap controls, frozen human labels, and appropriately separated test data. Do not infer model calibration, severity, tomato identity, or field performance from current outputs.

## Immediate next feature

Start with **optional environmental context for record-only observations**. The current form can pressure a user to enter values they do not know; the database already supports nullable context, so the workflow should preserve “unknown” without weakening validation for supplied measurements. Then add resumable drafts and offline recovery before expanding model behavior.
