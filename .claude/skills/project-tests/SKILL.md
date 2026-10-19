---
name: project-tests
description: Run and diagnose Jevision prototype regression, build, and browser integration checks. Use when verifying code changes or setup recovery; use evaluate-detection or evaluate-html-layout for model accuracy experiments.
---

# Project tests

Read [Claude.md](../../../Claude.md) for the code map. Run commands from the project root and inspect `package.json` for the current test entry points. Use focused checks for the changed behavior, then the regression suite when warranted.

## Choose the checks

| Change | Focused check |
|---|---|
| Find strategies, ownership, or geometry | `node --test tests/find-objects.test.js` |
| HTML questions or decision policy | `node --test tests/layout.test.js` |
| Box evaluator or frozen Find snapshots | `.venv/bin/python -m unittest tests.test_scoring tests.test_frontend_modules -v` |
| Setup or downloads | `.venv/bin/python -m unittest tests.test_setup tests.test_download tests.test_photo_datasets -v` |
| Library, HTML API, or rendering | `.venv/bin/python -m unittest tests.test_layout -v` |
| Tool wiring and browser behavior | `.venv/bin/python -m unittest tests.test_tool_modules -v` |
| Service startup, shutdown, or reload | `.venv/bin/python -m unittest tests.test_services tests.test_server_reload -v` |

`pnpm test` runs Node and Python tests, including Chromium integration with mocked model responses. It makes no paid model calls. Use `pnpm build` for frontend changes; after building, `JEV_UI_TEST_ROOT=dist .venv/bin/python -m unittest tests.test_tool_modules -v` checks the bundled UI. Do not repeat passing checks without a new change or unresolved concern.

## Prerequisites and failures

If dependencies or Chromium are absent, `pnpm run setup` prepares them and downloads the example datasets. Read its effects before using it on an existing installation: it configures `.env` and may install Linux browser libraries. Preserve keys and custom datasets.

Trace failures through the actual failing module. Distinguish assertion failures from missing dependencies, browser startup problems, port conflicts, and unavailable external services. Fix the cause; do not skip an assertion or change reference labels merely to get a pass.

For setup recovery, use an isolated public-source copy with empty data folders and a fresh browser context. Verify 25 photo categories / 13,955 photos and 484 HTML pairs through the real API and UI. A fresh installation must not rely on existing IndexedDB records. Shut down only processes started for the check and retain small diagnostics under `.jev-image-data/`.

Optional `tests/browser_*.py` scripts differ: inspect their headers and CLI before running. Some make live model calls, some use the local server without inference, and `browser_hot_reload.py` starts its own services. Use live phases when the task calls for model evaluation; regression verification alone does not require them.

Report what passed, what failed or was not exercised, and any remaining limitation. A working mocked UI or successful HTTP request does not establish model accuracy. See [development and evaluation](../../../docs/development.md) for the full workflows.
