import world from "world-atlas/countries-110m.json";
import { borderSegments } from "./geo.js";

let cached = null;

export function worldBorders() {
  if (!cached) cached = borderSegments(world, 1.002);
  return cached;
}
