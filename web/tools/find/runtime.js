/**
 * Browser/API boundaries for the Find Objects engines.
 * Defaults use real crop rendering and the local API proxy; tests can inject image/transport I/O
 * without replacing subdivision, prompts, ownership, or result assembly.
 */
import { sendImageJudgment } from "../../api.js";
import { base64UrlSafeId } from "../../shared.js";
import { cropImageRegion } from "./geometry.js";

export function createFindRuntime(overrides = {}) {
  return {
    state: { findProgress: null },
    updateFindProgress() {},
    sendFindImageJudgment: sendImageJudgment,
    createImageBitmap: (...args) => globalThis.createImageBitmap(...args),
    cropImageRegion,
    base64UrlSafeId,
    ...overrides,
  };
}
