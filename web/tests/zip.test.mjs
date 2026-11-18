// The stored-ZIP writer used for crops.zip and the overlay images.
import assert from "node:assert/strict";
import { test } from "node:test";
import { crc32, zip } from "../src/export/zip.js";

test("crc32 check value", () => assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926));

test("zip round trip through its central directory", () => {
  const files = [{ name: "crops/S1-P01-B4.png", data: Uint8Array.from([1, 2, 3, 250]) },
    { name: "crops/S1-P01-B4-1.png", data: new Uint8Array(0) }, { name: "é.txt", data: new TextEncoder().encode("hi") }];
  const z = zip(files, new Date(2026, 10, 18, 12, 30, 10));
  const v = new DataView(z.buffer);
  const end = z.length - 22;
  assert.equal(v.getUint32(end, true), 0x06054b50);
  assert.equal(v.getUint16(end + 10, true), files.length);
  let p = v.getUint32(end + 16, true);
  for (const f of files) {
    assert.equal(v.getUint32(p, true), 0x02014b50);
    const n = v.getUint16(p + 28, true), local = v.getUint32(p + 42, true);
    assert.equal(new TextDecoder().decode(z.subarray(p + 46, p + 46 + n)), f.name);
    assert.equal(v.getUint32(p + 16, true), crc32(f.data));
    const ln = v.getUint16(local + 26, true), size = v.getUint32(local + 18, true);
    assert.deepEqual(z.subarray(local + 30 + ln, local + 30 + ln + size), f.data);
    p += 46 + n;
  }
});
