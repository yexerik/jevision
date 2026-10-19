/**
 * Find Objects crop transforms, subdivision, ownership, and duplicate geometry.
 * Coordinates pass from padded uploads to the prepared image and finally back to the source photo.
 */
import { FIND_ALL_LIMITS } from "./limits.js";

export function mapCropBoxToPreparedImage(box, crop) {
  const cropBox = mapBoxToPhoto(box, crop.content);
  if (!cropBox) return null;
  const mapped = {
    left: crop.region.left + cropBox.left * (crop.region.right - crop.region.left),
    top: crop.region.top + cropBox.top * (crop.region.bottom - crop.region.top),
    right: crop.region.left + cropBox.right * (crop.region.right - crop.region.left),
    bottom: crop.region.top + cropBox.bottom * (crop.region.bottom - crop.region.top),
  };
  return isValidBox(mapped) ? mapped : null;
}

export function isKnownFindCount(choice, version) {
  return version === "v3" || version === "v4"
    ? ["none", "one", "two", "three_or_more", "several"].includes(choice)
    : ["none", "one", "several"].includes(choice);
}

export function createFindGridRegions(parent, rows, columns, overlap, canvasWidth, canvasHeight) {
  const children = [];
  const coreWidth = (parent.core.right - parent.core.left) / columns;
  const coreHeight = (parent.core.bottom - parent.core.top) / rows;
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const core = {
        left: parent.core.left + column * coreWidth,
        top: parent.core.top + row * coreHeight,
        right: column === columns - 1 ? parent.core.right : parent.core.left + (column + 1) * coreWidth,
        bottom: row === rows - 1 ? parent.core.bottom : parent.core.top + (row + 1) * coreHeight,
      };
      const haloX = Math.max(8 / canvasWidth, coreWidth * overlap);
      const haloY = Math.max(8 / canvasHeight, coreHeight * overlap);
      const crop = {
        left: Math.max(parent.crop.left, core.left - haloX),
        top: Math.max(parent.crop.top, core.top - haloY),
        right: Math.min(parent.crop.right, core.right + haloX),
        bottom: Math.min(parent.crop.bottom, core.bottom + haloY),
      };
      if ((crop.right - crop.left) * canvasWidth >= FIND_ALL_LIMITS.minCropPixels && (crop.bottom - crop.top) * canvasHeight >= FIND_ALL_LIMITS.minCropPixels) {
        children.push({ core, crop, depth: parent.depth + 1 });
      }
    }
  }
  return children;
}

export function queueFindRegionSplitVersion(region, queue, checked, canvasWidth, canvasHeight, strategy) {
  if (region.depth >= FIND_ALL_LIMITS.maxDepth) return 1;
  const coreWidth = (region.core.right - region.core.left) * canvasWidth;
  const coreHeight = (region.core.bottom - region.core.top) * canvasHeight;
  const useQuadrants = strategy.split === "quadrants" && Math.min(coreWidth / 2, coreHeight / 2) >= 96;
  const regions = useQuadrants
    ? createFindGridRegions(region, 2, 2, strategy.splitHalo, canvasWidth, canvasHeight)
    : splitFindRegionWithHalo(region, canvasWidth, canvasHeight, strategy.splitHalo);
  const remaining = FIND_ALL_LIMITS.maxRegions - checked - queue.length;
  if (!regions.length || regions.length > remaining) return Math.max(1, regions.length);
  queue.push(...regions);
  return 0;
}

export function splitFindRegionWithHalo(region, canvasWidth, canvasHeight, overlap) {
  const coreWidth = (region.core.right - region.core.left) * canvasWidth;
  const coreHeight = (region.core.bottom - region.core.top) * canvasHeight;
  const rows = coreWidth >= coreHeight ? 1 : 2;
  const columns = coreWidth >= coreHeight ? 2 : 1;
  return createFindGridRegions(region, rows, columns, overlap, canvasWidth, canvasHeight);
}

export function mapRegionToPhoto(region, content) {
  const width = content.right - content.left;
  const height = content.bottom - content.top;
  if (!width || !height) return null;
  const mapped = {
    left: Math.max(0, (region.left - content.left) / width),
    top: Math.max(0, (region.top - content.top) / height),
    right: Math.min(1, (region.right - content.left) / width),
    bottom: Math.min(1, (region.bottom - content.top) / height),
  };
  return mapped.left < mapped.right && mapped.top < mapped.bottom ? mapped : null;
}

export function queueFindRegionSplit(region, queue, checked, canvasWidth, canvasHeight) {
  const split = splitFindRegion(region, canvasWidth, canvasHeight);
  const remaining = FIND_ALL_LIMITS.maxRegions - checked - queue.length;
  if (!split.children.length || split.children.length > remaining) {
    region.splitUnresolved = Math.max(1, split.unresolved);
    return;
  }
  queue.push(...split.children);
  region.splitUnresolved = split.unresolved;
}

export function paddedBoxRegion(box, width, height) {
  const boxWidth = box.right - box.left;
  const boxHeight = box.bottom - box.top;
  const padX = Math.max(boxWidth * 0.5, 24 / width);
  const padY = Math.max(boxHeight * 0.5, 24 / height);
  return {
    left: Math.max(0, box.left - padX),
    top: Math.max(0, box.top - padY),
    right: Math.min(1, box.right + padX),
    bottom: Math.min(1, box.bottom + padY),
  };
}

export function splitFindRegion(region, canvasWidth, canvasHeight) {
  if (region.depth >= FIND_ALL_LIMITS.maxDepth) return { children: [], unresolved: 1 };
  const coreWidth = (region.core.right - region.core.left) * canvasWidth;
  const coreHeight = (region.core.bottom - region.core.top) * canvasHeight;
  const splitVertically = coreWidth >= coreHeight;
  let cores;
  if (splitVertically) {
    const midX = (region.core.left + region.core.right) / 2;
    cores = [
      { left: region.core.left, top: region.core.top, right: midX, bottom: region.core.bottom },
      { left: midX, top: region.core.top, right: region.core.right, bottom: region.core.bottom },
    ];
  } else {
    const midY = (region.core.top + region.core.bottom) / 2;
    cores = [
      { left: region.core.left, top: region.core.top, right: region.core.right, bottom: midY },
      { left: region.core.left, top: midY, right: region.core.right, bottom: region.core.bottom },
    ];
  }
  const children = [];
  let unresolved = 0;
  cores.forEach((childCore) => {
    const haloX = Math.max(8 / canvasWidth, (childCore.right - childCore.left) * FIND_ALL_LIMITS.splitHalo);
    const haloY = Math.max(8 / canvasHeight, (childCore.bottom - childCore.top) * FIND_ALL_LIMITS.splitHalo);
    const crop = {
      left: Math.max(region.crop.left, childCore.left - haloX),
      top: Math.max(region.crop.top, childCore.top - haloY),
      right: Math.min(region.crop.right, childCore.right + haloX),
      bottom: Math.min(region.crop.bottom, childCore.bottom + haloY),
    };
    const child = { core: childCore, crop, depth: region.depth + 1 };
    if ((crop.right - crop.left) * canvasWidth >= FIND_ALL_LIMITS.minCropPixels && (crop.bottom - crop.top) * canvasHeight >= FIND_ALL_LIMITS.minCropPixels) children.push(child);
    else unresolved += 1;
  });
  return { children, unresolved };
}

export function findAmbiguousDuplicatePairs(detections) {
  const pairs = [];
  for (let leftIndex = 0; leftIndex < detections.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < detections.length; rightIndex += 1) {
      const left = detections[leftIndex];
      const right = detections[rightIndex];
      if (!left.id || !right.id || !left.sourceCrop || !right.sourceCrop || !left.preparedBox || !right.preparedBox) continue;
      if (intersectionOverUnion(left.sourceCrop, right.sourceCrop) <= 0) continue;
      const areaLeft = boxArea(left.box);
      const areaRight = boxArea(right.box);
      const smallerArea = Math.min(areaLeft, areaRight);
      if (!smallerArea) continue;
      const overlap = boxIntersectionArea(left.box, right.box);
      const coverage = overlap / smallerArea;
      if (intersectionOverUnion(left.box, right.box) >= FIND_ALL_LIMITS.duplicateBoxIou) continue;
      const centerDistance = boxCenterDistance(left.box, right.box);
      const largestSide = Math.max(boxWidth(left.box), boxHeight(left.box), boxWidth(right.box), boxHeight(right.box));
      if (centerDistance > Math.max(largestSide * 0.9, Math.sqrt(smallerArea) * 1.5, 0.08)) continue;
      if (coverage < 0.35 && rectangleGapDistance(left.box, right.box) > Math.max(0.035, Math.sqrt(smallerArea) * 0.3)) continue;
      pairs.push({ left, right, overlap: coverage });
    }
  }
  return pairs.sort((a, b) => b.overlap - a.overlap).slice(0, FIND_ALL_LIMITS.maxDuplicatePairsPerBatch);
}

export function boxArea(box) {
  return Math.max(0, box.right - box.left) * Math.max(0, box.bottom - box.top);
}

export function suppressNestedFindClusters(clusters) {
  const ordered = [...clusters].sort((a, b) => a.depth - b.depth || boxArea(b.core) - boxArea(a.core));
  const kept = [];
  for (const candidate of ordered) {
    const coveredByParent = kept.some((parent) => parent.depth < candidate.depth
      && parent.core.left <= candidate.core.left + 1e-5
      && parent.core.top <= candidate.core.top + 1e-5
      && parent.core.right >= candidate.core.right - 1e-5
      && parent.core.bottom >= candidate.core.bottom - 1e-5);
    if (!coveredByParent) kept.push(candidate);
  }
  return kept;
}

export function boxWidth(box) { return Math.max(0, box.right - box.left); }

export function boxHeight(box) { return Math.max(0, box.bottom - box.top); }

export function boxIntersectionArea(a, b) {
  return Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
    * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
}

export function boxCenterDistance(a, b) {
  return Math.hypot((a.left + a.right - b.left - b.right) / 2, (a.top + a.bottom - b.top - b.bottom) / 2);
}

export function rectangleGapDistance(a, b) {
  const gapX = Math.max(0, a.left - b.right, b.left - a.right);
  const gapY = Math.max(0, a.top - b.bottom, b.top - a.bottom);
  return Math.hypot(gapX, gapY);
}

export function isRefinedBoxInsideCandidate(refined, candidate) {
  const centerX = (refined.left + refined.right) / 2;
  const centerY = (refined.top + refined.bottom) / 2;
  const padX = boxWidth(candidate) * 0.08;
  const padY = boxHeight(candidate) * 0.08;
  return centerX >= candidate.left - padX && centerX <= candidate.right + padX
    && centerY >= candidate.top - padY && centerY <= candidate.bottom + padY
    && boxIntersectionArea(refined, candidate) / Math.max(boxArea(refined), 1e-8) >= 0.7;
}

export function paddedPairRegion(a, b, width, height) {
  const left = Math.min(a.left, b.left);
  const top = Math.min(a.top, b.top);
  const right = Math.max(a.right, b.right);
  const bottom = Math.max(a.bottom, b.bottom);
  const padX = Math.max((right - left) * 0.5, 64 / width);
  const padY = Math.max((bottom - top) * 0.5, 64 / height);
  return {
    left: Math.max(0, left - padX),
    top: Math.max(0, top - padY),
    right: Math.min(1, right + padX),
    bottom: Math.min(1, bottom + padY),
  };
}

export function preferredDuplicateDetection(left, right) {
  const confidenceDifference = Number(left.confidence || 0) - Number(right.confidence || 0);
  if (Math.abs(confidenceDifference) >= 0.2) return confidenceDifference > 0 ? left : right;
  const verificationDifference = Number(left.verificationConfidence || 0) - Number(right.verificationConfidence || 0);
  if (Math.abs(verificationDifference) >= 0.2) return verificationDifference > 0 ? left : right;
  return boxArea(left.box) <= boxArea(right.box) ? left : right;
}

export function combineDuplicateDetections(left, right) {
  const smallerArea = Math.min(boxArea(left.box), boxArea(right.box));
  const coverage = boxIntersectionArea(left.box, right.box) / Math.max(smallerArea, 1e-8);
  if (coverage >= 0.55) return preferredDuplicateDetection(left, right);
  const box = {
    left: Math.min(left.box.left, right.box.left),
    top: Math.min(left.box.top, right.box.top),
    right: Math.max(left.box.right, right.box.right),
    bottom: Math.max(left.box.bottom, right.box.bottom),
  };
  const preparedBox = {
    left: Math.min(left.preparedBox.left, right.preparedBox.left),
    top: Math.min(left.preparedBox.top, right.preparedBox.top),
    right: Math.max(left.preparedBox.right, right.preparedBox.right),
    bottom: Math.max(left.preparedBox.bottom, right.preparedBox.bottom),
  };
  return {
    id: [left.id, right.id].sort().join("+"), box, preparedBox,
    sourceCrop: {
      left: Math.min(left.sourceCrop.left, right.sourceCrop.left),
      top: Math.min(left.sourceCrop.top, right.sourceCrop.top),
      right: Math.max(left.sourceCrop.right, right.sourceCrop.right),
      bottom: Math.max(left.sourceCrop.bottom, right.sourceCrop.bottom),
    },
    confidence: Math.max(Number(left.confidence || 0), Number(right.confidence || 0)),
    classificationConfidence: Math.max(Number(left.classificationConfidence || 0), Number(right.classificationConfidence || 0)),
    verificationConfidence: Math.max(Number(left.verificationConfidence || 0), Number(right.verificationConfidence || 0)),
  };
}

export function cropImageRegion(bitmap, region, overlayBox = null, overlayCore = null) {
  const sx = Math.max(0, Math.floor(region.left * bitmap.width));
  const sy = Math.max(0, Math.floor(region.top * bitmap.height));
  const ex = Math.min(bitmap.width, Math.ceil(region.right * bitmap.width));
  const ey = Math.min(bitmap.height, Math.ceil(region.bottom * bitmap.height));
  const sourceWidth = Math.max(1, ex - sx);
  const sourceHeight = Math.max(1, ey - sy);
  const scale = Math.min(1568 / Math.max(sourceWidth, sourceHeight), Math.max(1, 280 / Math.min(sourceWidth, sourceHeight)));
  const drawWidth = Math.max(1, Math.round(sourceWidth * scale));
  const drawHeight = Math.max(1, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(280, drawWidth);
  canvas.height = Math.max(280, drawHeight);
  const drawLeft = Math.floor((canvas.width - drawWidth) / 2);
  const drawTop = Math.floor((canvas.height - drawHeight) / 2);
  const content = {
    left: drawLeft / canvas.width,
    top: drawTop / canvas.height,
    right: (drawLeft + drawWidth) / canvas.width,
    bottom: (drawTop + drawHeight) / canvas.height,
  };
  const sourceRegion = {
    left: sx / bitmap.width,
    top: sy / bitmap.height,
    right: ex / bitmap.width,
    bottom: ey / bitmap.height,
  };
  const context = canvas.getContext("2d", { alpha: false });
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, sx, sy, sourceWidth, sourceHeight, drawLeft, drawTop, drawWidth, drawHeight);
  if (overlayBox) {
    const regionWidth = sourceRegion.right - sourceRegion.left;
    const regionHeight = sourceRegion.bottom - sourceRegion.top;
    const overlays = Array.isArray(overlayBox) ? overlayBox : [{ box: overlayBox, color: "#ff3828" }];
    overlays.forEach((overlay) => {
      const box = overlay.box || overlay;
      const left = content.left + ((box.left - sourceRegion.left) / regionWidth) * (content.right - content.left);
      const top = content.top + ((box.top - sourceRegion.top) / regionHeight) * (content.bottom - content.top);
      const right = content.left + ((box.right - sourceRegion.left) / regionWidth) * (content.right - content.left);
      const bottom = content.top + ((box.bottom - sourceRegion.top) / regionHeight) * (content.bottom - content.top);
      context.strokeStyle = overlay.color || "#ff3828";
      context.lineWidth = Math.max(3, Math.round(Math.min(canvas.width, canvas.height) * 0.012));
      context.strokeRect(left * canvas.width, top * canvas.height, (right - left) * canvas.width, (bottom - top) * canvas.height);
      if (overlay.label) {
        const fontSize = Math.max(12, Math.round(Math.min(canvas.width, canvas.height) * 0.035));
        context.font = "700 " + fontSize + "px sans-serif";
        const labelWidth = context.measureText(String(overlay.label)).width + 10;
        const labelHeight = fontSize + 6;
        const labelTop = Math.max(0, top * canvas.height - labelHeight);
        context.fillStyle = overlay.color || "#ff3828";
        context.fillRect(left * canvas.width, labelTop, labelWidth, labelHeight);
        context.fillStyle = "#ffffff";
        context.fillText(String(overlay.label), left * canvas.width + 5, labelTop + fontSize + 1);
      }
    });
  }
  if (overlayCore) {
    const regionWidth = sourceRegion.right - sourceRegion.left;
    const regionHeight = sourceRegion.bottom - sourceRegion.top;
    const left = content.left + ((overlayCore.left - sourceRegion.left) / regionWidth) * (content.right - content.left);
    const top = content.top + ((overlayCore.top - sourceRegion.top) / regionHeight) * (content.bottom - content.top);
    const right = content.left + ((overlayCore.right - sourceRegion.left) / regionWidth) * (content.right - content.left);
    const bottom = content.top + ((overlayCore.bottom - sourceRegion.top) / regionHeight) * (content.bottom - content.top);
    context.save();
    context.strokeStyle = "rgba(36, 112, 184, 0.92)";
    context.lineWidth = Math.max(1, Math.round(Math.min(canvas.width, canvas.height) * 0.004));
    context.setLineDash([Math.max(3, Math.round(Math.min(canvas.width, canvas.height) * 0.018)), Math.max(2, Math.round(Math.min(canvas.width, canvas.height) * 0.012))]);
    context.strokeRect(left * canvas.width, top * canvas.height, (right - left) * canvas.width, (bottom - top) * canvas.height);
    context.restore();
  }
  return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve({ blob, content, region: sourceRegion, width: canvas.width, height: canvas.height }) : reject(new Error("Could not prepare an image region for analysis.")), "image/jpeg", 0.9));
}

export function intersectionOverUnion(a, b) {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const intersection = width * height;
  const areaA = (a.right - a.left) * (a.bottom - a.top);
  const areaB = (b.right - b.left) * (b.bottom - b.top);
  const union = areaA + areaB - intersection;
  return union > 0 ? intersection / union : 0;
}

export function suppressFindDuplicates(detections) {
  const score = (detection) => {
    const boxConfidence = Number.isFinite(detection.confidence) ? detection.confidence : -1;
    const verificationConfidence = Number.isFinite(detection.verificationConfidence) ? detection.verificationConfidence : -1;
    return [boxConfidence, verificationConfidence];
  };
  const sorted = [...detections].sort((a, b) => {
    const scoreA = score(a);
    const scoreB = score(b);
    return scoreB[0] - scoreA[0] || scoreB[1] - scoreA[1];
  });
  const kept = [];
  for (const candidate of sorted) {
    if (!kept.some((existing) => isDuplicateFindDetection(existing, candidate))) kept.push(candidate);
  }
  return kept;
}

export function isDuplicateFindDetection(a, b) {
  if (intersectionOverUnion(a.box, b.box) >= FIND_ALL_LIMITS.duplicateBoxIou) return true;
  if (!a.sourceCrop || !b.sourceCrop || intersectionOverUnion(a.sourceCrop, b.sourceCrop) <= 0) return false;
  const widthA = a.box.right - a.box.left;
  const heightA = a.box.bottom - a.box.top;
  const widthB = b.box.right - b.box.left;
  const heightB = b.box.bottom - b.box.top;
  const areaA = widthA * heightA;
  const areaB = widthB * heightB;
  const intersection = Math.max(0, Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left))
    * Math.max(0, Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top));
  const smallerArea = Math.min(areaA, areaB);
  // A repeated small-object detection can shift substantially between overlapping
  // crops. Require some shared box area, then use center distance to reject nearby
  // but distinct instances. Requiring near-containment here kept duplicates when
  // the same ant was boxed from opposite sides of a crop boundary.
  if (!smallerArea || intersection / smallerArea < FIND_ALL_LIMITS.duplicateBoxCoverage) return false;
  const centerAX = (a.box.left + a.box.right) / 2;
  const centerAY = (a.box.top + a.box.bottom) / 2;
  const centerBX = (b.box.left + b.box.right) / 2;
  const centerBY = (b.box.top + b.box.bottom) / 2;
  const centerDistance = Math.hypot(centerAX - centerBX, centerAY - centerBY);
  const smallerScale = Math.sqrt(smallerArea);
  const largestSide = Math.max(widthA, heightA, widthB, heightB);
  const centerTolerance = Math.max(smallerScale * 0.6, largestSide * 0.5);
  return centerDistance <= centerTolerance;
}

export function isBoxCenterOwnedByRegion(x, y, core, root) {
  if (x < root.left || x > root.right || y < root.top || y > root.bottom) return false;
  const ownsX = x >= core.left && (x < core.right || (core.right === root.right && x <= root.right));
  const ownsY = y >= core.top && (y < core.bottom || (core.bottom === root.bottom && y <= root.bottom));
  return ownsX && ownsY;
}

export function isValidBox(box) {
  if (!box || typeof box !== "object") return false;
  const { left, top, right, bottom } = Object.fromEntries(["left", "top", "right", "bottom"].map((edge) => [edge, Number(box[edge])]));
  return [left, top, right, bottom].every((edge) => Number.isFinite(edge) && edge >= 0 && edge <= 1) && left < right && top < bottom;
}

export function mapBoxToPhoto(box, content) {
  const mapped = {
    left: (Number(box.left) - content.left) / (content.right - content.left),
    top: (Number(box.top) - content.top) / (content.bottom - content.top),
    right: (Number(box.right) - content.left) / (content.right - content.left),
    bottom: (Number(box.bottom) - content.top) / (content.bottom - content.top),
  };
  mapped.left = Math.max(0, Math.min(1, mapped.left));
  mapped.top = Math.max(0, Math.min(1, mapped.top));
  mapped.right = Math.max(0, Math.min(1, mapped.right));
  mapped.bottom = Math.max(0, Math.min(1, mapped.bottom));
  return isValidBox(mapped) ? mapped : null;
}
