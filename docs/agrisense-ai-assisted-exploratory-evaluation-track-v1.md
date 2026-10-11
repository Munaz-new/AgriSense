# AgriSense AI-assisted exploratory evaluation track (v1)

**Status:** Development-only guidance; no evaluation results are asserted here.

**Applies to:** Exploratory software and model behavior checks during application development.

**Does not replace:** `tomato-independent-development-evaluation-collection-protocol-v1.md` or its independent reviewer and adjudicator requirements.

## Purpose

Use AI-assisted checks to find obvious application failures, identify confusing messages, and organize follow-up tests. The assistant may help draft test cases, summarize observed system output, and flag cases that deserve human attention. These checks are provisional engineering evidence. They are not expert-verified ground-truth labels, independent human review, clinical or agronomic validation, or a field-performance study.

The formal independent evaluation protocol remains unchanged and continues to govern any work represented as that evaluation. Its reviewer approvals and qualified adjudicator must never be described as complete unless real people have explicitly agreed and the agreement is documented. AI-assisted development may proceed without pretending that those approvals exist.

## Keep exploratory observations separate

- Do not write AI assessments into reviewer, adjudication, or final-label columns in the independent evaluation `labels.csv`.
- Do not change, approve, or relabel existing evaluation candidates through this track. Existing candidates remain subject to their separate governance and protocol review.
- Keep exploratory run notes in a separate, versioned report or issue. Do not merge provisional assessments into training, validation, test, or human-label datasets.
- Use only images whose provenance and permitted use are understood. Keep evaluation assets outside the application dataset and repository where required by their source terms and project policy.
- Do not use the sealed held-out test set to choose images, prompts, thresholds, or model settings.

## What an exploratory record should capture

For each run, record enough information to reproduce what the application did without implying that the result is correct:

| Record item | What to capture |
|---|---|
| Run identity | Run ID, date/time and timezone, operator, test purpose, application commit, and environment/device/browser. |
| Image provenance | Opaque image ID, source URL/owner, permission and attribution terms, acquisition method, known source-reported date, raw SHA-256, and any known relationship to another image. Treat species and condition statements from a source as source claims. |
| Technical check | File format, dimensions, technical validation result, and exact API response/error. A technical pass only means the file passed file checks. |
| Suitability check | Plant-content screening outcome (`plant`, `non_plant`, `inconclusive`, or unavailable), exact user-facing message, verifier version/weights if known, and any failure. Screening is a zero-shot exploratory check, not a measured plant detector. |
| Disease output | Exact returned class, predictor identity, checkpoint hash, preprocessing/version, and raw score exactly as returned. Label the score **uncalibrated**; it is not a probability of correctness. Do not infer severity. |
| User workflow | Camera/gallery path, selected plant/crop, save mode, loading/error/retry behavior, whether history reflects the saved record, and what the user saw. Redact secrets and personal data. |
| AI assistance | AI tool/model and version if known, prompt or task description, what the AI summarized or suggested, its uncertainty, and the human/operator disposition. Keep raw application output separate from AI interpretation. |
| Outcome | Reproducible steps, expected vs observed behavior, evidence reference, limitations, and whether a human follow-up is needed. Do not call the outcome a disease label or ground truth. |

If the running app does not expose a value, write “not available”; do not reconstruct it from assumptions. In particular, the application currently returns the suitability outcome and message, not the verifier’s internal similarity values.

## Exploratory test method

1. Define a narrow question before each run (for example, whether an unsupported image format is rejected clearly, or whether an ambiguous suitability result blocks analysis and saving).
2. Use a small, source-documented case set spanning the software paths under examination: readable and corrupt images, supported and unsupported formats, clearly plant-like and unrelated content, ambiguous content, network/service failures, and record retry behavior. Case selection is not a sampling claim.
3. Capture exact response codes, visible messages, and persistence effects. Keep model prediction, suitability decision, and technical file validation as separate observations.
4. Ask an AI assistant to help summarize logs or propose additional edge cases only after preserving the exact application output. Record the assistant’s uncertainty and do not convert its description into a reviewed label.
5. Reproduce suspected issues with a deterministic test where practical. Escalate botanical identity, disease, severity, and treatment questions to qualified human review.
6. Report failures, inconclusive cases, skipped runs, and unavailable dependencies. Do not report only successful examples.

## Known interpretation limits

- The tomato classifier is a closed-set 11-class model. It can return a tomato disease class for a non-tomato image if suitability screening fails to stop it.
- The CLIP-based suitability check is prompt-based and has no measured accuracy claim in this application. Its similarities, where available internally, are not probabilities.
- The disease model’s softmax score is uncalibrated. A high score is not verified correctness; a “healthy” output does not rule out disease.
- Severity measurement and validated health progression are unavailable. Do not derive either from the predicted class, score, or user-entered environmental context.
- AI assistants can share model blind spots, misread images, or confidently summarize errors. Repeating a result with another AI does not create independent human evidence.
- A small set of exploratory examples is useful for discovering software failures, not for estimating field accuracy, approving a threshold, or supporting efficacy claims.

## Reporting language

Use language such as **“provisional AI-assisted exploratory observation”**, **“application returned…”**, and **“requires human review.”** State the model/version, input provenance, test scope, missing evidence, and uncertainty. Do not use “expert-verified,” “ground truth,” “confirmed disease,” “validated diagnosis,” or “independent validation” for AI-generated assessments.

Before any formal research claim, use the unchanged independent evaluation protocol, obtain the required explicit reviewer agreements, identify a qualified adjudicator, complete documented image-permission and overlap review, freeze human labels and inventory, and follow the protocol’s reporting requirements.
