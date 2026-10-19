# Jevision prototype

A community prototype for counting and locating objects, searching photos, and checking HTML layouts with TypeSafe image judgments.

**V6 is the default Find All strategy and exposes editable settings. V5 and V6 remain experimental; V4 is the fixed comparison baseline.** Version numbers and model confidence do not establish accuracy.

Model operations send selected images/crops and questions to TypeSafe using your API key and can incur usage charges. The key stays on the Python server. Count automatically analyzes a photo when you select it.

## Quick start

Install Python 3.10+ with virtual-environment support, Node.js 22.12+, and pnpm 11. You also need your own TypeSafe API key. Run commands from the project root; examples use Linux/WSL shell paths.

```sh
pnpm run setup
```

Setup updates the virtual environment's pip, installs dependencies, checks Playwright Chromium, downloads example datasets, and creates an ignored `.env`. It needs internet access and disk space; Linux may request sudo for browser libraries. Setup makes no model calls. Rerunning it preserves existing credentials and configured photo roots.

Replace the placeholder in `.env`:

```dotenv
TYPESAFE_API_KEY=your_typesafe_api_key_here
```

Start the app and open [http://127.0.0.1:8765](http://127.0.0.1:8765):

```sh
pnpm start
```

Use **`pnpm run setup`**, including `run`; `pnpm setup` configures pnpm itself. See the [dataset guide](docs/photo-datasets.md) for separate downloads and installation recovery.

## Tools

Choose a dataset and photo. Dataset settings let you edit its name and target class.

| Tool | Current behavior and main limitation | Route | Details |
|---|---|---|---|
| Count objects | One whole-photo count question; exact options stop at 20, followed by 21+ | `/tools/count` | [Count design](docs/count-objects-design.md) |
| Find objects | Combines crop judgments into detections; small and crowded targets remain difficult | `/tools/find` | [Find design](docs/find-objects-design.md) |
| Search images | Ranks only the current page of photos, not the whole collection | `/tools/search` | [Search design](docs/search-images-design.md) |
| Validate HTML | Checks one rendered viewport, not every page state or interaction | `/tools/qa` | [HTML design](docs/html-layout-design.md) |

## Prototype scope

Each tool guide describes current question use, optimization gaps, limitations, and validation needs. Find, Search, and HTML validation already ask multiple questions; Count asks one count question. Spatial questions could guide crops or gather more evidence, but the app has no established policy proving those benefits. Missing application workflows are not limits on Jev's capabilities.

For HTML, paste or upload a page, choose a preview size, and select **Render preview** for a local screenshot or **Validate layout** to send it to TypeSafe. Expected components are under **Optional checks**; dataset downloads are under **Get example pages**. Results appear beside the source on wide screens and below it on smaller screens.

## Find objects: modes and versions

**Locate all → V6** is selected by default. Use the version selector to compare strategies, or choose **Locate one** to return at most one box:

| Version | Role | Numeric UI controls |
|---|---|---|
| V1–V3 | Historical comparison strategies | Fixed defaults |
| V4 | Comparison baseline; individual detections and clickable cluster references | Fixed defaults |
| V5 | Experimental verification and identity pipeline | Fixed defaults |
| **V6** | **Default**; experimental V4-based implementation | Five editable percentages |

To customize V6, open **Locate all → V6 → Advanced settings**. You can change count confidence for splitting, box confidence for checking, verification acceptance, same-object merge probability, and duplicate-box IoU. The [V6 guide](docs/find-objects-v6.md#advanced-settings) explains defaults and effects.

**Questions and instructions**, **About this version**, and **Understanding results** are collapsed by default. Open them when you want prompt details, version behavior, or definitions.

Settings reset on reload, lock during a search, and can be restored with **Reset to defaults**. Each V6 result records the settings used. Editing V6 does not change V4's preset. At default settings, V6 uses V4's detection policy; it does not claim better accuracy.

Cluster references and V5's dashed identity-review outlines do not add to the individual-object count. A completed scan does not prove that every object was found.

Below the result, click **Request JSON** or **Response JSON** to open a popup. Close it with **Close**, **Escape**, or a click outside to return to your place on the page. Crop previews stay on each card.

## Understanding the percentages

- **Model confidence/probability:** a model signal used by a decision rule, not measured accuracy.
- **Precision:** how many returned boxes match reference objects.
- **Recall:** how many reference objects receive a matching box.
- **IoU:** intersection over union, the overlap between two boxes.

Duplicate suppression compares **two predictions** and can remove boxes. Benchmark IoU compares **a prediction with a reference label** and changes scoring only. Benchmarks report IoU 0.50 as the primary standard and 0.30 as a localization diagnostic. Normal Find usage has no reference boxes to calculate precision or recall.

See [Understanding detection results](docs/detection-metrics.md) for examples and [configuration reference](docs/find-objects-design.md#configuration-reference) for fixed settings.

## Datasets and service configuration

Setup downloads ant/bee and sea-animal photos plus Design2Code HTML/reference pairs. Photos are version-pinned and hash-verified; [the dataset guide](docs/photo-datasets.md) lists sources and counts. Photo folders supply class labels, not audited object counts or boxes.

Add PNG/JPEG photos through the app, or place them under your photo root and select **Rescan folder**.

| `.env` setting | Default after setup | Purpose |
|---|---|---|
| `TYPESAFE_API_KEY` | Replace the placeholder | Server-side API authentication |
| `PHOTO_ROOT` | `.photo` | Photo collection root |
| `PORT` | `8765` | Frontend or production port |
| `API_PORT` | `8766` | Development API port |

Shell variables override `.env`. Development needs distinct frontend/API ports. Detection thresholds are not `.env` settings.

## Commands

| Command | Purpose |
|---|---|
| `pnpm run setup` | Install dependencies, Chromium, and datasets |
| `pnpm start` / `pnpm dev` | Start Vite and the watched Python API |
| `pnpm stop` | Stop project services gracefully on Linux/WSL |
| `pnpm test` | Run regression tests with mocked model responses |
| `pnpm build` | Build the frontend into `dist/` |
| `pnpm start:prod` | Serve the build and API locally; build first |
| `pnpm check:public` | Check files, public history, build output, and commit-email configuration |

Both servers bind to loopback. Publishing source to GitHub does not create an authenticated hosted service.

## Validation and limitations

```sh
pnpm test
pnpm build
JEV_UI_TEST_ROOT=dist .venv/bin/python -m unittest tests.test_tool_modules -v
```

These checks make no paid model calls and verify software behavior, not model accuracy. Live evaluation runners make real API calls; see [development and evaluation](docs/development.md) before using them.

[GitHub checks](.github/workflows/checks.yml) also run source tests, the production
build, bundled browser checks, and the public-file scan on pushes and pull requests.

Use independent labels for quality measurements. Counts can be wrong; detections can be missed, loose, duplicated, or incorrectly merged. HTML screenshots can omit hidden states or blocked assets. Each tool's design guide explains its validation scope.

## Troubleshooting

| Symptom | Action |
|---|---|
| Setup invokes pnpm configuration | Use `pnpm run setup` |
| Chromium cannot launch | Rerun setup and check missing-library diagnostics |
| API key is not configured | Replace the placeholder; check shell overrides |
| Port is occupied | Stop existing services or choose distinct unused ports |
| Same-origin request rejected | Use the frontend URL; keep the proxy's `changeOrigin: false`. See [troubleshooting](docs/development.md#same-origin-errors-in-development) |
| Advanced settings are missing | Select Locate all, then V6 |

## Before publishing to GitHub

Keep raw runs, screenshots, and API exchanges under `.jev-image-data/`, and written benchmark reports under `.jev-image-data/private-docs/`. The entire parent directory is ignored. Public docs describe methods and settings without including local benchmark results.

Credentials, photos, datasets, library metadata, dependencies, builds, and local agent settings are also ignored. Each clone supplies its own credentials. Keep separate backups of custom uploads and saved results.

```sh
pnpm check:public
git status --short
git diff --cached
```

If the check reports `public-commit-identity-not-configured`, configure your public name and GitHub noreply email using [SECURITY.md](SECURITY.md). `pnpm check:public --files-only` checks content while leaving identity unchecked.

Review the files being committed: ignores do not remove tracked files or history. Push the reviewed branch and intended tags. Do not use `git push --mirror` or upload the entire working directory. See [publication guidance](SECURITY.md) for private snapshot refs and other check limitations.

## Documentation

- [Tool guides](#tools): current behavior and prototype gaps.
- [V6 controls](docs/find-objects-v6.md): settings, defaults, and CLI overrides.
- [Development](docs/development.md): services, tests, and live evaluations.
- [Datasets](docs/photo-datasets.md): sources, installation, and attribution.
- [Frontend map](docs/frontend-structure.md): module responsibilities.
- [Agent context](Claude.md): contributor instructions; [Agent.md](Agent.md) links to the same file.
- [Shared skills](Claude.md#shared-project-skills): reusable test and integration workflows.

## License

The project's original source code and documentation are available under the
[MIT License](LICENSE). You may fork, use, modify, and redistribute them, including
commercially. Keep the copyright and license notice with copies or substantial
portions. You do not have to publish your changes. The software comes without warranty.

Third-party dependencies, fonts, and downloaded datasets retain their own licenses;
MIT does not relicense them. See [dataset sources and attribution](docs/photo-datasets.md).
TypeSafe API access is separate and requires your own key; service terms and usage
charges still apply.

Contributions are welcome; see [Contributing](CONTRIBUTING.md).
