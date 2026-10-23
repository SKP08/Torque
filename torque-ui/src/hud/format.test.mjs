import test from "node:test";
import assert from "node:assert";
import { formatRate } from "./format.js";

test("formatRate picks sensible units", () => {
  assert.strictEqual(formatRate(0), "0 B/s");
  assert.strictEqual(formatRate(512), "512 B/s");
  assert.strictEqual(formatRate(1536), "1.5 KB/s");
  assert.strictEqual(formatRate(5 * 1024 * 1024), "5.0 MB/s");
  assert.strictEqual(formatRate(undefined), "0 B/s");
  assert.strictEqual(formatRate(-5), "0 B/s");
});
