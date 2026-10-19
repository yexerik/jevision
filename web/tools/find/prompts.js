/**
 * Find Objects questions and request assembly shared by V1–V4.
 * Keeps historical wording and version-specific question shapes unchanged for benchmark comparability.
 */
import * as v6Prompts from "./v6/prompts.js";
import { singularize } from "../../shared.js";

export function findPresenceQuestion(target) {
  return "Is at least one distinct real " + target + " visibly present in `photo`?";
}

export function findMultiplicityQuestion(target) {
  return "How many separate real " + target + " can you see in `photo`? Choose none, one, or several.";
}

export function findMultiplicityInstruction(target) {
  if (isAntTarget(target)) return "Count ant bodies, not legs or antennae. Small or partly hidden ants still count when the visible body shape or segments identify an ant; do not require all legs or the full body to be visible. Count every separate ant body once. Ignore petals, leaves, seeds, texture, shadows, pictures, toys, and reflections. If two bodies overlap, count them separately only when you can distinguish both.";
  return "Count only clearly identifiable real " + target + " in this crop. none means zero; one means exactly one; several means at least two separate objects. Count each object once, not its parts. Ignore pictures, toys, reflections, shadows, and uncertain fragments. The app splits regions classified as several.";
}

export function findAllBoxInstruction(target) {
  if (isAntTarget(target)) return "Draw one tight box around one visible ant body in `photo`. Include its head, thorax, and abdomen when visible; exclude legs, antennae, nearby ants, petals, and background. If several ants are visible, choose one whose body center is nearest the center of this crop.";
  return "Draw one tight box around one clearly identifiable real " + singularize(target) + " instance in `photo`. Include that object's visible body, but exclude nearby objects and background. If several are visible, choose one instance whose body center is nearest the center of this crop.";
}

export function findVersionSummary(version) {
  if (version === "v6") return "Default Find All strategy: experimental V6 uses the V4 detection policy with five editable percentages under Advanced settings. No accuracy improvement has been established. V4 remains available with fixed settings.";
  if (version === "v5") return "Experimental evidence search: checks the full photo and a 3×3 grid, then verifies candidates within a fixed budget. The current default can leave crowded child crops unsearched; adaptive search remains an experimental configuration. Dashed review outlines show verified candidates with unresolved identity; they do not increase the located count. Located boxes may still need extent review.";
  if (version === "v4") return "Searches overlapping image regions for objects and clusters. Click a cluster box to inspect its zoomed crop and individual findings.";
  if (version === "v3") return "Checks the full photo and adaptive regions together, then refines weak boxes and checks likely duplicates.";
  if (version === "v2") return "Checks an overlapping 2×2 grid; crowded or unclear regions are split into smaller regions.";
  return "Classifies image regions first, then locates objects in positive regions with a separate box request.";
}

export function findQuestionForVersion(target, version) {
  if (version === "v6") return v6Prompts.findQuestionForVersion(target, version);
  if (version === "v4") return findQuestionForVersion(target, "v3");
  if (version === "v3") return "How many separate real " + target + " have their body centers inside the blue dashed rectangle in `photo`? Choose none, one, two, or three_or_more.";
  if (version === "v2") return "How many separate real " + target + " have their body centers inside the blue dashed rectangle in `photo`? Choose none, one, or several.";
  return findMultiplicityQuestion(target);
}

export function findInstructionForVersion(target, version) {
  if (version === "v6") return v6Prompts.findInstructionForVersion(target, version);
  if (version === "v4") return findInstructionForVersion(target, "v3");
  if (version === "v3") {
    const identity = isAntTarget(target)
      ? "Count distinct ant bodies, not legs or antennae. Count a partly hidden ant when its visible body is identifiable. Ignore petals, leaves, seeds, texture, shadows, pictures, toys, and reflections."
      : "Count clearly identifiable real " + target + " objects, not their parts. Ignore pictures, toys, reflections, shadows, and uncertain fragments.";
    return identity + " The thin blue dashed rectangle marks the crop's owned core; the surrounding image is context only. Count an object only when its body center is inside that rectangle. Do not count an object whose center is outside it, even if it is visible in the surrounding context. If objects overlap, count them separately only when both bodies can be distinguished. Choose none for zero, one for exactly one, two for exactly two, or three_or_more for at least three objects inside the rectangle. The app divides a core classified as two or more into four smaller regions.";
  }
  if (version === "v2") {
    const identity = isAntTarget(target)
      ? "Count distinct ant bodies, not legs or antennae. Count a partly hidden ant when its visible body is identifiable. Ignore petals, leaves, seeds, texture, shadows, pictures, toys, and reflections."
      : "Count clearly identifiable real " + target + " objects, not their parts. Ignore pictures, toys, reflections, shadows, and uncertain fragments.";
    return identity + " The thin blue dashed rectangle marks the crop's owned core; the surrounding image is context only. Count an object only when its body center is inside that rectangle. Do not count an object whose center is outside it, even if it is visible in the surrounding context. If objects overlap, count them separately only when both bodies can be distinguished. Choose none for zero, one for exactly one, or several for at least two objects inside the rectangle. The app divides a core classified as several into smaller regions.";
  }
  return findMultiplicityInstruction(target);
}

export function findBoxInstructionForVersion(target, version) {
  if (version === "v6") return v6Prompts.findBoxInstructionForVersion(target, version);
  if (version === "v4") return findBoxInstructionForVersion(target, "v3");
  if (version === "v2") return "In `photo`, draw one tight box around a clearly identifiable real " + singularize(target) + " whose body center is inside the blue dashed rectangle. Use the surrounding crop only as context. If several target centers are inside the rectangle, choose the one nearest the rectangle's center. Include its recognizable body and exclude legs, antennae, other instances, the blue line, and background. The paired count question decides whether this core needs further subdivision.";
  if (version === "v3") return "In `photo`, draw one tight box around a clearly identifiable real " + singularize(target) + " whose body center is inside the blue dashed rectangle. Use the surrounding crop only as context. If several target centers are inside the rectangle, choose the one nearest the rectangle's center. Include the object's recognizable body, not detached parts, the blue line, or neighboring instances. The paired count question decides whether this core should be divided and searched again.";
  return findAllBoxInstruction(target);
}

export function findVersionRequestSummary(version) {
  if (version === "v6") return v6Prompts.findVersionRequestSummary(version);
  if (version === "v5") return "Each question receives its own image. The full-photo answer cannot cancel the minimum scan. Original observations and identity decisions remain available in the search evidence.";
  if (version === "v4") return "Count + individual Box + cluster Box questions share each tile request. Dense tiles become clickable cluster references; their child tiles continue the detailed search.";
  if (version === "v3") return "The first batch includes the full photo and overlapping tiles. A confident single-target answer uses the full-photo box; otherwise the app follows the tile results.";
  return version === "v1"
    ? "Choice classifies the crop first; a separate batched Box request locates crops classified as one."
    : "Each crop gets a Count question and a Box question together in the same batched image request; Box answers are retained only for single-target crops.";
}

export function findVersionRefinementSummary(version) {
  if (version === "v6") return v6Prompts.findVersionRefinementSummary(version);
  if (version === "v5") return "Retains original boxes; automatic refinement regressed in development benchmarks. Uncertain extent, identity, coverage and budget states remain explicit. V5 is not yet validated for general accuracy.";
  if (version === "v4") return "Dense regions keep a cluster-level reference while adaptive child regions search for individual targets. Click a cluster outline to inspect its zoomed crop and accepted findings.";
  if (version === "v3") return "Crowded tiles split adaptively; weak boxes receive a red-outline check and nearby overlapping boxes get a same-object check.";
  if (version === "v2") return "Crowded tiles split along their longer side. Low-confidence empty tiles also split at the first two levels; weak boxes receive a red-outline check.";
  return "Several crops split along their longer side. Low-confidence boxes get a red-outline check; uncertain boxes split and search again.";
}

export function findMultiplicityCriteria(target) {
  const singular = singularize(target);
  return {
    none: "No clearly identifiable real " + target + " are visible.",
    one: "Exactly one clearly identifiable real " + singular + " is visible.",
    several: "At least two clearly identifiable, separate real " + target + " are visible.",
  };
}

export function findCountCriteriaForVersion(target, version) {
  if (version === "v3" || version === "v4") {
    const singular = singularize(target);
    return {
      none: "No clearly identifiable real " + target + " are visible.",
      one: "Exactly one clearly identifiable real " + singular + " is visible.",
      two: "Exactly two separate, clearly identifiable real " + target + " are visible.",
      three_or_more: "At least three separate, clearly identifiable real " + target + " are visible.",
    };
  }
  return findMultiplicityCriteria(target);
}

export function findPresenceInstruction() {
  return "Do not count reflections, pictures, or toys.";
}

export function findBoxInstruction(target) {
  return "One clearly visible real " + singularize(target) + " in `photo`. If several are present, choose one near the center of the image.";
}

export function findBatchRequest(items, target, mode, version = "v2") {
  const regions = {};
  const assets = {};
  const questions = {};
  items.forEach((item) => {
    const path = "regions." + item.key;
    regions[item.key] = item.reference;
    assets[item.reference] = { type: "image", part: item.part };
    if (mode === "count_box") {
      const rootProbe = (version === "v3" || version === "v4") && item.rootProbe;
      const question = rootProbe
        ? "How many separate real " + target + " are visible in the full photo `" + path + "`? Choose none, one, two, or three_or_more."
        : findQuestionForVersion(target, version).replaceAll("`photo`", "`" + path + "`");
      const rootIdentity = isAntTarget(target)
        ? "Count distinct ant bodies, not legs or antennae. Count a partly hidden ant when its visible body is identifiable. Ignore petals, leaves, seeds, texture, shadows, pictures, toys, and reflections."
        : "Count clearly identifiable real " + target + " objects, not their parts. Ignore pictures, toys, reflections, shadows, and uncertain fragments.";
      const instruction = rootProbe
        ? rootIdentity + " Count each distinct body visible in the full photo once. If bodies overlap, count them separately only when both are identifiable. Answer only about this full photo; ignore all other region images in the request."
        : findInstructionForVersion(target, version) + " Answer only about this crop; ignore all other region images in the request.";
      questions[item.key + "_multiplicity"] = { type: "choice", instructions: question + " " + instruction, criteria: findCountCriteriaForVersion(target, version) };
      questions[item.key + "_target_box"] = {
        type: "box",
        instructions: (rootProbe
          ? "Draw one tight box around one clearly identifiable real " + singularize(target) + " in the full photo `" + path + "`. Include its recognizable body and exclude background and detached parts. If several are visible, choose the target whose body center is nearest the image center."
          : findBoxInstructionForVersion(target, version).replaceAll("`photo`", "`" + path + "`")) + " Answer only about this image; ignore all other region images in the request.",
      };
      if (version === "v4" && !rootProbe) {
        questions[item.key + "_cluster_box"] = {
          type: "box",
          instructions: "Draw the smallest box that contains the whole visible group of clearly identifiable real " + target + " whose body centers are inside the blue dashed core in `" + path + "`. Include all of those target bodies, even when they touch or overlap; exclude targets whose centers are outside the core, detached parts, and background. This is a group reference box, not a box around one instance. Answer only about this image; ignore all other region images in the request.",
        };
      }
    } else if (mode === "classify") {
      const question = findMultiplicityQuestion(target).replaceAll("`photo`", "`" + path + "`") + " Answer about this region only; ignore the other region images in the request.";
      const instruction = findMultiplicityInstruction(target) + " Answer about this region only; ignore the other region images in the request.";
      questions[item.key + "_multiplicity"] = { type: "choice", instructions: question + " " + instruction, criteria: findMultiplicityCriteria(target) };
    } else if (mode === "locate") {
      const instructions = findAllBoxInstruction(target).replaceAll("`photo`", "`" + path + "`") + " Ignore the other region images in this request.";
      questions[item.key + "_target_box"] = { type: "box", instructions };
    } else if (mode === "verify") {
      const object = singularize(target);
      const isV3 = version === "v3" || version === "v4";
      const instructions = "Does the red outline in `" + path + "` contain enough of one distinct real " + object + " to identify that instance? Judge only the outlined area. A target partly hidden or clipped by the crop can count when its visible body is recognizable. If more of the same object's body is visible elsewhere in this crop, the box should include it rather than isolating a small piece. Do not count only a leg, antenna, texture, or fragment that cannot identify one instance. Ignore the other region images in this request.";
      questions[item.key + "_box_check"] = {
        type: "noul",
        instructions,
        criteria: {
          true: "The red outline contains enough of one distinct real " + object + " to identify that instance, including when the instance is partly hidden or clipped by the crop.",
          false: "The outline contains only background, texture, an unrelated object, or a small fragment such as a leg or body segment that is not enough to identify one distinct " + object + ". It also does not count when a larger recognizable part of the same target is visible outside the outline in this crop.",
        },
      };
      if (isV3 && item.refineBox) {
        questions[item.key + "_tight_box"] = {
          type: "box",
          instructions: "Draw a tight box around the single identifiable real " + object + " body inside the existing red outline in `" + path + "`. The red outline is only a search area; do not repeat its dimensions. Include the recognizable body and exclude detached legs, antennae, neighboring targets, and background. If more than one target body is inside, choose the body nearest the crop center. Ignore all other region images in this request.",
        };
      }
    } else if (mode === "duplicate_check") {
      const object = singularize(target);
      const antGuidance = isAntTarget(target)
        ? " For ants, the head, thorax, and abdomen connected as one insect are one ant even when the outlines land on different body sections. Separate ants each have their own connected body."
        : "";
      const question = "Do the red and blue outlines in `" + path + "` refer to the same individual real " + object + ", or to two different individuals?";
      questions[item.key + "_same_object"] = {
        type: "choice",
        instructions: question + " Compare the recognizable bodies, not the outline size or nearby background. Same means both boxes point to the same physical target, including when one box is loose, shifted, or cropped differently." + antGuidance + " Different means each box identifies a separate target body. Choose uncertain if the crop does not show enough detail to tell. Ignore all other region images in this request.",
        criteria: {
          same: isAntTarget(target) ? "Both outlines refer to one ant, including when they mark different connected sections of that ant's head, thorax, and abdomen." : "Both outlines refer to the same individual target body.",
          different: isAntTarget(target) ? "Each outline points to a separate ant body; each ant has its own connected head, thorax, and abdomen." : "The outlines refer to two distinct target bodies, even if their boxes overlap.",
          uncertain: "The visible crop does not establish whether these are the same individual.",
        },
      };
    }
  });
  return { model: "jev-1.14.0", state: { regions }, assets, questions };
}

export function isAntTarget(target) {
  return singularize(String(target || "").trim().toLowerCase()) === "ant";
}
