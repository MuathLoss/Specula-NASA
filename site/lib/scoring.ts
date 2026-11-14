import type { DetectionTrack } from "@/types/specula";
import { isMockTrackId } from "@/lib/tracks";

export type TargetCheck = {
  label: string;
  mode: string | null;
  framesOnData: number;
  framesLikelyVisible: number;
  framesFound: number;
  scoreVsAllFrames: number | null;
  scoreVsVisibleFrames: number | null;
  falseTargetPoints: number;
  medianPositionErrorArcsec: number | null;
  note: string | null;
};

export type RecoveryBin = {
  id: string;
  label: string;
  recovered: number;
  visible: number;
  fraction: number;
};

export type TrackCounts = {
  total: number;
  known: number;
  candidates: number;
  byPatch: Record<string, { known: number; candidates: number }>;
};

export type ScoringReport = {
  generatedUtc: string | null;
  atlas: TargetCheck | null;
  ceres: TargetCheck | null;
  bins: RecoveryBin[];
  tracks: TrackCounts | null;
  nepNote: string | null;
};

export type PipelineFacts = {
  knownTracks: number;
  candidateTracks: number;
  targetsClaimed: boolean;
  objectIds: string[];
};

export type PipelineStat = {
  label: string;
  value: string;
};

export type PipelineCopy = {
  recoveredAtlas: string | null;
  recoveredKnown: string | null;
  noNewObjects: string | null;
  validation: string | null;
  claim: string | null;
  nep: string | null;
  stats: PipelineStat[];
};

const BIN_ORDER = ["V<15", "V15-17", "V>=17"];

const BIN_LABELS: Record<string, string> = {
  "V<15": "Brighter than V 15",
  "V15-17": "V 15–17",
  "V>=17": "Fainter than V 17",
};

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const num = (v: unknown): number | undefined =>
  typeof v === "number" && Number.isFinite(v) ? v : undefined;

const str = (v: unknown): string | undefined =>
  typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;

function parseTarget(raw: unknown, label: string): TargetCheck | null {
  if (!isObj(raw)) return null;
  const framesOnData = num(raw.frames_on_data);
  const framesLikelyVisible = num(raw.frames_likely_visible);
  const framesFound = num(raw.frames_found);
  const falseTargetPoints = num(raw.false_target_points);
  if (
    framesOnData === undefined ||
    framesLikelyVisible === undefined ||
    framesFound === undefined ||
    falseTargetPoints === undefined
  ) {
    return null;
  }
  return {
    label,
    mode: str(raw.mode) ?? null,
    framesOnData,
    framesLikelyVisible,
    framesFound,
    scoreVsAllFrames: num(raw.score_vs_all_frames) ?? null,
    scoreVsVisibleFrames: num(raw.score_vs_visible_frames) ?? null,
    falseTargetPoints,
    medianPositionErrorArcsec: num(raw.median_position_error_arcsec) ?? null,
    note: str(raw.note) ?? null,
  };
}

function parseBins(raw: unknown): RecoveryBin[] {
  if (!isObj(raw)) return [];
  const keys = [
    ...BIN_ORDER.filter((key) => key in raw),
    ...Object.keys(raw).filter((key) => !BIN_ORDER.includes(key)),
  ];
  return keys.flatMap((key) => {
    const row = raw[key];
    if (!isObj(row)) return [];
    const recovered = num(row.recovered);
    const visible = num(row.visible);
    const fraction = num(row.fraction);
    if (recovered === undefined || visible === undefined || fraction === undefined)
      return [];
    return [
      {
        id: key,
        label: BIN_LABELS[key] ?? key,
        recovered,
        visible,
        fraction,
      },
    ];
  });
}

function parseTrackCounts(raw: unknown): TrackCounts | null {
  if (!isObj(raw)) return null;
  const total = num(raw.total);
  const known = num(raw.known);
  const candidates = num(raw.candidates);
  if (total === undefined || known === undefined || candidates === undefined) return null;
  const byPatch: TrackCounts["byPatch"] = {};
  if (isObj(raw.by_patch)) {
    for (const [patch, row] of Object.entries(raw.by_patch)) {
      if (!isObj(row)) continue;
      byPatch[patch] = {
        known: num(row.known) ?? 0,
        candidates: num(row.candidates) ?? 0,
      };
    }
  }
  return { total, known, candidates, byPatch };
}

/** Parse scoring.json. Throws when the file is not an object. */
export function parseScoring(raw: unknown): ScoringReport {
  if (!isObj(raw)) throw new Error("expected a scoring object");
  return {
    generatedUtc: str(raw.generated_utc) ?? null,
    atlas: parseTarget(raw["3I_ATLAS_blind_test"], "3I/ATLAS"),
    ceres: parseTarget(raw.ceres_check, "Ceres"),
    bins: parseBins(raw.known_asteroids_recovered),
    tracks: parseTrackCounts(raw.tracks),
    nepNote: str(raw.nep_note) ?? null,
  };
}

export function factsFromTracks(tracks: readonly DetectionTrack[]): PipelineFacts {
  const live = tracks.filter((track) => !isMockTrackId(track.track_id));
  const known = live.filter((track) => track.status === "known");
  const candidates = live.filter((track) => track.status === "candidate");
  return {
    knownTracks: known.length,
    candidateTracks: candidates.length,
    targetsClaimed: live.some((track) => track.is_target_claimed),
    objectIds: known.flatMap((track) => (track.object_id ? [track.object_id] : [])),
  };
}

function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

function arcsec(value: number): string {
  const digits = Math.abs(value) >= 10 ? 0 : 1;
  return `${value.toFixed(digits)}″`;
}

function photos(check: TargetCheck): string {
  const visible = check.framesLikelyVisible;
  const share =
    visible > 0
      ? percent(check.framesFound / visible)
      : percent(check.scoreVsVisibleFrames ?? 0);
  const error =
    check.medianPositionErrorArcsec === null
      ? null
      : `median error ${arcsec(check.medianPositionErrorArcsec)}`;
  const parts = [
    `${check.framesFound} of ${visible} visible photos (${share})`,
    error,
    `${check.falseTargetPoints} false points`,
  ];
  return parts.filter((part): part is string => part !== null).join(", ");
}

function hasId(ids: readonly string[], objectId: string): boolean {
  return ids.includes(objectId);
}

function isDeliveredRun(report: ScoringReport, facts: PipelineFacts): boolean {
  return (
    facts.knownTracks === 8 &&
    facts.candidateTracks === 0 &&
    report.tracks?.total === 8 &&
    report.tracks.candidates === 0 &&
    report.atlas?.framesFound === 50 &&
    report.atlas.falseTargetPoints === 0 &&
    report.ceres?.framesFound === 134 &&
    report.ceres.falseTargetPoints === 0
  );
}

/**
 * Honest sentences for the v0.3 validation.
 * Wording stays on "recovered" and "candidate", and does not call the run a discovery.
 */
export function pipelineCopy(
  report: ScoringReport | null,
  facts: PipelineFacts,
): PipelineCopy {
  const ids = facts.objectIds;
  const atlas = hasId(ids, "3I");
  const ceres = hasId(ids, "1");
  const trio = hasId(ids, "20") && hasId(ids, "232") && hasId(ids, "207");
  const noCandidates = facts.candidateTracks === 0 && facts.knownTracks > 0;
  const noFalsePoints =
    report?.atlas?.falseTargetPoints === 0 && report.ceres?.falseTargetPoints === 0;
  const noFalseAlarms = noCandidates && noFalsePoints;

  const recoveredAtlas =
    atlas && report?.atlas && report.atlas.framesFound > 0
      ? noFalseAlarms
        ? "Our pipeline recovered 3I/ATLAS, the interstellar comet, in SPHEREx photos, with zero false alarms."
        : "Our pipeline recovered 3I/ATLAS, the interstellar comet, in SPHEREx photos."
      : null;

  const recoveredKnown =
    ceres && trio && noCandidates
      ? "It also recovered Ceres and three known main-belt asteroids, and found no false objects in any patch."
      : ceres && noCandidates
        ? "It also recovered Ceres and other known asteroids, and found no false objects in any patch."
        : null;

  const noNewObjects = noCandidates
    ? "No new objects: every moving thing we found is already known to NASA."
    : null;

  const validation = !report
    ? null
    : isDeliveredRun(report, facts)
      ? "This is a validation run. Settings were locked before the 3I/ATLAS check. That first locked run recovered 3I/ATLAS and also kept 39 false paths. A stricter rule, set only from the scrambled-data noise test, then removed every false path and kept 3I/ATLAS."
      : "This is a validation run. The noise threshold is set from scrambled data, and known objects are matched afterwards by position.";

  const claim = facts.targetsClaimed
    ? "A track the detector marked as a target is labelled as such. Every other known object is matched afterwards by position."
    : facts.knownTracks > 0
      ? atlas
        ? "The pipeline does not name a target. 3I/ATLAS and the other known objects are matched afterwards by position."
        : "The pipeline does not name a target. Known objects are matched afterwards by position."
      : null;

  const nep =
    report?.nepNote && noCandidates
      ? "The North Ecliptic Pole patch has no known asteroid. This run found no candidate there."
      : null;

  const stats: PipelineStat[] = [];
  if (report?.atlas)
    stats.push({ label: "3I/ATLAS recovered", value: photos(report.atlas) });
  if (report?.ceres)
    stats.push({ label: "Ceres recovered", value: photos(report.ceres) });
  for (const bin of report?.bins ?? []) {
    stats.push({
      label: bin.label,
      value: `${percent(bin.fraction)} of visible photos (${bin.recovered} of ${bin.visible})`,
    });
  }
  if (report?.tracks) {
    stats.push({
      label: "Tracks",
      value: `${report.tracks.known} known, ${report.tracks.candidates} candidates`,
    });
  }

  return {
    recoveredAtlas,
    recoveredKnown,
    noNewObjects,
    validation,
    claim,
    nep,
    stats,
  };
}
