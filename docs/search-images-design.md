# Search Images prototype design

Route: `/tools/search`. Code: [search.js](../web/tools/search.js), [batch preparation](../web/api.js), and [image preparation](../web/image-assets.js).

## Purpose and current approach

Rank photos on the selected dataset page against a visual query:

1. Choose a dataset, query, and page size of 6, 12, or 24 photos; default 12.
2. Process that page sequentially in six-image batches, preparing images with a 1024-pixel maximum-dimension argument.
3. Request `jev-latest`, asking one yes/no match question (Noul) per photo in the batch. Each question names its image.
4. Sort scores within the page and display probability bands. The likely/possible boundaries are .65/.40; low-scoring photos remain ranked.
5. Moving pages with a nonempty query starts another page search. Results stay in the current view.

## What has not been optimized

- Collection-wide retrieval, indexing, caching, and global ranking across pages.
- Additional questions to locate small query details and select follow-up crops.
- Query decomposition, relevance feedback, and score calibration across queries.
- The quality/cost tradeoff between six-image batches and isolated-image requests.

Multiple questions are already used. Their current arrangement is not an established optimum for retrieval.

## Known limitations and controls

Relevant photos outside the current page do not compete for ranking. Resizing can hide small details, and query wording can affect scores. Probability bands do not establish search precision or recall.

Users control the dataset, query, page, and page size. Model, batch size, preparation resolution, and score bands are code settings.

Dataset and page-size controls lock during a search. Missing, nonfinite, or
out-of-range match probabilities produce an error instead of an incomplete ranking.

## Validation scope

Mocked browser tests cover submission, image/question mapping, pagination, and display. Ranking quality needs independent query/photo relevance labels and a fixed candidate collection. Report ranking measures such as precision at a chosen rank and recall over labeled candidates. A page test cannot establish collection-wide retrieval performance.

## How to experiment

Start with `searchMatchQuestion`, `searchMatchCriteria`, and `searchImages`. Compare question packaging on identical candidates before changing retrieval policy. For guided crops, retain full-image scores; for an index, measure shortlist misses too. Follow [evaluation practice](development.md#changing-detection-or-evaluation-settings) with search-specific labels, actual model identity, failures, usage, and timing.
