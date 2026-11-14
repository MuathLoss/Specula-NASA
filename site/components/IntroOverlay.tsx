"use client";

import { useEffect, useId, useState, useSyncExternalStore } from "react";
import type { AppManifest, Patch } from "@/types/specula";
import { formatUtc } from "@/lib/frame-caption";
import type { PipelineCopy } from "@/lib/scoring";

const STORAGE_KEY = "specula.introDismissed";
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function loadDismissed(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function saveDismissed() {
  try {
    window.localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    // Ignore quota or private-mode failures; the overlay can still be closed.
  }
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useIntroOverlay() {
  const dismissed = useSyncExternalStore(subscribe, loadDismissed, () => true);
  const [forced, setForced] = useState(false);
  const openIntro = () => setForced(true);
  const closeIntro = () => {
    saveDismissed();
    setForced(false);
  };
  return { open: forced || !dismissed, openIntro, closeIntro };
}

export function IntroOverlay({
  open,
  onClose,
  manifest,
  pipeline = null,
}: {
  open: boolean;
  onClose: () => void;
  manifest?: AppManifest | null;
  pipeline?: PipelineCopy | null;
}) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const published = manifest?.data_through_utc
    ? (formatUtc(manifest.data_through_utc) ?? manifest.data_through_utc)
    : null;
  const patches = manifest?.patches ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="border-line bg-raised text-ink max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-lg border p-5 text-sm shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-ink text-lg font-semibold tracking-wide">
            About Specula
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted ring-line hover:bg-hover hover:text-ink rounded px-2 py-1 text-xs ring-1"
          >
            Close
          </button>
        </div>

        <div className="text-ink space-y-3 leading-relaxed">
          <p>
            SPHEREx is NASA&apos;s infrared all-sky survey. It photographs the sky in many
            infrared colours so we can measure the distances and compositions of objects
            across the solar system and beyond.
          </p>
          <p>
            This viewer shows five SPHEREx patches from the published data pack: two fixed
            fields on the ecliptic, one at the north ecliptic pole, and two moving fields
            that follow Ceres and the interstellar comet 3I/ATLAS.
          </p>
          {patches.length > 0 && (
            <ul className="text-muted list-disc space-y-1 pl-5">
              {patches.map((patch) => (
                <li key={patch.id}>
                  <span className="text-ink">{patch.name}</span>
                  {patch.kind ? ` · ${patchKindLabel(patch)}` : ""}
                </li>
              ))}
            </ul>
          )}
          <p>
            In the sky view, a cyan circle marks a known object. An orange diamond marks a
            candidate, not a confirmed discovery. Faint predicted positions stay hidden
            until you turn on &quot;Show faint (predicted)&quot;.
          </p>
          {pipeline && <PipelineCopyBlock copy={pipeline} />}
          {published && (
            <p className="text-muted font-mono text-xs">
              Latest published: data through {published}
            </p>
          )}
          <AboutSection title="Data & credits">
            <p>SPHEREx images (NASA/IPAC Infrared Science Archive, IRSA).</p>
            <p>
              Known-object positions, orbits and the comet list from NASA JPL (Small-Body
              Database, Horizons, sb_ident).
            </p>
            <p>Bright stars from the Yale Bright Star Catalogue.</p>
          </AboutSection>
          <AboutSection title="AI use">
            <p>
              Parts of the data pipeline, the association step, this website&apos;s code
              and our documentation were written with the help of Claude (Anthropic), an
              AI assistant. Every result was checked by the team against NASA JPL data.
            </p>
          </AboutSection>
        </div>
      </div>
    </div>
  );
}

function patchKindLabel(patch: Patch): string {
  return patch.kind === "moving" ? "moving field" : "fixed field";
}

function AboutSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-muted text-xs font-semibold tracking-wide uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

function PipelineCopyBlock({ copy }: { copy: PipelineCopy }) {
  const sentences = [copy.recoveredAtlas, copy.recoveredKnown, copy.noNewObjects].filter(
    (line): line is string => Boolean(line),
  );
  if (sentences.length === 0 && !copy.validation && copy.stats.length === 0) return null;
  return (
    <div className="border-line bg-raised space-y-2 rounded border p-3">
      <h3 className="text-muted text-xs font-semibold tracking-wide uppercase">
        Pipeline validation
      </h3>
      {sentences.map((line) => (
        <p key={line}>{line}</p>
      ))}
      {copy.validation && (
        <p className="text-muted text-xs leading-relaxed">{copy.validation}</p>
      )}
      {copy.claim && <p className="text-muted text-xs leading-relaxed">{copy.claim}</p>}
      {copy.stats.length > 0 && (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 font-mono text-xs">
          {copy.stats.map((stat) => (
            <div key={stat.label} className="contents">
              <dt className="text-muted">{stat.label}</dt>
              <dd className="text-ink">{stat.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
