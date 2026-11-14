"use client";

import type { FocusMode } from "@/lib/focus";

const OPTIONS: { mode: FocusMode; label: string }[] = [
  { mode: "photo", label: "This photo" },
  { mode: "big", label: "Big" },
  { mode: "all", label: "All" },
];

export function FocusControl({
  mode,
  counts,
  onChange,
}: {
  mode: FocusMode;
  counts: Record<FocusMode, number>;
  onChange: (mode: FocusMode) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Focus"
      className="flex w-full min-w-0 flex-nowrap items-center gap-1"
    >
      <span className="text-muted shrink-0 text-[10px] tracking-wide uppercase">
        Focus
      </span>
      {OPTIONS.map((option) => {
        const active = mode === option.mode;
        const count = counts[option.mode];
        return (
          <button
            key={option.mode}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.mode)}
            className={`ring-line shrink-0 rounded px-1.5 py-0.5 text-[10px] whitespace-nowrap ring-1 ${
              active
                ? "bg-hover text-ink"
                : "bg-raised text-muted hover:bg-hover hover:text-ink"
            }`}
          >
            {option.label} ({count})
          </button>
        );
      })}
    </div>
  );
}
