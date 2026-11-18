// Part 8: the app. Print a background -> measure photos (in the browser) -> check the results -> download.
// Processing runs on the user's machine; Cloudflare Pages only serves these files.
import { OPENCV, loadOpenCV } from "./opencv.js";
import { imageIdFor, runGrid } from "./pipeline.js";
import { NOTE, particlesCsv, summaryCsv } from "./export/csv.js";

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
    return runGrid(cv, bgr, { sampleId, photo, imageId, metadata, lineMm, forDisplay: true, keepContext: true });
  } finally {
    rgba.delete();
    bgr.delete();
  }
}

async function readImage(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

const nextFrame = () => new Promise((r) => setTimeout(r, 0));

function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
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

  let cv;
  try {
    // The pinned CDN copy, checked by its hash; ?opencv=local (or a CDN failure) uses web/vendor/.
    cv = params.get("opencv") === "local" ? await loadOpenCV({ src: OPENCV.vendorPath, integrity: null })
      : await loadOpenCV().catch(() => loadOpenCV({ src: OPENCV.vendorPath, integrity: null }));
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
        const img = await readImage(file);
        const res = await processPhoto(cv, img, file, { sampleId: f.get("sampleId"), photo, metadata, lineMm });
        state.photos.push({ name: file.name, ...res, rows: res.rows.slice(), decisions: [] });
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

  document.querySelectorAll("[data-download]").forEach((b) => b.addEventListener("click", () => {
    const rows = state.photos.flatMap((p) => p.rows);
    const name = b.dataset.download;
    if (name === "particles.csv") download(name, particlesCsv(rows), "text/csv");
    else if (name === "summary.csv") download(name, summaryCsv(rows), "text/csv");
    else if (name === "NOTE.txt") download(name, `${NOTE}\n`, "text/plain");
    else download(name, JSON.stringify(state.photos.map((p) => ({ photo: p.name, ...p.run, review: p.decisions })), null, 2),
      "application/json");
  }));
}

if (typeof document !== "undefined") main();
