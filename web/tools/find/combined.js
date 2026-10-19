/**
 * Shared combined Count + Box search loop for V2–V4.
 * Version modules supply grid policies; this loop preserves their probes, refinement, deduplication,
 * budgets, and optional V4 cluster references without copying the search algorithm.
 */
import {
  mapCropBoxToPreparedImage,
  isKnownFindCount,
  createFindGridRegions,
  queueFindRegionSplitVersion,
  mapRegionToPhoto,
  paddedBoxRegion,
  findAmbiguousDuplicatePairs,
  boxArea,
  suppressNestedFindClusters,
  isRefinedBoxInsideCandidate,
  paddedPairRegion,
  preferredDuplicateDetection,
  combineDuplicateDetections,
  suppressFindDuplicates,
  isBoxCenterOwnedByRegion,
  isValidBox,
  mapBoxToPhoto,
} from "./geometry.js";
import { FIND_ALL_LIMITS } from "./limits.js";
import { findBatchRequest } from "./prompts.js";

export async function findAllObjectsCombined(preparedImage, imageId, target, version, selectStrategy, runtime) {
  const { state, sendFindImageJudgment, updateFindProgress, createImageBitmap, cropImageRegion, base64UrlSafeId } = runtime;
  const bitmap = await createImageBitmap(preparedImage.blob);
  const canvasWidth = bitmap.width;
  const canvasHeight = bitmap.height;
  const strategy = selectStrategy(preparedImage, canvasWidth, canvasHeight);
  const root = { ...preparedImage.content };
  const rootRegion = { core: root, crop: { ...root }, depth: 0 };
  const queue = createFindGridRegions(rootRegion, strategy.rows, strategy.columns, strategy.initialHalo, canvasWidth, canvasHeight);
  const allDetections = [];
  const clusterCandidates = [];
  const checkedDuplicatePairs = new Set();
  let boxes = [];
  let clusters = [];
  let checked = 0;
  let apiRequests = 0;
  let unresolved = 0;

  try {
    while (queue.length && checked < FIND_ALL_LIMITS.maxRegions && apiRequests < FIND_ALL_LIMITS.maxApiRequests) {
      const batch = queue.splice(0, Math.min(strategy.batchSize, FIND_ALL_LIMITS.maxRegions - checked));
      const items = await Promise.all(batch.map(async (region, index) => {
        const uploadCrop = await cropImageRegion(bitmap, region.crop, null, region.core);
        return { ...region, uploadCrop, key: "r" + index, reference: base64UrlSafeId(), part: version + "-region-" + index };
      }));
      if ((version === "v3" || version === "v4") && checked === 0) {
        const uploadCrop = await cropImageRegion(bitmap, root);
        items.push({ core: root, crop: root, depth: 0, uploadCrop, key: "root", reference: base64UrlSafeId(), part: version + "-full-photo-probe", rootProbe: true });
      }
      state.findProgress = { checked, calls: apiRequests, found: boxes.length, pending: queue.length + batch.length };
      updateFindProgress(target);
      apiRequests += 1;
      const analyzed = await sendFindImageJudgment(
        findBatchRequest(items, target, "count_box", version),
        items.map((item) => ({ part: item.part, blob: item.uploadCrop.blob, name: item.part + ".jpg", width: item.uploadCrop.width, height: item.uploadCrop.height, region: item.uploadCrop.region })),
        version.toUpperCase() + " · Count + Box in " + items.length + " regions",
      );
      checked += batch.length;
      const candidates = [];
      const rootItem = items.find((item) => item.rootProbe);
      const rootAnswer = rootItem && analyzed.answers?.[rootItem.key + "_multiplicity"];
      const rootBoxAnswer = rootItem && analyzed.answers?.[rootItem.key + "_target_box"];
      const rootBox = isValidBox(rootBoxAnswer?.box) ? mapCropBoxToPreparedImage(rootBoxAnswer.box, rootItem.uploadCrop) : null;
      const rootSingleCandidate = (version === "v3" || version === "v4") && rootAnswer?.choice === "one"
        && Number(rootAnswer.confidence) >= 0.8
        && rootBox && isBoxCenterOwnedByRegion((rootBox.left + rootBox.right) / 2, (rootBox.top + rootBox.bottom) / 2, root, root)
        ? { ...rootItem, box: rootBox, confidence: Number(rootBoxAnswer.confidence), classificationConfidence: Number(rootAnswer.confidence) }
        : null;

      if (rootSingleCandidate) candidates.push(rootSingleCandidate);
      for (const item of items) {
        if (item.rootProbe || rootSingleCandidate) continue;
        const answer = analyzed.answers?.[item.key + "_multiplicity"];
        const choice = answer?.choice;
        const confidence = Number(answer?.confidence);
        const uncertainEmpty = choice === "none"
          && item.depth <= (strategy.maxNoneRefinementDepth ?? -1)
          && confidence < (strategy.minNoneConfidence ?? FIND_ALL_LIMITS.minChoiceConfidence);
        if (!Number.isFinite(confidence) || confidence < FIND_ALL_LIMITS.minChoiceConfidence || uncertainEmpty || !isKnownFindCount(choice, version)) {
          unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
          continue;
        }
        if (choice === "none") continue;
        if (version === "v4" && ["two", "three_or_more", "several"].includes(choice)) {
          const clusterAnswer = analyzed.answers?.[item.key + "_cluster_box"];
          const preparedBox = isValidBox(clusterAnswer?.box) ? mapCropBoxToPreparedImage(clusterAnswer.box, item.uploadCrop) : null;
          const box = preparedBox ? mapBoxToPhoto(preparedBox, preparedImage.content) : null;
          if (box) clusterCandidates.push({ id: "cluster-candidate-" + (clusterCandidates.length + 1), box, preparedBox, core: item.core, depth: item.depth, confidence: Number(clusterAnswer.confidence) });
          unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
          continue;
        }
        if (choice !== "one") {
          unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
          continue;
        }
        const boxAnswer = analyzed.answers?.[item.key + "_target_box"];
        const box = isValidBox(boxAnswer?.box) ? mapCropBoxToPreparedImage(boxAnswer.box, item.uploadCrop) : null;
        if (!box) {
          unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
          continue;
        }
        const centerX = (box.left + box.right) / 2;
        const centerY = (box.top + box.bottom) / 2;
        if (!isBoxCenterOwnedByRegion(centerX, centerY, item.core, root)) {
          unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
          continue;
        }
        candidates.push({ ...item, box, confidence: Number(boxAnswer.confidence), classificationConfidence: confidence });
      }

      const needingCheck = candidates.filter((candidate) => !Number.isFinite(candidate.confidence) || candidate.confidence < FIND_ALL_LIMITS.minBoxConfidence);
      let checkAnswers = {};
      if (needingCheck.length && apiRequests < FIND_ALL_LIMITS.maxApiRequests) {
        const checkItems = await Promise.all(needingCheck.map(async (candidate, index) => {
          const region = paddedBoxRegion(candidate.box, canvasWidth, canvasHeight);
          const crop = await cropImageRegion(bitmap, region, candidate.box);
          return { ...candidate, sourceKey: candidate.key, checkCrop: crop, refineBox: version === "v3" || version === "v4", key: "v" + index, reference: base64UrlSafeId(), part: version + "-box-check-" + index };
        }));
        apiRequests += 1;
        const checkedBoxes = await sendFindImageJudgment(
          findBatchRequest(checkItems, target, "verify", version),
          checkItems.map((item) => ({ part: item.part, blob: item.checkCrop.blob, name: item.part + ".jpg", width: item.checkCrop.width, height: item.checkCrop.height, region: item.checkCrop.region })),
          version.toUpperCase() + " · red-outline check " + checkItems.length + " boxes",
        );
        checkItems.forEach((item) => {
          const tightBox = checkedBoxes.answers?.[item.key + "_tight_box"]?.box;
          checkAnswers[item.sourceKey] = {
            ...checkedBoxes.answers?.[item.key + "_box_check"],
            tightBox: isValidBox(tightBox) ? mapCropBoxToPreparedImage(tightBox, item.checkCrop) : null,
          };
        });
      }

      for (const item of candidates) {
        let verificationConfidence;
        if (!Number.isFinite(item.confidence) || item.confidence < FIND_ALL_LIMITS.minBoxConfidence) {
          verificationConfidence = Number(checkAnswers[item.key]?.noul);
          const minCheckProbability = version === "v3" || version === "v4" ? FIND_ALL_LIMITS.minV3BoxCheckProbability : FIND_ALL_LIMITS.minBoxCheckProbability;
          if (!Number.isFinite(verificationConfidence) || verificationConfidence < minCheckProbability) {
            unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
            continue;
          }
          if ((version === "v3" || version === "v4") && checkAnswers[item.key]?.tightBox) {
            const refined = checkAnswers[item.key].tightBox;
            if (refined && isRefinedBoxInsideCandidate(refined, item.box) && boxArea(refined) < boxArea(item.box) * 0.85) item.box = refined;
          }
        }
        const box = mapBoxToPhoto(item.box, preparedImage.content);
        const sourceCrop = mapRegionToPhoto(item.crop, preparedImage.content);
        if (box && sourceCrop) allDetections.push({ id: item.reference, box, preparedBox: item.box, sourceCrop, confidence: item.confidence, classificationConfidence: item.classificationConfidence, verificationConfidence });
        else unresolved += queueFindRegionSplitVersion(item, queue, checked, canvasWidth, canvasHeight, strategy);
      }
      if ((version === "v3" || version === "v4") && allDetections.length > 1) {
        const geometricallyDeduped = suppressFindDuplicates(allDetections);
        allDetections.splice(0, allDetections.length, ...geometricallyDeduped);
        const duplicatePairs = findAmbiguousDuplicatePairs(allDetections).filter((pair) => {
          const pairKey = [pair.left.id, pair.right.id].sort().join(":");
          pair.key = pairKey;
          return !checkedDuplicatePairs.has(pairKey);
        });
        if (duplicatePairs.length) {
          duplicatePairs.forEach((pair) => checkedDuplicatePairs.add(pair.key));
          if (apiRequests < FIND_ALL_LIMITS.maxApiRequests) {
            const pairItems = await Promise.all(duplicatePairs.map(async (pair, index) => {
              const region = paddedPairRegion(pair.left.preparedBox, pair.right.preparedBox, canvasWidth, canvasHeight);
              const crop = await cropImageRegion(bitmap, region, [
                { box: pair.left.preparedBox, color: "#ff3828" },
                { box: pair.right.preparedBox, color: "#286aff" },
              ]);
              return { key: "d" + index, reference: base64UrlSafeId(), part: version + "-duplicate-check-" + index, region, crop, pair };
            }));
            apiRequests += 1;
            try {
              const duplicateCheck = await sendFindImageJudgment(
                findBatchRequest(pairItems, target, "duplicate_check"),
                pairItems.map((item) => ({ part: item.part, blob: item.crop.blob, name: item.part + ".jpg", width: item.crop.width, height: item.crop.height, region: item.crop.region })),
                version.toUpperCase() + " · same-object check in " + pairItems.length + " overlapping box pairs",
              );
              for (const item of pairItems) {
                const answer = duplicateCheck.answers?.[item.key + "_same_object"];
                const sameProbability = Number(answer?.probabilities?.same);
                if (answer?.choice !== "same" || !Number.isFinite(sameProbability) || sameProbability < FIND_ALL_LIMITS.minDuplicatePairProbability) continue;
                const leftIndex = allDetections.findIndex((detection) => detection.id === item.pair.left.id);
                const rightIndex = allDetections.findIndex((detection) => detection.id === item.pair.right.id);
                if (leftIndex < 0 || rightIndex < 0) continue;
                const merged = combineDuplicateDetections(item.pair.left, item.pair.right);
                const keepIndex = preferredDuplicateDetection(item.pair.left, item.pair.right) === item.pair.left ? leftIndex : rightIndex;
                const removeIndex = keepIndex === leftIndex ? rightIndex : leftIndex;
                allDetections[keepIndex] = merged;
                allDetections.splice(removeIndex, 1);
              }
            } catch {
              unresolved += duplicatePairs.length;
            }
          } else {
            unresolved += duplicatePairs.length;
          }
        }
      }
      boxes = suppressFindDuplicates(allDetections).map(({ sourceCrop, ...detection }) => detection);
      state.findProgress = { checked, calls: apiRequests, found: boxes.length, pending: queue.length };
      updateFindProgress(target);
    }
    if (version === "v4" && clusterCandidates.length) {
      const visibleClusters = suppressNestedFindClusters(clusterCandidates).map((cluster, index) => ({ ...cluster, id: "C" + (index + 1) }));
      for (const cluster of visibleClusters) {
        cluster.findings = boxes.filter((detection) => detection.preparedBox && isBoxCenterOwnedByRegion(
          (detection.preparedBox.left + detection.preparedBox.right) / 2,
          (detection.preparedBox.top + detection.preparedBox.bottom) / 2,
          cluster.core,
          root,
        )).map((detection) => ({ ...detection, displayNumber: boxes.indexOf(detection) + 1 }));
        const overlays = cluster.findings.filter((detection) => detection.preparedBox).map((detection) => ({ box: detection.preparedBox, color: "#ff5d43", label: detection.displayNumber }));
        cluster.previewBlob = (await cropImageRegion(bitmap, cluster.core, overlays)).blob;
      }
      clusters = visibleClusters;
    }
  } finally {
    bitmap.close();
  }
  if (queue.length) unresolved += queue.length;
  return { imageId, mode: "all", version, boxes, clusters, checked, apiRequests, unresolved };
}
