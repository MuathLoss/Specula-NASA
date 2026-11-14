// lib/timeline.ts
// Bursts for the scrubber, the NEW rule, and image URLs.

import type {
  Burst,
  DataUpdate,
  Frame,
  AppManifest,
  Patch,
  PatchTimeline,
  Pointing,
} from "@/types/specula";

export const DEFAULT_NEW_BADGE_DAYS = 7;
const DAY_MS = 86_400_000;

function time(ts: string | undefined | null): number | null {
  if (!ts) return null;
  const t = Date.parse(ts);
  return Number.isNaN(t) ? null : t;
}

/** "0001_2026W27_1A_0405_1_D2" -> "2026W27_1A_0405" (frame ids embed their burst id). */
export function burstIdFromFrameId(frameId: string): string | null {
  const m = /^\d+_(\d{4}W\d{2}_[0-9A-Z]{2}_\d{4})_/.exec(frameId);
  return m ? m[1] : null;
}

/**
 * Scrubber steps for a patch, in time order. timeline.json (when loaded) gives
 * frame ids and composites; pointings.json covers every patch and supplies the
 * pointing geometry.
 */
export function buildBursts(
  patchId: string,
  pointings: Pointing[],
  timeline: PatchTimeline | null,
): Burst[] {
  const patchPointings = pointings.filter((p) => p.patch_id === patchId);
  const byBurst = new Map(patchPointings.map((p) => [p.burst_id, p]));

  const raw: Omit<Burst, "index">[] = timeline
    ? timeline.bursts.map((b) => ({
        burst_id: b.burst_id,
        patch_id: patchId,
        time_utc: b.time_utc,
        frame_ids: b.frame_ids ?? [],
        composite: b.composite ?? b.representative,
        pointing: byBurst.get(b.burst_id),
      }))
    : patchPointings.map((p) => ({
        burst_id: p.burst_id,
        patch_id: patchId,
        time_utc: p.time_utc,
        frame_ids: [],
        pointing: p,
      }));

  return raw
    .sort((a, b) => (time(a.time_utc) ?? 0) - (time(b.time_utc) ?? 0))
    .map((b, index) => ({ ...b, index }));
}

/**
 * Index of a burst in the same time order `buildBursts` uses.
 * -1 when that burst is not in the patch's pointings.
 */
export function burstIndexForPatch(
  patchId: string,
  burstId: string,
  pointings: readonly { patch_id: string; burst_id: string; time_utc: string }[],
): number {
  const rows = pointings
    .filter((p) => p.patch_id === patchId)
    .sort((a, b) => (time(a.time_utc) ?? 0) - (time(b.time_utc) ?? 0));
  return rows.findIndex((p) => p.burst_id === burstId);
}

/**
 * Manifest NEW rule: a frame is NEW if its update_id is not a baseline update
 * and that update's ingested_utc >= latest_ingest_utc − new_badge_days
 * (dataset clock, not the visitor's clock).
 */
export function newFrameIds(
  frames: Frame[] | undefined,
  updates: DataUpdate[],
  manifest: AppManifest | undefined,
): Set<string> {
  const out = new Set<string>();
  if (!frames?.length) return out;
  const days = manifest?.new_badge_days ?? DEFAULT_NEW_BADGE_DAYS;
  const latest =
    time(manifest?.latest_ingest_utc) ??
    updates.reduce<number | null>((max, u) => {
      const t = time(u.ingested_utc);
      return t !== null && (max === null || t > max) ? t : max;
    }, null);
  if (latest === null) return out;

  const cutoff = latest - days * DAY_MS;
  const fresh = new Set(
    updates
      .filter((u) => !u.baseline && (time(u.ingested_utc) ?? -Infinity) >= cutoff)
      .map((u) => u.update_id),
  );
  for (const f of frames) if (f.update_id && fresh.has(f.update_id)) out.add(f.frame_id);
  return out;
}

/** A burst is NEW when any of its frames is NEW. */
export function newBurstIds(bursts: Burst[], newFrames: Set<string>): Set<string> {
  return new Set(
    bursts
      .filter((b) => b.frame_ids.some((id) => newFrames.has(id)))
      .map((b) => b.burst_id),
  );
}

export type ImageMode = "composite" | "full";

function patchFolder(patch: Patch): string {
  const f = patch.folder ?? `${patch.id}/`;
  return f.endsWith("/") ? f : `${f}/`;
}

const basename = (p: string) => p.slice(p.lastIndexOf("/") + 1);

export type BurstImageKind = "composite" | "full";

export type BurstImage = {
  url: string;
  kind: BurstImageKind;
};

/**
 * Candidate images for a burst, tried in order by Viewport2D:
 *   composite: /data/<folder>/composite/<burst_id>.webp
 *   full:      /data/<folder>/full/<frame_id>.webp, then /data/<frame_id>.webp
 * (the last form covers data copied into /data without its patch folders).
 */
export function burstImages(
  base: string,
  patch: Patch,
  burst: Burst | undefined,
  frame: Frame | undefined,
  mode: ImageMode,
): BurstImage[] {
  if (!burst) return [];
  const folder = patchFolder(patch);
  const composite: BurstImage[] = [
    {
      url: `${base}/${folder}${burst.composite ?? `composite/${burst.burst_id}.webp`}`,
      kind: "composite",
    },
  ];
  const full: BurstImage[] = frame?.image
    ? [
        { url: `${base}/${folder}${frame.image}`, kind: "full" },
        { url: `${base}/${basename(frame.image)}`, kind: "full" },
      ]
    : [];
  return mode === "composite" ? [...composite, ...full] : [...full, ...composite];
}

export function burstImageUrls(
  base: string,
  patch: Patch,
  burst: Burst | undefined,
  frame: Frame | undefined,
  mode: ImageMode,
): string[] {
  return burstImages(base, patch, burst, frame, mode).map((image) => image.url);
}

/** Pointing closest in time to `jd` (used for patches other than the active one). */
export function nearestPointing(
  pointings: Pointing[],
  patchId: string,
  jd: number,
): Pointing | undefined {
  let best: Pointing | undefined;
  for (const p of pointings) {
    if (p.patch_id !== patchId) continue;
    if (!best || Math.abs(p.jd - jd) < Math.abs(best.jd - jd)) best = p;
  }
  return best;
}
