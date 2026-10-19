# Agent context

Shared context for coding agents. `Agent.md` is a relative symlink to this file; edit `Claude.md`. `.claude/CLAUDE.md` imports it. Start with [README](README.md) for setup and user behavior.

## Shared project skills

Maintain skills in `.claude/skills/`; `.agent/skills` and `.agents/skills` are relative symlinks. Local settings beside them stay ignored.

| Skill | Use |
|---|---|
| [typesafe-ai](.claude/skills/typesafe-ai/SKILL.md) | TypeSafe integration and judgment design |
| [project-tests](.claude/skills/project-tests/SKILL.md) | Regression, build, browser checks, and setup recovery |
| [evaluate-detection](.claude/skills/evaluate-detection/SKILL.md) | Frozen object-detection evaluations |
| [evaluate-html-layout](.claude/skills/evaluate-html-layout/SKILL.md) | Frozen layout evaluations and calibration |

Skills use portable `SKILL.md` files. There are no hooks, permission bypasses, model overrides, or automatic live evaluation runs. Follow the authorized task scope when choosing paid inference.

## Project and code map

Jevision prototype is a community prototype using vanilla JavaScript, Python, and TypeSafe judgments. Models provide estimates; class-folder datasets do not supply object-count or box ground truth.

| Code | Responsibility |
|---|---|
| [web/app.js](web/app.js), [web/index.html](web/index.html), [web/styles.css](web/styles.css) | Shell, navigation, dataset editing, and appearance |
| [web/tools/count.js](web/tools/count.js) | Automatic counting and saved results |
| [web/tools/find.js](web/tools/find.js), [Find engine](web/tools/find/engine.js) | Controls, locate-one flow, locate-all strategies, and inspection |
| [web/tools/search.js](web/tools/search.js) | Page-level photo ranking |
| [web/layout.js](web/layout.js), [layout_renderer.py](layout_renderer.py) | HTML screenshot checks and isolated rendering |
| [web/shared.js](web/shared.js), [web/library.js](web/library.js) | State, helpers, workspace API/IndexedDB, images |
| [web/api.js](web/api.js), [web/image-assets.js](web/image-assets.js) | Multipart transport and image preparation |
| [server.py](server.py) | Local API, library, uploads, datasets, credentialed proxy |
| [scripts/setup.py](scripts/setup.py), [services.py](scripts/services.py), [run_server.py](scripts/run_server.py) | Installation, supervision, stop/reload |
| [benchmark_find.py](scripts/benchmark_find.py), [benchmark_layout.py](scripts/benchmark_layout.py) | Live evaluation and saved-result analysis |
| [frontend_modules.py](scripts/frontend_modules.py) | Frozen frontend dependency graphs |
| [tests/](tests/), [vite.config.js](vite.config.js) | Checks, build, ports, and proxy |

Dataset downloaders are `scripts/download_photo_datasets.py` and `scripts/download_design2code.py`. See [dataset provenance](docs/photo-datasets.md) and the [frontend map](docs/frontend-structure.md).

## Setup and commands

Requirements and effects are in [Quick start](README.md#quick-start). Use `pnpm run setup`, not pnpm's own `pnpm setup` command. Preserve existing keys and configured photo roots.

| Command | Purpose |
|---|---|
| `pnpm start` / `pnpm dev` | Vite + watched API |
| `pnpm stop` | Graceful project stop on Linux/WSL |
| `pnpm test` | Node/Python and mocked browser tests; no paid judgments |
| `pnpm build` | Production frontend |
| `pnpm start:prod` | Local built frontend/API |
| `pnpm check:public` | Files, history, build, and commit-identity privacy check |

Default frontend/API ports are 8765/8766. Shell values override `.env`; development needs distinct ports. Frontend edits reload; backend Python/`.env` edits restart the API. Results/downloads do not trigger restarts. See [service details](docs/development.md#running-and-stopping-services).

## Find implementation boundaries

- V1 has its own classify/localize loop. V2–V4 share `combined.js`, `prompts.js`, `geometry.js`, and `limits.js`, including version branches.
- Locate all with V6 is the initial UI selection, with five editable percentages; V4 remains the fixed comparison control. Cluster references do not count as individual objects.
- V5 is an independent evidence pipeline using scoped images, retained observations, and constrained identity resolution. Extent-review boxes differ from confirmed-by-checks results.
- V6 has a separate V4-based implementation under `web/tools/find/v6/`. Per-search overrides are validated/copied; editing them must not mutate V4 or shared defaults.
- `runtime.js` supplies injectable image/transport/progress boundaries. Engines must not boot the app or bind DOM events.

Preserve multipart names, API schemas, coordinate transforms, image isolation, ownership rules, and result states unless the task changes them. A Box question yields one box; crop composition and identity handling belong to code. Zero unresolved work does not establish full recall. See [Find design](docs/find-objects-design.md).

## Prototype scope documentation

Tool guides: [Count](docs/count-objects-design.md), [Find](docs/find-objects-design.md), [Search](docs/search-images-design.md), [HTML](docs/html-layout-design.md).

Update the relevant guide and README when behavior changes. Keep current defaults, disabled experiments, and proposals distinct. Describe actual question use and unoptimized policies; do not imply an API limitation from an omitted workflow or claim improvement without evidence.

## Local state and publication boundaries

| Location | Local content |
|---|---|
| `.env` | Credentials, ports, photo root |
| `.photo/`, `photos/`, `data/` | Example photos, uploads, HTML/reference pairs |
| `.jev-image-data/` | Library metadata, results, raw runs, private notes |
| `.jev-image-data/private-docs/` | Measured reports and experiment reviews |
| Browser IndexedDB `jev-image-library` | Legacy browser datasets/uploads |

Filesystem locations above are ignored. Preserve user data unless deletion is requested. Downloaders cannot restore custom uploads or judgment history. Scanning skips hidden subfolders unless configured as the root; HTML dataset images are excluded from photo tools.

The app is named Jevision prototype and described as a community prototype. Avoid
inventing product taglines or accuracy claims. Keep the legacy `.jev-image-data/` path,
`jev-image-library` database, and `jev-image-theme` preference key compatible with
existing installations.

Public docs describe methods/configuration without benchmark results or private-report links. The public photo manifest contains relative filenames and hashes, not pixels. Keep credentials server-side and out of browser modules, bundles, logs, and commits. Use project-relative paths in repository docs.

Before publishing, review `git status --short`, `git diff --cached`, and [SECURITY.md](SECURITY.md). Do not publish private snapshot refs, `.git`, or the entire workspace. Leave identity choices to the user.

## Making and verifying changes

1. Find the owning module and preserve unrelated version behavior.
2. Run focused checks for changed behavior. Use `pnpm test` for regression coverage and `pnpm build` after frontend changes.
3. After building, run `JEV_UI_TEST_ROOT=dist .venv/bin/python -m unittest tests.test_tool_modules -v` for the bundle.
4. Inspect optional browser/evaluation scripts before running them; some make paid calls. Distinguish software checks from accuracy evidence.

For accuracy work, freeze source, labels, actual model identity, and settings. Preserve historical runs and failures; never replace an unfavorable repeat. Independent labels and representative sources are required for accuracy claims. Follow [evaluation practice](docs/development.md#changing-detection-or-evaluation-settings).
