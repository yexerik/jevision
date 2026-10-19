/**
 * Find Objects tool: dataset/version controls, locate-one flow, and result/API inspection.
 * Locate-all delegates to the version-specific strategy modules; cluster previews do not launch new inference.
 */
import { bindV6Settings, renderV6Settings, validV6Settings } from "./find/v6/settings-ui.js";
import { sendImageJudgment } from "../api.js";
import { prepareImage } from "../image-assets.js";
import { selectedDataset, objectUrl, getImageBlob } from "../library.js";
import { singularize, base64UrlSafeId, fillDatasetSelect, state, $ } from "../shared.js";
import { runFindAll } from "./find/engine.js";
import { boxArea, isValidBox, mapBoxToPhoto } from "./find/geometry.js";
import {
  findPresenceQuestion,
  findVersionSummary,
  findQuestionForVersion,
  findInstructionForVersion,
  findBoxInstructionForVersion,
  findVersionRequestSummary,
  findVersionRefinementSummary,
  findPresenceInstruction,
  findBoxInstruction,
} from "./find/prompts.js";
import { createFindRuntime } from "./find/runtime.js";

// Keep dialogs, focus, and text selection while in-flight responses update.
const findApiExchangeViews = new WeakMap();

export function findSelectedDataset() {
  return state.datasets.find((dataset) => dataset.id === state.findDatasetId) || null;
}

export function findSelectedImage() {
  const dataset = findSelectedDataset();
  return dataset?.images[state.findImageIndex] || null;
}

export function selectFindPhoto(index) {
  const dataset = findSelectedDataset();
  if (!dataset || !dataset.images.length || state.findBusy) return;
  state.findImageIndex = Math.max(0, Math.min(dataset.images.length - 1, Number(index)));
  clearFindResult();
  state.findError = "";
  clearFindApiLog();
  renderFindView();
}

export function clearFindResult() {
  state.findResult?.clusters?.forEach((cluster) => {
    if (cluster.previewUrl) URL.revokeObjectURL(cluster.previewUrl);
  });
  state.findResult = null;
  state.findSelectedClusterId = "";
}

export function clearFindApiLog() {
  $("#findApiExchangeList")?.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  state.findApiLog.forEach((entry) => {
    entry.uploads?.forEach((upload) => {
      if (upload.previewUrl) URL.revokeObjectURL(upload.previewUrl);
    });
  });
  state.findApiLog = [];
}

export function renderFindView() {
  const datasetSelect = $("#findDatasetSelect");
  if (!datasetSelect) return;
  if (!state.datasets.some((dataset) => dataset.id === state.findDatasetId)) state.findDatasetId = selectedDataset()?.id || state.datasets[0]?.id || "";
  state.findDatasetId = fillDatasetSelect(datasetSelect, state.findDatasetId);
  datasetSelect.disabled = state.findBusy;
  state.findMode = $("#findModeSelect").value || state.findMode;
  $("#findModeSelect").disabled = state.findBusy;
  state.findVersion = $("#findVersionSelect").value || state.findVersion || "v6";
  $("#findVersionSelect").disabled = state.findBusy;
  $("#findVersionControl").classList.toggle("hidden", state.findMode !== "all");
  $("#findVersionDetails").classList.toggle("hidden", state.findMode !== "all");
  const dataset = findSelectedDataset();
  if (!dataset || !dataset.images.length) state.findImageIndex = 0;
  else state.findImageIndex = Math.max(0, Math.min(dataset.images.length - 1, state.findImageIndex));
  const target = dataset?.target || "";
  const image = findSelectedImage();
  $("#findTargetLabel").textContent = dataset ? "Target: " + target : "Choose a dataset.";
  $("#findVersionSummary").textContent = findVersionSummary(state.findVersion);
  $("#findQuestionText").textContent = dataset ? state.findMode === "all" ? findQuestionForVersion(target, state.findVersion) : findPresenceQuestion(target) : "Select a dataset to see the find question.";
  $("#findInstructionText").textContent = dataset ? state.findMode === "all" ? findInstructionForVersion(target, state.findVersion) : findPresenceInstruction() : "Do not count reflections, pictures, or toys.";
  $("#findBoxPromptLabel").textContent = state.findMode === "all" ? "Box question" : "Box instructions";
  $("#findBoxInstructionText").textContent = dataset ? state.findMode === "all" ? findBoxInstructionForVersion(target, state.findVersion) : findBoxInstruction(target) : "The box question locates one example object.";
  $("#findVerifyQuestionText").textContent = dataset && state.findMode === "all" ? findVersionRequestSummary(state.findVersion) : "Only used in Locate all mode.";
  $("#findVerifyInstructionText").textContent = dataset && state.findMode === "all" ? "Every question points to its own named crop. Returned box coordinates map through the crop's content area and source rectangle back to the photo." : "Only used in Locate all mode.";
  $("#findRetryInstructionText").textContent = dataset && state.findMode === "all" ? findVersionRefinementSummary(state.findVersion) : "Only used in Locate all mode.";
  const slider = $("#findPhotoSlider");
  slider.max = String(Math.max(0, (dataset?.images.length || 0) - 1));
  slider.value = String(state.findImageIndex);
  slider.disabled = !image || state.findBusy;
  $("#findPhotoPosition").textContent = dataset?.images.length ? (state.findImageIndex + 1) + " / " + dataset.images.length : "0 photos";
  $("#findPreviousPhoto").disabled = !image || state.findImageIndex <= 0 || state.findBusy;
  $("#findNextPhoto").disabled = !image || state.findImageIndex >= dataset.images.length - 1 || state.findBusy;
  $("#findObjectButton").disabled = !image || !target || state.findBusy;
  const findButton = $("#findObjectButton");
  findButton.replaceChildren(document.createTextNode(state.findBusy ? "Finding target… " : (state.findMode === "all" ? "Find all " : "Find ") + (target ? singularize(target) : "target") + " "));
  const findIcon = document.createElement("span");
  findIcon.textContent = state.findBusy ? "···" : "⌖";
  findButton.append(findIcon);

  const stage = $("#findPhotoStage");
  stage.replaceChildren();
  if (image) {
    const photoWrap = document.createElement("div");
    photoWrap.className = "selected-photo-wrap find-photo-wrap";
    const img = document.createElement("img");
    img.src = objectUrl(image);
    img.alt = image.name;
    photoWrap.append(img);
    stage.append(photoWrap);
    const caption = document.createElement("span");
    caption.className = "find-photo-caption";
    caption.textContent = image.name;
    stage.append(caption);
    if (state.findResult?.imageId === image.id) {
      if (state.findResult.clusters?.length) drawFindClusterBoxes(photoWrap, state.findResult.clusters, target);
      if (state.findResult.reviewBoxes?.length) drawObjectBoxes(photoWrap, state.findResult.reviewBoxes, target, true);
      if (state.findResult.boxes?.length) drawObjectBoxes(photoWrap, state.findResult.boxes, target);
    }
  } else {
    const empty = document.createElement("div");
    empty.className = "feature-empty";
    empty.innerHTML = '<span>⌖</span><strong>' + (dataset ? "This dataset has no photos" : "Choose a dataset photo") + '</strong><small>' + (dataset ? "Add photos to this dataset, then come back to locate its target." : "The target comes from the selected dataset.") + "</small>";
    stage.append(empty);
  }

  const status = $("#findObjectStatus");
  status.classList.toggle("error", Boolean(state.findError));
  if (state.findBusy) status.textContent = state.findMode === "all" && state.findProgress ? "Searching regions · " + state.findProgress.checked + " checked · " + state.findProgress.found + " found · " + state.findProgress.pending + " queued…" : "Checking target presence and finding its box…";
  else if (state.findError) status.textContent = state.findError;
  else if (state.findResult && state.findResult.imageId === image?.id && state.findResult.mode === "all") {
    const result = state.findResult;
    const version = result.version ? result.version.toUpperCase() + " · " : "";
    const count = result.boxes.length + " " + (result.boxes.length === 1 ? singularize(target) : target);
    const regions = result.checked + " region" + (result.checked === 1 ? "" : "s");
    const unresolved = result.unresolved + " unresolved region" + (result.unresolved === 1 ? "" : "s");
    const clusterRefs = result.clusters?.length ? " " + result.clusters.length + " cluster reference" + (result.clusters.length === 1 ? "" : "s") + " available." : "";
    status.textContent = version + (result.unresolved ? (result.boxes.length ? "At least " + count + " located. " : "No target boxes located. ") + unresolved + (result.unresolved === 1 ? " needs" : " need") + " review; a search limit or an ambiguous crop stopped the search." : count + " located across " + regions + " using " + result.apiRequests + " API requests.") + clusterRefs;
    if (result.version === "v6") status.textContent = "V6 experimental · " + status.textContent.replace(/^V6 · /, "");
    if (result.version === "v5") {
      const pending = result.pendingRegions || 0;
      status.textContent = "V5 experimental · " + result.boxes.length + " located ("
        + result.confirmedCount + " confirmed by checks; " + result.localizationReview + " need extent review) · "
        + (result.reviewBoxes?.length || 0) + " review outlines excluded from count; "
        + result.registry.unresolvedGroups + " identity groups unresolved. Initial scan: "
        + result.coverage.completed + "/" + result.coverage.expected + " tiles; "
        + result.checked + " total regions searched. "
        + (pending ? "Search incomplete: " + pending + " queued regions were not searched. " : "")
        + (result.termination?.includes("depth-limit") ? "Some regions reached the zoom limit. " : "")
        + (result.unresolved ? "Review remains. " : "")
        + (result.budget.stopped ? "Stopped: " + result.budget.stopped.replaceAll("-", " ") + ". " : "")
        + result.apiRequests + " HTTP attempts.";
    }
  } else if (state.findResult && state.findResult.imageId === image?.id && state.findResult.present) {
    const boxConfidence = state.findResult.boxes?.[0]?.confidence;
    const confidence = Number.isFinite(boxConfidence) ? " · " + Math.round(boxConfidence * 100) + "% box confidence" : "";
    status.textContent = state.findResult.boxes?.length ? "One " + singularize(target) + " highlighted" + confidence : "Target likely present, but no usable box was returned.";
  } else if (state.findResult && state.findResult.imageId === image?.id) {
    status.textContent = "No " + singularize(target) + " found in this photo.";
  } else status.textContent = image ? "Choose Find " + (state.findMode === "all" ? "all " : "") + singularize(target) + "." : "Choose a dataset photo, then run Find target.";
  const evidence = $("#findEvidenceData"), evidencePanel = $("#findEvidencePanel");
  const v5 = state.findResult && state.findResult.imageId === image?.id && state.findResult.version === "v5";
  if (evidencePanel) evidencePanel.classList.toggle("hidden", !v5);
  if (evidence) evidence.textContent = v5 ? JSON.stringify(state.findResult, null, 2) : "";
  renderDetectionDetails($("#findDetectionDetails"), state.findResult && state.findResult.imageId === image?.id ? state.findResult.boxes : [], target);
  renderFindClusterDetails($("#findClusterDetail"), state.findResult && state.findResult.imageId === image?.id ? state.findResult : null, target);
  renderV6Settings(state.findResult?.imageId === image?.id ? state.findResult : null);
  renderFindApiInspector();
}

export function renderDetectionDetails(container, detections, target) {
  if (!container) return;
  container.replaceChildren();
  const validDetections = (detections || []).filter((detection) => isValidBox(detection.box));
  container.classList.toggle("hidden", validDetections.length === 0);
  if (!validDetections.length) return;

  const heading = document.createElement("strong");
  heading.className = "find-detection-heading";
  heading.textContent = "BOX DETAILS";
  const list = document.createElement("ol");
  list.className = "find-detection-list";
  validDetections.forEach((detection, index) => {
    const item = document.createElement("li");
    const score = Number(detection.confidence);
    const boxColor = Number.isFinite(score) ? score >= 0.7 ? "#26a879" : score >= 0.5 ? "#d5aa15" : "#dc5149" : "#ff5d43";
    const number = document.createElement("span");
    number.className = "find-detection-number";
    number.style.setProperty("--box-color", boxColor);
    number.textContent = String(index + 1);
    const description = document.createElement("span");
    description.className = "find-detection-description";
    const title = document.createElement("strong");
    title.textContent = singularize(target);
    const scores = document.createElement("small");
    const boxConfidence = Number.isFinite(score) ? Math.round(score * 100) + "% box confidence" : "Box confidence unavailable";
    const checkConfidence = Number(detection.verificationConfidence);
    scores.title = "Model confidence and verification probability are not measured precision or recall. Open Understanding results for definitions.";
    scores.textContent = Number.isFinite(checkConfidence)
      ? boxConfidence + " · " + Math.round(checkConfidence * 100) + "% verification"
      : boxConfidence;
    description.append(title, scores);
    item.append(number, description);
    list.append(item);
  });
  container.append(heading, list);
}

export function drawFindClusterBoxes(photoWrap, clusters, target) {
  [...clusters].sort((a, b) => boxArea(b.box) - boxArea(a.box)).forEach((cluster) => {
    if (!isValidBox(cluster.box)) return;
    const outline = document.createElement("button");
    outline.type = "button";
    outline.className = "cluster-detection-box";
    outline.style.left = (cluster.box.left * 100) + "%";
    outline.style.top = (cluster.box.top * 100) + "%";
    outline.style.width = ((cluster.box.right - cluster.box.left) * 100) + "%";
    outline.style.height = ((cluster.box.bottom - cluster.box.top) * 100) + "%";
    outline.style.zIndex = "1";
    const score = Number(cluster.confidence);
    const color = Number.isFinite(score) ? score >= 0.7 ? "#26a879" : score >= 0.5 ? "#d5aa15" : "#dc5149" : "#687ce2";
    outline.style.setProperty("--cluster-color", color);
    outline.setAttribute("aria-label", cluster.id + ", cluster of " + target + ". Open zoomed findings.");
    const tag = document.createElement("span");
    tag.className = "cluster-detection-label";
    tag.textContent = cluster.id;
    outline.append(tag);
    outline.addEventListener("click", () => {
      state.findSelectedClusterId = cluster.id;
      renderFindView();
      $("#findClusterDetail")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    photoWrap.append(outline);
  });
}

export function renderFindClusterDetails(container, result, target) {
  if (!container) return;
  container.replaceChildren();
  const cluster = result?.clusters?.find((item) => item.id === state.findSelectedClusterId);
  container.classList.toggle("hidden", !cluster);
  if (!cluster) return;

  const header = document.createElement("div");
  header.className = "find-cluster-detail-head";
  const title = document.createElement("strong");
  title.textContent = cluster.id + " · Cluster zoom";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "find-cluster-close";
  close.textContent = "Close";
  close.addEventListener("click", () => {
    state.findSelectedClusterId = "";
    renderFindView();
  });
  header.append(title, close);

  const summary = document.createElement("p");
  summary.className = "find-cluster-summary";
  const findingCount = cluster.findings?.length || 0;
  const clusterConfidence = Number(cluster.confidence);
  summary.textContent = cluster.id + " is a reference for a dense " + target + " region. "
    + (Number.isFinite(clusterConfidence) ? "Cluster box confidence: " + Math.round(clusterConfidence * 100) + "%. " : "")
    + (findingCount ? findingCount + " individual " + (findingCount === 1 ? singularize(target) : target) + " box" + (findingCount === 1 ? "" : "es") + " were accepted inside this crop." : "No individual boxes were accepted inside this crop; review the zoomed region.");
  const content = document.createElement("div");
  content.className = "find-cluster-detail-content";
  if (cluster.previewBlob) {
    if (!cluster.previewUrl) cluster.previewUrl = URL.createObjectURL(cluster.previewBlob);
    const image = document.createElement("img");
    image.className = "find-cluster-preview";
    image.src = cluster.previewUrl;
    image.alt = "Zoomed crop for " + cluster.id;
    content.append(image);
  }
  const list = document.createElement("ol");
  list.className = "find-cluster-findings";
  (cluster.findings || []).forEach((detection) => {
    const item = document.createElement("li");
    const ref = document.createElement("strong");
    ref.textContent = "Object " + detection.displayNumber;
    const score = document.createElement("small");
    const confidence = Number(detection.confidence);
    score.textContent = Number.isFinite(confidence) ? Math.round(confidence * 100) + "% box confidence" : "Box confidence unavailable";
    item.append(ref, score);
    list.append(item);
  });
  content.append(list);
  container.append(header, summary, content);
}

export function renderFindApiInspector() {
  const list = $("#findApiExchangeList");
  if (!list) return;
  if (!state.findApiLog.length) {
    list.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "find-api-empty";
    empty.textContent = "Run Find Objects to see each API request and its response here.";
    list.append(empty);
    return;
  }
  state.findApiLog.forEach((entry, index) => {
    let view = findApiExchangeViews.get(entry);
    if (!view) {
      view = createFindApiExchange(entry, index);
      findApiExchangeViews.set(entry, view);
    }
    const responseJson = JSON.stringify(entry.response || { error: entry.error || "Waiting for response…" }, null, 2);
    if (view.response.textContent !== responseJson) view.response.textContent = responseJson;
    if (list.children[index] !== view.exchange) list.insertBefore(view.exchange, list.children[index] || null);
  });
  while (list.children.length > state.findApiLog.length) list.lastElementChild.remove();
}

function createFindApiExchange(entry, index) {
  const exchange = document.createElement("article");
  exchange.className = "find-api-exchange";
  const heading = document.createElement("h3");
  heading.textContent = "API exchange " + (index + 1) + " · " + entry.phase + (entry.sourcePhoto ? " · " + entry.sourcePhoto : "");
  const actions = document.createElement("div");
  actions.className = "find-api-json-actions";
  const cropLabel = document.createElement("h4");
  cropLabel.textContent = "CROP IMAGES SENT TO JEV";
  const cropGrid = document.createElement("div");
  cropGrid.className = "find-api-crop-grid";
  entry.uploads.forEach((upload) => {
    const figure = document.createElement("figure");
    figure.className = "find-api-crop";
    const preview = document.createElement("img");
    preview.src = upload.previewUrl;
    preview.alt = "Uploaded crop " + upload.part;
    preview.loading = "lazy";
    const caption = document.createElement("figcaption");
    const coordinates = upload.region
      ? " · x " + Math.round(upload.region.left * 100) + "–" + Math.round(upload.region.right * 100) + "% / y " + Math.round(upload.region.top * 100) + "–" + Math.round(upload.region.bottom * 100) + "%"
      : "";
    caption.textContent = upload.part + " · " + upload.width + "×" + upload.height + coordinates;
    figure.append(preview, caption);
    cropGrid.append(figure);
  });
  const request = createFindJsonDialog("Request JSON", heading.textContent, "find-api-request-" + index);
  request.output.textContent = JSON.stringify({ sourcePhoto: entry.sourcePhoto, request: entry.request, uploads: entry.uploads.map(({ previewUrl, ...upload }) => upload) }, null, 2);
  const response = createFindJsonDialog("Response JSON", heading.textContent, "find-api-response-" + index);
  actions.append(request.button, response.button);
  exchange.append(heading, actions, cropLabel, cropGrid, request.dialog, response.dialog);
  return { exchange, response: response.output };
}

function createFindJsonDialog(label, context, id) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button button-outline find-api-json-button";
  button.textContent = label;
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-controls", id);
  const dialog = document.createElement("dialog");
  dialog.id = id;
  dialog.className = "find-api-json-dialog";
  dialog.setAttribute("aria-labelledby", id + "-title");
  const header = document.createElement("header");
  header.className = "find-api-json-dialog-header";
  const titleGroup = document.createElement("div");
  const title = document.createElement("h2");
  title.id = id + "-title";
  title.textContent = label;
  const subtitle = document.createElement("p");
  subtitle.textContent = context;
  titleGroup.append(title, subtitle);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "button button-outline find-api-json-close";
  close.textContent = "Close ×";
  close.autofocus = true;
  close.addEventListener("click", () => dialog.close());
  header.append(titleGroup, close);
  const body = document.createElement("div");
  body.className = "find-api-json-dialog-body";
  body.tabIndex = 0;
  const output = document.createElement("pre");
  output.className = "find-api-json-output";
  body.append(output);
  dialog.append(header, body);
  let startedOutside = false;
  const outside = (event) => {
    const bounds = dialog.getBoundingClientRect();
    return event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right
      || event.clientY < bounds.top || event.clientY > bounds.bottom);
  };
  dialog.addEventListener("pointerdown", (event) => { startedOutside = outside(event); });
  dialog.addEventListener("click", (event) => {
    if (startedOutside && outside(event)) dialog.close();
    startedOutside = false;
  });
  button.addEventListener("click", () => {
    startedOutside = false;
    dialog.showModal();
    body.scrollTop = 0;
  });
  return { button, dialog, output };
}

export async function sendFindImageJudgment(request, uploads, phase) {
  const entry = {
    phase,
    sourcePhoto: findSelectedImage()?.name || "",
    request,
    uploads: uploads.map(({ part, blob, name, width, height, region }) => ({ part, name, type: blob.type || "application/octet-stream", sizeBytes: blob.size, width, height, region, previewUrl: URL.createObjectURL(blob) })),
    response: null,
    error: "",
  };
  state.findApiLog.push(entry);
  renderFindApiInspector();
  try {
    return await sendImageJudgment(request, uploads, "/api/system-one", (response) => {
      entry.response = response;
      renderFindApiInspector();
    });
  } catch (error) {
    entry.error = error.message || "API request failed.";
    throw error;
  } finally {
    renderFindApiInspector();
  }
}

export async function findObjects() {
  const dataset = findSelectedDataset();
  const image = findSelectedImage();
  const target = dataset?.target || "";
  if (!dataset || !image || !target || state.findBusy) return;
  if (state.findMode === "all" && state.findVersion === "v6" && !validV6Settings()) return;
  state.findBusy = true;
  state.findProgress = state.findMode === "all" ? { checked: 0, found: 0, pending: 1 } : null;
  clearFindResult();
  state.findError = "";
  clearFindApiLog();
  renderFindView();
  try {
    const sourceBlob = await getImageBlob(image);
    const preparedImage = await prepareImage(sourceBlob, 1568, true);
    if (state.findMode === "all") {
      state.findResult = await findAllObjectsInImage(preparedImage, image.id, target, state.findVersion);
    } else {
      const reference = base64UrlSafeId();
      const part = "find-photo";
      const request = {
        model: "jev-1.14.0",
        state: { photo: reference },
        assets: { [reference]: { type: "image", part } },
        questions: {
          target_visible: {
            type: "noul",
            instructions: findPresenceQuestion(target) + " " + findPresenceInstruction(),
          },
          target_box: {
            type: "box",
            instructions: findBoxInstruction(target),
          },
        },
      };
      const payload = await sendFindImageJudgment(request, [{ part, blob: preparedImage.blob, name: "photo.jpg", width: preparedImage.width, height: preparedImage.height }], "Locate one");
      const targetVisible = payload.answers.target_visible?.noul;
      if (typeof targetVisible !== "number" || !Number.isFinite(targetVisible) || targetVisible < 0 || targetVisible > 1) throw new Error("The API returned an unexpected target-presence answer.");
      const present = targetVisible >= 0.5;
      const boxAnswer = payload.answers.target_box;
      const box = present && isValidBox(boxAnswer?.box) ? mapBoxToPhoto(boxAnswer.box, preparedImage.content) : null;
      state.findResult = {
        imageId: image.id,
        mode: "one",
        present,
        probability: targetVisible,
        boxes: box ? [{ box, confidence: Number(boxAnswer?.confidence) }] : [],
      };
    }
  } catch (error) {
    state.findError = error.message || "Could not locate the target in this photo.";
  } finally {
    state.findBusy = false;
    state.findProgress = null;
    renderFindView();
  }
}

export function updateFindProgress(target) {
  const progress = state.findProgress;
  if (!progress) return;
  const status = $("#findObjectStatus");
  status.classList.remove("error");
  status.textContent = "Searching regions · " + progress.checked + " checked · " + progress.calls + " requests · " + progress.found + " found · " + progress.pending + " queued…";
  const button = $("#findObjectButton");
  button.replaceChildren(document.createTextNode("Finding " + singularize(target) + "… "));
  const icon = document.createElement("span");
  icon.textContent = "···";
  button.append(icon);
}

export function drawObjectBoxes(photoWrap, detections, target, review = false) {
  if (!photoWrap) return;
  detections.forEach((detection, index) => {
    const { box, confidence } = detection;
    if (!isValidBox(box)) return;
    const outline = document.createElement("div");
    outline.className = review ? "review-detection-box object-detection-review" : "object-detection-box";
    outline.setAttribute("role", "img");
    outline.setAttribute("aria-label", (review ? "Review candidate; identity unresolved. Bounding box " : "Bounding box ") + (index + 1) + " around " + singularize(target));
    outline.style.left = (Number(box.left) * 100) + "%";
    outline.style.top = (Number(box.top) * 100) + "%";
    outline.style.width = ((Number(box.right) - Number(box.left)) * 100) + "%";
    outline.style.height = ((Number(box.bottom) - Number(box.top)) * 100) + "%";
    const score = Number(confidence);
    const boxColor = Number.isFinite(score) ? score >= 0.7 ? "#26a879" : score >= 0.5 ? "#d5aa15" : "#dc5149" : "#ff5d43";
    outline.style.setProperty("--box-color", boxColor);
    const label = document.createElement("span");
    label.className = "object-detection-label";
    label.textContent = (review ? "R" : "") + String(index + 1);
    label.setAttribute("aria-hidden", "true");
    outline.append(label);
    photoWrap.append(outline);
  });
}

export function bindFindEvents() {
  bindV6Settings(renderFindView);
  $("#findDatasetSelect").addEventListener("change", (event) => {
    state.findDatasetId = event.target.value;
    state.findImageIndex = 0;
    clearFindResult();
    state.findError = "";
    clearFindApiLog();
    renderFindView();
  });
  $("#findModeSelect").addEventListener("change", (event) => {
    state.findMode = event.target.value === "one" ? "one" : "all";
    clearFindResult();
    state.findError = "";
    clearFindApiLog();
    renderFindView();
  });
  $("#findVersionSelect").addEventListener("change", (event) => {
    state.findVersion = ["v1", "v2", "v3", "v4", "v5", "v6"].includes(event.target.value) ? event.target.value : "v6";
    clearFindResult();
    state.findError = "";
    clearFindApiLog();
    renderFindView();
  });
  $("#findPhotoSlider").addEventListener("input", (event) => selectFindPhoto(event.target.value));
  $("#findPreviousPhoto").addEventListener("click", () => selectFindPhoto(state.findImageIndex - 1));
  $("#findNextPhoto").addEventListener("click", () => selectFindPhoto(state.findImageIndex + 1));
  $("#findObjectButton").addEventListener("click", findObjects);
}

export function findAllObjectsInImage(preparedImage, imageId, target, version = "v1") {
  return runFindAll(preparedImage, imageId, target, version, createFindRuntime({ state, sendFindImageJudgment, updateFindProgress, v6Config: { ...state.findV6Config } }));
}
