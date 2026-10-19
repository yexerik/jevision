/**
 * Locate-all strategy dispatcher. V1 keeps its two-stage algorithm; V2–V4 each select their
 * own policy before entering the shared combined loop. The default remains historical V1;
 * the UI explicitly supplies its selected version (currently V6).
 */
import { findAllObjectsV1 } from "./v1.js";
import { findAllObjectsV2 } from "./v2.js";
import { findAllObjectsV3 } from "./v3.js";
import { findAllObjectsV4 } from "./v4.js";
import { findAllObjectsV6 } from "./v6.js";
import { findAllObjectsV5 } from "./v5.js";
import { withVisibleInstancePolicy } from "./policy.js";
import { createFindRuntime } from "./runtime.js";

export async function runFindAll(preparedImage, imageId, target, version = "v1", runtime = createFindRuntime()) {
  if (version === "v5") return findAllObjectsV5(preparedImage, imageId, target, runtime);
  if (version === "v2-policy" || version === "v4-policy") {
    const base = version.split("-")[0];
    const send = runtime.sendFindImageJudgment;
    const result = await runFindAll(preparedImage, imageId, target, base, {
      ...runtime, sendFindImageJudgment: (request, ...args) => send(withVisibleInstancePolicy(request, target), ...args),
    });
    return { ...result, version };
  }
  const strategies = { v2: findAllObjectsV2, v3: findAllObjectsV3, v4: findAllObjectsV4, v6: findAllObjectsV6 };
  if (Object.hasOwn(strategies, version)) return strategies[version](preparedImage, imageId, target, runtime);
  return { ...(await findAllObjectsV1(preparedImage, imageId, target, runtime)), version: "v1" };
}
