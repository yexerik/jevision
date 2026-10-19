/**
 * Shared image resize/padding preparation for all visual tools.
 * Optionally returns the content transform needed to map inference boxes back to the photo.
 */
export async function prepareImage(blob, maxDimension = 1568, includeTransform = false) {
  const bitmap = await createImageBitmap(blob, { imageOrientation: "from-image" });
  const sourceWidth = bitmap.width;
  const sourceHeight = bitmap.height;
  const maxSide = Math.max(sourceWidth, sourceHeight);
  const minSide = Math.min(sourceWidth, sourceHeight);
  let scale = Math.min(maxDimension / maxSide, Math.max(1, 280 / minSide));
  let drawWidth = Math.max(1, Math.round(sourceWidth * scale));
  let drawHeight = Math.max(1, Math.round(sourceHeight * scale));
  if (drawWidth * drawHeight > 2458624) {
    scale *= Math.sqrt(2458624 / (drawWidth * drawHeight));
    drawWidth = Math.max(1, Math.round(sourceWidth * scale));
    drawHeight = Math.max(1, Math.round(sourceHeight * scale));
  }
  const canvasWidth = Math.max(280, drawWidth);
  const canvasHeight = Math.max(280, drawHeight);
  const drawLeft = Math.floor((canvasWidth - drawWidth) / 2);
  const drawTop = Math.floor((canvasHeight - drawHeight) / 2);
  const content = {
    left: drawLeft / canvasWidth,
    top: drawTop / canvasHeight,
    right: (drawLeft + drawWidth) / canvasWidth,
    bottom: (drawTop + drawHeight) / canvasHeight,
  };
  const canvas = document.createElement("canvas");
  canvas.width = canvasWidth;
  canvas.height = canvasHeight;
  const context = canvas.getContext("2d", { alpha: false });
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvasWidth, canvasHeight);
  context.drawImage(bitmap, drawLeft, drawTop, drawWidth, drawHeight);
  bitmap.close();
  return new Promise((resolve, reject) => {
    canvas.toBlob((output) => {
      if (!output) return reject(new Error("Could not prepare the photo for analysis."));
      resolve(includeTransform ? { blob: output, content, width: canvasWidth, height: canvasHeight, sourceBlob: blob } : output);
    }, "image/jpeg", 0.9);
  });
}
