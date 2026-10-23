import { mesh } from "topojson-client";

const DEG = Math.PI / 180;

// lon 0 / lat 0 faces the camera (+z); north is +y.
export function lonLatToVector(lon, lat, radius = 1) {
  const phi = lat * DEG;
  const lambda = lon * DEG;

  return [
    radius * Math.cos(phi) * Math.sin(lambda),
    radius * Math.sin(phi),
    radius * Math.cos(phi) * Math.cos(lambda),
  ];
}

// Euler angles (order XYZ) that turn the globe so lon/lat faces the camera.
export function rotationFor(lon, lat) {
  return [lat * DEG, -lon * DEG, 0];
}

// Shortest way round for an angle difference.
export function wrapAngle(angle) {
  return Math.atan2(Math.sin(angle), Math.cos(angle));
}

// Country borders and coastlines as one flat list of line segments
// (x1,y1,z1,x2,y2,z2,...), ready for a LineSegments buffer.
export function borderSegments(topology, radius = 1.002) {
  const lines = mesh(topology, topology.objects.countries).coordinates;
  const out = [];

  for (const line of lines) {
    for (let i = 1; i < line.length; i += 1) {
      out.push(
        ...lonLatToVector(line[i - 1][0], line[i - 1][1], radius),
        ...lonLatToVector(line[i][0], line[i][1], radius),
      );
    }
  }

  return new Float32Array(out);
}

// Latitude / longitude grid lines every `step` degrees.
export function graticuleSegments(step = 20, radius = 1.0, resolution = 4) {
  const out = [];

  for (let lon = -180; lon < 180; lon += step) {
    for (let lat = -90; lat < 90; lat += resolution) {
      out.push(...lonLatToVector(lon, lat, radius), ...lonLatToVector(lon, lat + resolution, radius));
    }
  }

  for (let lat = -80; lat <= 80; lat += step) {
    for (let lon = -180; lon < 180; lon += resolution) {
      out.push(...lonLatToVector(lon, lat, radius), ...lonLatToVector(lon + resolution, lat, radius));
    }
  }

  return new Float32Array(out);
}

// A lifted arc between two surface points, as a list of [x,y,z].
export function arcPoints(from, to, steps = 40, lift = 0.35) {
  const a = lonLatToVector(from.lon, from.lat);
  const b = lonLatToVector(to.lon, to.lat);

  const dot = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const angle = Math.acos(dot);
  const sin = Math.sin(angle) || 1;
  const height = 1 + lift * (angle / Math.PI);

  const points = [];

  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const wa = Math.sin((1 - t) * angle) / sin;
    const wb = Math.sin(t * angle) / sin;
    const bulge = 1 + (height - 1) * Math.sin(Math.PI * t);

    points.push([
      (a[0] * wa + b[0] * wb) * bulge,
      (a[1] * wa + b[1] * wb) * bulge,
      (a[2] * wa + b[2] * wb) * bulge,
    ]);
  }

  return points;
}
