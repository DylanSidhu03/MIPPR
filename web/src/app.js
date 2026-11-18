// Part 8: the app. Print a background -> measure photos (in the browser) -> check the results -> download.
// Processing runs on the user's machine; Cloudflare Pages only serves these files.
import { OPENCV_LOCAL_URL, loadOpenCV } from "./opencv.js";
import { photoContext } from "./review/context.js";
import { fileProblem, pixelProblem } from "./limits.js";
import { APP_VERSION, imageIdFor, runGrid } from "./pipeline.js";
import { NOTE, particlesCsv, summaryCsv } from "./export/csv.js";
import { summaryHtml } from "./export/report.js";
import { zip } from "./export/zip.js";
import { drawOverlay } from "./review/screen.js";

export { particlesCsv, summaryCsv };

/**
 * Run one photo through parts 1-5 in the browser.
 * `imageData` is a canvas ImageData (RGBA); `file` the uploaded File (for its name and hash).
 * Returns runGrid's result (rows, problems, quality, run, display, outlines), or throws with a
 * message for the user when the photo has no printed MIPPR sheet.
 */
export async function processPhoto(cv, imageData, file, { sampleId, photo, metadata, lineMm } = {}) {
  const imageId = await imageIdFor(file.name, await file.arrayBuffer());
  const rgba = cv.matFromImageData(imageData);
  const bgr = new cv.Mat();
  try {
    cv.cvtColor(rgba, bgr, cv.COLOR_RGBA2BGR);
    const res = runGrid(cv, bgr, { sampleId, photo, imageId, photoFile: file.name, metadata, lineMm, forDisplay: true,
      keepContext: true });
    return { ...res, problems: res.problems.map((q) => q.asDict()) };
  } finally {
    rgba.delete();
    bgr.delete();
  }
}

/**
 * The photo processor: a background worker (worker.js) when the browser allows it, else the page itself.
 * `process(file, options)` resolves with runGrid's result; `onPage` says which is in use.
 */
async function startProcessor() {
  try {
    const worker = new Worker(new URL("./worker.js", import.meta.url));
    const pending = new Map();
    let next = 0;
    await new Promise((resolve, reject) => {
      worker.onmessage = ({ data }) => (data.type === "ready" ? resolve() : reject(new Error(data.message)));
      worker.onerror = (e) => reject(new Error(e.message || "The background worker failed to start."));
      worker.postMessage({ type: "init", opencv: OPENCV_LOCAL_URL });
    });
    worker.onmessage = ({ data }) => {
      const p = pending.get(data.id);
      pending.delete(data.id);
      if (data.type === "done") p.resolve(data.result);
      else p.reject(new Error(data.message));
    };
    return {
      onPage: false,
      process: (file, options) => new Promise((resolve, reject) => {
        const id = next++;
        pending.set(id, { resolve, reject });
        worker.postMessage({ type: "process", id, file, options });
      }),
    };
  } catch (e) {
    console.warn(`Processing on the page (no background worker: ${e.message})`);
    const cv = await loadOpenCV();
    return { onPage: true, process: async (file, options) => processPhoto(cv, await readImage(file), file, options) };
  }
}

/** The photo's measuring context, built on the page from the photo itself, for the outline tools. */
async function contextFor(file, lineMm) {
  const cv = await loadOpenCV();
  const rgba = cv.matFromImageData(await readImage(file));
  const bgr = new cv.Mat();
  try {
    cv.cvtColor(rgba, bgr, cv.COLOR_RGBA2BGR);
    return photoContext(cv, bgr, { lineMm });
  } finally {
    rgba.delete();
    bgr.delete();
  }
}

async function readImage(file) {
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

const nextFrame = () => new Promise((r) => setTimeout(r, 0));

function download(name, data, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([data], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function canvasBytes(canvas, type = "image/png", quality) {
  return new Uint8Array(await (await canvas.convertToBlob({ type, quality })).arrayBuffer());
}

function rgbaCanvas({ width, height, rgba }) {
  const c = new OffscreenCanvas(width, height);
  c.getContext("2d").putImageData(new ImageData(rgba, width, height), 0, 0);
  return c;
}

/** The photo's overlay (outlines coloured by review status, box labels) on a canvas. */
function overlayCanvas(photo) {
  const base = rgbaCanvas(photo.display);
  const c = new OffscreenCanvas(base.width, base.height);
  drawOverlay(c.getContext("2d"), base, photo);
  return c;
}

/** A JPEG data URL of the overlay, at most `maxWidth` px wide, for summary.html. */
async function overlayDataUrl(photo, maxWidth = 1200) {
  const full = overlayCanvas(photo);
  const s = Math.min(1, maxWidth / full.width);
  const c = new OffscreenCanvas(Math.round(full.width * s), Math.round(full.height * s));
  c.getContext("2d").drawImage(full, 0, 0, c.width, c.height);
  const blob = await c.convertToBlob({ type: "image/jpeg", quality: 0.85 });
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.readAsDataURL(blob);
  });
}

function li(text, cls = "") {
  const el = document.createElement("li");
  el.textContent = text;
  if (cls) el.className = cls;
  return el;
}

async function main() {
  const $ = (s) => document.querySelector(s);
  const form = $("#measure-form"), run = $("#run"), status = $("#status");
  const state = { photos: [], active: null, screen: null };
  const params = new URLSearchParams(location.search);
  const remember = (id) => {
    const el = $(id);
    try {
      el.value = localStorage.getItem(`mippr${id}`) ?? el.value;
      el.addEventListener("change", () => localStorage.setItem(`mippr${id}`, el.value));
    } catch {
      /* storage blocked: nothing to remember */
    }
  };
  remember("#reviewer");
  remember("#role");

  let processor;
  try {
    // OpenCV.js is served with the site (web/vendor/); ?worker=off processes on the page.
    processor = params.get("worker") === "off"
      ? { onPage: true, process: async (file, options) => processPhoto(await loadOpenCV(), await readImage(file), file, options) }
      : await startProcessor();
    run.disabled = false;
    run.textContent = "Measure";
  } catch (e) {
    run.textContent = "Image tools failed to load";
    status.append(li(e.message, "refused"));
    return;
  }

  const showPhoto = (i) => {
    state.active = i;
    $("#photo-tabs").querySelectorAll("button").forEach((b, k) => b.setAttribute("aria-pressed", String(k === i)));
    const photo = state.photos[i];
    import("./review/screen.js").then(({ ReviewScreen }) => {
      state.screen = new ReviewScreen($("#review-area"), photo, {
        getReviewer: () => ({ reviewer: $("#reviewer").value.trim(), role: $("#role").value }),
        onChange: () => {},
      });
    });
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(form);
    const files = [...form.elements.files.files];
    const metadata = Object.fromEntries(["date", "operator", "lab", "setup", "site"].map((k) => [k, f.get(k) || ""]));
    const lineMm = f.get("lineMm") ? Number(f.get("lineMm")) : null;
    run.disabled = true;
    status.replaceChildren();
    let photo = Number(f.get("photo") || 1);
    for (const file of files) {
      const item = status.appendChild(li(`${file.name}: measuring…`));
      await nextFrame();
      try {
        const res = await processor.process(file, { sampleId: f.get("sampleId"), photo, metadata, lineMm });
        // The outline tools need the photo's measuring context: kept from an on-page run, else built on demand.
        state.photos.push({ name: file.name, ...res, rows: res.rows.slice(), decisions: [],
          makeContext: () => contextFor(file, lineMm) });
        const warn = res.problems.map((p) => p.message).join(" ");
        item.textContent = `${file.name}: ${res.rows.length} particles, ${res.rows.filter((r) => r.review_reason).length} flagged for checking` +
          ` (${res.run.background_type.replace("_", " ")})${warn ? `. ${warn}` : ""}`;
        if (warn) item.className = "warn";
        photo += 1;
      } catch (err) {
        item.textContent = `${file.name}: not measured. ${err.message.replaceAll("\n", " ")}`;
        item.className = "refused";
      }
    }
    run.disabled = false;
    if (!state.photos.length) return;
    const tabs = $("#photo-tabs");
    tabs.replaceChildren(...state.photos.map((p, i) => {
      const b = document.createElement("button");
      b.textContent = `${p.run.picture_label} · ${p.name}`;
      b.addEventListener("click", () => showPhoto(i));
      return b;
    }));
    $("#review").hidden = false;
    $("#export").hidden = false;
    showPhoto(state.photos.length - 1);
  });

  document.addEventListener("keydown", (e) => {
    if (state.screen?.handleKey(e)) e.preventDefault();
  });

  document.querySelectorAll("[data-download]").forEach((b) => b.addEventListener("click", async () => {
    const rows = state.photos.flatMap((p) => p.rows);
    const name = b.dataset.download;
    if (name === "crops.zip" || name === "overlays.zip" || name === "summary.html") {
      const label = b.textContent;
      b.disabled = true;
      b.textContent = "Preparing…";
      try {
        if (name === "crops.zip") {
          const files = [];
          for (const p of state.photos) for (const k of p.crops) files.push({ name: k.file, data: await canvasBytes(rgbaCanvas(k)) });
          download(name, zip(files), "application/zip");
        } else if (name === "overlays.zip") {
          const files = [];
          for (const p of state.photos) files.push({ name: `${p.run.picture_label}_overlay.png`, data: await canvasBytes(overlayCanvas(p)) });
          download(name, zip(files), "application/zip");
        } else {
          const photos = [];
          for (const p of state.photos) photos.push({ ...p, overlay: await overlayDataUrl(p) });
          download(name, summaryHtml(photos, { appVersion: APP_VERSION }), "text/html");
        }
      } finally {
        b.disabled = false;
        b.textContent = label;
      }
      return;
    }
    if (name === "particles.csv") download(name, particlesCsv(rows), "text/csv");
    else if (name === "summary.csv") download(name, summaryCsv(rows), "text/csv");
    else if (name === "NOTE.txt") download(name, `${NOTE}\n`, "text/plain");
    else download(name, JSON.stringify(state.photos.map((p) => ({ photo: p.name, ...p.run, review: p.decisions })), null, 2),
      "application/json");
  }));
}

if (typeof document !== "undefined") main();
