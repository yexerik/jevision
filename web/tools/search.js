/**
 * Search Images tool: scores the current page in six-image batches.
 * Uses Noul judgments for the query, then ranks and groups matches by probability.
 */
import { sendImageJudgment, prepareImageAssets } from "../api.js";
import { selectedDataset, objectUrl } from "../library.js";
import { fillDatasetSelect, state, $ } from "../shared.js";

export function renderSemanticSearchView() {
  const datasetSelect = $("#searchDatasetSelect");
  if (!datasetSelect) return;
  if (!state.datasets.some((dataset) => dataset.id === state.searchDatasetId)) state.searchDatasetId = selectedDataset()?.id || state.datasets[0]?.id || "";
  state.searchDatasetId = fillDatasetSelect(datasetSelect, state.searchDatasetId);
  datasetSelect.disabled = state.searchBusy;
  const dataset = state.datasets.find((item) => item.id === state.searchDatasetId) || null;
  $("#searchQuestionText").textContent = searchMatchQuestion();
  const criteria = searchMatchCriteria();
  $("#searchInstructionText").textContent = criteria.true + " " + criteria.false;
  const pageSizeSelect = $("#searchPageSize");
  pageSizeSelect.disabled = state.searchBusy;
  state.searchPageSize = Number(pageSizeSelect.value) || state.searchPageSize;
  const totalPages = Math.max(1, Math.ceil((dataset?.images.length || 0) / state.searchPageSize));
  state.searchPageIndex = Math.min(state.searchPageIndex, totalPages - 1);
  const pageStart = dataset?.images.length ? state.searchPageIndex * state.searchPageSize + 1 : 0;
  const pageEnd = dataset ? Math.min((state.searchPageIndex + 1) * state.searchPageSize, dataset.images.length) : 0;
  $("#searchPhotoCount").textContent = dataset ? (dataset.images.length ? "Photos " + pageStart + "–" + pageEnd + " of " + dataset.images.length : "No photos in this dataset") : "Choose a dataset.";
  $("#semanticSearchButton").disabled = !dataset || !dataset.images.length || state.searchBusy;
  $("#semanticSearchButton").innerHTML = state.searchBusy ? "Searching…" : 'Search images <span>↗</span>';
  $("#searchPageLabel").textContent = "Page " + (state.searchPageIndex + 1) + " of " + totalPages;
  $("#searchPreviousPage").disabled = !dataset || state.searchPageIndex === 0 || state.searchBusy;
  $("#searchNextPage").disabled = !dataset || state.searchPageIndex >= totalPages - 1 || state.searchBusy;
  if (state.searchResults.length) renderSemanticResults();
}

export function renderSemanticResults() {
  const host = $("#semanticSearchResults");
  host.replaceChildren();
  const queryHeading = document.createElement("div");
  queryHeading.className = "search-results-heading";
  const title = document.createElement("strong");
  const bestScore = state.searchResults[0]?.probability || 0;
  title.textContent = (bestScore < 0.4 ? 'No strong matches for “' : 'Matches on this page for “') + state.searchQuery + '”';
  const count = document.createElement("span");
  count.textContent = state.searchResults.length + " photos ranked · Page " + (state.searchPageIndex + 1);
  queryHeading.append(title, count);
  host.append(queryHeading);
  const groups = new Map();
  state.searchResults.forEach((result) => {
    const percent = Math.round(Math.max(0, Math.min(1, result.probability)) * 100);
    const band = Math.min(90, Math.floor(percent / 10) * 10);
    if (!groups.has(band)) groups.set(band, []);
    groups.get(band).push({ ...result, percent });
  });
  [...groups.entries()].sort((a, b) => b[0] - a[0]).forEach(([band, matches]) => {
    const section = document.createElement("section");
    section.className = "probability-band";
    const bandHeading = document.createElement("div");
    bandHeading.className = "probability-band-heading";
    const label = document.createElement("strong");
    label.textContent = band === 90 ? "90–100%" : band + "–" + (band + 9) + "%";
    const number = document.createElement("span");
    number.textContent = matches.length + (matches.length === 1 ? " photo" : " photos");
    bandHeading.append(label, number);
    const grid = document.createElement("div");
    grid.className = "probability-band-grid";
    matches.forEach(({ image, probability, percent }) => {
      const card = document.createElement("article");
      card.className = "semantic-result-card";
      const img = document.createElement("img");
      img.src = objectUrl(image);
      img.alt = image.name;
      const copy = document.createElement("div");
      copy.className = "semantic-result-copy";
      const name = document.createElement("strong");
      name.textContent = image.name;
      const dataset = state.datasets.find((item) => item.id === state.searchDatasetId);
      const sub = document.createElement("small");
      sub.textContent = dataset ? dataset.name : "";
      const badge = document.createElement("span");
      badge.className = "match-badge" + (probability >= 0.65 ? " likely" : probability >= 0.4 ? " possible" : " low");
      badge.textContent = percent + "% match";
      copy.append(name, sub);
      card.append(img, copy, badge);
      grid.append(card);
    });
    section.append(bandHeading, grid);
    host.append(section);
  });
}

export function searchMatchQuestion() {
  return "Does this photo match the visual search request in `query`?";
}

export function searchMatchCriteria() {
  return {
    true: "The requested object, scene, or visible detail is clearly present in the photo.",
    false: "The requested visual content is absent or cannot be identified in the photo.",
  };
}

export async function searchImages(event) {
  event.preventDefault();
  const dataset = state.datasets.find((item) => item.id === state.searchDatasetId);
  const query = $("#semanticSearchQuery").value.trim();
  if (!dataset || !query || state.searchBusy) return;
  state.searchPageSize = Number($("#searchPageSize").value) || 12;
  const pageStart = state.searchPageIndex * state.searchPageSize;
  const pageImages = dataset.images.slice(pageStart, pageStart + state.searchPageSize);
  if (!pageImages.length) return;
  state.searchBusy = true;
  state.searchQuery = query;
  state.searchResults = [];
  $("#semanticSearchResults").replaceChildren();
  $("#searchProgress").classList.remove("hidden");
  const batchSize = 6;
  const batches = Math.ceil(pageImages.length / batchSize);
  const collected = [];
  renderSemanticSearchView();
  try {
    for (let start = 0; start < pageImages.length; start += batchSize) {
      const batch = pageImages.slice(start, start + batchSize);
      const batchNumber = Math.floor(start / batchSize) + 1;
      $("#searchProgress").textContent = "Checking page " + (state.searchPageIndex + 1) + " · batch " + batchNumber + " of " + batches + " · " + Math.min(start + batch.length, pageImages.length) + " of " + pageImages.length + " photos";
      const { refs, uploads } = await prepareImageAssets(batch, 1024);
      const questions = {};
      refs.forEach(({ reference }, index) => {
        questions["match_" + index] = {
          type: "noul",
          instructions: searchMatchQuestion() + " Photo: " + reference,
          criteria: searchMatchCriteria(),
        };
      });
      const payload = await sendImageJudgment({
        model: "jev-latest",
        state: { query },
        assets: Object.fromEntries(refs.map(({ reference, part }) => [reference, { type: "image", part }])),
        questions,
      }, uploads);
      batch.forEach((image, index) => {
        const probability = payload.answers["match_" + index]?.noul;
        if (!Number.isFinite(probability) || probability < 0 || probability > 1) {
          throw new Error("The API did not return a valid match probability for every photo. Try the search again.");
        }
        collected.push({ image, probability });
      });
    }
    state.searchResults = collected.sort((a, b) => b.probability - a.probability);
    if (state.searchResults.length) renderSemanticResults();
    else {
      const empty = document.createElement("div");
      empty.className = "feature-empty";
      empty.innerHTML = '<span>⌕</span><strong>No results</strong><small>There were no photo results to rank.</small>';
      $("#semanticSearchResults").replaceChildren(empty);
    }
  } catch (error) {
    const message = document.createElement("div");
    message.className = "search-error";
    message.textContent = error.message || "Could not search this dataset.";
    $("#semanticSearchResults").replaceChildren(message);
  } finally {
    state.searchBusy = false;
    $("#searchProgress").classList.add("hidden");
    renderSemanticSearchView();
  }
}

export async function moveSearchPage(direction) {
  const dataset = state.datasets.find((item) => item.id === state.searchDatasetId);
  if (!dataset || state.searchBusy) return;
  const totalPages = Math.max(1, Math.ceil(dataset.images.length / state.searchPageSize));
  const nextPage = Math.max(0, Math.min(totalPages - 1, state.searchPageIndex + direction));
  if (nextPage === state.searchPageIndex) return;
  state.searchPageIndex = nextPage;
  state.searchResults = [];
  const query = $("#semanticSearchQuery").value.trim();
  if (query) {
    await searchImages({ preventDefault() {} });
  } else {
    $("#semanticSearchResults").innerHTML = '<div class="feature-empty"><span>⌕</span><strong>Search this page</strong><small>Enter a description to find matching photos on this page.</small></div>';
    renderSemanticSearchView();
  }
}

export function bindSearchEvents() {
  $("#searchDatasetSelect").addEventListener("change", (event) => {
    state.searchDatasetId = event.target.value;
    state.searchPageIndex = 0;
    state.searchResults = [];
    $("#semanticSearchResults").innerHTML = '<div class="feature-empty"><span>⌕</span><strong>Search your dataset</strong><small>Describe a visible object, scene, or detail to find matching photos.</small></div>';
    renderSemanticSearchView();
  });
  $("#searchPageSize").addEventListener("change", () => {
    state.searchPageSize = Number($("#searchPageSize").value) || 12;
    state.searchPageIndex = 0;
    state.searchResults = [];
    $("#semanticSearchResults").innerHTML = '<div class="feature-empty"><span>⌕</span><strong>Search this page</strong><small>Enter a description to find matching photos on this page.</small></div>';
    renderSemanticSearchView();
  });
  $("#searchPreviousPage").addEventListener("click", () => moveSearchPage(-1));
  $("#searchNextPage").addEventListener("click", () => moveSearchPage(1));
  $("#imageSearchForm").addEventListener("submit", searchImages);
}
