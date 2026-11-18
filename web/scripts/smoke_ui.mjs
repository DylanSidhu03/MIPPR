// Smoke test of the app in a real browser: upload two sheet photos and one photo without a sheet,
// measure them, review a few particles with the keyboard, and check the downloaded CSVs.
//
//   node web/scripts/fetch_opencv.mjs   # once
//   node web/scripts/smoke_ui.mjs       # needs Playwright with Chromium (not an npm dependency of the repo)
import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { extname, join, normalize } from "node:path";
import { deflateSync } from "node:zlib";

const root = new URL("../../", import.meta.url).pathname;
const fixtures = join(root, "web/tests/fixtures");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".png": "image/png", ".pdf": "application/pdf", ".json": "application/json" };

function serve() {
  const server = createServer((req, res) => {
    const path = normalize(join(root, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    const file = path.endsWith("/") ? join(path, "index.html") : path;
    if (!file.startsWith(root) || !existsSync(file) || statSync(file).isDirectory()) return res.writeHead(404).end();
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** A plain grey PNG with no sheet on it. */
function blankPng(path, w = 400, h = 300) {
  const crcTable = (buf) => {
    let c = 0xffffffff;
    for (const b of buf) {
      c ^= b;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type, "latin1"), data]);
    const c = Buffer.alloc(4);
    c.writeUInt32BE(crcTable(body));
    return Buffer.concat([len, body, c]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0), ihdr.writeUInt32BE(h, 4), (ihdr[8] = 8), (ihdr[9] = 0);
  const raw = Buffer.alloc((w + 1) * h, 200);
  for (let y = 0; y < h; y++) raw[y * (w + 1)] = 0;
  writeFileSync(path, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
}

const { chromium } = createRequire(import.meta.url)("playwright");
const server = await serve();
const base = `http://127.0.0.1:${server.address().port}/web/?opencv=local`;
const tmp = mkdtempSync(join(tmpdir(), "mippr-smoke-"));
blankPng(join(tmp, "not_a_sheet.png"));
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1300, height: 950 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(base);
  await page.waitForFunction(() => !document.querySelector("#run").disabled, null, { timeout: 120000 });
  await page.fill("input[name=sampleId]", "S042");
  await page.setInputFiles("input[name=files]", [join(fixtures, "quality_white_grid.png"), join(tmp, "not_a_sheet.png"),
    join(fixtures, "quality_black_grid.png")]);
  await page.click("#run");
  await page.waitForSelector(".particles tbody tr", { timeout: 300000 });
  const status = await page.$$eval("#status li", (ls) => ls.map((l) => [l.className, l.textContent]));
  assert.equal(status.length, 3);
  assert.match(status[0][1], /3 particles/);
  assert.equal(status[1][0], "refused");
  assert.match(status[1][1], /printed MIPPR backgrounds/);

  await page.keyboard.press("a");
  assert.match(await page.textContent(".panel .error"), /Enter your name/);
  await page.fill("#reviewer", "Tester");
  await page.click("h2");
  await page.keyboard.press("a"); // confirm the first particle in the review order
  await page.selectOption('[data-relabel="color"]', "grey"); // relabel the next one
  await page.click("h2");
  await page.keyboard.press("x"); // and reject it

  await page.locator("canvas").scrollIntoViewIfNeeded();
  const box = await page.locator("canvas").boundingBox();
  const [cw, ch] = await page.evaluate(() => [document.querySelector("canvas").width, document.querySelector("canvas").height]);
  const b = cw / 12; // B2 is the box in row 2, column 2
  await page.mouse.click(box.x + (1.5 * b * box.width) / cw, box.y + (1.5 * b * box.height) / ch);
  assert.match(await page.textContent(".panel h3"), /^B2/);

  const download = async (name) => {
    const [d] = await Promise.all([page.waitForEvent("download"), page.click(`[data-download="${name}"]`)]);
    const p = join(tmp, name);
    await d.saveAs(p);
    return readFileSync(p, "utf8");
  };
  const lines = (await download("particles.csv")).trim().split("\r\n");
  const head = lines[0].split(",");
  const rows = lines.slice(1).map((l) => Object.fromEntries(l.split(",").map((v, i) => [head[i], v])));
  assert.equal(rows.length, 6);
  const statuses = rows.filter((r) => r.picture_label === "S042-P02").map((r) => r.review_status).sort();
  assert.deepEqual(statuses, ["auto", "confirmed", "rejected"]);
  const rejected = rows.find((r) => r.review_status === "rejected");
  assert.equal(rejected.color_label, "grey");
  assert.ok(rejected.color_label_original && rejected.reviewed_by === "Tester" && rejected.reviewer_role === "expert");
  const summary = (await download("summary.csv")).trim().split("\r\n");
  assert.equal(summary[1].split(",").slice(0, 3).join(","), "S042,2,5"); // the rejected particle leaves the summary
  // Crops, overlays and the HTML summary.
  const binary = async (name) => {
    const [d] = await Promise.all([page.waitForEvent("download"), page.click(`[data-download="${name}"]`)]);
    const p = join(tmp, name);
    await d.saveAs(p);
    return readFileSync(p);
  };
  const entries = (z) => { // names in a ZIP's central directory
    const end = z.length - 22, n = z.readUInt16LE(end + 10);
    let p = z.readUInt32LE(end + 16);
    const names = [];
    for (let i = 0; i < n; i++) {
      const len = z.readUInt16LE(p + 28);
      names.push(z.subarray(p + 46, p + 46 + len).toString());
      p += 46 + len;
    }
    return names;
  };
  const crops = entries(await binary("crops.zip"));
  assert.deepEqual(crops.sort(), rows.map((r) => r.crop_file).sort());
  assert.deepEqual(entries(await binary("overlays.zip")).sort(), ["S042-P01_overlay.png", "S042-P02_overlay.png"]);
  const html = (await binary("summary.html")).toString();
  assert.match(html, /Sample S042/);
  assert.equal((html.match(/<img src="data:image\/jpeg/g) || []).length, 2);
  assert.deepEqual(errors, []);
  console.log("smoke test passed: measure, refuse a photo without a sheet, review with keys and clicks, download");
} finally {
  await browser.close();
  server.close();
}
