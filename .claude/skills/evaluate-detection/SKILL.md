---
name: evaluate-detection
description: Prepare, snapshot, run, or analyze reproducible Jevision prototype Find Objects evaluations against independent reference boxes. Use for strategy and policy-control comparisons, localization/recall analysis, and detection changes; ordinary UI checks belong to project-tests.
---

# Evaluate object detection

Read the [Find design](../../../docs/find-objects-design.md), [evaluation commands](../../../docs/development.md), and the relevant runner/evaluator code before changing an experiment. Commands below run from the project root.

## Establish the experiment

Identify whether the task requires new inference, saved-result analysis, or evaluator tests. Reuse existing task authorization; avoid new paid runs when saved data answers the question. For a live comparison, establish source images, independently checked reference boxes, versions, repeats, model identity, and request/cost limits before inference.

The existing `scripts.benchmark_find prepare` selects a small COCO development set: 12 images across people/cars/dogs. It does **not** evaluate `.photo` automatically. Our ant/bee and sea-animal datasets have class folders, not object boxes. For project images, freeze independently audited annotations and explicitly adapt the runner or evaluator input to that cohort. Do not infer ground truth from model predictions or folder names.

Keep source/scene groups separate between tuning and confirmation; crops, duplicates, and repeats of a source stay together. Repeated runs measure variability, not additional independent images. Audit box policy, depictions, crowd regions, occlusion, and class boundaries before seeing prediction overlays. Record exclusions and retain full-set results when a policy subset is reported.

## Existing COCO runner

Use a fresh, descriptive output folder; do not overwrite historical evidence:

```sh
.venv/bin/python -m scripts.benchmark_find prepare --out .jev-image-data/find-example
# Start the app separately with pnpm start before live inference.
.venv/bin/python -m scripts.benchmark_find run --out .jev-image-data/find-example --base http://127.0.0.1:8765
.venv/bin/python -m scripts.benchmark_find analyze --out .jev-image-data/find-example
```

`prepare` downloads public inputs and freezes labels and production module hashes, without calling Jev. Review the manifest and ground truth before `run`; preparation does not create a completed label audit. The default live comparison is 12 images × four versions × three repeats = 144 image evaluations, each potentially making multiple HTTP requests. Use the actual running app URL and inspect CLI options rather than assuming its default port.

Keep the model, source, prompts, images, and labels fixed within a comparison. Resume only matching, complete experiment identities. Investigate hash mismatches, missing runs, failed requests, or missing token usage; do not silently drop them. `analyze` scores saved results without new inference. The generic `scripts/score_boxes.py` accepts frozen evaluator inputs; inspect its schema and tests before preparing custom inputs.

The runner also exposes `snapshot` to reuse verified images/annotations while freezing the current engine for a new experiment. Inspect `--source`, `--versions`, `--repeats`, and `--config` in the current CLI. Supported experimental controls include `v2-policy`, `v4-policy`, and `v5`. Match box/prompt policy when comparing V5 with controls so a policy change is not credited to the search algorithm. A snapshot of the existing development cohort remains development data; it does not create an independent confirmation set. Read repeat counts and the selected versions from its frozen manifest rather than assuming the original 144-run plan.

## Assess the evidence

Use one-to-one matching and micro-aggregated TP/FP/FN at IoU .50, with IoU .30 as a localization diagnostic. Count unmatched predictions on negatives as false positives. Report precision, recall, F1, duplicate candidates, repeat variation, HTTP attempts/errors, usage, cost assumptions, and timing conditions. Fixed-IoU precision/recall is not COCO AP/mAP.

Keep V4 cluster references separate from individual-object boxes. Correct counts or zero unresolved regions do not prove complete localization. Inspect clipped bodies, loose boxes, missed regions, coordinate mapping, and duplicate suppression before assigning a root cause. Lowering the evaluation IoU changes the standard, not the boxes.

Validate evaluator changes with `.venv/bin/python -m unittest tests.test_scoring tests.test_frontend_modules -v`. Preserve raw evidence locally under `.jev-image-data/`; publish only explicitly requested summaries stripped of credentials and personal paths. State dataset coverage, policy mismatches, and limits on generalization.
