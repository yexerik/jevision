/**
 * Count Objects tool: photo selection, automatic counting, and saved count results.
 * Sends a count Choice for the selected image and avoids showing stale results after selection changes.
 */
import { prepareImage } from "../image-assets.js";
import { allDatasets, saveDataset, selectedDataset, selectedImage, objectUrl } from "../library.js";
import { singularize, base64UrlSafeId, state, $, $$, showToast } from "../shared.js";

export function setSelectedImage(id) {
  if (!id) return;
  if (state.selectedImageId === id) return scrollSelectedPhotoIntoView();
  state.selectedImageId = id;
  clearResult();
  updatePhotoSelection();
  updatePhotoSlider();
  updateCountButton();
  scrollSelectedPhotoIntoView();
  queueAutoCount();
}

export function updatePhotoSelection() {
  $$(".photo-tile").forEach((tile) => {
    const selected = tile.dataset.imageId === state.selectedImageId;
    tile.classList.toggle("selected", selected);
    tile.setAttribute("aria-pressed", String(selected));
    let label = tile.querySelector(".photo-selected-label");
    if (selected && !label) {
      label = document.createElement("span");
      label.className = "photo-selected-label";
      label.textContent = "Selected";
      tile.append(label);
    } else if (!selected && label) label.remove();
  });
}

export function scrollSelectedPhotoIntoView() {
  const tile = $$(".photo-tile").find((item) => item.dataset.imageId === state.selectedImageId);
  if (tile) requestAnimationFrame(() => tile.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" }));
}

export function updatePhotoSlider() {
  const dataset = selectedDataset();
  const images = dataset ? dataset.images : [];
  const index = images.findIndex((image) => image.id === state.selectedImageId);
  const controls = $("#photoSliderControls");
  const slider = $("#photoSlider");
  const position = $("#photoSliderPosition");
  controls.classList.toggle("hidden", images.length === 0);
  slider.max = String(Math.max(0, images.length - 1));
  slider.value = String(Math.max(0, index));
  slider.disabled = images.length < 2;
  position.textContent = images.length ? (index < 0 ? "Choose a photo" : (index + 1) + " / " + images.length) : "0 photos";
  $("#previousPhotoButton").disabled = index <= 0;
  $("#nextPhotoButton").disabled = index < 0 || index >= images.length - 1;
}

export function selectPhotoAt(index) {
  const dataset = selectedDataset();
  if (!dataset || !dataset.images.length) return;
  const safeIndex = Math.max(0, Math.min(dataset.images.length - 1, Number(index)));
  setSelectedImage(dataset.images[safeIndex].id);
}

export function queueAutoCount(delay = 400) {
  clearTimeout(state.autoCountTimer);
  state.autoCountTimer = setTimeout(() => {
    const image = selectedImage();
    const target = targetName();
    if (!image || !target) return;
    if (state.busy) {
      state.pendingAutoCount = true;
      return;
    }
    state.pendingAutoCount = false;
    countObjects();
  }, delay);
}

export function renderCountView() {
  if (!$("#countView")) return;
  const dataset = selectedDataset();
  renderPhotoGrid();
  const target = dataset ? (dataset.target || "cars").trim() : "";
  $("#countQuestionText").textContent = target ? countQuestion(target) : "Select a dataset to see the count question.";
  $("#countInstructionText").textContent = target ? countInstructions(target) : "The dataset target determines which objects are counted.";
  $("#photoPanelSubhead").textContent = dataset ? dataset.name + " · " + dataset.images.length + (dataset.images.length === 1 ? " photo" : " photos") : "Select a dataset to see its images.";
  $("#photoCountFoot").textContent = dataset ? dataset.images.length + (dataset.images.length === 1 ? " photo" : " photos") : "0 photos";
  $("#addPhotosButton").disabled = !dataset;
  updatePhotoSlider();
  updateCountButton();
}

export function renderPhotoGrid() {
  const host = $("#photoGrid");
  if (!host) return;
  const dataset = selectedDataset();
  host.replaceChildren();
  if (!dataset || !dataset.images.length) {
    const empty = document.createElement("div");
    empty.className = "photo-grid-empty";
    empty.innerHTML = '<span>▧</span><strong>' + (dataset ? "This dataset has no photos" : "Your photos live here") + '</strong><small>' + (dataset ? "Add photos to this dataset to view them here." : "Select a dataset or create one to add images.") + "</small>";
    host.append(empty);
    return;
  }
  dataset.images.forEach((image) => {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "photo-tile" + (image.id === state.selectedImageId ? " selected" : "");
    tile.dataset.imageId = image.id;
    tile.setAttribute("aria-label", "Select " + image.name);
    tile.setAttribute("aria-pressed", String(image.id === state.selectedImageId));
    const img = document.createElement("img");
    img.src = objectUrl(image);
    img.alt = "";
    const name = document.createElement("span");
    name.className = "photo-name";
    name.textContent = image.name;
    tile.append(img, name);
    if (image.id === state.selectedImageId) {
      const selectedLabel = document.createElement("span");
      selectedLabel.className = "photo-selected-label";
      selectedLabel.textContent = "Selected";
      tile.append(selectedLabel);
    }
    tile.addEventListener("click", () => setSelectedImage(image.id));
    host.append(tile);
  });
  scrollSelectedPhotoIntoView();
}

export function targetName() {
  const dataset = selectedDataset();
  return dataset ? (dataset.target || "cars").trim() : "";
}

export function countQuestion(target) {
  return "How many distinct real " + target + " are visibly present in `photo`?";
}

export function countInstructions(target) {
  return "Count each visible " + singularize(target) + " once. Include a partially visible one only if it is identifiable. Do not count reflections, depictions in pictures, or toys. Choose the exact count, or 21_plus for 21 or more.";
}

export function updateCountButton() {
  const button = $("#countButton");
  const image = selectedImage();
  const target = targetName();
  button.disabled = !image || !target || state.busy;
  const label = button.querySelector("span:nth-child(2)");
  label.textContent = state.busy ? "Asking Jev…" : "Count " + (target || "objects") + " again";
  button.querySelector(".button-arrow").textContent = state.busy ? "···" : "↗";
}

export function clearResult() {
  $("#resultCard").classList.add("hidden");
  $("#resultCard").replaceChildren();
  $("#errorMessage").classList.add("hidden");
  $("#errorMessage").textContent = "";
}

export function buildCriteria(target) {
  const singular = singularize(target);
  const criteria = {};
  for (let count = 0; count <= 20; count += 1) {
    const description = count === 0 ? "No " + target + " are visible." : count + " " + (count === 1 ? singular : target) + " are visible.";
    criteria[String(count)] = description;
  }
  criteria["21_plus"] = "21 or more distinct " + target + " are visible.";
  return criteria;
}

export async function countObjects() {
  const image = selectedImage();
  const target = targetName();
  if (!image || !target || state.busy) return;
  clearTimeout(state.autoCountTimer);
  state.pendingAutoCount = false;
  clearResult();
  state.busy = true;
  updateCountButton();
  const requestDataset = selectedDataset();
  const requestImage = image;
  const requestImageId = image.id;
  const requestDatasetId = requestDataset.id;
  const requestTarget = target;
  const isCurrentSelection = () => state.selectedDatasetId === requestDatasetId && state.selectedImageId === requestImageId && targetName() === requestTarget;
  try {
    const sourceBlob = image.blob || (image.url ? await fetch(image.url).then((response) => {
      if (!response.ok) throw new Error("Could not read this photo from the workspace folder.");
      return response.blob();
    }) : null);
    if (!sourceBlob) throw new Error("This photo is unavailable.");
    const prepared = await prepareImage(sourceBlob);
    const reference = base64UrlSafeId();
    const requestBody = {
      model: "jev-latest",
      state: { photo: reference },
      assets: { [reference]: { type: "image", part: "photo-file" } },
      questions: {
        object_count: {
          type: "choice",
          instructions: countQuestion(target) + " " + countInstructions(target),
          criteria: buildCriteria(target),
        },
      },
    };
    const form = new FormData();
    form.append("request", new Blob([JSON.stringify(requestBody)], { type: "application/json" }));
    form.append("photo-file", prepared, "photo.jpg");
    const response = await fetch("/api/count-cars", { method: "POST", body: form });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.error || payload.message || (payload.detail && JSON.stringify(payload.detail)) || "TypeSafe could not analyze this photo.";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const answer = payload.answers && payload.answers.object_count;
    if (!answer || answer.type !== "choice" || typeof answer.choice !== "string") throw new Error("The API returned an unexpected answer format.");
    if (isCurrentSelection()) displayResult(answer, target);
    if (requestDataset && requestImage) {
      requestImage.results = (requestImage.results || []).filter((result) => result.target !== target);
      requestImage.results.unshift({ target, choice: answer.choice, confidence: answer.confidence, probabilities: answer.probabilities, createdAt: Date.now() });
      await saveDataset(requestDataset, { resultImage: requestImage });
      state.datasets = await allDatasets();
    }
  } catch (error) {
    if (isCurrentSelection()) {
      $("#errorMessage").textContent = error.message || "Something went wrong while counting objects.";
      $("#errorMessage").classList.remove("hidden");
    }
  } finally {
    state.busy = false;
    updateCountButton();
    if (state.pendingAutoCount) queueAutoCount(0);
  }
}

export function displayResult(answer, target) {
  const result = $("#resultCard");
  result.replaceChildren();
  result.classList.remove("hidden");
  const countLabel = answer.choice === "21_plus" ? "21+" : answer.choice;
  const confidenceScore = Number(answer.confidence) || 0;
  const confidence = Math.round(confidenceScore * 100);
  const confidenceClass = confidenceScore >= 0.7 ? "confidence-high" : confidenceScore >= 0.5 ? "confidence-medium" : "confidence-low";
  result.classList.remove("confidence-high", "confidence-medium", "confidence-low");
  result.classList.add(confidenceClass);
  const top = document.createElement("div");
  top.className = "result-top";
  const heading = document.createElement("div");
  heading.innerHTML = '<div class="result-kicker">JEV ESTIMATE</div><div class="result-count"></div><div class="result-sub"></div>';
  heading.querySelector(".result-count").append(document.createTextNode(countLabel));
  const noun = document.createElement("small");
  noun.textContent = countLabel === "1" ? singularize(target) : target;
  heading.querySelector(".result-count").append(noun);
  heading.querySelector(".result-sub").textContent = "Most likely visible count";
  const confidenceChip = document.createElement("span");
  confidenceChip.className = "confidence-chip";
  confidenceChip.textContent = confidence + "% confidence";
  top.append(heading, confidenceChip);
  result.append(top);
  if (answer.probabilities && typeof answer.probabilities === "object") {
    const title = document.createElement("div");
    title.className = "probability-title";
    title.textContent = "LIKELIHOOD BY COUNT";
    result.append(title);
    const list = document.createElement("div");
    list.className = "probability-list";
    Object.entries(answer.probabilities).sort((a, b) => b[1] - a[1]).slice(0, 3).forEach(([count, probability]) => {
      const row = document.createElement("div");
      row.className = "probability-row";
      const label = document.createElement("span");
      label.textContent = count === "21_plus" ? "21+" : count;
      const track = document.createElement("span");
      track.className = "probability-track";
      const fill = document.createElement("span");
      fill.className = "probability-fill";
      fill.style.display = "block";
      fill.style.width = Math.max(0, Math.min(100, Number(probability) * 100)) + "%";
      track.append(fill);
      const percent = document.createElement("span");
      percent.textContent = Math.round(Number(probability) * 100) + "%";
      row.append(label, track, percent);
      list.append(row);
    });
    result.append(list);
  }
}

export function bindCountEvents() {
  $("#countButton").addEventListener("click", countObjects);
  $("#photoSlider").addEventListener("input", (event) => selectPhotoAt(event.target.value));
  $("#previousPhotoButton").addEventListener("click", () => selectPhotoAt(Number($("#photoSlider").value) - 1));
  $("#nextPhotoButton").addEventListener("click", () => selectPhotoAt(Number($("#photoSlider").value) + 1));
  $("#imageSortButton").addEventListener("click", () => {
    const dataset = selectedDataset();
    if (!dataset) return;
    dataset.images.reverse();
    renderPhotoGrid();
    updatePhotoSlider();
    showToast("Photo order changed.");
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !$("#countView").classList.contains("hidden")) {
      event.preventDefault();
      $("#photoSlider").focus();
    }
  });
}
