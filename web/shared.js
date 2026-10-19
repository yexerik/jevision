/**
 * Shared browser state and small UI/text helpers.
 * Tools share dataset selections through this object; importing this file does not start the app.
 */

export const state = {
  db: null,
  datasets: [],
  selectedDatasetId: "",
  selectedImageId: "",
  imageUrls: new Map(),
  busy: false,
  autoCountTimer: null,
  pendingAutoCount: false,
  editingDatasetId: "",
  findDatasetId: "",
  findImageIndex: 0,
  findMode: "all",
  findVersion: "v6",
  findV6Config: {},
  findSelectedClusterId: "",
  findBusy: false,
  findProgress: null,
  findResult: null,
  findError: "",
  findApiLog: [],
  searchDatasetId: "",
  searchBusy: false,
  searchResults: [],
  searchQuery: "",
  searchPageIndex: 0,
  searchPageSize: 12,
};

export const $ = (selector) => document.querySelector(selector);
export const $$ = (selector) => Array.from(document.querySelectorAll(selector));

export function makeId() {
  return globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : "id-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

export function singularize(value) {
  const irregular = { people: "person", buses: "bus", bicycles: "bicycle", cars: "car", trucks: "truck" };
  return irregular[value.toLowerCase()] || value.replace(/s$/i, "");
}

export function base64UrlSafeId() {
  return makeId().replace(/-/g, "").replace(/_/g, "");
}

export function fillDatasetSelect(select, currentId) {
  const current = state.datasets.some((dataset) => dataset.id === currentId) ? currentId : "";
  select.replaceChildren(new Option("Select a dataset", ""));
  state.datasets.forEach((dataset) => select.add(new Option(dataset.name + " · " + dataset.images.length + (dataset.images.length === 1 ? " photo" : " photos"), dataset.id)));
  select.value = current;
  return current;
}

export function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3600);
}
