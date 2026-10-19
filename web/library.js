/**
 * Dataset storage and image access shared by the tools.
 * Combines workspace API datasets with IndexedDB datasets and preserves existing selection semantics.
 */
import { makeId, state, showToast } from "./shared.js";

export function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("jev-image-library", 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("datasets")) {
        request.result.createObjectStore("datasets", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open the local image library."));
  });
}

export function browserDatasets() {
  return new Promise((resolve, reject) => {
    const request = state.db.transaction("datasets", "readonly").objectStore("datasets").getAll();
    request.onsuccess = () => resolve(request.result.sort((a, b) => b.createdAt - a.createdAt));
    request.onerror = () => reject(request.error);
  });
}

export async function allDatasets() {
  // Workspace datasets are served by Python; browser-created datasets live in IndexedDB.
  // A browser storage failure should not hide the workspace library (especially on a
  // direct tool route, where the user expects the dataset selector to be ready).
  const [browserResult, apiResult] = await Promise.allSettled([
    state.db ? browserDatasets() : Promise.resolve([]),
    fetch("/api/library", { cache: "no-store" }),
  ]);
  const browser = browserResult.status === "fulfilled" ? browserResult.value : [];

  if (apiResult.status === "fulfilled") {
    const response = apiResult.value;
    const payload = await response.json().catch(() => ({}));
    if (response.ok) {
      return browser.concat(payload.datasets || []).sort((a, b) => b.createdAt - a.createdAt);
    }
    if (browser.length) return browser;
    throw new Error(payload.error || "Could not scan the workspace photo folder.");
  }

  if (browser.length) return browser;
  throw new Error("Could not load datasets from the workspace or browser storage.");
}

export async function saveDataset(dataset, { resultImage = null } = {}) {
  if (dataset.storage === "workspace") {
    const response = await fetch("/api/dataset-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: dataset.id,
        ...(resultImage
          ? { images: [{ path: resultImage.path, results: resultImage.results || [] }] }
          : { name: dataset.name, target: dataset.target }),
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Could not save dataset settings.");
    return dataset;
  }
  return new Promise((resolve, reject) => {
    const transaction = state.db.transaction("datasets", "readwrite");
    transaction.objectStore("datasets").put(dataset);
    transaction.oncomplete = () => resolve(dataset);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error("Could not save this dataset."));
  });
}

export function selectedDataset() {
  return state.datasets.find((dataset) => dataset.id === state.selectedDatasetId) || null;
}

export function selectedImage() {
  const dataset = selectedDataset();
  return dataset && dataset.images.find((image) => image.id === state.selectedImageId) || null;
}

export function objectUrl(image) {
  if (image.url) return image.url;
  if (!state.imageUrls.has(image.id)) state.imageUrls.set(image.id, URL.createObjectURL(image.blob));
  return state.imageUrls.get(image.id);
}

export async function uploadPhotos(datasetId, files) {
  const form = new FormData();
  form.append("datasetId", datasetId);
  validFiles(files).forEach((file) => form.append("photos", file, file.name));
  const response = await fetch("/api/dataset-photos", { method: "POST", body: form });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Could not copy photos into the workspace.");
  return payload.paths || [];
}

export function validFiles(fileList) {
  const files = Array.from(fileList || []);
  const valid = files.filter((file) => ["image/png", "image/jpeg"].includes(file.type));
  if (valid.length !== files.length) showToast("Only PNG and JPEG photos are supported.", true);
  if (valid.length > 25) showToast("Choose up to 25 photos at a time. The first 25 will be added.", true);
  return valid.slice(0, 25);
}

export function filesToImages(fileList) {
  return validFiles(fileList).map((file) => ({ id: makeId(), name: file.name, type: file.type, blob: file, addedAt: Date.now(), results: [] }));
}

export async function getImageBlob(image) {
  if (image.blob) return image.blob;
  if (!image.url) throw new Error("This photo is unavailable.");
  const response = await fetch(image.url);
  if (!response.ok) throw new Error("Could not read " + image.name + " from the workspace folder.");
  return response.blob();
}
