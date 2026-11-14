// specula_orbit.js - Specula frontend helper (tested: matches our Python solver to 1e-9 AU and puts Ceres
// inside every SPHEREx ceres pointing within 0.008 deg). ES module for React + Vite.
// 3D frame = heliocentric ecliptic J2000, AU (z = ecliptic north). Three.js is y-up: use (x, z, -y) if you want
// the ecliptic as the floor.
const RAD = Math.PI / 180;
// Position (AU, heliocentric ecliptic J2000) of one orbits.json entry ("objects" or "planets") at time jdTdb.
function orbitPosition(o, jdTdb) {
  const e = o.e, i = o.i_deg * RAD, node = o.node_deg * RAD, peri = o.peri_deg * RAD, n = o.n_deg_day * RAD;
  let xp, yp;
  if (o.orbit_type === "elliptic") {
    let M = o.M_deg * RAD + n * (jdTdb - o.epoch_jd_tdb);
    M = (((M + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;   // wrap to -pi..pi
    let E = e < 0.8 ? M + e * Math.sin(M) : Math.PI * Math.sign(M || 1);
    for (let k = 0; k < 50; k++) {                       // Newton: solve E - e sin E = M
      const d = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
      E -= d;
      if (Math.abs(d) < 1e-14) break;
    }
    xp = o.a_au * (Math.cos(E) - e);
    yp = o.a_au * Math.sqrt(1 - e * e) * Math.sin(E);
  } else {                                               // hyperbolic (3I/ATLAS)
    const a = o.q_au / (1 - e);                          // negative
    const M = n * (jdTdb - o.tp_jd_tdb);
    let H = Math.asinh(M / e);
    for (let k = 0; k < 100; k++) {                      // Newton: solve e sinh H - H = M
      const d = (e * Math.sinh(H) - H - M) / (e * Math.cosh(H) - 1);
      H -= d;
      if (Math.abs(d) < 1e-14) break;
    }
    xp = a * (Math.cosh(H) - e);
    yp = -a * Math.sqrt(e * e - 1) * Math.sinh(H);
  }
  const cO = Math.cos(node), sO = Math.sin(node), ci = Math.cos(i), si = Math.sin(i);
  const cw = Math.cos(peri), sw = Math.sin(peri);
  return [
    (cO * cw - sO * sw * ci) * xp + (-cO * sw - sO * cw * ci) * yp,
    (sO * cw + cO * sw * ci) * xp + (-sO * sw + cO * cw * ci) * yp,
    sw * si * xp + cw * si * yp,
  ];
}
// RA/Dec J2000 (deg) -> unit vector in the 3D frame (ecliptic J2000): for cosmos.json stars, lines, labels.
const EPS = 23.4392911 * RAD;
function radecToEcliptic(raDeg, decDeg) {
  const ra = raDeg * RAD, dec = decDeg * RAD;
  const x = Math.cos(dec) * Math.cos(ra), y = Math.cos(dec) * Math.sin(ra), z = Math.sin(dec);
  return [x, y * Math.cos(EPS) + z * Math.sin(EPS), -y * Math.sin(EPS) + z * Math.cos(EPS)];
}
// Time: jdUtc = date.getTime() / 86400000 + 2440587.5 ; jdTdb = jdUtc + 69.2 / 86400
const jdTdbFromDate = (date) => date.getTime() / 86400000 + 2440587.5 + 69.2 / 86400;
export { orbitPosition, radecToEcliptic, jdTdbFromDate };
