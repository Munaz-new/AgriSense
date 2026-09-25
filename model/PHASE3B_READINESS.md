# Phase 3B readiness report

Completed 2026-09-25. **PASS: the existing tomato pipeline is technically ready for
full-training setup on a stronger Windows machine, subject to validating that
machine's environment.** No full training was started. This check establishes
software readiness, not model quality or research validity.

## Scope and preserved Phase 3A preparation

Inspected the Phase 3A checkpoint (`dbf3564`), configuration, preparation and loading
code, architecture, training loop, and tests. No production model, preparation, or
backend implementation was changed. Materialized the existing Phase 3A audit as the
active manifest without re-curation or re-splitting, then validated it using the
existing `load_manifest` pipeline. The active manifest equals the complete audit.

- Training: 21,108 images; validation: 6,614; test: 3,719.
- Retained: 31,441 of 32,535 source files. Existing exclusions remain unchanged.
- All 11 classes occur in every split. Their label order remains: `Bacterial_spot`,
  `Early_blight`, `Late_blight`, `Leaf_Mold`, `Septoria_leaf_spot`,
  `Spider_mites Two-spotted_spider_mite`, `Target_Spot`,
  `Tomato_Yellow_Leaf_Curl_Virus`, `Tomato_mosaic_virus`, `healthy`, `powdery_mildew`.
- Labels are zero-based: `Bacterial_spot` = 0, `powdery_mildew` = 10.
- Manifest SHA-256: `44d46bb8e46fbd9dc5c90cafb636086a073e137c251f654d9d29251ab398a109`.

## Measured sanity test

- Device: CPU, Intel Core i7-8550U; 8 logical CPUs, 2 PyTorch intra-op threads.
- Environment: Python 3.14.7, PyTorch 2.14.0+cpu; CUDA unavailable to PyTorch.
- Exact scope: **11 distinct training samples, 1 batch, 1 optimizer step**.
  Selected the first manifest training entry per class, including powdery mildew.
  No validation or test samples were forwarded through the model.
- Dataset loading and batch creation: passed using existing `CropDataset` and its
  training augmentation, wrapped in a bounded `Subset` and `DataLoader`.
- Inputs: float32 `[11, 3, 224, 224]`, all finite.
- Labels: int64 `[11]`, exactly `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]`.
- Model: unchanged configured Hybrid CNN + Transformer, 648,331 parameters,
  randomly initialized with seed 42. No reduced architecture or resolution.
- Forward pass: passed; finite logits `[11, 11]`.
- Cross-entropy loss: passed; scalar `2.427874803543091`. This is a diagnostic
  value from random initialization, not a research or evaluation result.
- Backward propagation: passed; all parameter gradients present and finite.
  Nonzero gradients verified in CNN, patch embedding, positional embeddings,
  Transformer attention, and classifier probes.
- Optimizer: exactly one AdamW step, learning rate 0.0003, weight decay 0.01,
  gradient clipping at 1.0, matching the existing training settings. Branch probe
  weights changed and all resulting weights remained finite. Optimizer state
  confirmed one step. Disposable updated weights were not saved.
- Sanity runtime: **2.494 seconds**, including batch loading, model/optimizer
  construction, forward/loss/backward/update, and assertions.
- Manifest validation: 77.866 seconds. Total runner: **123.208 seconds**, including
  complete source snapshots before/after; excludes Python imports and separate tests.
- Process CPU: 95.273 CPU-seconds over the whole runner, average 77.33% on a
  one-core basis. Sanity portion: 2.875 CPU-seconds.
- Peak process RAM: **1,063.97 MiB** (Linux maximum resident set, whole process).
  System snapshot before the run: 19 GiB total RAM, about 12 GiB available.
- GPU utilization/memory: unavailable; `nvidia-smi` could not communicate with
  the NVIDIA driver. No GPU execution was tested.

## Verification, warnings, and limitations

44 model tests and 32 backend tests passed. Both Python dependency checks passed.
The sanity runner reported no errors or Python warnings. Backend tests first stalled
under the sandbox (the documented Phase 3A TestClient limitation); the interrupted
attempt was rerun successfully outside it. The backend emitted two existing
Starlette/AnyIO deprecation warnings. The model dependency check warned that pip's
cache directory was not writable; dependency validation still passed.

All 32,535 source paths, file sizes, modification times, and SHA-256 values were
identical before and after. File hashes also matched the Phase 3A inventory.
**Original dataset images were not modified, renamed, moved, copied, or deleted.**
Selected-image pixel hashes, class coverage, split isolation, and the exclusion
ledger passed the existing manifest validator.

The known corrupt image and conflicting/duplicate groups remain excluded under
Phase 3A policy. Exact pixel deduplication does not verify near-duplicates or
source-leaf independence. No accuracy, precision, recall, F1, or other model-quality
results were produced.

## Files generated or changed

- `model/configs/tomato.local.json`: ignored local configuration pointing at the
  existing external source root (workstation path intentionally omitted).
- `model/data/tomato_splits.json`: ignored active manifest, equal to Phase 3A audit.
- `model/runs/phase3b_sanity.py`: ignored bounded workstation diagnostic runner;
  Linux resource measurement is workstation-specific. It refuses report overwrite.
- `model/reports/tomato_phase3b_sanity.json`: ignored measurements, exact sample paths,
  ordered mapping, validation results, timings, and source-integrity evidence.
- `model/PHASE3B_READINESS.md`: this report.
- `README.md`: current checkpoint status and link to this report.

Checkpoint packaging additionally includes `model/sanity.py`, a reusable CPU runner
derived from the original ignored script, and `model/tests/test_sanity.py` for its
output guards and portable resource reporting. The reusable runner accepts explicit
local configuration/audit paths, enforces the full ordered tomato mapping, and
handles missing Windows resource measurements without inventing values. The
measurements above came from the original local script; the real-data check was
not repeated during packaging. `.gitignore` also covers common extracted dataset
roots, temporary files, additional environment directories, and private key stores.
Packaging verification passed 53 model tests (including nine new safety/portability
cases), 32 backend tests, both dependency checks, and whitespace validation. The
backend's two existing deprecation warnings and pip's cache warning remain
non-failing. No new optimizer steps were performed for packaging.

Python/pytest may also refresh ignored bytecode/test caches. The existing Phase 3A
audit was preserved. No checkpoint or training-history files were created.

## Windows readiness and stopping point

The dataset mapping, preprocessing, configured architecture, autograd, and optimizer
have passed this CPU check. Full training can be considered after approval and
Windows setup: transfer the same dataset hierarchy and validated manifest, set the
Windows dataset path in a local config, install/validate the Python environment and
appropriate PyTorch/GPU setup, then repeat a bounded check on that machine. This
Linux run does not certify Windows/CUDA compatibility, full-epoch runtime, or that
the configured full-training batch size of 16 fits its GPU. Preserve the audit and
split membership when transferring; do not silently regenerate a new split.

No deployment, backend model activation, Git commit, or Git push occurred. The
backend remains in development-only mock mode. **Stopped after Phase 3B; further
training requires user approval.**
