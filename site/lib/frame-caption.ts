import type {
  PatchHeader,
  Pointing,
  TimelineBurst,
  TimelineFrame,
} from "@/types/specula";

/** Every delivered frame is a SPHEREx exposure (contract §1, §3, §4). */
export const SPHEREX_INSTRUMENT = "SPHEREx";

export type CaptionLine = {
  key: string;
  label: string;
  value: string;
};

export type FrameCaptionInput = {
  mode: "composite" | "full";
  patch?: PatchHeader | null;
  frame?: TimelineFrame | null;
  burst?: TimelineBurst | null;
  framesInBurst?: TimelineFrame[];
  pointing?: Pointing | null;
  /** Undefined keeps the composite image line. Null omits it. */
  imageLine?: string | null;
  /** Frames used for the wavelength line. Defaults to framesInBurst. */
  wavelengthFrames?: TimelineFrame[];
};

function finite(n: number | null | undefined): n is number {
  return typeof n === "number" && Number.isFinite(n);
}

function nonempty(s: string | null | undefined): s is string {
  return typeof s === "string" && s.trim() !== "";
}

export function formatWavelengthUm(um: number): string {
  const rounded = um
    .toFixed(4)
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(/\.$/, "");
  return `${rounded} µm`;
}

export function formatUtc(iso: string): string | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return `${new Date(t).toISOString().replace(".000Z", "Z").replace("T", " ").replace("Z", "")} UTC`;
}

function formatRaDec(ra: number, dec: number): string {
  const decSign = dec < 0 ? "−" : dec > 0 ? "+" : "";
  return `RA ${ra.toFixed(6)}°, Dec ${decSign}${Math.abs(dec).toFixed(6)}° (J2000)`;
}

function uniqueSorted(values: number[]): number[] {
  return [...new Set(values.map((v) => v))].sort((a, b) => a - b);
}

function wavelengthRange(values: number[]): string | null {
  const nums = uniqueSorted(values.filter((v) => finite(v) && v > 0));
  if (nums.length === 0) return null;
  if (nums.length === 1) return formatWavelengthUm(nums[0]);
  return `${formatWavelengthUm(nums[0])}–${formatWavelengthUm(nums[nums.length - 1])}`;
}

function detectorWavelengths(frames: TimelineFrame[]): string | null {
  const byDet = new Map<string, number[]>();
  for (const frame of frames) {
    if (
      !nonempty(frame.detector) ||
      !finite(frame.wavelength_um) ||
      frame.wavelength_um <= 0
    ) {
      continue;
    }
    const list = byDet.get(frame.detector) ?? [];
    list.push(frame.wavelength_um);
    byDet.set(frame.detector, list);
  }
  if (byDet.size === 0) return null;
  const parts = [...byDet.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([det, ums]) => {
      const range = wavelengthRange(ums);
      return range ? [`${det} ${range}`] : [];
    });
  return parts.length ? parts.join(" · ") : null;
}

function timeRange(frames: TimelineFrame[], fallback?: string | null): string | null {
  const times = frames
    .map((f) => f.time_utc)
    .filter(nonempty)
    .map((iso) => ({ iso, t: Date.parse(iso) }))
    .filter((x) => !Number.isNaN(x.t))
    .sort((a, b) => a.t - b.t);
  if (times.length === 0) return fallback ? formatUtc(fallback) : null;
  const start = formatUtc(times[0].iso);
  const end = formatUtc(times[times.length - 1].iso);
  if (!start) return end;
  if (!end || start === end) return start;
  const startDay = times[0].iso.slice(0, 10);
  const endDay = times[times.length - 1].iso.slice(0, 10);
  if (startDay === endDay && end.startsWith(startDay)) {
    return `${start.replace(" UTC", "")}–${end.slice(startDay.length + 1)}`;
  }
  return `${start} – ${end}`;
}

function pointingCenter(
  mode: "composite" | "full",
  frame?: TimelineFrame | null,
  burst?: TimelineBurst | null,
  pointing?: Pointing | null,
): string | null {
  if (mode === "full" && frame && finite(frame.ra_center) && finite(frame.dec_center)) {
    return formatRaDec(frame.ra_center, frame.dec_center);
  }
  if (burst && finite(burst.ra_center) && finite(burst.dec_center)) {
    return formatRaDec(burst.ra_center, burst.dec_center);
  }
  if (frame && finite(frame.ra_center) && finite(frame.dec_center)) {
    return formatRaDec(frame.ra_center, frame.dec_center);
  }
  if (pointing && finite(pointing.ra_deg) && finite(pointing.dec_deg)) {
    return formatRaDec(pointing.ra_deg, pointing.dec_deg);
  }
  return null;
}

function fieldOfView(
  patch?: PatchHeader | null,
  pointing?: Pointing | null,
): string | null {
  const parts: string[] = [];
  if (pointing && finite(pointing.fov_deg) && pointing.fov_deg > 0) {
    const fov = pointing.fov_deg.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
    parts.push(`${fov}° field of view`);
  }
  if (patch && finite(patch.pixel_scale_arcsec) && patch.pixel_scale_arcsec > 0) {
    parts.push(`${patch.pixel_scale_arcsec}″/px`);
  }
  if (patch && finite(patch.size_px) && patch.size_px > 0) {
    parts.push(`${patch.size_px} px`);
  }
  if (patch && nonempty(patch.projection)) {
    const north = patch.north_up ? ", north up" : "";
    parts.push(`${patch.projection}${north}`);
  }
  return parts.length ? parts.join(" · ") : null;
}

function detectorsOf(
  burst?: TimelineBurst | null,
  frames: TimelineFrame[] = [],
): string[] {
  const fromBurst = (burst?.detectors ?? []).filter(nonempty);
  if (fromBurst.length) return [...new Set(fromBurst)];
  return [...new Set(frames.map((f) => f.detector).filter(nonempty))];
}

/** Compact label for a composite, e.g. "D1 + D4 · false colour (infrared)". */
export function compositeImageLabel(detectors: string[]): string | null {
  const dets = [...new Set(detectors.filter(nonempty))];
  if (dets.length === 0) return "false colour (infrared)";
  if (dets.length === 1) return `${dets[0]} · greyscale (single detector)`;
  return `${dets.join(" + ")} · false colour (infrared)`;
}

/** Label when a composite request is showing one detector frame. */
export function singlePhotoImageLabel(detector?: string | null): string {
  return nonempty(detector) ? `${detector} · single photo` : "single photo";
}

export function fullFrameImageLabel(
  detector?: string | null,
  wavelengthUm?: number | null,
): string | null {
  const det = nonempty(detector) ? detector : null;
  const um =
    typeof wavelengthUm === "number" && Number.isFinite(wavelengthUm) && wavelengthUm > 0
      ? formatWavelengthUm(wavelengthUm)
      : null;
  if (det && um) return `${det} · ${um}`;
  if (det) return det;
  return um;
}

/**
 * Build caption lines from delivered timeline / pointing / patch fields only.
 * Missing values are omitted; nothing is invented.
 */
export function buildFrameCaption(input: FrameCaptionInput): CaptionLine[] {
  const { mode, patch, frame, burst, pointing } = input;
  const framesInBurst = input.framesInBurst ?? [];
  const lines: CaptionLine[] = [];
  const add = (key: string, label: string, value: string | null | undefined) => {
    if (nonempty(value)) lines.push({ key, label, value });
  };

  const detectors = detectorsOf(burst, framesInBurst);
  if (mode === "full") {
    const det = nonempty(frame?.detector) ? frame.detector : detectors[0];
    const um =
      frame && finite(frame.wavelength_um) && frame.wavelength_um > 0
        ? formatWavelengthUm(frame.wavelength_um)
        : null;
    const instrument = det
      ? um
        ? `${SPHEREX_INSTRUMENT} · detector ${det} · ${um}`
        : `${SPHEREX_INSTRUMENT} · detector ${det}`
      : SPHEREX_INSTRUMENT;
    add("instrument", "Telescope", instrument);
  } else {
    add("instrument", "Telescope", SPHEREX_INSTRUMENT);
    if (input.imageLine === undefined) {
      add("bands", "Image", compositeImageLabel(detectors) ?? "composite");
    } else if (nonempty(input.imageLine)) {
      add("bands", "Image", input.imageLine);
    }
    add(
      "wavelength",
      "Wavelength",
      detectorWavelengths(input.wavelengthFrames ?? framesInBurst),
    );
  }

  if (patch && nonempty(patch.name)) add("patch", "Patch", patch.name);

  if (mode === "composite") {
    add(
      "time",
      "Observation",
      timeRange(framesInBurst, burst?.time_utc ?? frame?.time_utc),
    );
  } else {
    add(
      "time",
      "Observation",
      frame?.time_utc
        ? formatUtc(frame.time_utc)
        : timeRange(framesInBurst, burst?.time_utc),
    );
  }

  if (mode === "full" && frame && finite(frame.mjd) && frame.mjd > 0) {
    add("mjd", "MJD", frame.mjd.toFixed(6).replace(/0+$/, "").replace(/\.$/, ""));
  }

  add("pointing", "Pointing", pointingCenter(mode, frame, burst, pointing));
  add("scale", "Scale", fieldOfView(patch, pointing));

  if (mode === "full" && frame && nonempty(frame.frame_id)) {
    const burstId = nonempty(frame.burst_id)
      ? frame.burst_id
      : nonempty(burst?.burst_id)
        ? burst.burst_id
        : null;
    add(
      "ids",
      "Frame",
      burstId ? `${frame.frame_id} · burst ${burstId}` : frame.frame_id,
    );
  } else if (burst && nonempty(burst.burst_id)) {
    const n = burst.frame_ids.length || framesInBurst.length;
    add("ids", "Burst", n > 0 ? `${burst.burst_id} · ${n} frames` : burst.burst_id);
  }

  if (mode === "full" && frame && finite(frame.coverage)) {
    add(
      "coverage",
      "Coverage",
      `${(frame.coverage * 100).toFixed(1).replace(/\.0$/, "")}%`,
    );
  }
  if (mode === "full" && frame && nonempty(frame.quality) && frame.quality !== "ok") {
    add(
      "quality",
      "Quality",
      frame.quality === "warn_transients" ? "transients warning" : frame.quality,
    );
  }

  return lines;
}
