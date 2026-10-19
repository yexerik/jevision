/**
 * Application shell: initializes the library, routes between tools, and manages dataset editing.
 * Tool-specific rendering, events, and inference live in their own modules.
 */
import { sendImageJudgment } from "./api.js";
import { prepareImage } from "./image-assets.js";
import { initLayout } from "./layout.js";
import {
  openDatabase,
  browserDatasets,
  allDatasets,
  saveDataset,
  selectedDataset,
  objectUrl,
  uploadPhotos,
  validFiles,
  filesToImages,
} from "./library.js";
import { state, $, $$, showToast } from "./shared.js";
import { queueAutoCount, renderCountView, clearResult, bindCountEvents } from "./tools/count.js";
import { renderFindView, bindFindEvents } from "./tools/find.js";
import { renderSemanticSearchView, bindSearchEvents } from "./tools/search.js";

const VIEW_PATHS = { home: "/", count: "/tools/count", find: "/tools/find", search: "/tools/search", qa: "/tools/qa" };

function applyTheme(isDark) {
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) themeColor.content = isDark ? "#151a24" : "#f5f6f8";
  const button = $("#themeToggle");
  if (!button) return;
  const label = isDark ? "Light mode" : "Dark mode";
  button.setAttribute("aria-label", "Switch to " + label.toLowerCase());
  button.title = "Switch to " + label.toLowerCase();
  button.setAttribute("aria-pressed", String(isDark));
  button.querySelector("span[aria-hidden]").textContent = isDark ? "☀" : "☾";
  button.querySelector(".theme-toggle-label").textContent = label;
}

function toggleTheme() {
  const isDark = document.documentElement.dataset.theme !== "dark";
  applyTheme(isDark);
  try { localStorage.setItem("jev-image-theme", isDark ? "dark" : "light"); } catch { /* Theme still works for this session. */ }
}

function formatDate(date) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function viewFromPath(pathname = window.location.pathname) {
  const normalizedPath = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  return Object.entries(VIEW_PATHS).find(([, path]) => path === normalizedPath)?.[0] || "home";
}

function setView(name, { navigate = true } = {}) {
  if (!Object.hasOwn(VIEW_PATHS, name)) name = "home";
  const nextPath = VIEW_PATHS[name];
  if (navigate && window.location.pathname !== nextPath) window.history.pushState({ view: name }, "", nextPath);
  const labels = { home: "Overview", count: "Count objects", find: "Find objects", search: "Search images", qa: "Validate HTML layouts" };
  $$(".page-view").forEach((view) => view.classList.toggle("hidden", view.id !== ({ home: "homeView", count: "countView", find: "findView", search: "searchView", qa: "qaView" })[name]));
  $("#breadcrumbCurrent").textContent = labels[name] || "Overview";
  $$("[data-view]").forEach((button) => {
    const activeNavView = name === "home" ? "home" : "count";
    button.classList.toggle("active", button.dataset.view === activeNavView && button.classList.contains("nav-item"));
    button.classList.toggle("selected", button.dataset.view === name && button.classList.contains("tool-link"));
  });
  if (name === "count") renderCountView();
  if (name === "find") renderFindView();
  if (name === "search") renderSemanticSearchView();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setSelectedDataset(id) {
  clearTimeout(state.autoCountTimer);
  state.pendingAutoCount = false;
  clearResult();
  state.selectedDatasetId = id || "";
  const dataset = selectedDataset();
  state.selectedImageId = dataset && dataset.images[0] ? dataset.images[0].id : "";
  renderEverything();
  if (state.selectedImageId) queueAutoCount();
}

function renderEverything() {
  renderDatasetSelectors();
  renderDatasetNav();
  renderDatasetSummary();
  renderCountView();
  renderFindView();
  renderSemanticSearchView();
}

function renderDatasetSelectors() {
  const select = $("#datasetSelect");
  const current = state.selectedDatasetId;
  select.replaceChildren(new Option("Select a dataset", ""));
  state.datasets.forEach((dataset) => {
    select.add(new Option(dataset.name, dataset.id));
  });
  select.value = current;
  const dataset = selectedDataset();
  $("#activeTargetLabel").textContent = dataset ? "Each photo in this dataset is counted as " + (dataset.target || "cars") + "." : "Choose a dataset to see its count target.";
  $("#addPhotosButton").disabled = !dataset;
  $("#editDatasetButton").disabled = !dataset;
}

function renderDatasetNav() {
  const host = $("#datasetNav");
  host.replaceChildren();
  if (!state.datasets.length) {
    const empty = document.createElement("div");
    empty.className = "sidebar-empty";
    empty.textContent = "Your image sets will appear here";
    host.append(empty);
    return;
  }
  state.datasets.forEach((dataset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dataset-nav-item" + (dataset.id === state.selectedDatasetId ? " active" : "");
    button.innerHTML = '<span class="dataset-folder">▤</span><span class="dataset-nav-name"></span><span class="dataset-nav-count"></span>';
    button.querySelector(".dataset-nav-name").textContent = dataset.name;
    button.querySelector(".dataset-nav-count").textContent = String(dataset.images.length);
    button.addEventListener("click", () => {
      setSelectedDataset(dataset.id);
      setView("count");
    });
    host.append(button);
  });
}

function renderDatasetSummary() {
  $("#datasetCountPill").textContent = String(state.datasets.length);
  const host = $("#datasetSummaryGrid");
  host.replaceChildren();
  if (!state.datasets.length) {
    const empty = document.createElement("div");
    empty.className = "library-empty";
    empty.innerHTML = '<span class="empty-stack">▤</span><strong>No datasets yet</strong><span>Create a dataset and add photos to start exploring your images.</span><button type="button" class="inline-action" id="createFirstDataset">Create your first dataset <span>→</span></button>';
    empty.querySelector("button").addEventListener("click", openDatasetModal);
    host.append(empty);
    return;
  }
  state.datasets.forEach((dataset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dataset-card";
    const preview = dataset.images[0];
    button.innerHTML = '<span class="dataset-card-icon">▤</span><span class="dataset-card-copy"><strong></strong><small></small></span><span class="dataset-card-arrow">→</span>';
    if (preview) {
      const icon = button.querySelector(".dataset-card-icon");
      icon.replaceChildren();
      const img = document.createElement("img");
      img.src = objectUrl(preview);
      img.alt = "";
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = "cover";
      img.style.borderRadius = "inherit";
      icon.append(img);
    }
    button.querySelector("strong").textContent = dataset.name;
    button.querySelector("small").textContent = (dataset.target || "cars") + " · " + dataset.images.length + (dataset.images.length === 1 ? " photo" : " photos") + " · " + formatDate(new Date(dataset.createdAt));
    button.addEventListener("click", () => {
      setSelectedDataset(dataset.id);
      setView("count");
    });
    host.append(button);
  });
}

function openDatasetModal(datasetId = "") {
  const dataset = state.datasets.find((item) => item.id === datasetId) || null;
  state.editingDatasetId = dataset ? dataset.id : "";
  $("#datasetForm").reset();
  $("#fileSelectionSummary").textContent = "No photos selected";
  $("#modalTitle").textContent = dataset ? "Dataset settings" : "Create a dataset";
  $("#modalDescription").textContent = dataset ? "Update this dataset’s name and count target." : "Group photos around one counting target so every photo uses the same setting.";
  $("#datasetSubmitIcon").textContent = dataset ? "✓" : "＋";
  $("#datasetSubmitLabel").textContent = dataset ? "Save changes" : "Create dataset";
  $("#datasetPhotoUploadFields").classList.toggle("hidden", Boolean(dataset));
  $("#datasetName").value = dataset ? dataset.name : "";
  const target = dataset ? (dataset.target || "cars").trim() : "cars";
  const presets = ["cars", "people", "buses", "bicycles", "trucks", "whales"];
  const preset = presets.find((item) => item === target.toLowerCase());
  $("#datasetTarget").value = preset || "other";
  $("#customDatasetTarget").value = preset ? "" : target;
  $("#customDatasetTarget").classList.toggle("hidden", Boolean(preset));
  $("#customDatasetTarget").required = !preset;
  $("#datasetModal").classList.remove("hidden");
  $(dataset && !preset ? "#customDatasetTarget" : "#datasetName").focus();
}

function closeDatasetModal() {
  $("#datasetModal").classList.add("hidden");
  $("#datasetForm").reset();
  $("#fileSelectionSummary").textContent = "No photos selected";
  state.editingDatasetId = "";
}

async function createDataset(event) {
  event.preventDefault();
  const name = $("#datasetName").value.trim();
  if (!name) return;
  const chosenTarget = $("#datasetTarget").value === "other" ? $("#customDatasetTarget").value.trim() : $("#datasetTarget").value;
  if (!chosenTarget) return;
  const editingDataset = state.datasets.find((dataset) => dataset.id === state.editingDatasetId) || null;
  const selectedFiles = validFiles($("#datasetFiles").files);
  let dataset = editingDataset;
  try {
    if (editingDataset) {
      dataset.name = name;
      dataset.target = chosenTarget.toLowerCase();
      await saveDataset(dataset);
    } else {
      const response = await fetch("/api/datasets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, target: chosenTarget.toLowerCase() }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Could not create a workspace dataset.");
      if (selectedFiles.length) await uploadPhotos(payload.id, selectedFiles);
      dataset = { id: payload.id, storage: "workspace" };
    }
    state.datasets = await allDatasets();
    if (!editingDataset) {
      state.selectedDatasetId = dataset.id;
      const created = state.datasets.find((item) => item.id === dataset.id);
      state.selectedImageId = created && created.images[0] ? created.images[0].id : "";
    }
    closeDatasetModal();
    renderEverything();
    if (!editingDataset) {
      setView("count");
      const created = selectedDataset();
      showToast(created && created.images.length ? "Dataset created with " + created.images.length + " photos for " + created.target + "." : "Dataset created. Add photos whenever you’re ready.");
      if (created && created.images.length) queueAutoCount();
    } else {
      showToast("Dataset settings saved. This set now counts " + dataset.target + ".");
      queueAutoCount();
    }
  } catch (error) {
    showToast("Could not save this workspace dataset. " + error.message, true);
  }
}

async function addPhotos(fileList) {
  const dataset = selectedDataset();
  const files = validFiles(fileList);
  if (!dataset || !files.length) return;
  if (dataset.storage === "workspace") {
    try {
      const paths = await uploadPhotos(dataset.id, files);
      state.datasets = await allDatasets();
      const updated = state.datasets.find((item) => item.id === dataset.id);
      state.selectedImageId = updated && updated.images.find((image) => image.path === paths[0])?.id || "";
      renderEverything();
      showToast(paths.length + (paths.length === 1 ? " photo copied into the workspace." : " photos copied into the workspace."));
      if (state.selectedImageId) queueAutoCount();
    } catch (error) {
      showToast("Could not add photos. " + error.message, true);
    }
    return;
  }
  const images = filesToImages(files);
  dataset.images = dataset.images.concat(images);
  try {
    await saveDataset(dataset);
    state.datasets = await allDatasets();
    state.selectedImageId = images[0].id;
    renderEverything();
    showToast(images.length + (images.length === 1 ? " photo added." : " photos added."));
    queueAutoCount();
  } catch (error) {
    showToast("Could not add photos. " + error.message, true);
  }
}

async function refreshApiStatus() {
  const dot = $("#apiDot");
  const text = $("#apiStatusText");
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();
    if (health.apiKeyConfigured) {
      dot.className = "status-dot online";
      text.textContent = "API key configured";
    } else {
      dot.className = "status-dot offline";
      text.textContent = "API key needed";
    }
  } catch (error) {
    dot.className = "status-dot offline";
    text.textContent = "App server unavailable";
  }
}

function bindEvents() {
  bindCountEvents();
  bindFindEvents();
  bindSearchEvents();
  applyTheme(document.documentElement.dataset.theme === "dark");
  $("#themeToggle").addEventListener("click", toggleTheme);
  $$("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  $(".brand").addEventListener("click", (event) => { event.preventDefault(); setView("home"); });
  window.addEventListener("popstate", () => {
    const view = viewFromPath();
    if (window.location.pathname !== VIEW_PATHS[view]) window.history.replaceState({ view }, "", VIEW_PATHS[view]);
    setView(view, { navigate: false });
  });
  ["#topAddDataset", "#sidebarAddDataset", "#createDatasetHome", "#newDatasetButton", "#createFirstDataset"].forEach((selector) => {
    const button = $(selector);
    if (button) button.addEventListener("click", openDatasetModal);
  });
  $("#closeModal").addEventListener("click", closeDatasetModal);
  $("#cancelModal").addEventListener("click", closeDatasetModal);
  $("#datasetModal").addEventListener("click", (event) => { if (event.target === $("#datasetModal")) closeDatasetModal(); });
  $("#datasetForm").addEventListener("submit", createDataset);
  $("#datasetFiles").addEventListener("change", (event) => {
    const files = validFiles(event.target.files);
    $("#fileSelectionSummary").textContent = files.length ? files.length + (files.length === 1 ? " photo selected" : " photos selected") : "No photos selected";
  });
  $("#datasetSelect").addEventListener("change", (event) => setSelectedDataset(event.target.value));
  $("#editDatasetButton").addEventListener("click", () => openDatasetModal(state.selectedDatasetId));
  $("#datasetTarget").addEventListener("change", () => {
    const isOther = $("#datasetTarget").value === "other";
    $("#customDatasetTarget").classList.toggle("hidden", !isOther);
    $("#customDatasetTarget").required = isOther;
    if (isOther) $("#customDatasetTarget").focus();
  });
  $("#addPhotosButton").addEventListener("click", () => $("#addPhotosInput").click());
  $("#refreshLibraryButton").addEventListener("click", async () => {
    const selectedId = state.selectedDatasetId;
    try {
      state.datasets = await allDatasets();
      if (state.datasets.some((dataset) => dataset.id === selectedId)) state.selectedDatasetId = selectedId;
      else state.selectedDatasetId = "";
      const dataset = selectedDataset();
      if (!dataset || !dataset.images.some((image) => image.id === state.selectedImageId)) {
        state.selectedImageId = dataset && dataset.images[0] ? dataset.images[0].id : "";
      }
      renderEverything();
      showToast("Workspace folder rescanned.");
    } catch (error) {
      showToast("Could not rescan the workspace folder. " + error.message, true);
    }
  });
  $("#addPhotosInput").addEventListener("change", async (event) => { await addPhotos(event.target.files); event.target.value = ""; });
  $("#apiHelp").addEventListener("click", () => showToast("Add your key in the project .env file as TYPESAFE_API_KEY=… then restart the server."));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDatasetModal();
    }
  });
}

async function init() {
  $("#dateLabel").textContent = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" }).format(new Date()).toUpperCase();
  bindEvents();
  initLayout({ sendImageJudgment, prepareImage });
  const initialView = viewFromPath();
  if (window.location.pathname !== VIEW_PATHS[initialView]) window.history.replaceState({ view: initialView }, "", VIEW_PATHS[initialView]);
  setView(initialView, { navigate: false });
  refreshApiStatus();
  try {
    // Do not let a stalled IndexedDB open prevent workspace datasets from loading.
    const databasePromise = openDatabase();
    const databaseState = await Promise.race([
      databasePromise.then((db) => ({ db })).catch((error) => ({ error })),
      new Promise((resolve) => setTimeout(() => resolve({ timedOut: true }), 1500)),
    ]);
    state.db = databaseState.db || null;
    if (databaseState.error) console.warn("Browser dataset storage is unavailable; loading workspace datasets only.", databaseState.error);
    if (databaseState.timedOut) {
      console.warn("Browser dataset storage did not open in time; loading workspace datasets while it continues.");
      databasePromise.then(async (db) => {
        state.db = db;
        const browser = await browserDatasets();
        const workspace = state.datasets.filter((dataset) => dataset.storage === "workspace");
        state.datasets = browser.concat(workspace).sort((a, b) => b.createdAt - a.createdAt);
        renderEverything();
        setView(initialView, { navigate: false });
      }).catch((error) => console.warn("Browser dataset storage remains unavailable.", error));
    }
    state.datasets = await allDatasets();
    for (const dataset of state.datasets) {
      if (dataset.target) continue;
      const targetCounts = new Map();
      for (const image of dataset.images) {
        for (const result of image.results || []) {
          if (result.target) targetCounts.set(result.target, (targetCounts.get(result.target) || 0) + 1);
        }
      }
      dataset.target = [...targetCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "cars";
      await saveDataset(dataset);
    }
    state.datasets = await allDatasets();
    renderEverything();
    setView(initialView, { navigate: false });
  } catch (error) {
    console.error("Could not initialize the image library.", error);
    showToast("Could not load datasets: " + error.message, true);
  }
}

init();
