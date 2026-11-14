"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Patch } from "@/types/specula";
import { ShortcutsButton } from "@/components/ShortcutsDialog";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/viewer", label: "Sky" },
  { href: "/cosmos", label: "Cosmos" },
] as const;

interface HeaderProps {
  patches: Patch[];
  activePatchId: string | null;
  onPatchChange: (id: string) => void;
  status?: React.ReactNode;
  packVersion?: string | null;
  onOpenAbout?: () => void;
  /** Warm a patch's data before it is clicked (hover / keyboard focus). */
  onPatchPrefetch?: (id: string) => void;
  /** Active patch's per-patch data is still loading. */
  patchLoading?: boolean;
}

export function Header({
  patches,
  activePatchId,
  onPatchChange,
  status,
  packVersion,
  onOpenAbout,
  onPatchPrefetch,
  patchLoading = false,
}: HeaderProps) {
  const pathname = usePathname();

  return (
    <header className="border-line border-b pb-3">
      <div className="flex items-center gap-x-0.5 whitespace-nowrap max-sm:overflow-x-auto sm:gap-x-6">
        <div className="flex shrink-0 items-baseline gap-3">
          <Link
            href="/"
            className="text-xs font-bold tracking-wide sm:text-xl sm:tracking-[0.2em]"
          >
            SPECULA
          </Link>
          {packVersion ? (
            <span className="text-muted hidden font-mono text-[11px] sm:inline">
              pack v{packVersion}
            </span>
          ) : null}
        </div>

        <nav
          aria-label="Views"
          className="flex shrink-0 items-center gap-1 text-[11px] sm:gap-4 sm:text-sm"
        >
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={
                  active ? "text-ink" : "text-muted hover:text-ink transition-colors"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <span className="shrink-0">
          <ShortcutsButton />
        </span>

        {onOpenAbout && (
          <button
            type="button"
            onClick={onOpenAbout}
            className="text-muted ring-line hover:bg-hover hover:text-ink shrink-0 rounded px-1 py-0.5 text-[11px] ring-1 sm:px-2 sm:py-1 sm:text-sm"
          >
            About
          </button>
        )}

        {status && (
          <div className="text-muted shrink-0 text-[10px] whitespace-nowrap sm:ml-auto sm:text-xs">
            {status}
          </div>
        )}
      </div>

      <nav aria-label="Sky patches" className="mt-3 min-w-0 overflow-x-auto">
        <div className="flex w-max gap-1">
          {patches.map((p) => {
            const active = p.id === activePatchId;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onPatchChange(p.id)}
                onPointerEnter={() => onPatchPrefetch?.(p.id)}
                onFocus={() => onPatchPrefetch?.(p.id)}
                aria-current={active ? "page" : undefined}
                aria-busy={active && patchLoading ? true : undefined}
                title={[
                  p.name,
                  p.kind && `${p.kind} patch`,
                  p.date_start &&
                    p.date_end &&
                    `${p.date_start.slice(0, 10)} – ${p.date_end.slice(0, 10)}`,
                  p.n_bursts && `${p.n_bursts} bursts`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                className={`flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                  active
                    ? "bg-hover text-ink ring-line ring-1"
                    : "text-muted hover:bg-hover hover:text-ink"
                }`}
              >
                {p.name}
                {active && patchLoading && (
                  <span
                    className="border-muted border-t-ink h-3 w-3 animate-spin rounded-full border motion-reduce:animate-none"
                    aria-label="loading"
                  />
                )}
                {p.has_candidates && (
                  <span
                    className="h-1.5 w-1.5 rotate-45 bg-[#FF8C00] shadow-[0_0_6px_#FF8C00]"
                    aria-label="has Candidates"
                  />
                )}
              </button>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
