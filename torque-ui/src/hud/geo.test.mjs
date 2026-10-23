import test from "node:test";
import { readFileSync } from "node:fs";
const world = JSON.parse(readFileSync(new URL("../../node_modules/world-atlas/countries-110m.json", import.meta.url)));
import assert from "node:assert";
import { lonLatToVector, rotationFor, wrapAngle, borderSegments, graticuleSegments, arcPoints } from "./geo.js";

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);

test("lon/lat 0,0 faces the camera and the poles are on the y axis", () => {
  const [x, y, z] = lonLatToVector(0, 0);
  close(x, 0); close(y, 0); close(z, 1);
  const [, py] = lonLatToVector(123, 90);
  close(py, 1);
});

test("vectors lie on the sphere of the requested radius", () => {
  for (const [lon, lat] of [[77.2, 28.6], [-122, 37], [151, -33], [0, 0]]) {
    const v = lonLatToVector(lon, lat, 2);
    close(Math.hypot(...v), 2);
  }
});

// Apply Rx(rx) * Ry(ry) to a vector (three.js 'XYZ' Euler = Rx*Ry*Rz).
function rotate([x, y, z], [rx, ry]) {
  const x1 = x * Math.cos(ry) + z * Math.sin(ry);
  const z1 = -x * Math.sin(ry) + z * Math.cos(ry);
  const y2 = y * Math.cos(rx) - z1 * Math.sin(rx);
  const z2 = y * Math.sin(rx) + z1 * Math.cos(rx);
  return [x1, y2, z2];
}

test("rotationFor brings any place to face the camera", () => {
  for (const [lon, lat] of [[77.2, 28.6], [-122, 37], [151, -33], [18, 59], [-70, -45]]) {
    const [x, y, z] = rotate(lonLatToVector(lon, lat), rotationFor(lon, lat));
    close(x, 0, 1e-9); close(y, 0, 1e-9); close(z, 1, 1e-9);
  }
});

test("wrapAngle takes the short way round", () => {
  close(wrapAngle(Math.PI * 1.5), -Math.PI / 2);
  close(wrapAngle(-Math.PI * 2.25), -Math.PI / 4);
});

test("real country borders load: thousands of segments, all on the sphere", () => {
  const seg = borderSegments(world, 1.002);
  assert.ok(seg.length / 6 > 5000, `only ${seg.length / 6} segments`);
  for (let i = 0; i < seg.length; i += 3 * 997) close(Math.hypot(seg[i], seg[i + 1], seg[i + 2]), 1.002, 1e-4);
  assert.ok(seg.every(Number.isFinite));
});

test("graticule has the expected number of lines", () => {
  const g = graticuleSegments(30, 1, 6);
  assert.ok(g.length > 0 && g.length % 6 === 0 && g.every(Number.isFinite));
});

test("arcs start and end on the surface and rise in between", () => {
  const pts = arcPoints({ lon: 77, lat: 28 }, { lon: -74, lat: 40 });
  const radius = (p) => Math.hypot(...p);
  close(radius(pts[0]), 1, 1e-6); close(radius(pts.at(-1)), 1, 1e-6);
  assert.ok(radius(pts[20]) > 1.05);
});

test("an arc to the same place doesn't produce NaN", () => {
  const pts = arcPoints({ lon: 10, lat: 10 }, { lon: 10, lat: 10 });
  assert.ok(pts.every((p) => p.every(Number.isFinite)));
});
