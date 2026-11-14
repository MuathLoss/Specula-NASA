// lib/astro.ts
// Heliocentric ecliptic J2000 geometry helpers. All positions are in AU unless
// noted. Ecliptic frame: +x toward the vernal equinox, +z toward the north
// ecliptic pole.

import type { OrbitEntry } from "@/types/specula";
import {
  hasCompleteElements,
  isValidOrbit,
  orbitPath as catalogOrbitPath,
  orbitPosition as catalogOrbitPosition,
  radecToEcliptic,
} from "@/lib/orbit";

export type Vec3 = [number, number, number];

export const DEG = Math.PI / 180;
export const J2000_JD = 2451545.0;
/** cosmos.json obliquity_deg */
export const OBLIQUITY_J2000 = 23.4392911 * DEG;

export { hasCompleteElements, isValidOrbit as hasValidShape, radecToEcliptic };

/** True when every component is a finite number. */
export function isFiniteVec(v: ArrayLike<number> | null | undefined): boolean {
  if (!v) return false;
  for (let k = 0; k < v.length; k++) if (!Number.isFinite(v[k])) return false;
  return true;
}

/** Drop points with NaN/±Infinity/undefined components (e.g. before BufferGeometry). */
export function finitePoints<T extends ArrayLike<number>>(points: T[]): T[] {
  return points.filter(isFiniteVec);
}

/** Julian Date (UTC). */
export function julianDate(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5;
}

/** TDB − UTC used by the data pipeline (orbits.json how_to: "UTC + 69.2 s"). */
export const TDB_MINUS_UTC_S = 69.2;

/** Julian Date on the TDB scale, as orbits.json elements expect. */
export function julianDateTdb(date: Date): number {
  return julianDate(date) + TDB_MINUS_UTC_S / 86400;
}

/** Internal elements, angles in radians. Used by the JPL planet fallback only. */
interface Elements {
  a: number;
  e: number;
  i: number;
  node: number;
  peri: number;
}

function wrapPi(x: number): number {
  const t = (x + Math.PI) % (2 * Math.PI);
  return (t < 0 ? t + 2 * Math.PI : t) - Math.PI;
}

/** Solve Kepler's equation for elliptic (e<1) or hyperbolic (e>1) orbits. */
function solveAnomaly(M: number, e: number): number {
  if (e < 1) {
    let E = e < 0.8 ? M : Math.PI;
    for (let k = 0; k < 50; k++) {
      const d = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
      E -= d;
      if (Math.abs(d) < 1e-12) break;
    }
    return E;
  }
  let H = Math.asinh(M / e);
  for (let k = 0; k < 50; k++) {
    const d = (e * Math.sinh(H) - H - M) / (e * Math.cosh(H) - 1);
    H -= d;
    if (Math.abs(d) < 1e-12) break;
  }
  return H;
}

/** Position in the orbital plane for eccentric (E) or hyperbolic (H) anomaly. */
function planePosition(el: Elements, anomaly: number): [number, number] {
  const a = Math.abs(el.a);
  if (el.e < 1) {
    return [
      a * (Math.cos(anomaly) - el.e),
      a * Math.sqrt(1 - el.e * el.e) * Math.sin(anomaly),
    ];
  }
  return [
    a * (el.e - Math.cosh(anomaly)),
    a * Math.sqrt(el.e * el.e - 1) * Math.sinh(anomaly),
  ];
}

function planeToEcliptic(el: Elements, xp: number, yp: number): Vec3 {
  const cO = Math.cos(el.node),
    sO = Math.sin(el.node);
  const cw = Math.cos(el.peri),
    sw = Math.sin(el.peri);
  const ci = Math.cos(el.i),
    si = Math.sin(el.i);
  return [
    (cw * cO - sw * sO * ci) * xp + (-sw * cO - cw * sO * ci) * yp,
    (cw * sO + sw * cO * ci) * xp + (-sw * sO + cw * cO * ci) * yp,
    sw * si * xp + cw * si * yp,
  ];
}

/** Sample the orbit path. Hyperbolic orbits are clipped at maxRadiusAu. */
function samplePath(el: Elements, segments: number, maxRadiusAu: number): Vec3[] {
  const pts: Vec3[] = [];
  if (el.e < 1) {
    for (let k = 0; k <= segments; k++) {
      const [x, y] = planePosition(el, (k / segments) * 2 * Math.PI);
      pts.push(planeToEcliptic(el, x, y));
    }
    return pts;
  }
  const a = Math.abs(el.a);
  const coshMax = (maxRadiusAu / a + 1) / el.e;
  if (coshMax <= 1) return pts;
  const Hmax = Math.acosh(coshMax);
  for (let k = 0; k <= segments; k++) {
    const [x, y] = planePosition(el, -Hmax + (2 * Hmax * k) / segments);
    pts.push(planeToEcliptic(el, x, y));
  }
  return pts;
}

/** Orbit polyline for an orbits.json entry, using the tested two-body solver. */
export function orbitPath(o: OrbitEntry, segments = 160, maxRadiusAu = 50): Vec3[] {
  return finitePoints(catalogOrbitPath(o, segments, maxRadiusAu));
}

/**
 * Body position at `jdTdb` (see julianDateTdb) from an orbits.json entry.
 * Returns null if the elements are unusable or the result is not finite.
 */
export function orbitPosition(o: OrbitEntry, jdTdb: number): Vec3 | null {
  if (!isValidOrbit(o) || !Number.isFinite(jdTdb)) return null;
  const pos = catalogOrbitPosition(o, jdTdb);
  return isFiniteVec(pos) ? pos : null;
}

// ---------------------------------------------------------------------------
// Planets: JPL approximate Keplerian elements (Standish), valid 1800–2050.
// [a, e, I, L, long.peri, long.node] and their rates per Julian century.
// ---------------------------------------------------------------------------

export interface PlanetDef {
  id: string;
  name: string;
  el: [number, number, number, number, number, number];
  rate: [number, number, number, number, number, number];
}

export const PLANETS: PlanetDef[] = [
  {
    id: "mercury",
    name: "Mercury",
    el: [0.38709927, 0.20563593, 7.00497902, 252.2503235, 77.45779628, 48.33076593],
    rate: [0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081],
  },
  {
    id: "venus",
    name: "Venus",
    el: [0.72333566, 0.00677672, 3.39467605, 181.9790995, 131.60246718, 76.67984255],
    rate: [0.0000039, -0.00004107, -0.0007889, 58517.81538729, 0.00268329, -0.27769418],
  },
  {
    id: "earth",
    name: "Earth",
    el: [1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0],
    rate: [0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0],
  },
  {
    id: "mars",
    name: "Mars",
    el: [1.52371034, 0.0933941, 1.84969142, -4.55343205, -23.94362959, 49.55953891],
    rate: [0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343],
  },
  {
    id: "jupiter",
    name: "Jupiter",
    el: [5.202887, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909],
    rate: [-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106],
  },
  {
    id: "saturn",
    name: "Saturn",
    el: [9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448],
    rate: [-0.0012506, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794],
  },
  {
    id: "uranus",
    name: "Uranus",
    el: [19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.9542763, 74.01692503],
    rate: [-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589],
  },
  {
    id: "neptune",
    name: "Neptune",
    el: [30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574],
    rate: [0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.01262724],
  },
];

function planetElements(p: PlanetDef, jd: number): { el: Elements; M: number } {
  const T = (jd - J2000_JD) / 36525;
  const [a, e, I, L, varpi, node] = p.el.map((v, k) => v + p.rate[k] * T);
  return {
    el: { a, e, i: I * DEG, node: node * DEG, peri: (varpi - node) * DEG },
    M: wrapPi((L - varpi) * DEG),
  };
}

export function planetPosition(p: PlanetDef, jd: number): Vec3 {
  const { el, M } = planetElements(p, jd);
  const [x, y] = planePosition(el, solveAnomaly(M, el.e));
  return planeToEcliptic(el, x, y);
}

export function planetOrbit(p: PlanetDef, jd: number, segments = 180): Vec3[] {
  return samplePath(planetElements(p, jd).el, segments, Infinity);
}

// ---------------------------------------------------------------------------
// Directions & rays
// ---------------------------------------------------------------------------

/** Unit vector in the ecliptic frame for an equatorial (J2000) RA/Dec. */
export function raDecToEcliptic(raDeg: number, decDeg: number): Vec3 {
  const ra = raDeg * DEG,
    dec = decDeg * DEG;
  const xq = Math.cos(dec) * Math.cos(ra);
  const yq = Math.cos(dec) * Math.sin(ra);
  const zq = Math.sin(dec);
  const c = Math.cos(OBLIQUITY_J2000),
    s = Math.sin(OBLIQUITY_J2000);
  return [xq, c * yq + s * zq, -s * yq + c * zq];
}

export function add(a: Vec3, b: Vec3, k = 1): Vec3 {
  return [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
}

/** Points along origin + dir * d for d in [d0, d1]. */
export function rayPoints(
  origin: Vec3,
  dir: Vec3,
  d0: number,
  d1: number,
  n = 48,
): Vec3[] {
  const pts: Vec3[] = [];
  for (let k = 0; k <= n; k++) pts.push(add(origin, dir, d0 + ((d1 - d0) * k) / n));
  return pts;
}

/**
 * Segment from an observer at distances [dMin, dMax] AU along a line of sight.
 * `direction` is normalized. Distances are measured from the observer, not the Sun.
 */
export function lineOfSightSegment(
  origin: Vec3,
  direction: Vec3,
  dMin: number,
  dMax: number,
  samples = 24,
): Vec3[] | null {
  if (!isFiniteVec(origin) || !isFiniteVec(direction)) return null;
  if (!Number.isFinite(dMin) || !Number.isFinite(dMax)) return null;
  const norm = Math.hypot(direction[0], direction[1], direction[2]);
  if (!(norm > 0) || !Number.isFinite(norm)) return null;
  const u: Vec3 = [direction[0] / norm, direction[1] / norm, direction[2] / norm];
  const lo = Math.min(dMin, dMax);
  const hi = Math.max(dMin, dMax);
  if (!(hi > lo) || hi < 0) return null;
  const start = Math.max(lo, 0);
  if (!(hi > start)) return null;
  return rayPoints(origin, u, start, hi, samples);
}

/**
 * Parts of the line of sight origin + dir*d (d >= 0) whose heliocentric
 * distance lies in [rMin, rMax] AU. A sight line from Earth can cross a
 * heliocentric shell twice (near and far side), so this may return two runs.
 */
export function heliocentricRangeOnRay(
  origin: Vec3,
  dir: Vec3,
  rMin: number,
  rMax: number,
  samples = 400,
): Vec3[][] {
  const r0 = Math.hypot(origin[0], origin[1], origin[2]);
  const dMax = rMax + r0; // beyond this, |origin + dir*d| > rMax
  const runs: Vec3[][] = [];
  let current: Vec3[] | null = null;
  for (let k = 0; k <= samples; k++) {
    const p = add(origin, dir, (dMax * k) / samples);
    const r = Math.hypot(p[0], p[1], p[2]);
    if (r >= rMin && r <= rMax) {
      if (!current) runs.push((current = []));
      current.push(p);
    } else {
      current = null;
    }
  }
  return runs.filter((run) => run.length > 1);
}

/** Unit vector tilted `angle` rad away from `u`, rotated `phi` around it. */
export function tiltedDirection(u: Vec3, angle: number, phi: number): Vec3 {
  const ref: Vec3 = Math.abs(u[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  const p = normalize(cross(u, ref));
  const q = cross(u, p);
  const ca = Math.cos(angle),
    sa = Math.sin(angle);
  return normalize([
    u[0] * ca + (p[0] * Math.cos(phi) + q[0] * Math.sin(phi)) * sa,
    u[1] * ca + (p[1] * Math.cos(phi) + q[1] * Math.sin(phi)) * sa,
    u[2] * ca + (p[2] * Math.cos(phi) + q[2] * Math.sin(phi)) * sa,
  ]);
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(v: Vec3): Vec3 {
  const r = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / r, v[1] / r, v[2] / r];
}

// ---------------------------------------------------------------------------
// Scene mapping
// ---------------------------------------------------------------------------

export type ScaleMode = "compressed" | "linear";

const LINEAR_UNITS_PER_AU = 4;

/**
 * Map an ecliptic AU vector into Three.js scene units (Y-up).
 * scene.x = ecl.x, scene.y = ecl.z (north pole up), scene.z = -ecl.y.
 * "compressed" applies a log radial scale around the Sun so the inner
 * planets and Neptune fit in one view; directions from the Sun are preserved.
 * Lines that don't pass through the Sun curve slightly, so always sample
 * them with rayPoints() before mapping.
 */
export function toScene(v: Vec3, mode: ScaleMode): [number, number, number] {
  if (!isFiniteVec(v)) return [NaN, NaN, NaN]; // callers filter with isFiniteVec/finitePoints
  const r = Math.hypot(v[0], v[1], v[2]);
  const s =
    mode === "linear" ? LINEAR_UNITS_PER_AU : r === 0 ? 0 : (8 * Math.log2(1 + r)) / r;
  return [v[0] * s, v[2] * s, -v[1] * s];
}
