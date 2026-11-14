import { raDecToEcliptic, toScene, type Vec3 } from "@/lib/astro";
import type { SkyPath } from "@/types/specula";

export const STAR_SPHERE_RADIUS = 800;
const LINEAR_UNITS_PER_AU = 4;
const GALACTIC_NORTH: Vec3 = raDecToEcliptic(192.85948, 27.12825);

export type ScenePoint = [number, number, number];

export function toStarSphere(raDeg: number, decDeg: number): ScenePoint {
  const v = toScene(raDecToEcliptic(raDeg, decDeg), "linear");
  return [
    (v[0] / LINEAR_UNITS_PER_AU) * STAR_SPHERE_RADIUS,
    (v[1] / LINEAR_UNITS_PER_AU) * STAR_SPHERE_RADIUS,
    (v[2] / LINEAR_UNITS_PER_AU) * STAR_SPHERE_RADIUS,
  ];
}

export function skyPathPoints(path: SkyPath, close = true): ScenePoint[] {
  const pts = close && path.length > 0 ? [...path, path[0]] : [...path];
  const out: ScenePoint[] = [];
  for (const point of pts) {
    if (!point) continue;
    const [ra, dec] = point;
    if (!Number.isFinite(ra) || !Number.isFinite(dec)) continue;
    out.push(toStarSphere(ra, dec));
  }
  return out;
}

/** Offset a RA/Dec path toward the galactic pole by `latitudeDeg`. */
export function galacticLatitudePoints(
  path: SkyPath,
  latitudeDeg: number,
  close = true,
): ScenePoint[] {
  const angle = (latitudeDeg * Math.PI) / 180;
  const pts = close && path.length > 0 ? [...path, path[0]] : [...path];
  const out: ScenePoint[] = [];
  for (const point of pts) {
    if (!point) continue;
    const [ra, dec] = point;
    if (!Number.isFinite(ra) || !Number.isFinite(dec)) continue;
    const equator = raDecToEcliptic(ra, dec);
    const offset = rotateToward(equator, GALACTIC_NORTH, angle);
    const v = toScene(offset, "linear");
    out.push([
      (v[0] / LINEAR_UNITS_PER_AU) * STAR_SPHERE_RADIUS,
      (v[1] / LINEAR_UNITS_PER_AU) * STAR_SPHERE_RADIUS,
      (v[2] / LINEAR_UNITS_PER_AU) * STAR_SPHERE_RADIUS,
    ]);
  }
  return out;
}

function rotateToward(from: Vec3, toward: Vec3, angle: number): Vec3 {
  const axis = normalize(cross(from, toward));
  if (Math.hypot(axis[0], axis[1], axis[2]) < 1e-8) return from;
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const term = scale(axis, (1 - c) * dot(axis, from));
  return add(add(scale(from, c), scale(cross(axis, from), s)), term);
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function scale(v: Vec3, k: number): Vec3 {
  return [v[0] * k, v[1] * k, v[2] * k];
}

function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function normalize(v: Vec3): Vec3 {
  const n = Math.hypot(v[0], v[1], v[2]);
  if (n === 0) return [0, 0, 0];
  return [v[0] / n, v[1] / n, v[2] / n];
}
