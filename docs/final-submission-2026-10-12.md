# AgriSense: Plant Disease Detection and Health Monitoring Using Hybrid CNN-Transformer Architecture

Latest verification: **October 13, 2026**. Resumed from `e960871` on `main`.
The original October 12 verification used baseline `104ee584`.

Subsequent camera work is documented in the [phone-camera integration guide](phone-camera-integration.md).
It adds native capture handling and an explicit browser live camera; physical-device
and real browser camera testing remain unverified. Earlier bundle paths below
predate that feature; use Metro or the newer export identified in that guide.

**PARTIALLY READY.** The local real-model HTTP workflow, database persistence,
backup/restore, automated tests and frontend bundles pass. The complete browser
photo-picker → draft recovery → analysis → history workflow remains unverified
because Chrome previously denied automated file selection. No physical Android device was
used. Do not present these results as complete device verification or production
readiness. This report supersedes the October 11 readiness report for current status.

## October 13 resumption and current evidence

The initial index contained only `backend/delete_plant.py` and its tests. Both
were preserved, reviewed and committed unchanged as `0253b00` after focused tests.
No further application-code change was necessary. The previous integration commit
`e960871` was reviewed for plant retry identity, draft rejection/recovery and history
selection consistency; its regression tests pass. A fresh fetch confirmed
`origin/main` at `104ee58` before the resumption commits. Unrelated untracked
research files remain excluded from the submission commits.

Checks actually run on October 13:

| Check | Result | Scope |
| --- | --- | --- |
| Focused backend pytest | **45 passed**, 8.23 s | Deletion, backup, plant API/retries, real-serving contracts using test doubles; zero skipped |
| Model inference pytest | **24 passed**, 6.56 s | Existing inference contract; zero skipped; no training or dataset evaluation |
| Frontend suite | **59 passed** | Includes retry, history selection and rejected-draft regressions; zero skipped |
| TypeScript | PASS | `npm run typecheck` |
| Expo web, Android and iOS export | PASS | Fresh bundles at `/tmp/agrisense-submission-export-2026-10-13`; web embeds `http://localhost:8000`; native bundles are not APKs |
| Real-model HTTP smoke | PASS | Startup, health, plant replay/conflict, image upload/rejection, suitability, disease inference, record-only context, history/photos, unavailable trends and clean shutdown |
| Restart and isolated backup restore | PASS | Three observations/photos restored; source hashes unchanged; request identity preserved; missing-model restart retained record-only capability |
| Checkpoint identity | MATCH | SHA-256 below unchanged |
| Android prerequisites | STILL BLOCKED | Installed NDK is 28.2.13676358; React Native requires 27.1.12297006. Bundled Expo template rechecked: Gradle 9.3.1 required, only 9.1.0 cached |
| Whitespace/diff checks | PASS | Explicitly reviewed submission paths only |

The initial sandboxed backend pytest reached its 90-second timeout; the smoke
preflight confirmed socketpair `EPERM`. Approved execution with local sockets
passed without changing application code or weakening startup checks.

**Not rerun:** full backend/model suites (October 12 results below remain historical),
the already verified 1,003-record load run, native prebuild, dependency audits,
dependency installation, browser interaction and held-out model evaluation.
The former `/tmp` export/prebuild directories no longer existed; exports were
rebuilt once at the new path above. Temporary exports are not durable submission
artifacts: regenerate them with the command below after cleanup or reboot.
No Android APK build or physical-device test was performed.

**Essential remaining verification:** complete the real browser photo selection
and draft save/reload/restore/analysis/history walkthrough. The prior Chrome
file-access denial was not retried or bypassed. If college submission requires an
installable Android app, the missing build prerequisites and physical-device
camera/gallery/lifecycle verification remain blockers. For a local browser/API
demonstration, Android packaging is not required. Existing dependency advisories
and absent public access controls remain outside the trusted local-demo scope;
this work does not authorize public deployment or claim production readiness.

## October 12 completed work (preserved)

- Plant creation now accepts an optional request identity. Identical retries return
  the original plant (200), changed-content retries return 409, and new plants return
  201. The frontend locks an uncertain plant form and retries its original details;
  refreshing before retry no longer duplicates the plant in the displayed list.
  Distinct plants may legitimately have the same name. No database migration was needed.
- Fixed navigation that could display another plant's history under the selected
  plant name when draft protection prevented selection, including rapid consecutive
  history taps during an in-flight request.
- Fixed a stale browser recovery identity after definitive image/suitability
  rejection. It is removed before a new submission is unlocked; storage failure
  retains the recovery boundary and reports an actionable error. Preview rejection
  never clears an earlier uncertain save identity.
- Settings now shows actual tomato-model availability and correctly describes
  browser recovery versus native session-only drafts. Notes accept 2,000 characters
  to match the API. Scores display at most one decimal without changing stored
  values or the uncalibrated disclosure. Existing colors, typography, navigation and 48-pixel buttons remain.
- Added protected operator deletion: dry-run by default, exact-name confirmation,
  complete backup before deletion, concurrency refusal, transactional journal-row
  deletion and retained photo files. No live user data was deleted.
- Updated setup, demo, troubleshooting, Android and data-management instructions.
  The full project title is preserved in this report, README and API documentation.

## October 12 verification results (not all rerun)

| Check | Status | Evidence and limit |
| --- | --- | --- |
| Backend pytest | PASS | **154 passed**, zero skipped; includes migrations, image limits, input validation, crop restrictions, retry/conflict handling, backups and deletion refusal/recovery |
| Model pytest | PASS | **118 passed**, zero skipped; no retraining or new accuracy evaluation |
| Frontend tests | PASS | **59 passed**, zero skipped; transport, rendered components, draft-storage doubles and hook regression tests |
| TypeScript | PASS | `npm run typecheck` |
| Expo web, Android and iOS export | PASS | Final bundles in `/tmp/agrisense-submission-export-final`; these are not installable native apps |
| Android prebuild | PASS | Isolated `/tmp/agrisense-android-submission`, existing bundled template, `--no-install`; no repository native project or dependency changes |
| Android APK build | SKIPPED | Required Gradle 9.3.1 distribution and NDK 27.1.12297006 are absent; see Android section |
| Real backend startup, health and shutdown | PASS | Real checkpoint and local OpenCLIP weights; CPU, one worker; clean bounded shutdown |
| Real-model HTTP smoke/integration | PASS | Actual multipart upload, technical rejection, logo rejection, disease inference, optional fields, exact retry, 409 conflict, image retrieval, history and unavailable trends |
| Plant creation retries over HTTP | PASS | Same response/ID on replay; conflicting crop rejected; only one plant persisted |
| SQLite restart persistence | PASS | Separate server process reopened disposable journal and preserved records |
| Bounded journal and isolated restore | PASS | **1,003 observations and 1,003 images**, manifest hashes, SQLite integrity/foreign keys, replay identity and unchanged source hashes |
| Missing-model fallback | PASS | Record-only remains available; analysis unavailable; no mock substitution |
| Browser frontend | PASS, limited | Exported app loaded; real API plant creation and reload verified; 390 × 844 viewport inspected; corrected Settings, persisted fixture photos/results/manual context, duplicate warning and unavailable dashboard trend checked; backend-stop error/Reconnect control verified |
| Browser complete photo upload and recovery | NOT TESTED | File chooser opened; Chrome `setFiles` denied with “Not allowed”; no extension permission changed |
| Physical Android camera/gallery/lifecycle | NOT TESTED | No physical device was used |
| Python dependency consistency | PASS | `pip check` in both existing virtual environments |
| npm vulnerability audit | FAIL | Fresh audit: **23 affected packages, 16 high / 7 moderate / 0 critical**; braces, node-forge and uuid dependency chains; suggested Expo 44 downgrade is incompatible and was not applied |
| Python vulnerability audit / fresh dependency installation | NOT TESTED | Existing environments reused; no large dependency installation |
| `git diff --check` | PASS | Reviewed source, tests and documentation only |

Final bounded HTTP run added 1,000 records in 4.633 s and retrieved 1,003 records
in 0.031 s (809,511 bytes). These are one sequential localhost fixture run, not
capacity or device-performance claims. Its observed classifier output was
`Bacterial_spot`, score `99.65035915374756`, severity `null`. That is integration
output, not an independent diagnosis or calibrated confidence.

Checkpoint SHA-256, rechecked October 13:
`18372991aaf467e5aea4c5d1f3c9b4c6e8a17ef3a6586758c4644572c4f43b9c`.
Weights, original datasets, private evaluation files and personal records were not
modified or added to Git. Initial restricted-sandbox socketpair/DNS failures were
rerun with approved access; no model or startup safety checks were bypassed.

## Startup on this workstation

Terminal 1, backend (ordinary local journal; use the disposable variation below
for demonstrations that should not write personal records):

```bash
cd /home/munaz/Projects/AgriSense
OMP_NUM_THREADS=4 model/.venv/bin/python -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Terminal 2, frontend:

```bash
cd /home/munaz/Projects/AgriSense/frontend
npm run web
```

Open `http://localhost:8081`; check `http://localhost:8000/health` and `/docs`.
For analysis, `capabilities.tomato_analysis` and `plant_content_screening` must
both be true. Backend defaults are `database/agrisense.db` and `backend/uploads/`.
The backend reads exported shell variables, not `.env`; Expo reads `frontend/.env`.

For a fresh checkout, install dependencies only into its own environments:

```bash
cd /path/to/AgriSense
python -m venv model/.venv
model/.venv/bin/python -m pip install -r backend/requirements-inference.txt
cd frontend
npm ci
# Only when .env does not already exist:
cp -n .env.example .env
```

Tested here: Python 3.14.7, Node 22.23.2, Expo 57.0.24, React Native 0.86.3,
Java 21; the pinned requirements and npm lockfile are authoritative. Python 3.11+
and Node 22.13+ are the documented minimums, but a fresh installation was not
retested today. A compatible PyTorch wheel and the two local model artifacts are
required for real analysis. Provision the tomato checkpoint privately at
`model/checkpoints/tomato_gpu_epoch5_retry2/best.pt` (or set
`AGRISENSE_CHECKPOINT_PATH`) and the existing OpenCLIP ViT-B/32 weights in the local
cache (or set `AGRISENSE_PLANT_VERIFIER_WEIGHTS`). Startup does not download weights.
A Git clone alone does not contain these files. The original dataset is not needed
for inference. Do not regenerate or retrain the model for the submission.

Disposable demo backend, instead of Terminal 1 above:

```bash
cd /home/munaz/Projects/AgriSense
DEMO_DIR=$(mktemp -d /tmp/agrisense-college-demo-XXXXXX)
export AGRISENSE_DB_PATH="$DEMO_DIR/journal.db"
export AGRISENSE_UPLOAD_DIR="$DEMO_DIR/uploads"
OMP_NUM_THREADS=4 model/.venv/bin/python -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Keep that directory path if restarting the demo. `/tmp` is temporary, not backup
storage. To show the already exported browser bundle without Metro:

```bash
cd /home/munaz/Projects/AgriSense
model/.venv/bin/python -m http.server 8081 --bind 127.0.0.1 \
  --directory /tmp/agrisense-submission-export-2026-10-13
```

If this temporary directory is missing, recreate it first:

```bash
cd /home/munaz/Projects/AgriSense/frontend
CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform all \
  --output-dir /tmp/agrisense-submission-export-2026-10-13
```

Choose either Metro or the static server on port 8081, not both. The exported
bundle embeds `http://localhost:8000`; rebuild it if the API address changes.

## Android build and device verification

**No APK was produced.** Java 21, Android SDK platforms 35/36 and build tools
35/36/37 exist. The existing Expo template generates a Gradle **9.3.1** wrapper;
only **9.1.0** is cached. React Native requests NDK **27.1.12297006**;
only **28.2.13676358** is installed. No large toolchain download, EAS build,
production signing configuration or Play Store publishing was attempted.
The temporary prebuild used `org.agrisense.localdemo` solely for prerequisite
inspection; it does not establish a release application identity.

Safest current alternative: use an **Expo Go version compatible with SDK 57**.
Set `frontend/.env` to `EXPO_PUBLIC_API_URL=http://COMPUTER_LAN_IP:8000`, restart
Expo with `npm start`, and scan its QR code. Start the backend with `--host 0.0.0.0`
only on a trusted private LAN. Both devices must be on that LAN. Phone `localhost`
is the phone; Android emulator host access is `http://10.0.2.2:8000`.
For a browser reached through a LAN IP, set `AGRISENSE_CORS_ORIGINS` to its exact
origin, e.g. `http://192.168.1.10:8081`. There is no authentication or IoT integration.

Physical-device checklist, all still **NOT TESTED**:

- Camera/gallery permission grant, deny and revoke; picker cancellation; orientation.
- Real photo → validation/suitability → tomato analysis → saved result → history.
- Record-only save with blank fields; separate temperature/humidity/soil entries,
  humidity 0/100, invalid values, long notes and keyboard scrolling.
- Repeated observations, image previews, timezone display and persistence after restart.
- Network loss during save, rapid taps, timeout, history check and same-ID retry.
- App background/foreground and process termination; native drafts are not durable.
- Small screens, large text, screen reader, touch targets and Android back behavior.

## Private export and protected deletion

Stop writes before operator maintenance. Use an existing private directory outside
this repository for backups. Archives include notes and photos, are mode 0600,
and are **not encrypted**. Never include them in a public college/GitHub package.

```bash
cd /home/munaz/Projects/AgriSense
model/.venv/bin/python -m backend.backup \
  --database /absolute/path/to/journal.db --uploads /absolute/path/to/uploads \
  --output /private/existing-directory/agrisense-backup-001.zip

# Preview only: replace PLANT_UUID with the actual plant ID from GET /plants.
model/.venv/bin/python -m backend.delete_plant \
  --database /absolute/path/to/journal.db --uploads /absolute/path/to/uploads \
  --plant-id PLANT_UUID

# Only after reviewing the preview; exact plant name and fresh backup are required.
model/.venv/bin/python -m backend.delete_plant \
  --database /absolute/path/to/journal.db --uploads /absolute/path/to/uploads \
  --plant-id PLANT_UUID --apply --confirm-name 'Exact plant name' \
  --backup /private/existing-directory/before-plant-removal-001.zip
```

Deletion removes that plant and its observation rows transactionally. Other plants
are preserved. Missing/corrupt photos, wrong names, existing backup destinations,
unknown plants and journal changes during backup cause refusal. Photo files remain
in the original upload directory and backup; this command is **not secure erasure**.
There is no in-app delete button, individual-observation deletion, automatic
retention policy or photo garbage collection.

Restore remains an operator procedure: keep the live journal untouched; verify
all `manifest.json` SHA-256 entries; reconstruct `journal.sqlite` and `uploads/`
in a **new private directory**; run SQLite integrity and foreign-key checks;
start a test backend pointed at that copy; compare plants/history/photos before
switching any real service. Do not merge or overwrite the live database. The smoke
harness verifies restoration of its own generated archive, not arbitrary archives.

## Reproduce the checks

Run from the repository root in a terminal permitting loopback/socketpair traffic:

Focused checks used for the October 13 resumption:

```bash
cd /home/munaz/Projects/AgriSense
(cd backend && timeout 90s env OMP_NUM_THREADS=4 ../model/.venv/bin/python -m pytest -q -rs \
  tests/test_delete_plant.py tests/test_backup.py tests/test_api.py tests/test_real_integration.py)
timeout 60s env OMP_NUM_THREADS=4 model/.venv/bin/python -m pytest model/tests/test_inference.py -q -rs
npm --prefix frontend test
npm --prefix frontend run typecheck
timeout 180s model/.venv/bin/python -u -m backend.smoke_local --real-model --startup-timeout 60
git diff --check
```

Full historical checks, available when broader changes justify rerunning them:

```bash
cd /home/munaz/Projects/AgriSense
(cd backend && timeout 120s env OMP_NUM_THREADS=4 ../model/.venv/bin/python -m pytest -q -rs)
timeout 120s env OMP_NUM_THREADS=4 model/.venv/bin/python -m pytest model/tests -q -rs
npm --prefix frontend test
npm --prefix frontend run typecheck
(cd frontend && CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform all --output-dir /tmp/agrisense-new-export)
timeout 180s model/.venv/bin/python -u -m backend.smoke_local \
  --real-model --startup-timeout 60 --extra-records 1000
git diff --check
```

Smoke/test storage is disposable. The smoke additionally restarts with intentionally
missing weights, and serves the restored journal in another process. No request
uses production records. For audit details run `npm audit` from `frontend`;
its nonzero exit currently reflects the documented vulnerabilities.

## Demo and college handoff

1. Keep the exact project title above in the report, slides and repository.
2. Start a disposable demo backend and frontend; check health before presenting.
3. Create one tomato plant. Select the committed fixture
   `backend/tests/fixtures/tomato_leaf_bacterial_spot.jpg` for a reproducible software
   demonstration, clearly identifying it as a test fixture, or use a permitted
   real tomato leaf photo without claiming a verified diagnosis.
4. Check the file and plant suitability, then analyze and save. Show disease class,
   **uncalibrated model score**, and **severity unavailable**. Reopen history.
5. Add a record-only observation with soil condition and optional environmental
   context. Reload and show both observations; explain why health trend measurement
   remains unavailable. Potato/pepper support is record-only, not disease analysis.
6. Show the real test results, backup/export command and this limitations checklist.
7. Before claiming the complete browser workflow passes, manually finish photo
   selection and browser draft save → reload → restore → revalidate → save.
   Automated Chrome upload requires enabling the ChatGPT extension's **Allow access
   to file URLs** setting; no such permission was changed during this session.
8. Submit the reviewed GitHub commit plus README and this runbook. Use only approved
   demo images/data. Supply checkpoints privately only if college requirements and
   their provenance/licensing permit it; never stage weights, `.aws`, credentials,
   research review files, datasets or personal journals. Do not zip the whole workspace.
9. Use browser/Expo Go for the demo; do not describe exported Android JavaScript as
   an APK. Record physical-device evidence separately if required by the college.

## Troubleshooting and remaining limits

- **Cannot reach backend:** check `/health`, API host/port, server terminal and LAN;
  use Reconnect/Refresh. Restart Expo after changing `.env`. Check port conflicts.
- **Startup hangs only in restricted automation:** the sandbox can block asyncio
  socketpair wakeups. Use an approved local terminal; retain model/lifespan checks.
- **Analysis unavailable:** confirm local checkpoint and verifier weights/dependencies,
  then restart the backend. Record-only remains usable. Never substitute mock results.
- **Rejected/uncertain image:** choose a supported still image, 224–8192 pixels per
  side, at most 24 MP and 10 MiB. Use a clear leaf close-up. Technical acceptance
  does not establish plant or tomato identity; screening can be wrong.
- **Timeout:** keep the pending form, check history/list, retry its same request.
  Browser observation recovery survives reload; native recovery and plant-form
  retry identity do not. Do not create a new request until checking saved records.
- **Recovery storage unavailable:** free browser storage/close other AgriSense tabs;
  restore or explicitly discard the recovery copy. Draft storage is not a backup.
- **No severity or health trend:** expected. The model classifies 11 tomato classes;
  it does not measure lesion area or validated progression. Environmental values
  are manual context and are never inference inputs. Scores are uncalibrated.
- **Model validity:** existing curated holdout metrics are historical, not field
  validation or newly verified accuracy. Source/duplicate review remains separate.
- **Security boundary:** trusted local single-user demo only. No public authentication,
  TLS, encryption-at-rest or multi-user separation. Photos can retain EXIF metadata.
  npm advisories remain; Python vulnerabilities and public deployment were not audited.
- **Scale:** sequential backend journal check only; large-history rendering,
  multi-user concurrency and native performance are not established.
