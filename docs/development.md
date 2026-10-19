# Development and evaluation

Complete [setup](../README.md#quick-start), then run commands from the project root. Use the [frontend map](frontend-structure.md) to find implementation files and [Claude.md](../Claude.md) for contributor instructions.

## Running and stopping services

`pnpm start` runs Vite on port 8765 and a watched Python API on 8766. Tool routes are `/tools/count`, `/tools/find`, `/tools/search`, and `/tools/qa`.

- CSS updates live; HTML/JavaScript changes refresh the page when needed.
- Changes to `server.py`, `layout_renderer.py`, Python files in `scripts/`, or `.env` restart the API. Restarts clear in-memory jobs/caches, not saved results.
- Dataset downloads, results, and logs do not trigger reloads.
- Ctrl+C stops the supervised processes. If one exits, the supervisor stops the other.

From another terminal, `pnpm stop` stops this project's services on Linux/WSL, including custom-port instances. It uses exact entry paths and process identity, not arbitrary port listeners. It is safe to repeat.

Shutdown drains active requests and stops downloads at their next checkpoint. It waits 30 seconds without force-killing; if draining takes longer, use `pnpm stop --timeout 120`. An active network fetch can delay a checkpoint.

For a local production run, use `pnpm build` then `pnpm start:prod`. Set distinct development ports with `.env` or `PORT=8877 API_PORT=8878 pnpm start`; shell values take precedence. Launcher/dependency changes may require a restart.

`PHOTO_ROOT` selects the photo folder; setup uses `.photo`, while an unset value falls back to the workspace. Scanning skips hidden/common source folders and accepts PNG/JPEG. Add files and rescan, or use Add photos. See [datasets](photo-datasets.md).

## Documenting prototype scope

Update the relevant guide when changing behavior: [Count](count-objects-design.md), [Find](find-objects-design.md), [Search](search-images-design.md), or [HTML](html-layout-design.md). Keep current defaults, disabled experiments, and proposals distinct. Describe missing application policies without implying an API limitation or a proven benefit from extra questions.

Keep measured reports in `.jev-image-data/private-docs/` and raw runs under `.jev-image-data/`. Public guides describe methods and scope.

## Tests and evaluations

```sh
pnpm test
pnpm build
JEV_UI_TEST_ROOT=dist .venv/bin/python -m unittest tests.test_tool_modules -v
```

These checks use mocked model responses and make no paid judgments. They cover requests, rendering, geometry, server contracts, snapshots, and scoring—not model accuracy.

`tests/browser_hot_reload.py` starts isolated services, checks frontend/backend reloads, and stops its own processes without inference. Other `browser_*.py` scripts may make paid calls; read their headers and CLI first.

### Find evaluations

Prepare a small COCO development cohort, inspect its manifest/labels, then run:

```sh
.venv/bin/python -m scripts.benchmark_find prepare --out .jev-image-data/find-example
.venv/bin/python -m scripts.benchmark_find run \
  --out .jev-image-data/find-example --base http://127.0.0.1:8765 --workers 1
.venv/bin/python -m scripts.benchmark_find analyze --out .jev-image-data/find-example
```

Preparation downloads and freezes inputs; `run` needs the app and makes paid calls. Check the manifest's versions, repeats, labels, and work limits before inference. `analyze` scores saved results.

To reuse verified inputs with current code and chosen versions, create a fresh snapshot:

```sh
.venv/bin/python -m scripts.benchmark_find snapshot \
  --source .jev-image-data/find-example --out .jev-image-data/find-v4-v6-example \
  --versions v4 v6 --repeats 3
```

Then use `run` and `analyze` on the new output path. Snapshots freeze the module graph, harness, image hashes, labels, and schedule. Resume rejects changed provenance; never overwrite historical runs.

Optional snapshot controls:

| Option | Purpose |
|---|---|
| `--v6-config PATH.json` | Freeze the five [V6 gate overrides](find-objects-v6.md#benchmark-overrides) |
| `--config PATH.json` | Freeze V5 runtime overrides |
| `--versions v2-policy v4-policy v5` | Compare V5 with historical engines using its visible-instance prompt contract |

The COCO cohort covers people/cars/dogs, not insects or all target sizes. Reusing it for development does not create independent confirmation.

### Reproduce the layout evaluation

```sh
.venv/bin/python scripts/benchmark_layout.py prepare --out .jev-image-data/layout-example
.venv/bin/python scripts/benchmark_layout.py run \
  --out .jev-image-data/layout-example --base http://127.0.0.1:8765
.venv/bin/python scripts/benchmark_layout.py fit --out .jev-image-data/layout-example
.venv/bin/python scripts/benchmark_layout.py analyze --out .jev-image-data/layout-example
```

Preparation freezes labels, screenshots, and prompt/preparation modules. `run` makes live requests; completed responses are reused on matching resumes. Fit thresholds on calibration responses only.

Use `--suite overlap-calibration` and `--suite overlap-confirmation` for separate cohorts. Analyze confirmation with `--calibration PATH_TO_CALIBRATION` to reuse frozen thresholds. `--modules-from PATH_TO_SNAPSHOTS` selects an earlier frozen prompt. Keep related viewports and repeats grouped. See [HTML design](html-layout-design.md) for check semantics.

## Changing detection or evaluation settings

1. **Locate the setting.** Historical gates live in `web/tools/find/limits.js`; V5 defaults in `v5.js`; V6 overrides in `v6/config.js`. `.env` controls services/credentials, not detection gates.
2. **Freeze the comparison.** Fix source groups, labels/box policy, actual model identity, prompts, limits, concurrency, and repeats. Keep tuning and confirmation sources separate.
3. **Choose the right experiment.** Prompt, gate, crop, and identity changes can alter later requests, so measure complete searches. To isolate question packaging, first compare identical crops.
4. **Retain failures.** Save every attempt, error, and missing-usage flag. Do not drop hard cases or replace unfavorable repeats.
5. **Report comparable outcomes.** Include TP/FP/FN, micro and category metrics, duplicate/identity audits, usage, timing, and unresolved work. Distinguish displayed boxes from V5's confirmed-by-checks subset.

Changing evaluation IoU can rescore saved boxes without inference. Keep .50 as the primary standard and .30 as a localization diagnostic; label any other threshold explicitly. Source-group bootstrap intervals must keep repeats together. Repeats do not add independent images, and a low duplicate count does not prove merge safety.

The generic [box scorer](../scripts/score_boxes.py) accepts frozen predictions. Count and Search need their own count/relevance labels and metrics; box scores do not validate them.

### Reporting checklist

Record source/group counts, category/size coverage, annotation provenance, exclusions, model/configuration hashes, prediction scope, IoU, metrics, repeat variation, work limits, failures, unknown usage, and timing conditions. Store measured tables and evidence in ignored folders. See [metric definitions](detection-metrics.md).

## Same-origin errors in development

The API compares browser `Origin` with request `Host`. Keep Vite's explicit `changeOrigin: false`: its string proxy shorthand rewrites Host and causes legitimate frontend requests to fail. Use the frontend URL rather than calling the API port from a different browser origin. The proxy regression checks allowed GET/POST and rejected cross-origin requests.

## Client disconnects during HTTP responses

`AppHandler.handle_one_request` closes connections on broken pipe/reset/abort. Do not send another error response to that connection or retry a potentially billed judgment because its client disappeared. Keep response writes outside data-access/upstream error handlers so unrelated failures remain visible.

Run `.venv/bin/python -m unittest tests.test_server_disconnects -v` for focused coverage. A standalone server needs restarting after code updates. Disconnect handling does not guarantee cancellation of provider work already in flight.

## Live ant UI review

With the app running:

```sh
PYTHONPATH=. .venv/bin/python tests/browser_find_ants.py \
  --base http://127.0.0.1:8765 --out .jev-image-data/find-ui-example \
  --versions v4 v6 --repeats 3 --pause-ms 1000
```

This is a paid UI run, separate from `pnpm test`. It operates real dataset/photo controls and saves source/input hashes, screenshots, crop previews, and responses. The default cases are five supplied ant photos. Use `--dataset ID` with matching `--cases NAME.jpg ...` for other sources and `--v6-config PATH.json` for V6 controls.

Without annotations, this is qualitative review only. For reference-relative scoring, supply `--labels PATH.json` with matching image hashes and target, then use `scripts.score_find_ui`. Agent-created references require `--allow-agent-labels` for both steps and remain exploratory, not human-audited truth.

V5 fixed-response diagnostics are available in `scripts.analyze_find_evidence`. Replay uses only recorded observations/checks: it cannot invent missing verification, identity decisions, or adaptive crops. Full-policy changes require fresh inference.
