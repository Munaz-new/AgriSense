# Tomato independent development evaluation: collection and review protocol

## Purpose and scope

This protocol defines a small, independently sourced development set for checking the existing plant-content suitability verifier and the five-epoch, 11-class tomato disease model. The set is for error discovery and development decisions. It is not a field-performance study, a threshold approval, or a substitute for the sealed held-out test set.

The proposed set contains 170 images:

| Sampling group | Count | Required coverage |
|---|---:|---|
| Tomato leaves | 110 | 10 independently disease-labeled images for each of the 11 model classes below |
| Other-plant leaves | 20 | Leaves from known non-tomato plant species; sample more than one species where practical |
| Non-plant images | 20 | Images containing no plant leaf as the primary subject, including varied real-world content rather than only logos |
| Ambiguous images | 20 | Images reviewers cannot confidently identify as tomato leaf, other-plant leaf, or non-plant from the available image |
| **Total** | **170** | |

The exact tomato class names are `Bacterial_spot`, `Early_blight`, `Late_blight`, `Leaf_Mold`, `Septoria_leaf_spot`, `Spider_mites Two-spotted_spider_mite`, `Target_Spot`, `Tomato_Yellow_Leaf_Curl_Virus`, `Tomato_mosaic_virus`, `healthy`, and `powdery_mildew`. Disease labels must come from independent qualified review and source records where available, not from the model prediction or a folder name alone.

## Approval before collection

Before acquiring images, send the protocol and blank [label template](tomato-independent-development-evaluation-label-template-v1.csv) to the intended reviewers. Obtain their explicit agreement on:

1. Their relevant plant pathology or botanical expertise, role, and how disagreements will be adjudicated.
2. The image inclusion rules, category definitions, disease-label guide, and handling of uncertain or mixed symptoms.
3. Image source permissions, privacy restrictions, attribution requirements, and permitted local storage and use.
4. Blinding: reviewers must not see model predictions, scores, or the other reviewer’s decisions before submitting their own labels.
5. The planned development-only use, no automatic relabeling, and the process for documenting corrections or unresolved cases.

Record approval and reviewer identities outside the image labels as project governance records. Do not begin collection until both independent reviewers accept the labeling rules and a qualified adjudicator is identified for disease-label conflicts. Never infer approval from participation or from a previous AI assessment.

## Image selection and review

- Use new, independently sourced images for this evaluation where possible. Record provenance for each image: source or owner, source record/URL if allowed, collection method, permission status, and capture date only when known. Leave unknown dates blank.
- Sample tomato examples across all 11 disease classes at the stated quota. Seek varied lighting, backgrounds, devices, orientations, symptom severity, and framing; avoid selecting only clean textbook crops. Reviewers may mark a sample ambiguous or ungradable. Replace it only through the documented sampling process; retain the original disposition in the audit trail.
- For other-plant images, record the independently supported species or `unknown`; do not infer tomato identity from generic leaf appearance. For non-plant images, record the visible content category. For ambiguous images, leave disease unassigned unless the expert review supports one.
- Two reviewers label each image independently. Capture each reviewer’s category, species, disease label, decision, and notes before sharing decisions. A third qualified reviewer resolves disagreements. Preserve both original decisions and the resolution; do not silently overwrite them.
- Assign opaque image IDs. Keep filenames and provenance hidden during blinded disease labeling where feasible. Store image files in a separate, access-controlled evaluation directory, outside the application’s dataset and upload directories.

## Preventing overlap with existing data

The current curated manifest is `model/data/tomato_splits.json` (version 2): train 21,108, validation 6,614, and held-out test 3,719 entries. Its paths were verified against the configured local dataset root; the saved checkpoint run refers to that manifest. Do not add evaluation images to the original dataset, manifest, or any training/evaluation directory.

Before freezing the new set:

1. Keep every candidate in a separate location and make an inventory of file paths and raw SHA-256 hashes.
2. Compare candidates against **all** image paths in the current train, validation, and test manifest, and against the full source dataset inventory, not only the test rows. Use decoded-pixel hashes after EXIF orientation and RGB conversion for exact-image checks.
3. Check source URLs, photographer/source records, filenames, and known augmentation lineage. Run a documented, bounded perceptual-hash retrieval pass as a candidate generator only. A pHash match alone is not proof of shared source; review candidate pairs visually. Quarantine unresolved potential overlaps from this development set until reviewed.
4. Record the comparison method, version, input inventory hashes, candidates, dispositions, and exclusions. Do not claim complete independence if provenance is missing or candidate overlap remains unresolved.

Prior reports document unresolved near-duplicate candidates in the existing corpus. Reuse those reports and known lineage/conflict records; do not repeat the large duplicate investigation for this collection. An external source does not by itself prove independence if it reproduces an existing image.

## Evaluation after labels are frozen

Freeze reviewer labels and the candidate inventory before running either model. Save the checkpoint hash, verifier weight hash/version, preprocessing/version, software versions, and run date with results. Do not train or update weights during this experiment.

For suitability, report a confusion table by the four adjudicated categories; tomato acceptance and false-rejection rates; other-plant and non-plant false-acceptance rates; ambiguous-case acceptance/rejection/inconclusive rates; and exact numerators, denominators, and binomial confidence intervals. Report reviewer agreement and unresolved labels separately. The set is intentionally small: even zero false accepts among 20 examples leaves substantial uncertainty, so this pilot cannot validate a production rejection threshold.

For tomato disease prediction, report the 11-class confusion matrix, per-class precision/recall/F1/support, macro-F1, balanced accuracy, and top-1 accuracy with uncertainty intervals. Preserve the raw uncalibrated scores only as descriptive output; do not treat them as correctness probabilities or tune a score cutoff from this small sample. Ten images per class are suitable for finding conspicuous failure modes, not precise class-performance claims.

Keep all 3,719 held-out test entries sealed from collection choices, threshold/model selection, and development decisions. A final claim requires a separately planned, untouched test on a leakage-controlled evaluation set after development choices are frozen.

## Label template

Use [tomato-independent-development-evaluation-label-template-v1.csv](tomato-independent-development-evaluation-label-template-v1.csv). It contains headers only. Add one row per acquired image; do not prefill reviewer labels from the sampling target, source folder, model output, or prior automated assessment. Use blank values for unknown or not applicable fields and explain them in `notes` when useful. Keep original reviewer entries intact when an adjudicator resolves a disagreement.
