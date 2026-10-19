# V6 configuration and development

V6 is the Locate-all UI default, an experimental V4 fork with five editable percentages and separate search, prompt, geometry, and limit files under `web/tools/find/v6/`. V4 remains selectable with fixed settings. At default gates, V6 preserves V4's detection policy; choosing it as the UI default or changing a gate does not establish better accuracy.

## Advanced settings

Open **Find objects → Locate all → V6 → Advanced settings**. Enter percentages from 0 to 100, including decimals.

| Control | Default | Effect of increasing it |
|---|---|---|
| Split regions below this count confidence | 25% | Subdivide more uncertain regions |
| Verify boxes below this box confidence | 50% | Request more verification; not a display cutoff |
| Minimum verification probability | 65% | Accept fewer checked boxes |
| Minimum same-object merge probability | 55% | Require stronger evidence to merge |
| Duplicate-box overlap threshold (IoU) | 50% | Suppress fewer pairs through this rule; other rules still apply |

Controls lock during searches. Empty/out-of-range inputs prevent starting one. **Reset to defaults** restores all five values; reload also resets overrides. Each result's **Settings used for this result** preserves its effective gates, fixed limits, and grid, even after later edits.

Other limits stay fixed: 2×2 initial grid, 16 tiles per batch, 255 counted tile regions, 96 API requests, and depth 7. A full-photo probe is additional. See [Find design](find-objects-design.md#configuration-reference) for geometry and fixed gates.

## Benchmark overrides

Both runners accept `--v6-config PATH.json`, with only the five supported keys as probabilities from 0 to 1:

```json
{
  "minChoiceConfidence": 0.25,
  "minBoxConfidence": 0.5,
  "minV3BoxCheckProbability": 0.7,
  "minDuplicatePairProbability": 0.55,
  "duplicateBoxIou": 0.5
}
```

For COCO, supply the flag when creating a fresh `snapshot`. For the real UI runner, supply it with `--versions v4 v6`; it edits the controls before V6 searches. Results retain effective settings, and scoring checks them against requested overrides. Historical snapshots remain readable.

Commands and label requirements are in [development and evaluation](development.md). Evaluation IoU .50/.30 remains separate from duplicate-box IoU.

## Prototype scope

Tunable gates do not add guided cropping or exhaustive discovery. See [Find optimization gaps](find-objects-design.md#prototype-scope-and-optimization-gaps). Priorities are body-box localization, additional-instance discovery, and identity handling for touching objects.

Develop in [v6.js](../web/tools/find/v6.js) and its helpers; keep V4 unchanged as a control. Default-policy tests compare requests/results and cleanup. Shared browser/API changes still need historical-version regressions. Measure new policies with fixed labels, model, and work limits; retain original observations and keep measured reports private.
