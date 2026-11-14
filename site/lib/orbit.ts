import type { EllipticOrbit, HyperbolicOrbit, OrbitEntry, Vec3 } from "@/types/specula";

const RAD = Math.PI / 180;
const EPS = 23.4392911 * RAD;
const JD_UNIX_EPOCH = 2440587.5;
const TDB_MINUS_UTC_DAYS = 69.2 / 86400;

function isFiniteVec(v: ArrayLike<number> | null | undefined): boolean {
  if (!v) return false;
  for (let k = 0; k < v.length; k++) if (!Number.isFinite(v[k])) return false;
  return true;
}

/**
 * Position (AU, heliocentric ecliptic J2000) of one orbits.json entry
 * at time jdTdb. Port of specula_orbit.js; matches the pack's two-body
 * answers to ~1e-6 AU.
 */
export function orbitPosition(o: OrbitEntry, jdTdb: number): Vec3 {
  const e = o.e;
  const i = o.i_deg * RAD;
  const node = o.node_deg * RAD;
  const peri = o.peri_deg * RAD;
  const n = o.n_deg_day * RAD;
  let xp: number;
  let yp: number;

  if (o.orbit_type === "elliptic") {
    let M = o.M_deg * RAD + n * (jdTdb - o.epoch_jd_tdb);
    M = ((((M + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) - Math.PI;
    let E = e < 0.8 ? M + e * Math.sin(M) : Math.PI * Math.sign(M || 1);
    for (let k = 0; k < 50; k++) {
      const d = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
      E -= d;
      if (Math.abs(d) < 1e-14) break;
    }
    xp = o.a_au * (Math.cos(E) - e);
    yp = o.a_au * Math.sqrt(1 - e * e) * Math.sin(E);
  } else {
    const a = o.q_au / (1 - e);
    const M = n * (jdTdb - o.tp_jd_tdb);
    let H = Math.asinh(M / e);
    for (let k = 0; k < 100; k++) {
      const d = (e * Math.sinh(H) - H - M) / (e * Math.cosh(H) - 1);
      H -= d;
      if (Math.abs(d) < 1e-14) break;
    }
    xp = a * (Math.cosh(H) - e);
    yp = -a * Math.sqrt(e * e - 1) * Math.sinh(H);
  }

  const cO = Math.cos(node);
  const sO = Math.sin(node);
  const ci = Math.cos(i);
  const si = Math.sin(i);
  const cw = Math.cos(peri);
  const sw = Math.sin(peri);
  return [
    (cO * cw - sO * sw * ci) * xp + (-cO * sw - sO * cw * ci) * yp,
    (sO * cw + cO * sw * ci) * xp + (-sO * sw + cO * cw * ci) * yp,
    sw * si * xp + cw * si * yp,
  ];
}

/** RA/Dec J2000 (deg) -> unit vector in the 3D frame (ecliptic J2000). */
export function radecToEcliptic(raDeg: number, decDeg: number): Vec3 {
  const ra = raDeg * RAD;
  const dec = decDeg * RAD;
  const x = Math.cos(dec) * Math.cos(ra);
  const y = Math.cos(dec) * Math.sin(ra);
  const z = Math.sin(dec);
  return [
    x,
    y * Math.cos(EPS) + z * Math.sin(EPS),
    -y * Math.sin(EPS) + z * Math.cos(EPS),
  ];
}

/** JD TDB from a Date (UTC instant). jdTdb = JD UTC + 69.2 s. */
export function jdTdbFromDate(date: Date): number {
  return date.getTime() / 86400000 + JD_UNIX_EPOCH + TDB_MINUS_UTC_DAYS;
}

export function isValidOrbit(o: OrbitEntry | null | undefined): o is OrbitEntry {
  if (!o) return false;
  if (!Number.isFinite(o.e) || o.e < 0) return false;
  if (
    !Number.isFinite(o.i_deg) ||
    !Number.isFinite(o.node_deg) ||
    !Number.isFinite(o.peri_deg)
  ) {
    return false;
  }
  if (!Number.isFinite(o.n_deg_day) || o.n_deg_day === 0) return false;
  if (o.orbit_type === "elliptic") {
    return (
      o.e < 1 &&
      Number.isFinite(o.a_au) &&
      o.a_au !== 0 &&
      Number.isFinite(o.M_deg) &&
      Number.isFinite(o.epoch_jd_tdb)
    );
  }
  return o.e > 1 && Number.isFinite(o.q_au) && o.q_au > 0 && Number.isFinite(o.tp_jd_tdb);
}

export function hasCompleteElements(o: OrbitEntry): boolean {
  return isValidOrbit(o);
}

export function sampleEllipticOrbit(entry: EllipticOrbit, steps = 180): Vec3[] {
  if (!isValidOrbit(entry)) return [];
  const periodDays = 360 / entry.n_deg_day;
  const points: Vec3[] = [];
  for (let i = 0; i <= steps; i++) {
    points.push(orbitPosition(entry, entry.epoch_jd_tdb + (periodDays * i) / steps));
  }
  return points.filter(isFiniteVec);
}

export function sampleHyperbolicOrbit(
  entry: HyperbolicOrbit,
  jdCenter: number,
  spanDays = 400,
  steps = 180,
): Vec3[] {
  if (!isValidOrbit(entry) || !Number.isFinite(jdCenter) || spanDays <= 0 || steps < 1) {
    return [];
  }
  const points: Vec3[] = [];
  for (let i = 0; i <= steps; i++) {
    const jd = jdCenter - spanDays / 2 + (spanDays * i) / steps;
    points.push(orbitPosition(entry, jd));
  }
  return points.filter(isFiniteVec);
}

export function sampleOrbit(entry: OrbitEntry, jdCenter: number, steps = 180): Vec3[] {
  if (entry.orbit_type === "elliptic") return sampleEllipticOrbit(entry, steps);
  return sampleHyperbolicOrbit(entry, jdCenter, 400, steps);
}

function clipRadius(points: Vec3[], maxRadiusAu: number): Vec3[] {
  if (!Number.isFinite(maxRadiusAu) || maxRadiusAu <= 0) return points;
  return points.filter((p) => Math.hypot(p[0], p[1], p[2]) <= maxRadiusAu);
}

/**
 * Orbit polyline clipped at `maxRadiusAu` for hyperbolic paths.
 * Hyperbolic entries (e > 1), including 3I/ATLAS, are sampled in anomaly
 * from perihelion out to that radius — they are not dropped.
 */
export function orbitPath(o: OrbitEntry, segments = 160, maxRadiusAu = 50): Vec3[] {
  if (!isValidOrbit(o)) return [];
  if (o.orbit_type === "elliptic") {
    return sampleEllipticOrbit(o, segments);
  }
  const a = Math.abs(o.q_au / (1 - o.e));
  const coshMax = (maxRadiusAu / a + 1) / o.e;
  if (coshMax <= 1 || !Number.isFinite(coshMax)) return [];
  const Hmax = Math.acosh(coshMax);
  const n = o.n_deg_day * RAD;
  const points: Vec3[] = [];
  for (let k = 0; k <= segments; k++) {
    const H = -Hmax + (2 * Hmax * k) / segments;
    const M = o.e * Math.sinh(H) - H;
    points.push(orbitPosition(o, o.tp_jd_tdb + M / n));
  }
  return points.filter(isFiniteVec);
}

/**
 * Trajectory segment centred on `jdCenter` (TDB), clipped at `maxRadiusAu`.
 * For elliptic orbits this is the full closed path; for hyperbolic orbits
 * it is the inbound/outbound branch around that date.
 */
export function orbitPathAround(
  o: OrbitEntry,
  jdCenter: number,
  segments = 200,
  maxRadiusAu = 40,
  spanDays = 800,
): Vec3[] {
  if (!isValidOrbit(o)) return [];
  if (o.orbit_type === "elliptic") return sampleEllipticOrbit(o, segments);
  return clipRadius(sampleHyperbolicOrbit(o, jdCenter, spanDays, segments), maxRadiusAu);
}
