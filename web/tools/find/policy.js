/** Versioned V5 visible-instance contract; historical prompts remain frozen. */
import { isAntTarget } from "./prompts.js";

export const FIND_POLICY_VERSION = "visible-instance-v1";
export function visibleInstancePolicy(target) {
  return isAntTarget(target)
    ? "Box the visible ant head, thorax and abdomen together; exclude legs and antennae."
    : "Box the entire visible extent of one identifiable real instance, including attached visible extremities (feet, legs, ears, tail, wheels or fins as applicable). Do not invent hidden extent.";
}

export function withVisibleInstancePolicy(request, target) {
  const questions = Object.fromEntries(Object.entries(request.questions).map(([key, question]) => {
    let instructions = question.instructions;
    if (typeof instructions === "string" && !isAntTarget(target)) {
      instructions = instructions
        .replaceAll("exclude legs, antennae, other instances, the blue line, and background", "exclude other instances, the blue line, and background")
        .replaceAll("exclude detached legs, antennae, neighboring targets, and background", "exclude neighboring targets and background");
    }
    return [key, { ...question, instructions: instructions + " " + visibleInstancePolicy(target) }];
  }));
  return { ...request, questions };
}
