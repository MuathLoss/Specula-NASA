import type { AppManifest, CosmosData, Patch } from "@/types/specula";

const PATCHES: Array<Pick<Patch, "id" | "name">> = [
  { id: "ecliptic-virgo", name: "Ecliptic (Virgo)" },
  { id: "ecliptic-ra90", name: "Ecliptic (RA 90, Milky Way)" },
  { id: "nep-cats-eye", name: "North Ecliptic Pole (Cat's Eye)" },
  { id: "ceres", name: "Ceres" },
  { id: "3i-atlas", name: "3I/ATLAS" },
];

export function fallbackManifest(): AppManifest {
  return {
    version: "placeholder",
    generated_utc: "",
    data_through_utc: "",
    latest_ingest_utc: "",
    new_badge_days: 7,
    new_badge_rule: "",
    files: [],
    patches: PATCHES.map((p) => ({
      patch_id: p.id,
      id: p.id,
      name: p.name,
      kind: "fixed",
      n_frames: 0,
      n_bursts: 0,
      date_start: "",
      date_end: "",
      folder: `${p.id}/`,
      is_placeholder: true,
    })),
  };
}

export function fallbackCosmos(): CosmosData {
  return { stars: [], objects_3d: [] };
}
