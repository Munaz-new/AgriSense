# Phase 4A — real model training preparation

**READY for training preparation and review. Real training is not authorized or
started.** The pipeline and synthetic control tests are ready; Windows installation,
dataset transfer/integrity, CUDA execution and GPU batch capacity still require
verification on the actual training machine before training approval.

## Repository and inspection

The previous session recorded starting on `main` with a clean working tree.
This continuation on 2026-09-26 recovered **six modified tracked files and four
untracked Phase 4A files**, with an empty index. Local `main` and the existing
`origin/main` tracking ref both point to Phase 3C commit
`94a9918cc85143466169c570db6b2c06002f95f0`; no remote query or fetch was needed.
The working tree was compared against that exact commit. No Phase 4A work was
discarded or restarted. No staging, commit, push or deployment occurred. The
Phase 3B/3C reports and all prior commits are preserved.

Recovered work includes optimizer configuration, deterministic epoch seeds,
read-only preflight, CLI overrides, best/last checkpoints, completed-epoch resume,
the Windows template, all 30 existing training-control tests, README changes and
this draft report. The continuation fixed one preflight gap: a regular file in an
output directory's ancestry now fails before dataset access, rather than passing
preflight and failing when outputs are created. Two synthetic regression cases
cover direct and nested output parents. No training behavior was redesigned.

Inspected README's Phase 3A preparation record, the ignored full Phase 3A audit and
active manifest, both Phase 3B/3C reports, tomato config, model architecture,
preprocessing, preparation/validation, loaders, epoch loop, checkpoint reader/writer,
training/evaluation/inference CLIs, model/backend tests, backend trained adapter,
and ignore rules. Phase 3A has a generated JSON audit and README record rather than
a separate versioned Phase 3A Markdown report.

## Architecture preserved

- Input: float32 RGB `[batch, 3, 224, 224]` with the configured defaults.
- CNN: three 3×3 convolution blocks, channels 3→32→64→128, each with GroupNorm,
  GELU and 2×2 max pooling; adaptive average pooling produces 128 features.
- Transformer: 16×16 patch embedding, 196 tokens at width 128, learned positional
  embeddings, two independent encoder layers, four heads each, feed-forward width
  512, GELU, dropout 0.1; LayerNorm and token mean pooling produce 128 features.
- Fusion: concatenate local/global vectors into 256 features.
- Classifier: Linear(256,128), GELU, dropout, Linear(128,11), returning logits
  `[batch,11]`. Cross-entropy uses integer labels. No pretrained downloads or severity
  head are introduced. Architecture and Phase 3C inference code are unchanged.

## Authoritative classes and the Powdery Mildew issue

The authoritative config (`model/configs/tomato.json` and `TOMATO_CLASSES`), existing
Phase 3A audit, and active manifest all agree on **11 ordered classes**:

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
10. `powdery_mildew`

This is ten disease categories plus healthy, not ten total classes. No mismatch
remains in the repository metadata. The audit records 1,004 source `train` and 252
source `valid` images for Powdery Mildew. A different Windows archive may omit this
class: do not assume it matches. Both source splits must contain exactly these
folder names, and config, manifest labels, model output and checkpoint mapping
must agree. Training now explicitly rejects ten-class or reordered tomato configs.

The active manifest equals the Phase 3A audit. Retained split sizes are 21,108 train,
6,614 validation and 3,719 test, from 32,535 source files. These are dataset counts,
not performance results. Inspection in this phase read metadata only, not original
dataset images. The new training preflight will verify bytes and decoded hashes
when explicitly run on the Windows machine.

The continuation rechecked all 31,441 retained entries against their label indices,
class directory names and source splits. Both versioned configs and the ignored
local config match `TOMATO_CLASSES` and the manifest. Manifest and audit file
SHA-256 are both
`3605fb12256d269cc1ba8c348f9f8a91d2308265523d9ea00dff5e83621290a6`.
The pipeline's canonical JSON manifest digest is
`44d46bb8e46fbd9dc5c90cafb636086a073e137c251f654d9d29251ab398a109`.
The manifest, audit, prior Phase 3B sanity report and local configuration retain
their pre-continuation SHA-256 hashes. These checks establish metadata consistency;
they do not substitute for Windows source-byte verification.

## Dataset structure and loaders

Keep the supplied source hierarchy unchanged, including files excluded by the audit:

```text
tomato-dataset/
  train/
    Bacterial_spot/
    Early_blight/
    ...all remaining exact class folders listed above...
    healthy/
    powdery_mildew/
  valid/
    ...the same 11 class folders...
```

No physical test directory is created for this source layout. The manifest's `train`
and `test` memberships reference source `train/`; logical `val` references source
`valid/`. Phase 3A preserves cleaned validation membership and holds out 15% of each
class's cleaned training images for test. Corrupt/conflicting/duplicate exclusions
remain unchanged. Training reads the manifest; it never silently prepares a new
split. Only train and val loaders are iterated; test is reserved for separate later
evaluation. Manifest validation reads held-out files for integrity, not evaluation.

Preprocessing remains shared with inference: EXIF orientation, RGB, bilinear resize,
division by 255, ImageNet channel mean/std. Training alone applies a 50% horizontal
flip, rotation within ±15°, brightness and contrast factors in [0.9,1.1]. Validation
and test are unaugmented. Loaders retain `num_workers=0` for simple Windows behavior;
training shuffles, validation does not, and the final partial batch is retained.

Copy the existing ignored `model/data/tomato_splits.json` and, for provenance,
`model/reports/tomato_phase3a_audit.json` separately from Git. Keep the manifest
unchanged, including its original source-root provenance field; only the local
config's `dataset_path` changes. Membership uses relative paths and the validator
uses the configured current root. Changing the manifest changes its digest.
If the original manifest is unavailable or the transferred data fails validation,
stop and resolve the transfer; do not quietly regenerate splits.

## Training and checkpoint behavior

Configuration includes dataset/output paths, epochs, batch size, seed, learning
rate, optimizer (`adamw` or `sgd`), weight decay, and SGD momentum. Existing configs
remain readable via defaults. Default values: 30 epochs, batch 16, seed 42,
AdamW at 0.0003 with weight decay 0.01. SGD momentum defaults to 0.9. Gradient
clipping remains 1.0. No scheduler, mixed precision or early stopping is introduced.

Python/NumPy/PyTorch are seeded; deterministic algorithms are requested, cuDNN
benchmarking is disabled, and cuDNN determinism enabled. Each epoch resets seed to
`(seed + epoch - 1) % 2**32` and reconstructs loader generators. This makes completed-
epoch resume use the same shuffle/augmentation/dropout sequence in the same
environment. CUDA setup defaults `CUBLAS_WORKSPACE_CONFIG` to `:4096:8` before
initialization, rejects unsupported explicit values, and fails if CUDA is unavailable.
There is no automatic CPU fallback. CPU is the default. Unsupported deterministic
operations fail rather than silently weakening the requested behavior.

Reproducibility across different platforms, releases, or CPU/GPU is not guaranteed;
record the environment and retain the same machine/software for a resumed run.
See [PyTorch reproducibility guidance](https://docs.pytorch.org/docs/2.14/notes/randomness.html).

Epoch output reports measured training loss, validation loss, validation accuracy
(fraction 0–1), cumulative optimizer steps, and elapsed time. History retains the
existing epoch metrics. No example performance values or research results are
provided in this report.

For the Windows example configuration, artifacts would be:

- `model/checkpoints/tomato_run_01/best.pt`: strictly lowest validation-loss model.
- `model/checkpoints/tomato_run_01/best.last.pt`: last fully completed epoch.
- `model/checkpoints/tomato_run_01/best.history.json`: measured epoch records.
- `model/checkpoints/tomato_run_01/best.run.json`: resolved config, manifest digest,
  package/runtime versions, device, output paths and resume provenance.

Checkpoint format remains **v2**, compatible with Phase 3C's guarded loader:
architecture identifier, crop/class digest, model state, config, preprocessing
version, completed epoch/step counts, validation loss and manifest digest.
Best checkpoints omit optimizer contents and are for inference/evaluation.
Last checkpoints add optimizer state and `training_state` version 1 containing
history, runtime, seed policy and the best model snapshot/epoch/steps/loss.
All artifacts and temporary writes are ignored. They do not exist as a result of
Phase 4A. Output paths inside the source dataset, existing output prefixes and
non-directory output ancestors fail. Read-only preflight does not prove filesystem
write permissions or available disk space; verify these on the training machine.

Resume requires a trusted Phase 4A **last** checkpoint, matching manifest, class
mapping, hyperparameters and recorded runtime. Only file locations and total target
epochs may change. Use a new output prefix; the original run is retained. Its best
model is recovered even if no new epoch improves. Partial epochs are repeated from
the last completed epoch; an interruption before the first last-checkpoint requires
a fresh run. Best/legacy checkpoints cannot resume. Files are individually replaced
atomically, not as a multi-file transaction; the last checkpoint carries authoritative
history/best state if JSON/history or best-file updates were interrupted.

## Windows prerequisites and exact next steps

These commands are **proposals, not executed**. Work from the repository root in
PowerShell. No Node/frontend/backend server is required for model training.

1. After approval, obtain the prepared source changes and transfer the existing
   dataset/ignored manifest/audit without altering source images or membership.
2. Install 64-bit Python with wheels compatible with the pinned model requirements.
   Local validation used Python 3.14.7; `py -3.14` below targets that minor version.
   CUDA additionally needs compatible NVIDIA hardware, driver and CUDA-enabled
   PyTorch. Verify available Windows wheels for the pinned Torch 2.14.0; do not
   silently change pins if unavailable. Consult the official
   [Windows/PyTorch installation selector](https://pytorch.org/get-started/locally/).
3. Create the isolated model environment:

   ```powershell
   py -3.14 -m venv model/.venv
   ```

   Install `torch==2.14.0` from the official index appropriate to the machine's CPU
   or CUDA setup. The CUDA index must be chosen for that machine, so no unverified
   CUDA wheel command is prescribed. Then install/verify the remaining pinned
   requirements (NumPy 2.5.3, Pillow 12.1.1, pytest 9.0.2, pydantic 2.13.5):

   ```powershell
   .\model\.venv\Scripts\python.exe -m pip install -r model/requirements.txt
   .\model\.venv\Scripts\python.exe -m pip check
   .\model\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
   ```

4. Copy `model/configs/tomato.windows.example.json` to the ignored
   `model/configs/tomato.windows.local.json` only if the target does not already
   exist. Set `dataset_path` to the actual root containing train/valid. The template
   uses `../tomato-dataset` relative to the repository. A Windows JSON path can use
   forward slashes, such as `D:/datasets/tomato-dataset`; do not put private paths in
   the versioned template. Confirm all 11 classes and an unused checkpoint location.
5. Run safe local tests and preflight, with no training:

   ```powershell
   .\model\.venv\Scripts\python.exe -m pytest model/tests -q
   .\model\.venv\Scripts\python.exe -m model.train --config model/configs/tomato.windows.local.json --device cuda --check-only
   ```

   Use `--device cpu` when intentionally using CPU. Preflight validates the full
   manifest, source hashes, device availability and output paths. It does not create
   loaders/batches, test GPU batch capacity, run forward/backward, or write files.
   Resume preflight additionally loads/validates the existing last checkpoint.
6. Stop and review preflight output, GPU memory/capacity, paths and hyperparameters.
   Confirm write permissions and free disk space for checkpoints/history outside
   the source dataset. Windows wheel availability, driver compatibility and batch
   capacity have not been verified from this Linux CPU environment.
   Any desired real-data/GPU sanity step requires separate approval; the existing
   `model.sanity` command performs an optimizer step and was not run in Phase 4A.
7. **Only after explicit approval**, the proposed full-training command is:

   ```powershell
   .\model\.venv\Scripts\python.exe -m model.train --config model/configs/tomato.windows.local.json --device cuda --epochs 30 --batch-size 16
   ```

   CPU uses the same command with `--device cpu` and may be substantially slower;
   no timing estimate or GPU memory-fit guarantee has been established. Select a
   workable batch size before starting; resume rejects changing it.
8. If interrupted after a completed epoch, a proposed resume command is:

   ```powershell
   .\model\.venv\Scripts\python.exe -m model.train --config model/configs/tomato.windows.local.json --device cuda --epochs 30 --batch-size 16 --resume model/checkpoints/tomato_run_01/best.last.pt --checkpoint model/checkpoints/tomato_run_01_resume/best.pt
   ```

   `30` remains the total target, not 30 additional epochs. Use the same environment
   and all original training settings. Do not point `--resume` at `best.pt`.

After future training, evaluate the selected best checkpoint on held-out data in a
separately approved step. The backend remains a development mock until an evaluated
checkpoint is explicitly integrated. Unrelated-image rejection, source-leaf/near-
duplicate leakage, calibration, and field generalization remain unresolved.

## Changed files and validation evidence

Modified:

- `model/agrisense_model/config.py`: optimizer/regularization settings and validation.
- `model/configs/tomato.json`: explicit optimizer defaults; class mapping unchanged.
- `model/agrisense_model/engine.py`: deterministic cuDNN settings and loader seed override.
- `model/agrisense_model/checkpoints.py`: optional resume state and optimizer-free best export.
- `model/train.py`: CLI overrides, check-only and resume entry points.
- `README.md`: Phase 4A status, output behavior and documentation link.

Added:

- `model/agrisense_model/training.py`: read-only preflight and training orchestration,
  including the continuation's output-parent guard.
- `model/configs/tomato.windows.example.json`: portable, relative-path configuration.
- `model/tests/test_training.py`: 32 synthetic safety/control/compatibility cases
  (30 recovered plus two output-parent regression cases).
- `model/PHASE4A_READINESS.md`: this report and Windows procedure.

Checks performed in this continuation (2026-09-26):

- Recovered model suite, before edits:
  `model/.venv/bin/python -m pytest model/tests -q` — **107 passed in 5.95s**.
- New regression cases before the fix:
  `model/.venv/bin/python -m pytest model/tests/test_training.py -q -k output_parent_file`
  — **2 failed, 30 deselected in 1.36s**, demonstrating the missing rejection.
- Final model suite after the fix:
  `model/.venv/bin/python -m pytest model/tests -q` — **109 passed in 3.98s**,
  including both new regression cases. No unresolved test failures.
- Sandboxed backend attempt: `timeout 25s .venv/bin/python -m pytest -q`
  from `backend/` — timed out with **exit 124**, no test result.
- Backend rerun with the established outside-sandbox TestClient workaround:
  `.venv/bin/python -m pytest -q` from `backend/` —
  **37 passed, 2 warnings in 2.44s**. Warnings concern Starlette's deprecated httpx
  TestClient integration and AnyIO's deprecated BlockingPortal alias.
- `model/.venv/bin/python -m pip check` and
  `backend/.venv/bin/python -m pip check` — both **No broken requirements found**,
  exit 0. Both emitted only the non-writable pip-cache warning.
- All five model requirement pins match installed packages: Torch **2.14.0+cpu**,
  NumPy **2.5.3**, Pillow **12.1.1**, pytest **9.0.2**, pydantic **2.13.5**.
  Runtime: Python **3.14.7**, Linux x86_64, four Torch threads, no CUDA/cuDNN build.
- `model/.venv/bin/python -m model.train --help` — **exit 0**, all preparation,
  override and resume options present; this does not invoke training.
- Metadata/class/path/hash checks described above — passed. An initial artifact
  inventory assertion incorrectly assumed `model/runs/` was absent; inspection
  found the preserved Phase 3B helper `model/runs/phase3b_sanity.py`. The corrected
  artifact check distinguishes that existing script from training outputs.
- `git diff --check` and whitespace checks covering all four untracked files —
  passed; final index remains empty and HEAD unchanged.

The previous session recorded `compileall` and frontend TypeScript checking as
passing. They were not rerun: pytest imported the affected Python modules, while
frontend source, package manifest, lockfile and TypeScript config are unchanged
from Phase 3C. No frontend validation result is newly claimed here.

New tests use tiny generated images or in-memory doubles. Epoch execution and
checkpoint saving in orchestration tests are intercepted; no optimizer updates or
trained files are produced. Numeric fixtures test control flow only and are not
research results. Existing synthetic forward/gradient and invalid-checkpoint tests
remain. Real uninterrupted-versus-resumed optimizer trajectories, Windows/CUDA
execution, and full-epoch throughput have not been exercised in Phase 4A.

No dataset was downloaded or modified. No real-data training/preflight,
model checkpoint, runtime training history or performance report was generated.
The original audit/manifest/local config were only inspected and remain ignored;
`.gitignore`, backend/frontend implementation, architecture and Phase 3 reports are
unchanged. Virtual environments/caches may be refreshed by automated checks.

## Commit recommendation after review

Recommend committing exactly the ten files listed under Modified and Added above:
`README.md`, `model/agrisense_model/checkpoints.py`,
`model/agrisense_model/config.py`, `model/agrisense_model/engine.py`,
`model/configs/tomato.json`, `model/train.py`, `model/PHASE4A_READINESS.md`,
`model/agrisense_model/training.py`, `model/configs/tomato.windows.example.json`,
and `model/tests/test_training.py`. These are the complete current Git change set:
six unstaged modifications and four untracked additions. Do not include ignored
datasets, manifests, audits, local configs, environments, caches or runtime outputs.
Nothing has been staged or committed.

**Stop point:** preparation READY, Windows execution pending verification and
approval. No staging, commit, push, real training, deployment or next phase started.
