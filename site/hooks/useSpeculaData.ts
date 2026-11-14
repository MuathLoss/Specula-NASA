"use client";

// hooks/useSpeculaData.ts
// Loads the static Specula data from /data.
//
//   useSpeculaData()      global files, once per page load:
//                         manifest, history, pointings, detections.json,
//                         scoring.json, cosmos, orbits, objects.csv
//   usePatchData(patch)   per patch, on demand:
//                         <folder>/timeline.json, <folder>/markers.json
//
// Every file is validated on its own; a missing or malformed file falls back
// (empty or placeholder) without taking the others down. `sources`/`errors`
// say which files are real.

import { useCallback, useEffect, useState } from "react";
import type {
  AppManifest,
  CatalogObject,
  CosmosData,
  CosmosFile,
  CosmosStar,
  DataUpdate,
  AtlasMarker,
  Frame,
  FrameQuality,
  Marker,
  ObjectKind,
  OrbitEntry,
  Patch,
  PatchHeader,
  PatchKind,
  PatchTimeline,
  Pointing,
  TimelineBurst,
  Track,
  Vec3Tuple,
} from "@/types/specula";
import { parseAtlasMarkers, parseMarkers } from "@/lib/markers";
import { parseObjectsCsv } from "@/lib/parse-objects";
import { parseTracks } from "@/lib/parse-tracks";
import { parseScoring, type ScoringReport } from "@/lib/scoring";
import { liveTracks } from "@/lib/tracks";
import { fallbackCosmos, fallbackManifest } from "@/lib/specula-fallbacks";

export const DATA_BASE_URL = "/data";

export type DataSource = "remote" | "fallback";
type DataKey =
  | "manifest"
  | "history"
  | "pointings"
  | "detections"
  | "scoring"
  | "cosmos"
  | "orbits"
  | "objects";

export interface SpeculaBundle {
  manifest: AppManifest;
  updates: DataUpdate[];
  pointings: Pointing[];
  /** detections.json tracks. Ids that start with MOCK- are removed. */
  tracks: Track[];
  /** scoring.json, or null when that file is missing or unreadable. */
  scoring: ScoringReport | null;
  /** Stars and guides from cosmos.json; objects_3d from orbits.json + objects.csv. */
  cosmos: CosmosData;
  /** orbits.json planets keyed by planet id ("earth", "mars", …). */
  planetOrbits: Record<string, OrbitEntry>;
  /** addons/3i-atlas_markers.json, or [] when that file is absent. */
  atlasFocusMarkers: AtlasMarker[];
  sources: Record<DataKey, DataSource>;
  errors: Partial<Record<DataKey, string>>;
}

export interface UseSpeculaData extends Partial<
  Omit<SpeculaBundle, "sources" | "errors">
> {
  status: "loading" | "ready";
  sources: Partial<Record<DataKey, DataSource>>;
  errors: Partial<Record<DataKey, string>>;
  /** True if any global file fell back to placeholder data. */
  usingFallback: boolean;
  reload: () => void;
}

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const num = (v: unknown): number | undefined =>
  typeof v === "number" && Number.isFinite(v)
    ? v
    : typeof v === "string" && v.trim() !== "" && Number.isFinite(+v)
      ? +v
      : undefined;

const str = (v: unknown): string | undefined =>
  typeof v === "string" && v !== "" ? v : undefined;

function vec3(v: unknown): Vec3Tuple | undefined {
  if (!Array.isArray(v) || v.length !== 3) return undefined;
  const [x, y, z] = v.map(num);
  return x !== undefined && y !== undefined && z !== undefined ? [x, y, z] : undefined;
}

function listFrom(raw: unknown, key: string): unknown[] {
  if (Array.isArray(raw)) return raw;
  if (isObj(raw) && Array.isArray(raw[key])) return raw[key] as unknown[];
  throw new Error(`expected an array or { ${key}: [...] }`);
}

function framesAdded(v: unknown): string | number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") return v;
  return "";
}

function asPatchKind(v: unknown): PatchKind {
  return v === "moving" ? "moving" : "fixed";
}

function asQuality(v: unknown): FrameQuality {
  return v === "warn_transients" ? "warn_transients" : "ok";
}

function asKind(v: unknown): ObjectKind {
  return v === "dwarf_planet" || v === "interstellar" || v === "candidate"
    ? v
    : "asteroid";
}

function normalizeManifest(raw: unknown): AppManifest {
  const patches = listFrom(raw, "patches").map((p, i): Patch => {
    if (!isObj(p)) throw new Error(`patch #${i} is not an object`);
    const id = str(p.patch_id) || str(p.id);
    if (!id) throw new Error(`patch #${i} has no patch_id`);
    return {
      patch_id: id,
      id,
      name: str(p.name) ?? id,
      kind: asPatchKind(p.kind),
      n_frames: num(p.n_frames) ?? 0,
      n_bursts: num(p.n_bursts) ?? 0,
      date_start: str(p.date_start) ?? "",
      date_end: str(p.date_end) ?? "",
      folder: str(p.folder) ?? `${id}/`,
    };
  });
  if (patches.length === 0) throw new Error("manifest has no patches");
  const m = isObj(raw) ? raw : {};
  const files = Array.isArray(m.files)
    ? m.files.flatMap((f) => {
        if (!isObj(f) || !str(f.path) || num(f.bytes) === undefined) return [];
        return [{ path: f.path as string, bytes: num(f.bytes) as number }];
      })
    : [];
  return {
    version: str(m.version) ?? "",
    generated_utc: str(m.generated_utc) ?? "",
    data_through_utc: str(m.data_through_utc) ?? "",
    latest_ingest_utc: str(m.latest_ingest_utc) ?? "",
    new_badge_days: num(m.new_badge_days) ?? 7,
    new_badge_rule: str(m.new_badge_rule) ?? "",
    patches,
    files,
  };
}

function normalizeHistory(raw: unknown): DataUpdate[] {
  return listFrom(raw, "updates").flatMap((u): DataUpdate[] => {
    if (!isObj(u) || !str(u.update_id) || !str(u.ingested_utc)) return [];
    return [
      {
        update_id: u.update_id as string,
        ingested_utc: u.ingested_utc as string,
        baseline: u.baseline === true,
        data_through_utc: str(u.data_through_utc) ?? "",
        n_frames: num(u.n_frames) ?? 0,
        frames_added: framesAdded(u.frames_added),
        note: str(u.note) ?? "",
      },
    ];
  });
}

function normalizePointings(raw: unknown): Pointing[] {
  const out = listFrom(raw, "pointings").flatMap((p): Pointing[] => {
    if (!isObj(p)) return [];
    const burst_id = str(p.burst_id),
      patch_id = str(p.patch_id),
      time_utc = str(p.time_utc);
    const jd = num(p.jd),
      ra = num(p.ra_deg),
      dec = num(p.dec_deg);
    const dir = vec3(p.dir_ecl),
      earth = vec3(p.earth_au);
    if (
      !burst_id ||
      !patch_id ||
      !time_utc ||
      jd === undefined ||
      ra === undefined ||
      dec === undefined ||
      !dir ||
      !earth
    ) {
      return [];
    }
    return [
      {
        burst_id,
        patch_id,
        time_utc,
        jd,
        ra_deg: ra,
        dec_deg: dec,
        fov_deg: num(p.fov_deg) ?? 0,
        dir_ecl: dir,
        earth_au: earth,
      },
    ];
  });
  if (out.length === 0) throw new Error("no valid pointings");
  return out;
}

function normalizeStars(raw: unknown): CosmosStar[] {
  if (!isObj(raw) || !Array.isArray(raw.stars))
    throw new Error("expected { stars: [...] }");
  const cols = Array.isArray(raw.star_columns)
    ? (raw.star_columns as unknown[]).map(String)
    : [];
  const col = (name: string, fallback: number) =>
    cols.includes(name) ? cols.indexOf(name) : fallback;
  const iRa = col("ra_deg", 0),
    iDec = col("dec_deg", 1),
    iMag = col("vmag", 2),
    iBv = col("bv", 3);
  return raw.stars.flatMap((s): CosmosStar[] => {
    const ra = Array.isArray(s)
      ? num(s[iRa])
      : isObj(s)
        ? num(s.ra_deg ?? s.ra)
        : undefined;
    const dec = Array.isArray(s)
      ? num(s[iDec])
      : isObj(s)
        ? num(s.dec_deg ?? s.dec)
        : undefined;
    if (ra === undefined || dec === undefined) return [];
    const mag = Array.isArray(s)
      ? num(s[iMag])
      : isObj(s)
        ? num(s.vmag ?? s.mag)
        : undefined;
    const bv = Array.isArray(s) ? num(s[iBv]) : isObj(s) ? num(s.bv) : undefined;
    return [{ ra, dec, mag: mag ?? 6, bv: bv ?? null }];
  });
}

function normalizeCosmosFile(raw: unknown): Omit<CosmosData, "objects_3d"> {
  if (!isObj(raw)) throw new Error("expected a cosmos.json object");
  const stars = normalizeStars(raw);
  const file = raw as Partial<CosmosFile>;
  const lines =
    isObj(raw.lines) &&
    Array.isArray((raw.lines as { ecliptic?: unknown }).ecliptic) &&
    Array.isArray((raw.lines as { galactic_equator?: unknown }).galactic_equator)
      ? {
          ecliptic: (raw.lines as CosmosFile["lines"]).ecliptic.filter(
            (p): p is [number, number] =>
              Array.isArray(p) && num(p[0]) !== undefined && num(p[1]) !== undefined,
          ),
          galactic_equator: (raw.lines as CosmosFile["lines"]).galactic_equator.filter(
            (p): p is [number, number] =>
              Array.isArray(p) && num(p[0]) !== undefined && num(p[1]) !== undefined,
          ),
        }
      : undefined;
  const galactic_band = isObj(raw.galactic_band)
    ? {
        half_width_deg: num(raw.galactic_band.half_width_deg) ?? 10,
        note: str(raw.galactic_band.note) ?? "",
        columns: Array.isArray(raw.galactic_band.columns)
          ? raw.galactic_band.columns.map(String)
          : [],
        points: Array.isArray(raw.galactic_band.points)
          ? raw.galactic_band.points.flatMap((p): [number, number, number][] => {
              if (!Array.isArray(p) || p.length < 2) return [];
              const ra = num(p[0]),
                dec = num(p[1]),
                l = num(p[2]) ?? 0;
              return ra !== undefined && dec !== undefined ? [[ra, dec, l]] : [];
            })
          : [],
      }
    : undefined;
  const labels = Array.isArray(file.labels) ? file.labels : undefined;
  return {
    stars,
    obliquity_deg: num(raw.obliquity_deg),
    galactic_band,
    lines,
    labels,
  };
}

function normalizeOrbitEntry(o: Record<string, unknown>): OrbitEntry | null {
  const object_id = str(o.object_id) ?? str(o.name);
  const name = str(o.name) ?? object_id;
  const e = num(o.e);
  const i_deg = num(o.i_deg ?? o.i);
  const node_deg = num(o.node_deg);
  const peri_deg = num(o.peri_deg);
  const n_deg_day = num(o.n_deg_day);
  if (
    !object_id ||
    !name ||
    e === undefined ||
    i_deg === undefined ||
    node_deg === undefined ||
    peri_deg === undefined ||
    n_deg_day === undefined
  ) {
    return null;
  }
  const hyperbolic = o.orbit_type === "hyperbolic" || e >= 1;
  if (!hyperbolic) {
    const a_au = num(o.a_au ?? o.a);
    const M_deg = num(o.M_deg ?? o.mean_anomaly_deg);
    const epoch_jd_tdb = num(o.epoch_jd_tdb ?? o.epoch_jd);
    if (a_au === undefined || M_deg === undefined || epoch_jd_tdb === undefined)
      return null;
    return {
      object_id,
      name,
      orbit_type: "elliptic",
      a_au,
      e,
      i_deg,
      node_deg,
      peri_deg,
      M_deg,
      n_deg_day,
      epoch_jd_tdb,
    };
  }
  const q_au = num(o.q_au);
  const a_au = num(o.a_au ?? o.a) ?? (q_au !== undefined ? q_au / (1 - e) : undefined);
  const tp_jd_tdb = num(o.tp_jd_tdb ?? o.tp_jd);
  if (q_au === undefined || a_au === undefined || tp_jd_tdb === undefined) return null;
  return {
    object_id,
    name,
    orbit_type: "hyperbolic",
    q_au,
    a_au,
    e,
    i_deg,
    node_deg,
    peri_deg,
    tp_jd_tdb,
    n_deg_day,
    elements_epoch_jd_tdb: num(o.elements_epoch_jd_tdb),
    source: str(o.source),
  };
}

interface OrbitsBundle {
  objects: OrbitEntry[];
  planets: Record<string, OrbitEntry>;
}

function normalizeOrbits(raw: unknown): OrbitsBundle {
  if (!isObj(raw)) throw new Error("expected { objects, planets }");
  const objects: OrbitEntry[] = [];
  for (const o of Array.isArray(raw.objects) ? raw.objects : []) {
    if (!isObj(o)) continue;
    const orbit = normalizeOrbitEntry(o);
    if (orbit) objects.push(orbit);
  }
  const planets: Record<string, OrbitEntry> = {};
  for (const p of Array.isArray(raw.planets) ? raw.planets : []) {
    if (!isObj(p)) continue;
    const orbit = normalizeOrbitEntry(p);
    if (!orbit) continue;
    const id = orbit.object_id.replace(/^planet-/, "").toLowerCase();
    planets[id] = orbit;
  }
  if (objects.length === 0 && Object.keys(planets).length === 0) {
    throw new Error("no usable orbital elements");
  }
  return { objects, planets };
}

function buildCatalog(orbits: OrbitsBundle, meta: CatalogObject[]): CatalogObject[] {
  const byId = new Map(meta.map((o) => [o.object_id, o]));
  return orbits.objects.map((orbit) => {
    const m = byId.get(orbit.object_id);
    return {
      object_id: orbit.object_id,
      name: m?.name || orbit.name,
      kind:
        m?.kind ??
        asKind(orbit.orbit_type === "hyperbolic" ? "interstellar" : "asteroid"),
      status: m?.status ?? "known",
      H_mag: m?.H_mag ?? null,
      size_min_km: m?.size_min_km ?? null,
      size_max_km: m?.size_max_km ?? null,
      size_source: m?.size_source ?? "",
      distance_min_au: m?.distance_min_au ?? null,
      distance_max_au: m?.distance_max_au ?? null,
      show_in_3d: m?.show_in_3d ?? false,
      patches: m?.patches ?? [],
      n_frames: m?.n_frames ?? 0,
      first_utc: m?.first_utc ?? null,
      last_utc: m?.last_utc ?? null,
      orbit,
    };
  });
}

type Loaded<T> = { data: T; source: DataSource; error?: string };

async function loadFile<T>(
  path: string,
  parse: (res: Response) => Promise<T>,
  fallback: () => T,
  quiet404 = false,
): Promise<Loaded<T>> {
  try {
    const res = await fetch(`${DATA_BASE_URL}/${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return { data: await parse(res), source: "remote" };
  } catch (err) {
    const error = `${path}: ${err instanceof Error ? err.message : String(err)}`;
    if (!quiet404 || !error.endsWith("HTTP 404"))
      console.warn(`[specula] using fallback for ${error}`);
    return { data: fallback(), source: "fallback", error };
  }
}

const json =
  <T>(normalize: (raw: unknown) => T) =>
  async (res: Response) =>
    normalize(await res.json());

let bundlePromise: Promise<SpeculaBundle> | null = null;

export function loadSpeculaData(): Promise<SpeculaBundle> {
  bundlePromise ??= (async () => {
    const parts = {
      manifest: loadFile("manifest.json", json(normalizeManifest), fallbackManifest),
      history: loadFile("history.json", json(normalizeHistory), () => [] as DataUpdate[]),
      pointings: loadFile(
        "pointings.json",
        json(normalizePointings),
        () => [] as Pointing[],
      ),
      detections: loadFile("detections.json", json(parseTracks), () => [] as Track[]),
      scoring: loadFile(
        "scoring.json",
        json((raw): ScoringReport | null => parseScoring(raw)),
        () => null as ScoringReport | null,
      ),
      cosmos: loadFile("cosmos.json", json(normalizeCosmosFile), () => fallbackCosmos()),
      orbits: loadFile("orbits.json", json(normalizeOrbits), (): OrbitsBundle => ({
        objects: [],
        planets: {},
      })),
      objects: loadFile(
        "objects.csv",
        async (r) => parseObjectsCsv(await r.text()),
        () => [] as CatalogObject[],
      ),
    };
    const [entries, atlasFocusMarkers] = await Promise.all([
      Promise.all(Object.entries(parts).map(async ([k, p]) => [k, await p] as const)),
      loadFile(
        "addons/3i-atlas_markers.json",
        json(parseAtlasMarkers),
        () => [] as AtlasMarker[],
        true,
      ),
    ]);
    const r = Object.fromEntries(entries) as {
      [K in keyof typeof parts]: Awaited<(typeof parts)[K]>;
    };

    const errors: SpeculaBundle["errors"] = {};
    const sources = {} as SpeculaBundle["sources"];
    for (const [k, v] of Object.entries(r) as [DataKey, Loaded<unknown>][]) {
      sources[k] = v.source;
      if (v.error) errors[k] = v.error;
    }

    const tracks = liveTracks(r.detections.data);
    const candidatePatches = new Set(
      tracks.filter((t) => t.status === "candidate").map((t) => t.patch),
    );

    return {
      manifest: {
        ...r.manifest.data,
        patches: r.manifest.data.patches.map((p) => ({
          ...p,
          has_candidates: candidatePatches.has(p.id),
        })),
      },
      updates: r.history.data,
      pointings: r.pointings.data,
      tracks,
      scoring: r.scoring.data,
      cosmos: {
        ...r.cosmos.data,
        objects_3d: buildCatalog(r.orbits.data, r.objects.data),
      },
      planetOrbits: r.orbits.data.planets,
      atlasFocusMarkers: atlasFocusMarkers.data,
      sources,
      errors,
    };
  })();
  return bundlePromise;
}

const EMPTY_ATLAS_MARKERS: AtlasMarker[] = [];

export function useAtlasFocusMarkers(): AtlasMarker[] {
  return useSpeculaData().atlasFocusMarkers ?? EMPTY_ATLAS_MARKERS;
}

export function useSpeculaData(): UseSpeculaData {
  const [bundle, setBundle] = useState<SpeculaBundle | null>(null);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let active = true;
    loadSpeculaData().then((b) => {
      if (active) setBundle(b);
    });
    return () => {
      active = false;
    };
  }, [generation]);

  const reload = useCallback(() => {
    bundlePromise = null;
    patchCache.clear();
    setBundle(null);
    setGeneration((g) => g + 1);
  }, []);

  if (!bundle)
    return { status: "loading", sources: {}, errors: {}, usingFallback: false, reload };
  return {
    status: "ready",
    ...bundle,
    usingFallback: Object.keys(bundle.errors).length > 0,
    reload,
  };
}

export interface PatchData {
  timeline: PatchTimeline | null;
  markers: Marker[];
  /** Where timeline.json came from, or null if none was found. */
  timelinePath: string | null;
}

function normalizePatchHeader(
  raw: Record<string, unknown>,
  patch_id: string,
): PatchHeader {
  return {
    patch_id,
    name: str(raw.name) ?? patch_id,
    kind: asPatchKind(raw.kind),
    followed_object: str(raw.followed_object) ?? null,
    size_px: num(raw.size_px) ?? 351,
    pixel_scale_arcsec: num(raw.pixel_scale_arcsec) ?? 0,
    north_up: raw.north_up !== false,
    projection: str(raw.projection) ?? "TAN",
    date_start: str(raw.date_start) ?? "",
    date_end: str(raw.date_end) ?? "",
    n_frames: num(raw.n_frames) ?? 0,
    n_bursts: num(raw.n_bursts) ?? 0,
  };
}

function normalizeTimeline(raw: unknown): PatchTimeline {
  if (
    !isObj(raw) ||
    !isObj(raw.patch) ||
    !Array.isArray(raw.frames) ||
    !Array.isArray(raw.bursts)
  ) {
    throw new Error("expected { patch, frames, bursts }");
  }
  const patch_id = str(raw.patch.patch_id) ?? str(raw.patch.id);
  if (!patch_id) throw new Error("timeline patch has no patch_id");
  const frames = raw.frames.flatMap((f): Frame[] => {
    if (!isObj(f) || !str(f.frame_id) || !str(f.burst_id)) return [];
    return [
      {
        frame_id: f.frame_id as string,
        burst_id: f.burst_id as string,
        time_utc: str(f.time_utc) ?? "",
        mjd: num(f.mjd) ?? 0,
        detector: str(f.detector) ?? "",
        wavelength_um: num(f.wavelength_um) ?? 0,
        image: str(f.image) ?? "",
        thumb: str(f.thumb) ?? "",
        ra_center: num(f.ra_center) ?? 0,
        dec_center: num(f.dec_center) ?? 0,
        coverage: num(f.coverage) ?? 0,
        quality: asQuality(f.quality),
        update_id: str(f.update_id) ?? "",
        added_utc: str(f.added_utc) ?? "",
        diff: str(f.diff),
      },
    ];
  });
  const bursts = raw.bursts.flatMap((b): TimelineBurst[] => {
    if (!isObj(b) || !str(b.burst_id)) return [];
    return [
      {
        burst_id: b.burst_id as string,
        time_utc: str(b.time_utc) ?? "",
        frame_ids: Array.isArray(b.frame_ids)
          ? b.frame_ids.filter((x): x is string => typeof x === "string")
          : [],
        detectors: Array.isArray(b.detectors) ? b.detectors.map(String) : [],
        ra_center: num(b.ra_center) ?? 0,
        dec_center: num(b.dec_center) ?? 0,
        composite: str(b.composite) ?? "",
        composite_thumb: str(b.composite_thumb) ?? "",
        representative: str(b.representative) ?? "",
      },
    ];
  });
  return {
    patch: normalizePatchHeader(raw.patch, patch_id),
    frames,
    bursts,
  };
}

const patchCache = new Map<string, Promise<PatchData>>();

/**
 * timeline.json is looked up at <folder>/timeline.json, then at the /data
 * root (only used if its patch_id matches, for data copied without folders).
 */
export function loadPatchData(patch: Patch): Promise<PatchData> {
  const cached = patchCache.get(patch.id);
  if (cached) return cached;
  const folder = (patch.folder ?? `${patch.id}/`).replace(/\/?$/, "/");
  const promise = (async (): Promise<PatchData> => {
    const tryTimeline = async (path: string) => {
      const r = await loadFile(path, json(normalizeTimeline), () => null, true);
      return r.data && r.data.patch.patch_id === patch.id
        ? { timeline: r.data, path }
        : null;
    };
    const [inFolder, markers] = await Promise.all([
      tryTimeline(`${folder}timeline.json`),
      loadFile(`${folder}markers.json`, json(parseMarkers), () => [] as Marker[], true),
    ]);
    const found = inFolder ?? (await tryTimeline("timeline.json"));
    return {
      timeline: found?.timeline ?? null,
      timelinePath: found?.path ?? null,
      markers: markers.data,
    };
  })();
  patchCache.set(patch.id, promise);
  return promise;
}

export function usePatchData(patch: Patch | null): {
  status: "idle" | "loading" | "ready";
  data: PatchData | null;
} {
  const [state, setState] = useState<{ id: string; data: PatchData } | null>(null);

  useEffect(() => {
    if (!patch) return;
    let active = true;
    loadPatchData(patch).then((data) => {
      if (active) setState({ id: patch.id, data });
    });
    return () => {
      active = false;
    };
  }, [patch]);

  if (!patch) return { status: "idle", data: null };
  if (state?.id !== patch.id) return { status: "loading", data: null };
  return { status: "ready", data: state.data };
}
