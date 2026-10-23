const test = require("node:test");
const assert = require("node:assert");
const { computeBounds, fullBounds, MARGIN } = require("./position.cjs");

const size = { width: 620, height: 260 };

test("bottom centre of a plain work area", () => {
  const b = computeBounds({ x: 0, y: 0, width: 1920, height: 1040 }, size, "bottom");
  assert.deepStrictEqual(b, { x: 650, y: 1040 - 260 - MARGIN, width: 620, height: 260 });
});

test("respects a second monitor's offset and taskbar", () => {
  const b = computeBounds({ x: 1920, y: 0, width: 1920, height: 1000 }, size, "bottom");
  assert.strictEqual(b.x, 1920 + 650);
  assert.strictEqual(b.y, 1000 - 260 - MARGIN);
});

test("negative origin (monitor left of primary)", () => {
  const b = computeBounds({ x: -1280, y: 0, width: 1280, height: 720 }, size, "top");
  assert.strictEqual(b.x, -1280 + 330);
  assert.strictEqual(b.y, MARGIN);
});

test("never larger than the screen", () => {
  const b = computeBounds({ x: 0, y: 0, width: 400, height: 200 }, size, "center");
  assert.deepStrictEqual([b.width, b.height, b.x, b.y], [400, 200, 0, 0]);
});

test("full mode covers the whole display, offsets included", () => {
  assert.deepStrictEqual(fullBounds({ x: -1280, y: 0, width: 1280, height: 720, extra: 1 }),
    { x: -1280, y: 0, width: 1280, height: 720 });
});
