# HTML Layout Validator prototype design

Route: `/tools/qa`. Code: [layout.js](../web/layout.js), [API](../server.py), and [renderer](../layout_renderer.py).

## Purpose and current approach

Check visible defects in a screenshot:

1. Paste/upload HTML or choose a Design2Code pair. Select desktop (1280 × 900) or mobile (390 × 844). Expand **Optional checks** to list expected components; **Get example pages** contains the dataset download.
2. Render in a fresh offline Chromium context. Inline scripts/styles and embedded assets are allowed; external requests, local files, frames, forms, and popups are blocked.
3. Capture one viewport after a fixed delay, with screenshot animations disabled.
4. **Render preview** stops locally. **Validate layout** sends the prepared screenshot to `jev-1.14.0`.
5. Ask yes/no (Noul) questions for clipping, readability, and supplied requirements. A Choice distinguishes overlap-only, clipping-only, both, and neither. An optional reference adds a fidelity question.
6. Review the rendered page, reference (when loaded), and labeled probability scores. **How validation works** explains the checks, thresholds, and rendering restrictions. Export JSON with viewport, expected components, policy, thresholds, request, and response. Editing inputs clears the previous preview and report.

The overlap signal sums `overlap_only` and `both`. Multiple questions distinguish defect types; they do not locate defects or drive follow-up crops.

## What has not been optimized

- Targeted questions and higher-detail crops around suspected defects.
- Full-page scrolling, breakpoint sweeps, or hover/focus/modal states.
- Combining screenshot judgments with DOM geometry and keyboard/accessibility tests.
- General threshold calibration or an automatic HTML/CSS repair loop.

## Known limitations and controls

Hidden states, offscreen content, and late changes may be absent. Blocked or missing assets can make a page differ from its reference.

The policy flags overlap at .60, other checks at .70, and otherwise requests review above .30. These are decision thresholds. “No issues flagged” applies only to configured checks in this screenshot.

Users control source/example, viewport, expected components, preview/validation, and export. Prompts, thresholds, delay, and preparation are code settings. Renderer restrictions are intentional data-protection boundaries.

## Validation scope

Regression tests check questions, probability handling, clipping/overlap distinction, renderer restrictions, and UI wiring. Synthetic fixtures and reference pairs do not establish general accuracy or behavioral coverage. UI exports alone do not freeze screenshot/source hashes.

## How to experiment

Start with `buildLayoutRequest`, `layoutProbability`, `summarizeLayout`, and `LAYOUT_POLICY`. Follow the [layout evaluation workflow](development.md#reproduce-the-layout-evaluation): freeze screenshots, labels, model, and prompts; separate calibration from confirmation. Include clean, clipping-only, overlap-only, and combined-defect cases. Keep related viewports/repeats together and report each check separately.
