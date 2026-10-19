# Find Objects design and configuration

**V6 is the Locate-all UI default with editable settings; V4 is the fixed comparison baseline. V5/V6 remain experimental.** Use [the metrics guide](detection-metrics.md)
for terminology and [V6 controls](find-objects-v6.md) for editable settings. Code in
[the engine dispatcher](../web/tools/find/engine.js) is the implementation reference.

## Goal and modes

The control panel keeps the dataset, target, mode, and version visible. Expand
**Questions and instructions** for prompt details, **About this version** for strategy
behavior, or **Understanding results** for definitions. These sections start collapsed.

The API inspector below each result shows uploaded crops. Click **Request JSON** or
**Response JSON** to open a popup with wrapping JSON and its own scroll area. The
close button stays visible. Use **Close**, **Escape**, or a click outside to dismiss
it without losing your page position. An open response updates as it arrives.

**Locate one** sends a presence question and a Box question. Display requires
presence probability ≥ .50 and a valid mapped box. It does not use the version selector.

**Locate all** combines region judgments into individual detections. Each Box question
returns one box. Cluster references and unresolved review outlines are separate from
the individual count.

## Prototype scope and optimization gaps

Find already uses multiple questions. V2–V4/V6 combine count and individual Box
questions; V4/V6 add group boxes. V5 asks discovery, presence/extent, and identity
questions with image scoping. The open design questions are how those judgments
should guide a complete, efficient search:

- **Crop planning:** default discovery mainly uses geometric subdivision and count
  judgments. V5 has disabled positional/additional-instance experiments, but no
  established default spatial-guidance planner.
- **Instance coverage:** repeated Box questions can select the same prominent object
  or its fragments. Scanning every tile does not prove every object was localized.
- **Extent and identity:** refinement and duplicate handling can improve boxes or
  suppress real neighboring objects. Their combined effect needs reference labels.
- **Question packaging and budgets:** the benefit over a simple one-crop-per-request
  divide-and-conquer baseline is not established across representative photos.

These are application-policy gaps, not limits on Jev's question capabilities.
Compare packaging on fixed crops, then run complete searches to measure adaptive
changes. Keep new work in V6 and preserve V4 as a control. See
[evaluation practice](development.md#changing-detection-or-evaluation-settings).

## Strategy comparison

| Version | Initial cores | Main behavior |
|---|---|---|
| V1 | Four cores from two binary split rounds | Classify, then locate in separate requests |
| V2 | 2×2 | Combined Count/Box, binary subdivision |
| V3 | 3×3, with a small-image 2×2 fallback | Full-photo probe, refinement, identity checks |
| V4 | 2×2 | V3 detection machinery plus cluster references |
| V5 | Full photo plus 3×3 minimum scan | Recorded observations, verification, identity registry |
| V6 | 2×2 | Separate V4 fork with per-search gate overrides |

A core **owns** objects whose centers lie inside it. Its uploaded **crop** adds a
context halo. Initial/child halo fractions are V1 .06/.06, V2 .12/.12, V3 .16/.16,
and V4/V6 .14/.16. Add at least eight prepared-image pixels per edge and clip to
the parent crop. V1's split sequence can produce strips rather than a literal 2×2.

## V1 — classify regions, then locate

1. Classify each crop as `none`, `one`, or `several`.
2. Subdivide crowded, unknown, or low-confidence regions; locate `one` regions in a
   separate batched Box request.
3. Verify weak boxes, map coordinates, enforce ownership, and suppress duplicates.

The prompts describe the crop without an ownership marker; code checks ownership
afterward. A valid candidate owned by another core is dropped rather than retried.
V1 reserves request capacity for localization after classification.

## V2 — combine Count + Box on overlapping tiles

Ask count and individual Box together, with a blue outline marking the owned core.
Keep a box only for count `one`; split `several`, uncertain, invalid, or out-of-core
results along the longer side. A coarse `none` below .60 confidence also retries at
depths 1–2. Deeper regions retain the shared .25 floor. Apply weak-box verification
and geometric duplicate suppression.

## V3 — full-photo probe, grid subdivision, and refinement

- **Grid:** use 2×2 with binary splitting if either proposed 3×3 core dimension would
  be below 220 unpadded pixels; otherwise retain 3×3. The strategy is copied per run.
- **Probe:** the first batch includes the full photo. Count `one` at confidence ≥ .80
  with a valid root-owned box processes that candidate and skips the batch's tile
  answers. Those tiles were already uploaded; box verification still applies.
- **Counts:** request `none`, `one`, `two`, `three_or_more`; accept legacy `several`.
- **Splitting:** use quadrants while each child's shorter side can remain ≥ 96
  prepared pixels; otherwise split along the longer side. V2's .60 empty retry
  does not apply.
- **Refinement:** weak boxes get verification plus a tighter Box question. Replace
  the old box only when the new area is below 85%, its center is within an 8%-padded
  old boundary, and at least 70% of the new area intersects the old box.
- **Identity:** geometrically suppress duplicates, then check selected ambiguous pairs.

## V4 — cluster references and zoomed findings

V4 uses V3's probe, count categories, refinement, and identity checks on a 2×2 grid.
Each tile also gets a group Box question. For a confident multi-object count, retain
that group reference and keep subdividing for individuals.

Cluster boxes need valid mapped geometry but have no separate confidence gate.
Suppress nested references using ownership-core containment. Number retained groups
C1, C2, …; clicking one shows its ownership-core crop and accepted individual boxes.
Membership is based on individual box centers. A group reference never completes the
search or adds to the object count.

## Shared thresholds, geometry, and budgets

The [configuration reference](#configuration-reference) lists gates and limits.
Images and crops are resized/padded before inference. Map answers through upload
content bounds into prepared-image coordinates, then back to photo coordinates.
Root ownership excludes padding. Neighboring cores use half-open right/bottom edges,
except at the outer image boundary, to avoid owning the same center twice.

### Duplicate handling

Historical strategies sort by Box confidence, then verification probability.
Geometric suppression uses IoU ≥ .50, plus a second rule for overlapping source
crops: at least 20% of the smaller predicted box overlaps and centers are within a
scale-dependent tolerance. This can confuse nearby distinct objects.

V3/V4/V6 check remaining ambiguous pairs selected by source overlap, distance, shared
area, and gaps. A `same` answer at probability ≥ .55 merges them. At least 55%
smaller-box coverage keeps a preferred observation; otherwise the code unions their
boxes. Preference uses Box confidence, verification probability, then smaller area.
V6's two duplicate gates can be overridden per search.

### Incomplete results and inspection

Failed subdivision, work/depth limits, uncertain checks, and a remaining queue can
leave unresolved work. The UI reports “at least N located” and exposes requests,
responses, and uploaded crops. Zero unresolved regions means no recorded pending
work; a confident wrong judgment can still hide a miss.

V5 separately exposes extent review and unresolved identity outlines. Its ten-region
default funds the full photo and nine initial tiles, leaving queued child work
unsearched. See the V5 configuration below.

## Evaluation and known limitations

Small/blurred targets, occlusion, crop seams, fragments, and touching objects need
explicit test coverage. The [scorer](../scripts/score_boxes.py) uses one-to-one
matching at IoU .50, with .30 as a localization diagnostic. Group usefulness and false
identity merges need separate audits.

Mocked tests establish software behavior. Independent reference boxes, scene-separated
development/confirmation sources, actual model identity, and repeated live runs are
needed for quality measurements. Agent-drawn references remain exploratory; repeats
measure variability rather than additional independent sources. Keep measured reports
and raw evidence in ignored local folders.

## Implementation map and API references

- [find.js](../web/tools/find.js): controls, locate-one flow, results, and inspector.
- [Engine](../web/tools/find/engine.js): dispatches V1–V6; [combined.js](../web/tools/find/combined.js)
  implements the shared V2–V4 loop.
- [Prompts](../web/tools/find/prompts.js), [geometry](../web/tools/find/geometry.js), and
  [limits](../web/tools/find/limits.js): historical wording, transforms, and gates.
- [V5](../web/tools/find/v5.js): independent evidence pipeline; [V6](../web/tools/find/v6.js)
  and its helper directory: isolated V4-based development.
- [Frontend map](frontend-structure.md): shared infrastructure and snapshot handling.
- TypeSafe primitives: [Box](https://docs.typesafe.ai/primitives/box),
  [Choice](https://docs.typesafe.ai/primitives/choice), [Noul](https://docs.typesafe.ai/primitives/noul).

## Configuration reference

For definitions and worked examples, start with
[Understanding detection results](detection-metrics.md). Defaults below describe
current code, not calibrated accuracy guarantees. The UI exposes the dataset/photo, target in dataset settings, mode and
Locate-all strategy. V6 has five percentage inputs under Advanced settings; other
versions retain their fixed numeric gates. Locate all is initially selected with V6.
There are no detection-threshold `.env` variables.

### Locate one and historical V1–V4

| Setting and source | Default | Effect of increasing it |
|---|---|---|
| Locate-one presence probability in [find.js](../web/tools/find.js) | .50 | Requires stronger presence evidence before displaying its box; may hide true targets as well as false ones. A valid mapped box is still required. |
| `minChoiceConfidence` in [limits.js](../web/tools/find/limits.js) | .25 | More uncertain region classifications trigger subdivision, consuming work budget. This is Choice confidence, not `P(none)`. |
| `minBoxConfidence` | .50 | More candidate boxes require extra verification. This is a checking trigger, not a universal box rejection threshold. |
| `minBoxCheckProbability` | .70 in V1/V2 | Fewer weak boxes pass verification; rejected candidates may cause further subdivision. |
| `minV3BoxCheckProbability` | .65 in V3/V4 | Same effect for V3/V4. It is a Noul probability, not a measured precision percentage. |
| Full-photo shortcut in [combined.js](../web/tools/find/combined.js) | Choice `one`, confidence ≥ .80 in V3/V4, valid root-owned box | Fewer global single-object shortcuts; more tile processing. Normal weak-box verification still applies. |
| `duplicateBoxIou` | .50 | Fewer pairs qualify for this geometric suppression rule. Other overlap/center rules still apply. This compares predictions, not reference labels. |
| `duplicateBoxCoverage` | .20 of the smaller prediction | Fewer overlapping predictions qualify for the additional geometric duplicate heuristic. |
| `minDuplicatePairProbability` | .55 for `P(same)` in V3/V4 | Fewer model-assisted merges. May preserve duplicates as well as avoid incorrect merges; geometric suppression has already run. |
| `maxRegions` / `maxApiRequests` / `maxDepth` | 255 / 96 / 7 | Permits more discovery work; can increase latency/cost. API-request accounting in these historical engines is not V5's explicit HTTP-attempt budget. |

V2 separately retries coarse `none` classifications with confidence below .60 at
specified depths; see [v2.js](../web/tools/find/v2.js). V3/V4 do not inherit that rule.
V4 cluster outlines have no separate Box-confidence gate and do not count as objects.
The [strategy comparison](#strategy-comparison) describes the fixed layouts/halos.

### Experimental V6 user overrides

V6 uses the V4 baseline gates with per-search overrides for five percentages.
[The V6 guide](find-objects-v6.md#advanced-settings) owns the control/default table,
reset behavior, and benchmark JSON keys. All other budgets and geometry stay fixed.

### Experimental V5

[V5_CONFIG in v5.js](../web/tools/find/v5.js) is the source of truth. For a new
benchmark snapshot, `--config PATH.json` supplies V5 runtime overrides. That does not
change UI defaults or already frozen experiments. See the [development workflow](development.md#changing-detection-or-evaluation-settings).

| Setting | Current default | What changing it does |
|---|---|---|
| `rows` / `columns` | 3 / 3 | Changes minimum tile coverage. The full-photo probe is additional and cannot cancel these tiles. |
| `halo` | .18 | Fraction of core width/height added on each side, at least eight source pixels and clipped to the parent. This is not an “18% adjacent overlap” definition. Larger values supply more context but may produce repeated observations. |
| `maxRegions` / `maxDepth` / `batchSize` | 10 / 2 / 6 | Caps discovery, subdivision depth and regions per request. Ten regions fund the root plus nine minimum tiles, leaving no budget for queued child tiles; increasing depth alone does not fund further discovery. |
| `aggregatePresence` | `true` | Uses `1 − P(none)` for candidate presence. Uncertainty between one/two/three-or-more does not reject a box by itself. `false` reproduces the earlier winning-count gate for comparisons. |
| `discoveryGate` | .50 | Requires stronger candidate presence evidence, independent of certainty about the exact count. Every valid returned box is still recorded before this gate; fixed-response replay can inspect subsequent acceptance decisions. |
| `presenceGate` | .75 | Higher values accept fewer candidates after clean-crop presence checks. Rejected observations remain recorded. |
| `sameGate` / `differentGate` | .80 / .80 | Higher values establish fewer same/different relationships, increasing unresolved work. They are separate decisions; strong same evidence must respect existing different-instance constraints. |
| `completenessGate` | .60 | Higher values mark fewer boxes as passing the current extent checks. The score is `1 − max(four edge-cut probabilities)`, not a calibrated probability that every edge is correct. |
| `strictCompleteness` | `false` | If enabled, candidates below the extent gate are withheld rather than displayed for review. With the default, they appear in `boxes` and `localizationReview`, but not `confirmedCount`. |
| `refine` | `false` | Enables experimental recentered Box refinement when true. It is off by default; enabling it changes the search policy and needs evaluation. |
| `contextFactor` / `cleanRefinement` / `refinementIdentityGate` | 2.5 / `true` / .80 | Controls optional refinement context, annotations and same-instance acceptance. Context factor multiplies each box dimension, not area. |
| `scopedImages` | `true` | Each question sees its own crop; disabling it restores shared-image state for controlled ablations. It is not recommended as a user preference. |
| `maxAttempts` / `maxInputTokens` | 96 / 100,000 | Caps HTTP attempts, including retries, and sets a returned-input-token stopping target. The next request is estimated before sending; a response can overshoot the token estimate. Unknown usage stops further V5 requests. |
| `reserveFraction` | .40 | Reserves discovery allowance for subsequent verification/identity work. Increasing it may leave more discovery incomplete while funding checks. |

V5 merges retain their observations and can be recomputed. Ambiguous identities are
withheld from the individual count but shown separately as dashed review outlines.
`auditAllCandidates` and `auditAllPairs` request additional diagnostic checks.
Adaptive discovery, source-based pair nomination, extra positional Box attempts and
multiplicity rejection remain disabled by default. Saved-result replay cannot supply missing judgments or simulate new adaptive crops. The selected box within a resolved group comes
from an existing checked observation; it is not an invented union of boxes.

### Evaluation settings are separate

[benchmark_find.py](../scripts/benchmark_find.py) explicitly scores saved predictions
at **IoU .50** and **IoU .30**. IoU .50 is the primary quality standard; .30 diagnoses
looser localization. The generic [scorer](../scripts/score_boxes.py) takes a threshold
in `score(truth, predictions, threshold)`; its CLI reports both existing standards.
There is currently no UI or CLI IoU slider in the benchmark runner.

Raising evaluation IoU usually removes valid matches, lowering precision/recall;
it never changes the underlying predictions. Raising a model gate changes inference
behavior and must be measured with fresh complete searches. Defaults or display
colors must never be described as guaranteed precision or recall.
