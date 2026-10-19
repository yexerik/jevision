# Frontend module guide

`web/app.js` coordinates startup and navigation. Tool modules own their UI and requests; they do not initialize the application shell.

## Tools and application shell

| Module | Responsibility | Design notes |
|---|---|---|
| [app.js](../web/app.js) | Startup, theme, dataset editing, and view coordination | [Contributor guide](../Claude.md) |
| [count.js](../web/tools/count.js) | Automatic counting, display, and saved counts | [Count](count-objects-design.md) |
| [find.js](../web/tools/find.js) | Controls, locate-one flow, results, and API inspector | [Find](find-objects-design.md) |
| [search.js](../web/tools/search.js) | Six-image batches, page ranking, and pagination | [Search](search-images-design.md) |
| [layout.js](../web/layout.js) | HTML checks, dataset examples, and report export | [HTML](html-layout-design.md) |

Update the relevant design notes when changing request structure, controls, crop policy, or result meaning. They distinguish current behavior from proposed optimizations.

## Find Objects versions

[engine.js](../web/tools/find/engine.js) dispatches `runFindAll` to V1–V6. The UI selects V6 by default; V4 remains available with fixed settings.

| Files | Responsibility |
|---|---|
| [v1.js](../web/tools/find/v1.js) | Two-stage classification/localization |
| [v2.js](../web/tools/find/v2.js), [v3.js](../web/tools/find/v3.js), [v4.js](../web/tools/find/v4.js) | Historical version policies |
| [combined.js](../web/tools/find/combined.js) | Shared V2–V4 loop, including version branches |
| [prompts.js](../web/tools/find/prompts.js), [geometry.js](../web/tools/find/geometry.js), [limits.js](../web/tools/find/limits.js) | Historical questions, transforms, and gates |
| [v5.js](../web/tools/find/v5.js), [registry.js](../web/tools/find/registry.js) | Independent evidence and identity pipeline |
| [v6.js](../web/tools/find/v6.js) and `v6/` | Separate V4-based implementation and per-search configuration |
| [runtime.js](../web/tools/find/runtime.js) | Injectable browser/image/transport boundaries |

V2–V4 share helpers, so a change there can affect several versions. Develop V6 experiments in its own directory. Keep engines separate from DOM setup; tests replace I/O boundaries while exercising real search logic.

## Shared infrastructure

- [shared.js](../web/shared.js): state, DOM helpers, IDs, and selectors.
- [library.js](../web/library.js): workspace API/IndexedDB datasets and images.
- [api.js](../web/api.js): server-proxied multipart judgments and image batching.
- [image-assets.js](../web/image-assets.js): resize/padding and content transforms.

Design2Code screenshots are excluded from photo datasets; HTML uses separate endpoints. Preserve coordinate transforms, image/part references, and dataset/result isolation.

## Verification and evaluation compatibility

`pnpm test` covers ES modules, server/scoring contracts, snapshots, and mocked browser flows. Build with `pnpm build`, then check the bundle with `JEV_UI_TEST_ROOT=dist .venv/bin/python -m unittest tests.test_tool_modules -v`.

New Find snapshots hash the complete engine dependency graph and import it without app initialization. Historical monolithic snapshots retain their bridge. Preserve old artifacts; source changes need fresh live snapshots. See [development](development.md) for commands and [Find configuration](find-objects-design.md#configuration-reference) for policies.
