"use client";

import type { CatalogObject, Patch, Track } from "@/types/specula";
import type { PipelineCopy } from "@/lib/scoring";
import { objectKey, trackKey, type SelectionKey } from "@/lib/selection";
import { isMockTrackId } from "@/lib/tracks";

const OBJECT_ORDER = ["3I", "1", "20", "232", "207"];

const NAMES: Record<string, string> = {
  "1": "Ceres",
  "3I": "3I/ATLAS",
  "20": "20 Massalia",
  "232": "232 Russia",
  "207": "207 Hedda",
};

function shortName(track: Track, catalog?: CatalogObject): string {
  if (track.object_id && NAMES[track.object_id]) return NAMES[track.object_id];
  const raw = catalog?.name?.replace(/\s*\([^)]*\)\s*$/, "").trim();
  return raw || track.object_id || track.track_id;
}

function trackKeyFor(track: Track): SelectionKey {
  return track.status === "known" && track.object_id
    ? objectKey(track.object_id)
    : trackKey(track.track_id);
}

function sortTracks(tracks: readonly Track[]): Track[] {
  return [...tracks].sort((a, b) => {
    const ai = a.object_id ? OBJECT_ORDER.indexOf(a.object_id) : -1;
    const bi = b.object_id ? OBJECT_ORDER.indexOf(b.object_id) : -1;
    const ao = ai === -1 ? OBJECT_ORDER.length : ai;
    const bo = bi === -1 ? OBJECT_ORDER.length : bi;
    if (ao !== bo) return ao - bo;
    return (
      a.first_seen_utc.localeCompare(b.first_seen_utc) ||
      a.track_id.localeCompare(b.track_id)
    );
  });
}

export function PipelineStatus({
  copy,
  tracks,
  catalogById,
  patches,
  selectedId,
  onOpenTrack,
  detail,
}: {
  copy: PipelineCopy;
  tracks: readonly Track[];
  catalogById: Map<string, CatalogObject>;
  patches: readonly Patch[];
  selectedId: SelectionKey | null;
  onOpenTrack: (track: Track) => void;
  detail: boolean;
}) {
  const known = sortTracks(
    tracks.filter((track) => track.status === "known" && !isMockTrackId(track.track_id)),
  );
  const patchName = new Map(patches.map((patch) => [patch.id, patch.name]));
  const sentences = [copy.recoveredAtlas, copy.recoveredKnown, copy.noNewObjects].filter(
    (line): line is string => Boolean(line),
  );
  if (sentences.length === 0 && known.length === 0 && copy.stats.length === 0)
    return null;

  return (
    <section
      aria-label="Pipeline status"
      className="border-line bg-panel rounded-lg border px-4 py-3 text-sm"
    >
      <h2 className="text-muted mb-2 text-xs font-semibold tracking-widest uppercase">
        Pipeline
      </h2>
      <div className="space-y-2 leading-relaxed">
        {sentences.map((line) => (
          <p key={line} role={line === copy.noNewObjects ? "status" : undefined}>
            {line}
          </p>
        ))}
        {detail && copy.validation && (
          <p className="text-muted text-xs leading-relaxed">{copy.validation}</p>
        )}
        {detail && copy.claim && (
          <p className="text-muted text-xs leading-relaxed">{copy.claim}</p>
        )}
        {detail && copy.nep && (
          <p className="text-muted text-xs leading-relaxed">{copy.nep}</p>
        )}
      </div>
      {detail && copy.stats.length > 0 && (
        <dl className="mt-3 grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {copy.stats.map((stat) => (
            <div key={stat.label} className="contents">
              <dt className="text-muted text-xs">{stat.label}</dt>
              <dd className="text-ink mb-1 font-mono text-xs sm:mb-0 sm:text-right">
                {stat.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {known.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Recovered tracks">
          {known.map((track) => {
            const key = trackKeyFor(track);
            const selected = selectedId === key;
            const name = shortName(
              track,
              track.object_id ? catalogById.get(track.object_id) : undefined,
            );
            const photos = track.n_points || track.points.length;
            const where = patchName.get(track.patch) ?? track.patch;
            return (
              <li key={track.track_id}>
                <button
                  type="button"
                  onClick={() => onOpenTrack(track)}
                  aria-pressed={selected}
                  title={`${name} · ${where} · ${photos} photos`}
                  className={`rounded px-2 py-1 text-xs ring-1 transition-colors ${
                    selected
                      ? "bg-hover text-ink ring-line"
                      : "text-muted hover:bg-hover hover:text-ink ring-line"
                  }`}
                >
                  <span className="text-ink">{name}</span>
                  <span className="text-muted"> · {photos} photos</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
