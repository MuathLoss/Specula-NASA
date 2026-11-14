"use client";

import { useEffect, useState } from "react";
import type { CatalogObject, Detection, Marker } from "@/types/specula";
import { Tooltip } from "@/components/Tooltip";
import { copyText } from "@/lib/clipboard";
import { sizeRangeKm } from "@/types/specula";
import { formatVMagnitude } from "@/lib/markers";
import type { ResolvedSelection } from "@/lib/selection";

const KNOWN = "#00F0FF";
const CANDIDATE = "#FF8C00";

interface SidePanelProps {
  selection: ResolvedSelection | null;
  onClear?: () => void;
}

const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const fmt = (n: unknown, digits = 2) =>
  !ok(n) ? "—" : Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(digits);
const range = (a: number, b: number, unit: string) =>
  `${fmt(Math.min(a, b))}–${fmt(Math.max(a, b))} ${unit}`;
const KIND_LABEL: Record<string, string> = {
  asteroid: "Asteroid",
  dwarf_planet: "Dwarf planet",
  interstellar: "Interstellar object",
};

function candidateRows(d: Detection): Array<[string, React.ReactNode]> {
  const rows: Array<[string, React.ReactNode]> = [];
  if (ok(d.v_mag_est)) rows.push(["Estimated brightness", `V ${fmt(d.v_mag_est, 1)}`]);
  if (d.h_range && ok(d.h_range[0]) && ok(d.h_range[1])) {
    rows.push(["Estimated H", range(d.h_range[0], d.h_range[1], "mag")]);
  }
  if (ok(d.position_error_px)) {
    rows.push(["Position error", `${fmt(d.position_error_px, 1)} px`]);
  }
  if (ok(d.arc_hours)) rows.push(["Arc", `${fmt(d.arc_hours, 1)} h`]);
  if (d.linked_tracks && d.linked_tracks.length > 0) {
    rows.push(["Linked tracks", d.linked_tracks.join(", ")]);
  }
  if (d.comet_check) rows.push(["Comet check", d.comet_check]);
  return rows;
}

export function SidePanel({ selection, onClear }: SidePanelProps) {
  return (
    <aside
      className="border-line bg-panel flex flex-col rounded-lg border p-4 text-sm"
      aria-label="Object inspector"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-muted text-xs font-semibold tracking-widest uppercase">
          Inspector
        </h2>
        {selection && onClear && (
          <button
            type="button"
            onClick={onClear}
            className="text-muted hover:text-ink text-xs"
          >
            Clear
          </button>
        )}
      </div>
      {selection ? (
        // Keyed so details fade in when the selection changes.
        <div key={selection.key} className="animate-fade-in">
          <Details selection={selection} />
          <CopyActions selection={selection} />
        </div>
      ) : (
        <p className="animate-fade-in text-muted">
          Select an object in the 2D or 3D view.
        </p>
      )}
    </aside>
  );
}

function Details({ selection }: { selection: ResolvedSelection }) {
  if (selection.kind === "planet") {
    return (
      <>
        <Title color="#e8e8e8">{selection.planet.name}</Title>
        <Rows
          rows={[
            ["Status", "Planet"],
            ["Semi-major axis", `${fmt(selection.planet.el[0], 3)} AU`],
          ]}
        />
      </>
    );
  }

  if (selection.kind === "marker") {
    return <MarkerDetails marker={selection.marker} catalog={selection.catalog} />;
  }

  const d: Detection | undefined =
    selection.kind === "detection" ? selection.detection : undefined;
  const c: CatalogObject | undefined = selection.catalog;
  const isCandidate = d?.type === "candidate";
  const designation = d?.designation ?? c?.name ?? d?.track_id ?? "—";
  const rawSize = d?.size_est_km ?? (c ? sizeRangeKm(c) : undefined);
  const size = rawSize && ok(rawSize[0]) && ok(rawSize[1]) ? rawSize : undefined;
  const hasDistance = d && ok(d.distance_min_au) && ok(d.distance_max_au);
  const kind = c?.kind ? (KIND_LABEL[c.kind] ?? c.kind) : undefined;

  // Candidate sizes/distances are estimates; known sizes carry their source (e.g. "measured (JPL)").
  const sizeValue = !size ? (
    "—"
  ) : isCandidate ? (
    <Approx>{range(size[0], size[1], "km")}</Approx>
  ) : (
    <span>
      {range(size[0], size[1], "km")}
      {c?.size_source && (
        <span className="text-muted block text-[10px]">{c.size_source}</span>
      )}
    </span>
  );

  const rows: Array<[string, React.ReactNode]> = [
    ["Designation", designation],
    ["Status", isCandidate ? "Candidate" : `Known${kind ? ` · ${kind}` : ""}`],
    ["Size range", sizeValue],
    [
      "Distance range",
      isCandidate ? (
        hasDistance ? (
          <Approx>
            {range(d!.distance_min_au!, d!.distance_max_au!, "AU from Earth")}
          </Approx>
        ) : (
          "distance unknown"
        )
      ) : (
        "From its published orbit"
      ),
    ],
    ["Wavelength", d && ok(d.wavelength_um) ? `${fmt(d.wavelength_um, 3)} µm` : "—"],
  ];
  if (d && isCandidate) rows.push(...candidateRows(d));
  if (d) {
    rows.push(
      [
        "RA / Dec",
        ok(d.ra_deg) && ok(d.dec_deg)
          ? `${d.ra_deg.toFixed(4)}°, ${d.dec_deg >= 0 ? "+" : ""}${d.dec_deg.toFixed(4)}°`
          : "—",
      ],
      ["Magnitude", ok(d.mag) ? fmt(d.mag, 1) : "—"],
      [
        "Motion",
        ok(d.motion_arcsec_per_hr) ? `${fmt(d.motion_arcsec_per_hr, 1)} ″/hr` : "—",
      ],
      ...(isCandidate
        ? [["Score", ok(d.score) ? fmt(d.score, 2) : "—"] as [string, React.ReactNode]]
        : []),
      ...(ok(d.n_points)
        ? [["Photos", String(d.n_points)] as [string, React.ReactNode]]
        : []),
      ...(ok(d.match_sep_arcsec)
        ? [
            ["Catalogue match", `${fmt(d.match_sep_arcsec, 1)}″`] as [
              string,
              React.ReactNode,
            ],
          ]
        : []),
      ["Pixel", ok(d.x) && ok(d.y) ? `(${d.x.toFixed(1)}, ${d.y.toFixed(1)})` : "—"],
      ["Track", d.track_id],
      [
        "Frame",
        <span key="f" className="break-all">
          {d.frame_id}
        </span>,
      ],
    );
  }
  if (c) {
    if (ok(c.H_mag)) rows.push(["H magnitude", fmt(c.H_mag, 2)]);
    if (c.orbit)
      rows.push([
        "Orbit (a, e, i)",
        `${fmt(c.orbit.a_au, 3)} AU, ${fmt(c.orbit.e, 3)}, ${fmt(c.orbit.i_deg, 2)}°`,
      ]);
  }

  return (
    <>
      <Title
        color={isCandidate ? CANDIDATE : KNOWN}
        shape={isCandidate ? "diamond" : "circle"}
      >
        {isCandidate ? "Candidate" : "Known object"}
      </Title>
      <Rows rows={rows} />
      {isCandidate && (
        <p className="text-muted mt-3 text-[11px] leading-relaxed">
          Candidate values are approximate estimates and have not been confirmed.
          {d?.note ? ` ${d.note}` : ""}
        </p>
      )}
      {d && !isCandidate && (
        <p className="text-muted mt-3 text-[11px] leading-relaxed">
          {d.is_target_claimed
            ? "The detector marked this track as a target."
            : "Matched to the NASA catalogue afterwards by position. The detector did not claim this identity."}
        </p>
      )}
      {selection.kind === "catalog" && (
        <p className="text-muted mt-3 text-[11px] leading-relaxed">
          Not detected in the current patch.
        </p>
      )}
    </>
  );
}

function MarkerDetails({ marker, catalog }: { marker: Marker; catalog?: CatalogObject }) {
  const rawSize = catalog ? sizeRangeKm(catalog) : undefined;
  const size = rawSize && ok(rawSize[0]) && ok(rawSize[1]) ? rawSize : undefined;
  const kind = catalog?.kind ? (KIND_LABEL[catalog.kind] ?? catalog.kind) : undefined;
  const rows: Array<[string, React.ReactNode]> = [
    ["Designation", marker.name],
    ["Status", `Known${kind ? ` · ${kind}` : ""}`],
    [
      "Size range",
      size ? (
        <span>
          {range(size[0], size[1], "km")}
          {catalog?.size_source && (
            <span className="text-muted block text-[10px]">{catalog.size_source}</span>
          )}
        </span>
      ) : (
        "—"
      ),
    ],
    ["Magnitude", formatVMagnitude(marker.v_mag)],
    ["Pixel", `(${marker.x.toFixed(1)}, ${marker.y.toFixed(1)})`],
    ["Visibility", marker.likely_visible ? "Likely visible" : "Predicted (faint)"],
    [
      "Frame",
      <span key="f" className="break-all">
        {marker.frame_id}
      </span>,
    ],
  ];
  if (catalog) {
    if (ok(catalog.H_mag)) rows.push(["H magnitude", fmt(catalog.H_mag, 2)]);
    if (catalog.orbit)
      rows.push([
        "Orbit (a, e, i)",
        `${fmt(catalog.orbit.a_au, 3)} AU, ${fmt(catalog.orbit.e, 3)}, ${fmt(catalog.orbit.i_deg, 2)}°`,
      ]);
  }
  return (
    <>
      <Title color={KNOWN} shape="circle">
        Known object
      </Title>
      <Rows rows={rows} />
    </>
  );
}

function Title({
  children,
  color,
  shape,
}: {
  children: React.ReactNode;
  color: string;
  shape?: "circle" | "diamond";
}) {
  return (
    <div
      className="mb-3 flex items-center gap-2 text-base font-semibold"
      style={{ color }}
    >
      {shape && (
        <span
          className={
            shape === "circle"
              ? "h-2.5 w-2.5 rounded-full border-2"
              : "h-2.5 w-2.5 rotate-45 border-2"
          }
          style={{
            borderColor: color,
            boxShadow: shape === "diamond" ? `0 0 6px ${color}` : undefined,
          }}
        />
      )}
      {children}
    </div>
  );
}

function Approx({ children }: { children: React.ReactNode }) {
  return (
    <span>
      <span className="bg-raised text-muted mr-1.5 rounded px-1 py-px text-[10px] tracking-wide uppercase">
        Approximate
      </span>
      {children}
    </span>
  );
}

function Rows({ rows }: { rows: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="text-ink text-right font-mono text-xs leading-5">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------------------
// Quick actions

type ClipboardPayload = {
  id: { text: string; hint: string };
  coords: { text: string; hint: string } | null;
};

const signed = (n: number, digits: number) => `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;

/** What the copy buttons put on the clipboard for each kind of selection. */
function clipboardPayload(selection: ResolvedSelection): ClipboardPayload {
  switch (selection.kind) {
    case "planet":
      return { id: { text: selection.planet.name, hint: "planet name" }, coords: null };
    case "catalog":
      return {
        id: {
          text: selection.catalog.object_id,
          hint: `object_id (${selection.catalog.name})`,
        },
        coords: null,
      };
    case "marker": {
      const m = selection.marker;
      return {
        id: { text: m.object_id, hint: `object_id (${m.name})` },
        // markers.json has pixel positions only.
        coords: {
          text: `x ${m.x.toFixed(1)}, y ${m.y.toFixed(1)} px · frame ${m.frame_id}`,
          hint: "pixel position and frame",
        },
      };
    }
    case "detection": {
      const d = selection.detection;
      const id =
        d.type === "known" && d.object_id
          ? { text: d.object_id, hint: `object_id (${d.designation ?? d.track_id})` }
          : { text: d.track_id, hint: "track_id" };
      const coords =
        ok(d.ra_deg) && ok(d.dec_deg)
          ? {
              text: `${d.ra_deg.toFixed(6)} ${signed(d.dec_deg, 6)}`,
              hint: "RA Dec in degrees (J2000)",
            }
          : ok(d.x) && ok(d.y)
            ? {
                text: `x ${d.x.toFixed(1)}, y ${d.y.toFixed(1)} px · frame ${d.frame_id}`,
                hint: "pixel position and frame",
              }
            : null;
      return { id, coords };
    }
  }
}

function CopyActions({ selection }: { selection: ResolvedSelection }) {
  const payload = clipboardPayload(selection);
  const [status, setStatus] = useState<{ what: "id" | "coords"; ok: boolean } | null>(
    null,
  );

  useEffect(() => {
    if (!status) return;
    const t = setTimeout(() => setStatus(null), 1600);
    return () => clearTimeout(t);
  }, [status]);

  const copy = async (what: "id" | "coords", text: string) => {
    setStatus({ what, ok: await copyText(text) });
  };

  const button = (
    what: "id" | "coords",
    label: string,
    entry: { text: string; hint: string },
  ) => {
    const done = status?.what === what;
    return (
      <Tooltip
        content={
          <>
            Copy {entry.hint}:
            <span className="text-muted mt-0.5 block font-mono break-all">
              {entry.text}
            </span>
          </>
        }
        side="top"
        align={what === "id" ? "end" : "start"}
      >
        <button
          type="button"
          onClick={() => copy(what, entry.text)}
          className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs ring-1 transition-colors ${
            done && status.ok
              ? "text-emerald-300 ring-emerald-700/70"
              : done
                ? "text-amber-300 ring-amber-700/70"
                : "text-ink ring-line hover:bg-hover"
          }`}
        >
          <CopyIcon done={done && status.ok} />
          {done ? (status.ok ? "Copied" : "Copy failed") : label}
        </button>
      </Tooltip>
    );
  };

  return (
    <div className="border-line mt-4 flex flex-wrap gap-2 border-t pt-3">
      {payload.coords && button("coords", "Copy coordinates", payload.coords)}
      {button("id", "Copy ID", payload.id)}
      <span className="sr-only" role="status" aria-live="polite">
        {status ? (status.ok ? "Copied to clipboard" : "Copy failed") : ""}
      </span>
    </div>
  );
}

function CopyIcon({ done }: { done: boolean }) {
  return done ? (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      aria-hidden
    >
      <path d="M5 12.5l4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" />
    </svg>
  );
}
