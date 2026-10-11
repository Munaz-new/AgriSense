# Phases 7B–7E: local application readiness

Audit date: 2026-10-11. Baseline: `5386401`. Scope: one local user, existing tomato
checkpoint, temporary test databases/photos only. No research data, checkpoint,
independent evaluation candidates, reviewer decisions or formal protocol changed.
These are software integration checks, not agricultural validation or ground truth.

| Phase | Status | Remaining boundary |
| --- | --- | --- |
| 7B — integration | PARTIAL | Live API verified; physical camera/gallery and complete browser upload blocked |
| 7C — reliability | PARTIAL | Retry protection and browser recovery implemented; native durable recovery/device lifecycle pending |
| 7D — data/security | PARTIAL | Request protections and backup/export verified; dependency findings and deletion/retention controls remain |
| 7E — release preparation | COMPLETED | Local runbook, bundle checks and device checklist delivered; public release not approved |

Implementation commits: `948865a` (backend), `8614cf8` (frontend reliability),
`4823f7d` (two targeted dependency updates). Documentation is versioned separately.

## Startup diagnosis and resolution

The observed indefinite “Waiting for application startup” was reproduced under
bounded timeouts. A minimal Starlette `run_in_threadpool` call stalled without any
AgriSense imports, database or model. Stack dumps showed the event loop in epoll
and its worker waiting for work. Direct socketpair writes failed with `EPERM`;
asyncio debug logging showed its `_write_to_self` wakeup failing for the same
reason. The sandbox blocked the completion notification from the worker thread.
The same bounded minimal program outside that restriction completed immediately,
including clean asyncio shutdown. This distinguishes the failure from SQLite,
checkpoint corruption, a download wait, missing dependencies or OpenCLIP loading.

Resolution: run the local service/tests in an approved environment that permits
loopback/socketpair traffic. Do not remove the lifespan, move inference onto the
event loop, substitute mock results, or claim readiness before loading completes.
New startup logs identify database, tomato checkpoint and plant-suitability stages,
duration, and failure **type**, without exception payloads or configured paths.
The smoke harness checks socketpair access first and fails with an actionable error.

Final real-service timings: database 0.001 s, checkpoint 1.361 s, suitability
3.434 s. Earlier cold suitability loading took 7.721 s; these are observations,
not latency guarantees. Health returned HTTP 200 with analysis available. A second
process with intentionally absent weights returned record-only availability and
analysis unavailable. Both processes shut down cleanly. All weights were local;
startup neither downloaded nor replaced them.

## Environment and reproducible commands

Existing `model/.venv` was used: Python 3.14.7, torch 2.14.0+cu126,
torchvision 0.29.0+cu126, numpy 2.5.2, Pillow 12.3.0, open_clip_torch 2.32.0,
FastAPI 0.135.1 and uvicorn 0.41.0. CUDA was unavailable; serving used CPU.
`backend/.venv` has the API/Pillow stack but lacks the model dependencies.
No Python packages or model weights were installed. Both environments passed
`python -m pip check`; this checks dependency consistency, not vulnerabilities.

From the repository root (use a normal terminal permitting local sockets):

```bash
# Real HTTP requests, existing checkpoint, disposable SQLite/uploads, restart check.
timeout 180s model/.venv/bin/python -u -m backend.smoke_local --real-model --startup-timeout 60
# Omit --real-model to deliberately test missing-model record-only availability.
cd backend
timeout 180s env OMP_NUM_THREADS=4 ../model/.venv/bin/python -m pytest -q -rs
cd ..
timeout 180s env OMP_NUM_THREADS=4 model/.venv/bin/python -m pytest model/tests -q -rs
cd frontend
npm test
npm run typecheck
CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform all --output-dir /tmp/agrisense-release-check
```

The checkpoint remains `model/checkpoints/tomato_gpu_epoch5_retry2/best.pt`, SHA-256
`18372991aaf467e5aea4c5d1f3c9b4c6e8a17ef3a6586758c4644572c4f43b9c`.
Do not copy private runtime data or weights into Git. For ordinary startup use the
README. Defaults use SQLite `database/agrisense.db` and `backend/uploads/`;
test harnesses override both. Environment variables must be exported for the
backend; it does not load `.env`. Expo's public API URL is bundled at build time;
it contains no credentials. Phone localhost is not the development computer.

## Integration evidence

| Workflow | Result | Evidence / boundary |
| --- | --- | --- |
| Actual startup and health | PASS | Real uvicorn, local CPU model/verifier, HTTP health, bounded shutdown |
| Frontend/API connectivity | PASS | Chrome exported app created a temporary plant and reloaded it |
| Multipart image upload | PASS | Real HTTP fixture upload, stored image retrieval, corruption rejection |
| Browser photo picker | NOT TESTED end to end | Chooser opened; extension denied setting the fixture file |
| Physical camera / Android gallery | NOT TESTED | No physical device used |
| Suitability and unsupported content | PASS for fixtures | Actual verifier accepted committed leaf and rejected committed logo; API regression rejection cases passed |
| Existing disease checkpoint | PASS integration only | Real analysis stored checkpoint hash, experimental uncalibrated score, null severity; exact retry returned same row |
| Plant records and repeated observations | PASS | Real HTTP creation, ordered history, duplicate-photo flags, stable retry IDs, conflicting replay 409 |
| Optional environmental context | PASS | Blank fields remained null; 21.5 °C / 0% / Sandy loam persisted; invalid humidity 422; restart preserved values |
| Health trend honesty | PASS | Unavailable comparison reported; no score converted to severity or trend |
| Loading, errors, retry | PASS within tested scope | Hook/transport regression checks plus actual Chrome backend-stop error and Reconnect button |
| Browser draft storage/recovery | PASS automated contracts; NOT TESTED actual browser reload | Blob/identity storage double and hook tests; browser upload restriction blocked complete walkthrough |
| Responsive UI | PASS limited inspection | Chrome home/history at 390 × 844, readable controls/navigation; not a phone or exhaustive accessibility test |
| Backup/export integrity | PASS automated | Temporary SQLite snapshot, images and inventory hashes, null fields, permissions, refusal cases |

Actual smoke fixture output was `Bacterial_spot`, score `99.65035915374756`,
severity null. This is an observed output for a committed integration fixture,
not independent diagnosis, calibrated confidence or new accuracy evidence.

Final suites: backend **140 passed**, model **118 passed**, frontend **52 passed**,
zero skipped in these runs. TypeScript passed. Web, Android and iOS Expo exports
passed. Exports produce bundles, not signed installable applications. Non-failing
warnings: Node typeless test-module detection, bundler color environment conflict,
pip cache unwritable. Offline Expo dependency compatibility check reported up to
date but explicitly warned that offline validation is unreliable. Fresh install,
Python vulnerability audit, native builds, device lifecycle/performance and
large-journal load tests were not performed.

Chrome file-upload continuation requires enabling **Allow access to file URLs**
in the ChatGPT extension details (`chrome://extensions`). Then rerun the full
photo → validation → context → save → reopen → history workflow and browser draft
recovery. No browser file-access setting was changed by this work.

## Reliability changes (7C)

- A synchronous action guard prevents two taps before React renders from starting
  duplicate operations. Server request identity/replay protection is preserved.
- Browser photo reads have a 15-second bound; existing API requests use 30 seconds.
  Errors never become healthy labels or successful saves.
- Browser IndexedDB stores exact photo bytes, form strings and pending request ID
  before save transmission. A confirmed save removes the recovery copy. On
  recovery, history is checked first; an already-saved ID opens its result without
  resubmission. Uncertain submissions keep the same ID and mode and require fresh
  photo checks. Storage failures prevent transmission. Different pending IDs
  cannot overwrite one another within the storage transaction.
- Explicit draft saving is available before submission. Use one browser tab; this
  is not a cross-tab collaborative editor. Photos/notes remain private browser
  data until removed; browser clearing/eviction can remove the copy. Recovery is
  scoped to API URL, not a backup or an offline synchronization queue.
- Native restart recovery needs a durable native photo/storage adapter and device
  testing. No untested storage dependency was added. Keep uncertain native forms
  open, check history and retry with their existing ID.

## Data and security (7D)

Confirmed improvements: total request body capped at 10 MiB + 128 KiB multipart
allowance before unlimited spooling, including streamed requests; exact configured
browser origins required for writes; no-store and nosniff response headers;
sensitive exception text/path removed from startup and screening logs. Existing
technical decoding/size limits, parameterized SQLite operations, migration
preservation, foreign keys and idempotent observation commits remain intact.

This is **not authentication**. Requests without Origin (native/CLI) remain valid.
Any caller who can access the service can read/write its single-user records.
Bind loopback for desktop use; expose only to a trusted LAN for phone testing.
Keep access logs disabled for ordinary local use. No public deployment, users,
authorization model, TLS provisioning, or encryption-at-rest was added. Original
uploaded photo bytes may retain EXIF/location metadata. OS account permissions,
private storage and disk encryption remain the owner's responsibility.

### Private backup and export

From the repository root, choose a new destination outside the repository and
uploads (the destination parent must exist). Stop writes for the simplest operator
workflow; the command itself also uses a consistent committed SQLite snapshot.

```bash
model/.venv/bin/python -m backend.backup \
  --database /absolute/path/to/journal.db \
  --uploads /absolute/path/to/uploads \
  --output /private/backup/location/agrisense-backup-001.zip
```

The source is opened read-only. Schema 3, SQLite integrity/foreign keys, referenced
photo paths and stored photo hashes are checked. Missing photos, symlinks, unsafe
paths, corrupt hashes or existing destinations cause refusal. Legacy missing photo
hashes are calculated without updating their records. Output contains SQLite,
JSON records, referenced photos and a SHA-256 inventory. Destination creation is
exclusive with mode 0600. Failed creation removes only its own incomplete archive.
The archive is **unencrypted sensitive data**, including notes and photos; never
commit or share it publicly. There is no automatic backup schedule.

Restore is an operator workflow, not an implemented button/CLI: stop the service,
verify manifest hashes, extract into a **new isolated directory**, run SQLite
integrity/foreign-key checks, point test environment variables at that directory,
and verify counts/images/history before deciding to switch the real service.
Do not overwrite the live database or merge databases. Tests reconstructed an
isolated SQLite copy; no actual user backup/restore was performed. User-facing
selective deletion, retention policy, automated restore and secure erasure remain
unimplemented. No real records were deleted.

## Release boundary and Android checklist (7E)

### Dependency audit

`timeout 45s npm audit --json` reached the npm advisory service after sandbox DNS
denied the initial attempt. Initial result: 25 affected packages (1 critical,
17 high, 7 moderate). Targeted `npm update shell-quote source-map-js --ignore-scripts`
changed only those two lockfile entries: shell-quote 1.10.0 → 1.12.0 and
source-map-js 1.2.1 → 1.2.2. The update audit reports **23 affected packages:
0 critical, 16 high, 7 moderate**. No Expo/React Native version change or install
script execution occurred. These counts include inherited dependency-chain flags;
they do not establish that each advisory is exploitable through the app.

Remaining roots include `node-forge` (signature parsing), `braces` (pattern-parser
denial of service), and `uuid` (buffer bounds) in Expo/Metro/xcode dependencies.
The automatic suggested Expo 44 / React Native 0.72 downgrade is incompatible
with this SDK 57 app and was not applied. Do not run `npm audit fix --force`.
Dependency remediation requires upstream-compatible versions and a separate
compatibility review; public release remains blocked. The local bundler and API
must stay off public networks. No claim of a complete security audit is made.

Advisory references returned by npm:
[shell-quote](https://github.com/advisories/GHSA-pqg4-j6r4-53mv),
[source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q),
[node-forge](https://github.com/advisories/GHSA-86w9-cpqp-85rv),
[braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[uuid](https://github.com/advisories/GHSA-w5hq-g745-h8pq).

Additional executed checks: `model/.venv/bin/python -m pip check`,
`backend/.venv/bin/python -m pip check`, `CI=1 EXPO_OFFLINE=1 npx --no-install
expo install --check`, and `git diff --check`. All final source changes were
reviewed by explicit path; unrelated research files were not staged.

Current scope: local experimental app, not public production readiness. Dependency
advisories and device checks below remain release blockers. No publishing,
credentials, native package identity, signing configuration or app-store action
was undertaken. Existing formal independent research governance remains unchanged;
AI-assisted software checks satisfy none of its human reviewer requirements.

On a physical Android phone, record device/OS/Expo version, app commit, API URL,
checkpoint identity and observed results. Each checkbox starts **unchecked**:

- [ ] Trusted LAN connection, correct host/IP/port, health capabilities and reconnection.
- [ ] Camera permission grant/deny/revoke, gallery permission, picker cancellation.
- [ ] Actual camera/gallery image preview, orientation, cropped/large photos and HEIC behavior.
- [ ] Technical rejection of corrupt/unsupported files; logo/inconclusive screening,
      honest model-unavailable messaging and experimental analysis disclosures.
- [ ] Record-only save with all three optional fields absent, each independently
      supplied, humidity 0/100, invalid values, and keyboard-friendly form scrolling.
- [ ] Tomato analysis and saved checkpoint provenance; no inferred severity/health trend.
- [ ] Repeated same-leaf observations, timestamps/timezones, history/images after restart.
- [ ] Rapid taps, network loss during upload/save, timeout, history check and same-ID retry.
- [ ] Background/foreground, process termination, low memory and photo URI lifetime;
      native restart recovery is currently unavailable and must be communicated.
- [ ] Small screen/large text, screen reader labels, tap targets, safe areas and Android back behavior.
- [ ] Private backup/isolated restore walkthrough and explicit retention/deletion decision.

The next device-focused feature is durable native draft recovery, followed by a
physical-device end-to-end run. Public release additionally needs reviewed access
control/deployment design, dependency remediation and evidence appropriate to any
agricultural claims. Do not interpret test counts as approval for such claims.
