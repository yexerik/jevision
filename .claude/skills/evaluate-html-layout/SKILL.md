---
name: evaluate-html-layout
description: Prepare, run, fit, and analyze Jevision prototype HTML layout evaluations with frozen screenshots and separate calibration/confirmation groups. Use for Chromium-rendered HTML defect checks, layout prompt changes, overlap regressions, or threshold evaluation. General browser navigation and button tests belong to project-tests.
---

# Evaluate HTML layouts

Read [development and evaluation](../../../docs/development.md), `scripts/benchmark_layout.py`, `scripts/layout_fixtures.py`, and `web/layout.js` for the current suite and policy. Run commands from the project root.

## Select the scope

Distinguish regression checks, analysis of saved requests, and new live evaluation. Use live phases when the user's task requires model evaluation; existing saved responses may answer analysis-only questions. For a new experiment, record the prompt/policy change, model, cases, source groups, repeated-run count, and request/cost bounds.

Inspect the suite choices with the runner's `--help`. `initial` includes synthetic fixtures and available Design2Code reference controls; `overlap-calibration` is for overlap threshold fitting; `overlap-confirmation` supplies separate cases; `overlap-regression` includes clipping, overlap, and combined defects. Check the actual frozen manifest for coverage and request totals.

Review screenshots and freeze label/ambiguity policy before inference. Synthetic construction and agent-reviewed controls are not independent human labels. Different-page reference controls do not establish realistic reference-difference accuracy. Design2Code has an absent source image asset; do not label every rendering/reference difference as a layout bug. Preserve rendering isolation and use explicit viewports.

## Prepare, run, fit, analyze

Use a fresh output directory and the actual app URL:

```sh
.venv/bin/python scripts/benchmark_layout.py prepare --suite initial --out .jev-image-data/layout-example
# Start pnpm start separately before live inference.
.venv/bin/python scripts/benchmark_layout.py run --out .jev-image-data/layout-example --base http://127.0.0.1:8765
.venv/bin/python scripts/benchmark_layout.py fit --out .jev-image-data/layout-example
.venv/bin/python scripts/benchmark_layout.py analyze --out .jev-image-data/layout-example
```

Preparation renders cases locally and freezes source/image/manifest hashes without model calls. `run` makes three real requests per case and can reuse saved responses. Do not edit frozen files, substitute another prompt version into a resumed run, or include failed/missing responses as passes. Inspect failures and completeness before reporting metrics.

Use only calibration groups for fitting. Freeze a selected policy before confirmation and keep scene/source groups separate. To analyze a separate confirmation run, pass `--calibration` pointing to the frozen calibration output. `--modules-from` can prepare a paired experiment using an earlier module snapshot; inspect its expected directory structure first. Historical source snapshots and results stay unchanged.

## Score and report

The production overlap probability combines `overlap_only` and `both`; clipping-only examples remain distinct and combined defects can count toward both checks. Use production request builders and probability accessors instead of independently reimplementing them in a evaluation.

Report per-check confusion counts, precision/recall/F1, probability error, repeated-run stability, held-out performance, actual API usage, failures, and timing context. Identify whether thresholds came from calibration or implementation defaults. Synthetic success does not establish calibrated probabilities or correctness on arbitrary generated pages.

Keep raw screenshots, HTML, exchanges, and fitted settings under `.jev-image-data/`. Check summaries for credentials and personal paths before sharing. Validate evaluator or prompt-accessor changes with:

```sh
node --test tests/layout.test.js
.venv/bin/python -m unittest tests.test_layout_benchmark tests.test_layout -v
```

Do not promote a threshold or prompt merely because it improves the tuning set; report the separate confirmation result and remaining coverage gaps.
