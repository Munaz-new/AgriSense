# Independent tomato evaluation validator

Run the read-only validator from the repository root:

```sh
model/.venv/bin/python -m model.validate_independent_evaluation
```

Pass `--workspace`, `--manifest`, and `--dataset-root` to check a different collection or to compare against an accessible curated dataset. The default manifest is `model/data/tomato_splits.json`; the dataset root must contain the manifest's relative image paths. The validator does not write to the collection, manifest, or dataset.

The CSV template has **29 columns**. Reports use four category values: `tomato_leaf`, `other_plant_leaf`, `non_plant`, and `ambiguous`. Missing files, malformed rows, duplicate IDs, hash mismatches, unsupported categories, and exact hash matches are errors. Missing provenance, permission, reviewer details, hashes, or inaccessible dataset files are warnings. A header-only file is a valid zero-image collection.

When source files are accessible, the validator compares raw file SHA-256 and EXIF-oriented RGB pixel-byte SHA-256 values against all paths in the supplied manifest. A hash match is an exact overlap signal; no hash check establishes source independence, tomato species, or disease-label correctness. Provenance review, species confirmation, independent reviewer decisions, and any necessary adjudication remain required by the [collection protocol](tomato-independent-development-evaluation-collection-protocol-v1.md).
