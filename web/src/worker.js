// Background processing: runs parts 1-5 (pipeline.js runGrid) off the page, so it stays responsive on
// large batches. A classic worker, because OpenCV.js is a UMD script loaded with importScripts; the ES
// modules are loaded with import(). Messages:
//   {type: "init", opencv: url}                  -> {type: "ready"} or {type: "error", message}
//   {type: "process", id, file, options}         -> {type: "done", id, result} or {type: "failed", id, message}
// `result` is runGrid's {rows, problems (as dicts), quality, run, display, outlines, crops}, with the pixel
// buffers transferred, not copied.
/* eslint-env worker */
let cv = null, modules = null;

async function init(url) {
  self.importScripts(url);
  const { whenReady } = await import("./opencv.js");
  cv = await whenReady(self.cv);
  modules = await import("./pipeline.js");
}

async function imageDataOf(file) {
  const { fileProblem, pixelProblem } = await import("./limits.js");
  const tooBig = fileProblem(file);
  if (tooBig) throw new Error(tooBig);
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const px = pixelProblem(bitmap.width, bitmap.height);
  if (px) {
    bitmap.close();
    throw new Error(px);
  }
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

async function processFile(file, options) {
  const { imageIdFor, runGrid } = modules;
  const imageId = await imageIdFor(file.name, await file.arrayBuffer());
  const rgba = cv.matFromImageData(await imageDataOf(file));
  const bgr = new cv.Mat();
  try {
    cv.cvtColor(rgba, bgr, cv.COLOR_RGBA2BGR);
    const res = runGrid(cv, bgr, { ...options, imageId, photoFile: file.name, forDisplay: true });
    return { ...res, problems: res.problems.map((q) => q.asDict()), measured: undefined };
  } finally {
    rgba.delete();
    bgr.delete();
  }
}

self.onmessage = async ({ data }) => {
  if (data.type === "init") {
    try {
      await init(data.opencv);
      self.postMessage({ type: "ready" });
    } catch (e) {
      self.postMessage({ type: "error", message: e.message || String(e) });
    }
  } else if (data.type === "process") {
    try {
      const result = await processFile(data.file, data.options);
      const buffers = [result.display.rgba.buffer, ...result.crops.map((k) => k.rgba.buffer)];
      self.postMessage({ type: "done", id: data.id, result }, buffers);
    } catch (e) {
      self.postMessage({ type: "failed", id: data.id, message: e.message || String(e) });
    }
  }
};
