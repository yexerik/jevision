/**
 * Shared image preparation and multipart judgment transport.
 * Sends requests through the local Python proxy so credentials stay on the server.
 */
import { prepareImage } from "./image-assets.js";
import { getImageBlob } from "./library.js";
import { makeId } from "./shared.js";

export async function sendImageJudgment(request, uploads, endpoint = "/api/system-one", onResponse = null) {
  const form = new FormData();
  form.append("request", new Blob([JSON.stringify(request)], { type: "application/json" }));
  uploads.forEach(({ part, blob, name }) => form.append(part, blob, name));
  const response = await fetch(endpoint, { method: "POST", body: form });
  const payload = await response.json().catch(() => ({}));
  if (typeof onResponse === "function") onResponse({ status: response.status, ok: response.ok, body: payload });
  if (!response.ok) {
    const detail = payload.error || payload.message || (payload.detail && JSON.stringify(payload.detail)) || "TypeSafe could not analyze these photos.";
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.status = response.status;
    error.usage = payload.usage;
    throw error;
  }
  if (!payload.answers) {
    const error = new Error("The API returned an unexpected answer format.");
    error.status = response.status;
    error.usage = payload.usage;
    throw error;
  }
  return payload;
}

export async function prepareImageAssets(images, maxDimension = 1568) {
  const refs = [];
  const uploads = [];
  for (let index = 0; index < images.length; index += 1) {
    const blob = await prepareImage(await getImageBlob(images[index]), maxDimension);
    const reference = "image-" + makeId();
    const part = "photo-" + index;
    refs.push({ reference, part });
    uploads.push({ part, blob, name: "photo-" + index + ".jpg" });
  }
  return { refs, uploads };
}
