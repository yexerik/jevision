/**
 * Find Objects V1: classify crops first, then locate targets in separate Box requests.
 * Uses binary subdivision, ownership filtering, weak-box verification, and geometric deduplication.
 */
import {
  mapCropBoxToPreparedImage,
  queueFindRegionSplit,
  paddedBoxRegion,
  splitFindRegion,
  suppressFindDuplicates,
  isBoxCenterOwnedByRegion,
  isValidBox,
  mapBoxToPhoto,
} from "./geometry.js";
import { FIND_ALL_LIMITS } from "./limits.js";
import { findBatchRequest } from "./prompts.js";

export async function findAllObjectsV1(preparedImage, imageId, target, runtime) {
  const { state, sendFindImageJudgment, updateFindProgress, createImageBitmap, cropImageRegion, base64UrlSafeId } = runtime;
  const bitmap = await createImageBitmap(preparedImage.blob);
  const canvasWidth = bitmap.width;
  const canvasHeight = bitmap.height;
  const root = { ...preparedImage.content };
  const rootRegion = { core: root, crop: { ...root }, depth: 0 };
  const firstSplit = splitFindRegion(rootRegion, canvasWidth, canvasHeight);
  const queue = firstSplit.children.flatMap((region) => {
    const secondSplit = splitFindRegion(region, canvasWidth, canvasHeight);
    return secondSplit.children.length ? secondSplit.children : [region];
  });
  const allDetections = [];
  let boxes = [];
  let checked = 0;
  let apiRequests = 0;
  let unresolved = 0;

  try {
    // Keep one request in reserve: positive regions need a second, batched Box call.
    while (queue.length && checked < FIND_ALL_LIMITS.maxRegions && apiRequests + 1 < FIND_ALL_LIMITS.maxApiRequests) {
      const batch = queue.splice(0, Math.min(FIND_ALL_LIMITS.batchSize, FIND_ALL_LIMITS.maxRegions - checked));
      const items = await Promise.all(batch.map(async (region, index) => {
        const uploadCrop = await cropImageRegion(bitmap, region.crop);
        return { ...region, uploadCrop, key: "r" + index, reference: base64UrlSafeId(), part: "region-" + index };
      }));
      state.findProgress = { checked, calls: apiRequests, found: boxes.length, pending: queue.length + batch.length };
      updateFindProgress(target);
      apiRequests += 1;
      const classified = await sendFindImageJudgment(
        findBatchRequest(items, target, "classify"),
        items.map((item) => ({ part: item.part, blob: item.uploadCrop.blob, name: item.part + ".jpg", width: item.uploadCrop.width, height: item.uploadCrop.height, region: item.uploadCrop.region })),
        "Choice only · classify " + items.length + " regions",
      );
      checked += items.length;
      const positiveRegions = [];

      for (const item of items) {
        const multiplicity = classified.answers?.[item.key + "_multiplicity"];
        const choice = multiplicity?.choice;
        const confidence = Number(multiplicity?.confidence);
        if (!["none", "one", "several"].includes(choice) || !Number.isFinite(confidence) || confidence < FIND_ALL_LIMITS.minChoiceConfidence || choice === "several") {
          queueFindRegionSplit(item, queue, checked, canvasWidth, canvasHeight);
          unresolved += item.splitUnresolved || 0;
          continue;
        }
        if (choice === "none") continue;
        positiveRegions.push({ ...item, classificationConfidence: confidence });
      }

      let candidates = [];
      if (positiveRegions.length && apiRequests < FIND_ALL_LIMITS.maxApiRequests) {
        apiRequests += 1;
        state.findProgress = { checked, calls: apiRequests, found: boxes.length, pending: queue.length + positiveRegions.length };
        updateFindProgress(target);
        const located = await sendFindImageJudgment(
          findBatchRequest(positiveRegions, target, "locate"),
          positiveRegions.map((item) => ({ part: item.part, blob: item.uploadCrop.blob, name: item.part + ".jpg", width: item.uploadCrop.width, height: item.uploadCrop.height, region: item.uploadCrop.region })),
          "Box only · locate in " + positiveRegions.length + " positive regions",
        );
        for (const item of positiveRegions) {
          const answer = located.answers?.[item.key + "_target_box"];
          const box = isValidBox(answer?.box) ? mapCropBoxToPreparedImage(answer.box, item.uploadCrop) : null;
          const boxConfidence = Number(answer?.confidence);
          if (!box) {
            queueFindRegionSplit(item, queue, checked, canvasWidth, canvasHeight);
            unresolved += item.splitUnresolved || 0;
            continue;
          }
          candidates.push({ ...item, box, confidence: item.classificationConfidence, boxConfidence });
        }
      } else if (positiveRegions.length) {
        unresolved += positiveRegions.length;
      }

      const outsideCandidates = candidates.filter((candidate) => {
        const centerX = (candidate.box.left + candidate.box.right) / 2;
        const centerY = (candidate.box.top + candidate.box.bottom) / 2;
        return centerX < root.left || centerX > root.right || centerY < root.top || centerY > root.bottom;
      });
      outsideCandidates.forEach((candidate) => {
        queueFindRegionSplit(candidate, queue, checked, canvasWidth, canvasHeight);
        unresolved += candidate.splitUnresolved || 0;
      });
      const ownedCandidates = candidates.filter((candidate) => {
        const centerX = (candidate.box.left + candidate.box.right) / 2;
        const centerY = (candidate.box.top + candidate.box.bottom) / 2;
        return !outsideCandidates.includes(candidate) && isBoxCenterOwnedByRegion(centerX, centerY, candidate.core, root);
      });
      const needingCheck = ownedCandidates.filter((candidate) => !Number.isFinite(candidate.boxConfidence) || candidate.boxConfidence < FIND_ALL_LIMITS.minBoxConfidence);
      let checkAnswers = {};
      if (needingCheck.length && apiRequests < FIND_ALL_LIMITS.maxApiRequests) {
        const checkItems = await Promise.all(needingCheck.map(async (candidate, index) => {
          const region = paddedBoxRegion(candidate.box, canvasWidth, canvasHeight);
          const crop = await cropImageRegion(bitmap, region, candidate.box);
          return { ...candidate, sourceKey: candidate.key, checkRegion: region, checkCrop: crop, key: "v" + index, reference: base64UrlSafeId(), part: "box-check-" + index };
        }));
        apiRequests += 1;
        state.findProgress = { checked, calls: apiRequests, found: boxes.length, pending: queue.length + candidates.length };
        updateFindProgress(target);
        const checkedBoxes = await sendFindImageJudgment(
          findBatchRequest(checkItems, target, "verify"),
          checkItems.map((item) => ({ part: item.part, blob: item.checkCrop.blob, name: item.part + ".jpg", width: item.checkCrop.width, height: item.checkCrop.height, region: item.checkCrop.region })),
          "Check " + checkItems.length + " low-confidence boxes",
        );
        checkItems.forEach((item) => { checkAnswers[item.sourceKey] = checkedBoxes.answers?.[item.key + "_box_check"]; });
      }

      for (const item of ownedCandidates) {
        if (!Number.isFinite(item.boxConfidence) || item.boxConfidence < FIND_ALL_LIMITS.minBoxConfidence) {
          const verificationProbability = Number(checkAnswers[item.key]?.noul);
          if (!Number.isFinite(verificationProbability) || verificationProbability < FIND_ALL_LIMITS.minBoxCheckProbability) {
            queueFindRegionSplit(item, queue, checked, canvasWidth, canvasHeight);
            unresolved += item.splitUnresolved || 0;
            continue;
          }
          item.verificationConfidence = verificationProbability;
        }
        const box = mapBoxToPhoto(item.box, preparedImage.content);
        if (box) {
          allDetections.push({ box, sourceCrop: item.crop, confidence: item.boxConfidence, classificationConfidence: item.confidence, verificationConfidence: item.verificationConfidence });
        } else {
          queueFindRegionSplit(item, queue, checked, canvasWidth, canvasHeight);
          unresolved += item.splitUnresolved || 0;
        }
      }
      boxes = suppressFindDuplicates(allDetections).map(({ sourceCrop, ...detection }) => detection);
      state.findProgress = { checked, calls: apiRequests, found: boxes.length, pending: queue.length };
      updateFindProgress(target);
    }
  } finally {
    bitmap.close();
  }
  if (queue.length) unresolved += queue.length;
  return { imageId, mode: "all", boxes, checked, apiRequests, unresolved };
}
