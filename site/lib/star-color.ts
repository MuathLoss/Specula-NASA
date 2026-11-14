/** Approximate sRGB from Johnson B−V. Null (unknown) is a cool white. */
export function bvToRgb(bv: number | null | undefined): [number, number, number] {
  if (bv === null || bv === undefined || !Number.isFinite(bv)) return [0.92, 0.95, 1];
  const t = Math.min(2, Math.max(-0.4, bv));
  let r: number;
  let g: number;
  let b: number;
  if (t < 0.4) {
    const u = (t + 0.4) / 0.8;
    r = 0.7 + 0.3 * u;
    g = 0.8 + 0.18 * u;
    b = 1;
  } else if (t < 1.3) {
    const u = (t - 0.4) / 0.9;
    r = 1;
    g = 0.98 - 0.25 * u;
    b = 1 - 0.7 * u;
  } else {
    const u = (t - 1.3) / 0.7;
    r = 1;
    g = 0.73 - 0.28 * u;
    b = 0.3 - 0.15 * u;
  }
  return [r, g, b];
}

export function vmagToSize(vmag: number): number {
  const s = 2.2 * Math.pow(10, -0.18 * (vmag + 1.5));
  return Math.min(4.2, Math.max(0.35, s));
}
