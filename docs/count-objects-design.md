# Count Objects prototype design

Route: `/tools/count`. Code: [count.js](../web/tools/count.js) and [image preparation](../web/image-assets.js).

## Purpose and current approach

Estimate the visible target count in one photo:

1. Photo selection schedules automatic counting.
2. Prepare the whole image as a resized/padded JPEG.
3. Ask one Choice question with options `0`–`20` and `21_plus`, using `jev-latest` through `/api/count-cars`. The endpoint name does not restrict the target to cars.
4. Display the chosen count, confidence, and alternatives. Ignore stale display results after selection changes.

Saving a count updates only that photo's results, preserving dataset edits and other
photos. The server serializes library writes and keeps the newest result per target
when another browser tab submits older data.
5. Save the target, answer, probabilities, confidence, and timestamp with the image.

Instructions include identifiable partial objects and exclude reflections, pictures, and toys. This flow produces no instance boxes.

## What has not been optimized

- Regional counting, guided zooming, and reconciliation across overlapping crops.
- Additional questions about presence, dense areas, or separate groups.
- Exact totals above twenty and category-specific preprocessing.
- Confidence calibration or model selection for each category.

These are experiment opportunities. Extra questions can increase cost or double-count objects.

## Known limitations and controls

Small, touching, hidden, or ambiguous targets can be miscounted despite high confidence. Users choose the photo and target; prompts and count options are fixed in code.

Saved counts are local history, not frozen benchmarks: they omit image hashes, prompt snapshots, and resolved model identity. A request to `jev-latest` alone does not fix the model used in a comparison.

## Validation scope

Mocked browser tests check requests, display, and saving. Quality evaluation needs independently checked counts, a partial-instance policy, negatives, and crowded examples. Report exact-count accuracy and count error; evaluate `21_plus` separately. Find box scores do not validate this estimator.

## How to experiment

Start with `countQuestion`, `countInstructions`, and `buildCriteria`. Compare one change at a time against the whole-photo baseline. For regional counting, audit overlap ownership and count reconciliation. Follow [evaluation practice](development.md#changing-detection-or-evaluation-settings), recording model identity, failures, usage, and timing.
