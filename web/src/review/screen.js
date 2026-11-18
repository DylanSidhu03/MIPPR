// Part 6: the review screen. The photo's flattened grid with every outline, a panel for the selected
// particle, and the particle table in review order. Decisions go through corrections.js, the twin of
// pipeline/mippr/review/corrections.py, so labels change, numbers don't, and the prediction is kept.
import { REVIEW_COLORS, REVIEW_MORPHOLOGIES, apply, merge, reviewQueue, split } from "./corrections.js";
import { cutPieces, mergedOutline, pathOutline, polygonsMask } from "./edit.js";

const HINTS = {
  split: "Drag a line across the particle where it should be cut.",
  merge: "Click the other particle that is part of this one.",
  redraw: "Draw round the particle, holding the mouse button down; let go to finish.",
};

const isTrue = (v) => v === true || v === "True";
const fmt = (v, d = 2) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : v === "" || v == null ? "–" : String(v));

/** auto, flagged (auto with a review reason), confirmed, corrected or rejected. */
export function displayStatus(row) {
  return row.review_status === "auto" && row.review_reason ? "flagged" : row.review_status;
}

function inside(pt, poly) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

function distToPoly(pt, poly) {
  let best = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [ax, ay] = poly[j], [bx, by] = poly[i];
    const dx = bx - ax, dy = by - ay;
    const t = dx || dy ? Math.max(0, Math.min(1, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / (dx * dx + dy * dy))) : 0;
    best = Math.min(best, Math.hypot(pt[0] - ax - t * dx, pt[1] - ay - t * dy));
  }
  return best;
}

/**
 * Draw the photo's flattened grid (`base`, a canvas or image) with every outline, coloured by review
 * status (CSS variables --auto, --flagged, ...; rejected dashed) and labelled with its box. Used by the
 * review screen and for the overlay images.
 */
export function drawOverlay(ctx, base, photo, { selected = null } = {}) {
  ctx.drawImage(base, 0, 0);
  const width = ctx.canvas.width;
  const lw = Math.max(2, width / 450);
  const css = typeof document !== "undefined" ? getComputedStyle(document.documentElement) : null;
  ctx.font = `${Math.round(lw * 7)}px system-ui, sans-serif`;
  photo.rows.forEach((row, i) => {
    const status = displayStatus(row);
    ctx.strokeStyle = css?.getPropertyValue(`--${status}`).trim() || "#1f77b4";
    ctx.lineWidth = i === selected ? lw * 2.5 : lw;
    ctx.setLineDash(status === "rejected" ? [lw * 3, lw * 2] : []);
    let minX = Infinity, minY = Infinity;
    for (const poly of photo.outlines[i]) {
      ctx.beginPath();
      poly.forEach(([x, y], k) => (k ? ctx.lineTo(x + 0.5, y + 0.5) : ctx.moveTo(x + 0.5, y + 0.5)));
      ctx.closePath();
      ctx.stroke();
      for (const [x, y] of poly) (minX = Math.min(minX, x)), (minY = Math.min(minY, y));
    }
    ctx.setLineDash([]);
    ctx.lineWidth = lw * 1.5;
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.fillStyle = "#111";
    ctx.strokeText(row.particle_id, minX, minY - lw * 2);
    ctx.fillText(row.particle_id, minX, minY - lw * 2);
  });
}

export class ReviewScreen {
  /**
   * photo: {name, rows, display: {width, height, rgba}, outlines} (rows and outlines in the same order);
   * getReviewer(): {reviewer, role}; onChange(): called after every decision.
   */
  constructor(container, photo, { getReviewer, onChange }) {
    Object.assign(this, { container, photo, getReviewer, onChange, selected: null, message: "", mode: null, path: null });
    this.context = photo.context ?? null; // context.js: needed to measure edited outlines
    const { width, height, rgba } = photo.display;
    this.base = document.createElement("canvas");
    Object.assign(this.base, { width, height });
    this.base.getContext("2d").putImageData(new ImageData(rgba, width, height), 0, 0);
    this.build();
    this.selected = this.queue()[0] ?? null;
    this.render();
  }

  queue() {
    const index = new Map(this.photo.rows.map((r, i) => [r.particle_ref, i]));
    return reviewQueue(this.photo.rows).map((r) => index.get(r.particle_ref));
  }

  build() {
    this.container.innerHTML = `
      <div class="review-layout">
        <div><div class="canvas-wrap"><canvas></canvas></div></div>
        <aside class="panel"></aside>
      </div>
      <div class="particles"><table><thead><tr>
        <th>Box</th><th>Length mm</th><th>Width mm</th><th>Colour</th><th>Shape</th><th>Flags</th><th>Status</th>
      </tr></thead><tbody></tbody></table></div>`;
    this.canvas = this.container.querySelector("canvas");
    Object.assign(this.canvas, { width: this.base.width, height: this.base.height });
    this.panel = this.container.querySelector(".panel");
    this.tbody = this.container.querySelector("tbody");
    this.canvas.addEventListener("click", (e) => this.clickAt(e));
    this.canvas.addEventListener("pointerdown", (e) => this.pointerDown(e));
    this.canvas.addEventListener("pointermove", (e) => this.pointerMove(e));
    this.canvas.addEventListener("pointerup", (e) => this.pointerUp(e));
    this.tbody.addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-i]");
      if (tr) this.select(Number(tr.dataset.i));
    });
  }

  toGrid(e) {
    const r = this.canvas.getBoundingClientRect();
    return [((e.clientX - r.left) * this.canvas.width) / r.width, ((e.clientY - r.top) * this.canvas.height) / r.height];
  }

  clickAt(e) {
    if (this.mode === "split" || this.mode === "redraw") return; // drawing, not selecting
    const r = this.canvas.getBoundingClientRect();
    const pt = this.toGrid(e);
    let best = null, bestD = (12 * this.canvas.width) / r.width; // within about 12 screen px of an outline
    const reach = bestD;
    this.photo.outlines.forEach((polys, i) => {
      // A rejected row's outline (e.g. a particle replaced by its split pieces) loses to a kept one under it.
      const penalty = this.photo.rows[i].review_status === "rejected" ? reach / 2 : 0;
      for (const poly of polys) {
        const d = (inside(pt, poly) ? 0 : distToPoly(pt, poly)) + penalty;
        if (d < bestD) (best = i), (bestD = d);
      }
    });
    if (best === null) return;
    if (this.mode === "merge") this.finishMerge(best);
    else this.select(best);
  }

  // ── Outline tools: split, merge, redraw ──────────────────────────────────

  startMode(mode) {
    if (this.selected === null) return;
    if (!this.context) {
      this.message = "The outline tools need the photo's measurements; measure the photo again to use them.";
      return this.renderPanel();
    }
    this.mode = this.mode === mode ? null : mode;
    this.message = this.mode ? HINTS[mode] : "";
    this.render();
  }

  cancelMode() {
    this.mode = this.path = null;
    this.message = "";
    this.render();
  }

  pointerDown(e) {
    if (this.mode !== "split" && this.mode !== "redraw") return;
    this.path = [this.toGrid(e)];
    this.canvas.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }

  pointerMove(e) {
    if (!this.path) return;
    this.path.push(this.toGrid(e));
    this.draw();
    const ctx = this.canvas.getContext("2d");
    ctx.strokeStyle = "#d6336c";
    ctx.lineWidth = Math.max(2, this.canvas.width / 450);
    ctx.setLineDash([]);
    ctx.beginPath();
    const pts = this.mode === "split" ? [this.path[0], this.path[this.path.length - 1]] : this.path;
    pts.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.stroke();
  }

  pointerUp(e) {
    if (!this.path) return;
    this.path.push(this.toGrid(e));
    const path = this.path;
    this.path = null;
    if (this.mode === "split") this.finishSplit(path[0], path[path.length - 1]);
    else this.finishRedraw(path);
  }

  maskOf(i) {
    const { width, height } = this.photo.display;
    return polygonsMask(this.context.cv, this.photo.outlines[i], width, height);
  }

  finishSplit(p0, p1) {
    const { width, height } = this.photo.display;
    const pieces = cutPieces(this.context.cv, this.maskOf(this.selected), width, height, p0, p1);
    if (pieces.length < 2) {
      this.message = "That line doesn't cut the particle in two. Drag it right across the particle.";
      return this.render();
    }
    this.listDecision({ action: "split", outlines: pieces }, pieces.map((p) => [p]));
  }

  finishMerge(other) {
    if (other === this.selected) return;
    const { width, height } = this.photo.display;
    const outline = mergedOutline(this.context.cv, [this.maskOf(this.selected), this.maskOf(other)], width, height);
    this.listDecision({ action: "merge", outline, mergeWith: [this.photo.rows[other].particle_ref] }, [[outline]]);
  }

  finishRedraw(path) {
    const outline = pathOutline(path);
    if (!outline) {
      this.message = "Draw round the particle, holding the mouse button down.";
      return this.render();
    }
    const i = this.selected;
    this.mode = null;
    if (this.decide({ action: "edit_outline", outline })) {
      this.photo.outlines[i] = [outline];
      this.render();
    }
  }

  /** A split or merge: new rows from corrections.js, and their outlines (`newOutlines`, in order). */
  listDecision(partial, newOutlines) {
    const row = this.photo.rows[this.selected];
    const { reviewer, role } = this.getReviewer();
    const d = { particleRef: row.particle_ref, reviewer, role, at: new Date().toISOString(), ...partial };
    let rows;
    try {
      rows = (partial.action === "split" ? split : merge)(this.photo.rows, d, this.context);
    } catch (e) {
      this.message = e.message === "A decision needs a reviewer." ? "Enter your name above first." : e.message;
      return this.renderPanel();
    }
    const byRef = new Map(this.photo.rows.map((r, i) => [r.particle_ref, this.photo.outlines[i]]));
    const fresh = [...newOutlines];
    this.photo.outlines = rows.map((r) => byRef.get(r.particle_ref) ?? fresh.shift());
    this.photo.rows = rows;
    (this.photo.decisions ??= []).push({ particleRef: row.particle_ref, reviewer, role, ...partial });
    this.mode = null;
    this.message = "";
    this.selected = rows.findIndex((r) => !byRef.has(r.particle_ref));
    this.onChange?.();
    this.render();
  }

  select(i) {
    this.selected = i;
    this.mode = null;
    this.message = "";
    this.render();
  }

  draw() {
    drawOverlay(this.canvas.getContext("2d"), this.base, this.photo, { selected: this.selected });
  }

  renderPanel() {
    const q = this.queue();
    const open = q.filter((i) => this.photo.rows[i].review_status === "auto").length;
    if (this.selected === null) {
      this.panel.innerHTML = `<p>No particles found on this photo.</p>`;
      return;
    }
    const r = this.photo.rows[this.selected];
    const options = (list, value) =>
      list.map((v) => `<option value="${v}"${v === value ? " selected" : ""}>${v}</option>`).join("");
    const status = displayStatus(r);
    this.panel.innerHTML = `
      <p class="queue">${open} of ${q.length} still to check · ${q.indexOf(this.selected) + 1} in the review order</p>
      <h3>${r.particle_id} <span class="status ${status}">${status}</span></h3>
      <dl>
        <dt>Length</dt><dd>${fmt(r.length_mm)} mm${r.size_length_source === "fiber_length" ? ` (along the fiber ${fmt(r.fiber_length_mm)})` : ""}</dd>
        <dt>Width</dt><dd>${fmt(r.width_mm)} mm</dd>
        <dt>Size check</dt><dd>${r.size_uncertainty === "" ? "–" : `${fmt(100 * r.size_uncertainty, 0)}% ${isTrue(r.flag_size_uncertain) ? "(unsure)" : ""}`}</dd>
        <dt>Colour</dt><dd>${r.color_label || "–"} ${r.color_confidence !== "" ? `(${fmt(100 * r.color_confidence, 0)}%)` : ""}${r.color_secondary ? `, also ${r.color_secondary}` : ""}${r.color_label_original ? ` · was ${r.color_label_original}` : ""}</dd>
        <dt>Shape</dt><dd>${r.morphology_label} (${r.morphology_source}${r.morphology_confidence !== "" ? `, ${fmt(100 * r.morphology_confidence, 0)}%` : ""})${r.morphology_label_original ? ` · was ${r.morphology_label_original}` : ""}</dd>
        <dt>Flags</dt><dd>${r.review_reason ? r.review_reason.replaceAll(";", ", ") : "none"}</dd>
      </dl>
      <div class="actions">
        <button data-act="confirm" class="primary">Confirm <kbd>A</kbd></button>
        <button data-act="reject">Reject <kbd>X</kbd></button>
        <button data-act="prev">◀ <kbd>P</kbd></button>
        <button data-act="next">▶ <kbd>N</kbd></button>
      </div>
      <div class="actions">
        <button data-act="split"${this.mode === "split" ? ' aria-pressed="true"' : ""}>Split <kbd>S</kbd></button>
        <button data-act="merge"${this.mode === "merge" ? ' aria-pressed="true"' : ""}>Merge with… <kbd>G</kbd></button>
        <button data-act="redraw"${this.mode === "redraw" ? ' aria-pressed="true"' : ""}>Redraw outline <kbd>R</kbd></button>
      </div>
      <div class="actions">
        <label>Colour <select data-relabel="color">${options(REVIEW_COLORS, r.color_label)}</select></label>
        <label>Shape <select data-relabel="morphology">${options(REVIEW_MORPHOLOGIES, r.morphology_label)}</select></label>
      </div>
      <div class="actions">
        <label><input type="checkbox" data-tag="tar_like"${isTrue(r.tar_like) ? " checked" : ""}> tar-like <kbd>T</kbd></label>
        <label><input type="checkbox" data-tag="flag_bundle"${isTrue(r.flag_bundle) ? " checked" : ""}> fiber bundle <kbd>B</kbd></label>
      </div>
      <p class="error" role="alert">${this.message}</p>`;
    this.panel.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => this.act(b.dataset.act)));
    this.panel.querySelectorAll("[data-relabel]").forEach((s) =>
      s.addEventListener("change", () =>
        this.decide({ action: "relabel", [s.dataset.relabel === "color" ? "colorLabel" : "morphologyLabel"]: s.value })));
    this.panel.querySelectorAll("[data-tag]").forEach((c) =>
      c.addEventListener("change", () => this.decide({ action: "tag", tags: { [c.dataset.tag]: c.checked } })));
  }

  renderTable() {
    this.tbody.innerHTML = this.queue().map((i) => {
      const r = this.photo.rows[i];
      const status = displayStatus(r);
      return `<tr data-i="${i}" class="${i === this.selected ? "selected" : ""} ${status}">
        <td>${r.particle_id}</td><td>${fmt(r.length_mm)}</td><td>${fmt(r.width_mm)}</td>
        <td>${r.color_label || "–"}</td><td>${r.morphology_label}</td>
        <td>${r.review_reason ? r.review_reason.replaceAll(";", ", ") : ""}</td>
        <td><span class="status ${status}">${status}</span></td></tr>`;
    }).join("");
  }

  render() {
    this.draw();
    this.renderPanel();
    this.renderTable();
  }

  step(dir) {
    const q = this.queue();
    if (!q.length) return;
    const k = q.indexOf(this.selected);
    this.select(q[(k + dir + q.length) % q.length]);
  }

  act(name) {
    if (name === "split" || name === "merge" || name === "redraw") return this.startMode(name);
    if (name === "next") return this.step(1);
    if (name === "prev") return this.step(-1);
    this.decide({ action: name });
  }

  decide(partial) {
    if (this.selected === null) return false;
    const row = this.photo.rows[this.selected];
    const { reviewer, role } = this.getReviewer();
    try {
      this.photo.rows[this.selected] = apply(row, {
        particleRef: row.particle_ref, reviewer, role, at: new Date().toISOString(), ...partial,
      }, this.context);
      (this.photo.decisions ??= []).push({ particleRef: row.particle_ref, reviewer, role, ...partial });
      this.message = "";
    } catch (e) {
      this.message = e.message === "A decision needs a reviewer." ? "Enter your name above first." : e.message;
      this.renderPanel();
      return false;
    }
    this.onChange?.();
    if (partial.action === "confirm" || partial.action === "reject") {
      const next = this.queue().find((i) => this.photo.rows[i].review_status === "auto");
      this.selected = next ?? this.selected;
    }
    this.render();
    return true;
  }

  /** Keyboard shortcuts; returns true when the key was used. */
  handleKey(e) {
    if (e.target.closest("input, select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return false;
    const r = this.selected === null ? null : this.photo.rows[this.selected];
    const k = e.key.toLowerCase();
    if (k === "a") this.act("confirm");
    else if (k === "x") this.act("reject");
    else if (k === "n" || k === "arrowright") this.step(1);
    else if (k === "p" || k === "arrowleft") this.step(-1);
    else if (k === "c") this.panel.querySelector('[data-relabel="color"]')?.focus();
    else if (k === "m") this.panel.querySelector('[data-relabel="morphology"]')?.focus();
    else if (k === "t" && r) this.decide({ action: "tag", tags: { tar_like: !isTrue(r.tar_like) } });
    else if (k === "b" && r) this.decide({ action: "tag", tags: { flag_bundle: !isTrue(r.flag_bundle) } });
    else if (k === "s") this.startMode("split");
    else if (k === "g") this.startMode("merge");
    else if (k === "r") this.startMode("redraw");
    else if (k === "escape" && this.mode) this.cancelMode();
    else return false;
    return true;
  }
}
