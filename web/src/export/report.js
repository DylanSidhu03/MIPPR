// summary.html: a one-file report of a run, for sharing or printing. Per sample: counts by shape, colour and
// size class, review progress and flags; per photo: its scale, quality problems and the overlay image.
// Built from the same rows as particles.csv and summary.csv (buildSummary), so the numbers agree.
import { NOTE, buildSummary } from "./csv.js";

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const label = (k) => k.replace(/^count_(color_|size_)?/, "").replace(/^n_flag_/, "").replaceAll("_", " ");

function countTable(title, s, prefix, exclude = /^$/) {
  const cells = Object.entries(s).filter(([k, v]) => k.startsWith(prefix) && !exclude.test(k) && v !== "" && Number(v) > 0);
  if (!cells.length) return "";
  return `<div><h4>${esc(title)}</h4><table><tbody>${cells.map(([k, v]) =>
    `<tr><th scope="row">${esc(label(k))}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div>`;
}

/**
 * The report as an HTML string. `photos`: [{name, rows, run, problems, overlay}] where `overlay` is an
 * image data URL (or empty). `generatedAt` is an ISO time.
 */
export function summaryHtml(photos, { generatedAt = new Date().toISOString(), appVersion = "" } = {}) {
  const rows = photos.flatMap((p) => p.rows);
  const samples = buildSummary(rows).map((s) => {
    const flags = Object.entries(s).filter(([k, v]) => k.startsWith("n_flag_") && Number(v) > 0);
    const length = s.length_mm_median === "" ? "–"
      : `median ${Number(s.length_mm_median).toFixed(2)} mm (${Number(s.length_mm_min).toFixed(2)}–${Number(s.length_mm_max).toFixed(2)})`;
    return `<section><h2>Sample ${esc(s.sample_id)}</h2>
      <p>${esc(s.n_particles)} particles kept from ${esc(s.n_images)} photo(s) · length ${esc(length)} ·
        ${esc(s.n_reviewed)} reviewed, ${esc(s.n_corrected)} corrected</p>
      <div class="tables">${countTable("Shape", s, "count_", /^count_(color|size)_/)}
      ${countTable("Colour", s, "count_color_")}${countTable("Size class (mm)", s, "count_size_")}
      ${flags.length ? `<div><h4>Flagged for checking</h4><table><tbody>${flags.map(([k, v]) =>
        `<tr><th scope="row">${esc(label(k))}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div>` : ""}</div>
    </section>`;
  }).join("");
  const perPhoto = photos.map((p) => {
    const r = p.run;
    const scale = r.printer_scale?.scale && Math.abs(r.printer_scale.scale - 1) > 0.01
      ? ` · printer scale ${(100 * r.printer_scale.scale).toFixed(1)}% (corrected)` : "";
    const probs = (p.problems ?? []).map((q) => `<li>${esc(q.message)}</li>`).join("");
    return `<section class="photo"><h3>${esc(r.picture_label)} · ${esc(p.name)}</h3>
      <p>${esc(String(r.background_type).replace("_", " "))} · ${esc(r.paper)} · ${p.rows.length} particles ·
        ${Number(r.mm_per_px * 1000).toFixed(1)} µm per pixel${esc(scale)}</p>
      ${probs ? `<ul class="problems">${probs}</ul>` : ""}
      ${p.overlay ? `<img src="${p.overlay}" alt="Overlay of ${esc(r.picture_label)}: every particle outlined and labelled with its box">` : ""}
    </section>`;
  }).join("");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MIPPR summary</title>
<style>
  body { font: 15px/1.5 system-ui, sans-serif; color: #1b211e; background: #fff; margin: 0 auto; padding: 24px 16px; max-width: 960px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px; } h2 { margin-top: 28px; } h4 { margin: 12px 0 4px; }
  .meta, .note { color: #5c6661; } .tables { display: flex; flex-wrap: wrap; gap: 8px 32px; }
  table { border-collapse: collapse; } th, td { padding: 2px 10px 2px 0; text-align: left; font-weight: normal; }
  td { font-variant-numeric: tabular-nums; text-align: right; } th { color: #5c6661; }
  img { max-width: 100%; height: auto; border: 1px solid #d9dfdb; } .problems { color: #8a4b12; }
  @media print { .photo { break-inside: avoid; } }
</style></head><body>
<h1>MIPPR summary</h1>
<p class="meta">${esc(photos.length)} photo(s) · ${esc(rows.length)} particles · made ${esc(generatedAt.slice(0, 16).replace("T", " "))} UTC${appVersion ? ` · app ${esc(appVersion)}` : ""}</p>
<p class="note">${esc(NOTE)} Rejected particles are left out of the counts. Colour and shape rules are provisional.</p>
${samples}
<h2>Photos</h2>
${perPhoto}
</body></html>
`;
}
