"use client";

// Small CSS-only tooltip: shown on hover (after a short delay) and on keyboard
// focus, linked to its trigger with aria-describedby. No portal, so keep it
// inside containers that don't clip (or pick a `side` that stays inside).

import {
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";

type Side = "top" | "bottom" | "left" | "right";
type Align = "start" | "center" | "end";

const SIDE: Record<Side, string> = {
  top: "bottom-full mb-1.5",
  bottom: "top-full mt-1.5",
  left: "right-full mr-1.5 top-1/2 -translate-y-1/2",
  right: "left-full ml-1.5 top-1/2 -translate-y-1/2",
};

const ALIGN: Record<Align, string> = {
  start: "left-0",
  center: "left-1/2 -translate-x-1/2",
  end: "right-0",
};

export function Tooltip({
  content,
  side = "top",
  align = "center",
  className = "",
  children,
}: {
  content: ReactNode;
  side?: Side;
  align?: Align;
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const trigger = isValidElement(children)
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, {
        "aria-describedby": id,
      })
    : children;
  const horizontal = side === "top" || side === "bottom" ? ALIGN[align] : "";

  return (
    <span className={`group/tooltip relative inline-flex ${className}`}>
      {trigger}
      <span
        role="tooltip"
        id={id}
        className={`bg-raised/95 text-ink ring-line pointer-events-none absolute z-40 w-max max-w-64 rounded-md px-2 py-1 text-left text-[11px] leading-snug font-normal tracking-normal whitespace-normal normal-case opacity-0 shadow-lg ring-1 transition-opacity duration-150 group-focus-within/tooltip:opacity-100 group-hover/tooltip:opacity-100 group-hover/tooltip:delay-300 motion-reduce:transition-none ${SIDE[side]} ${horizontal}`}
      >
        {content}
      </span>
    </span>
  );
}

/** Keyboard key cap for tooltips and the shortcuts guide. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="border-line bg-hover text-ink inline-flex min-w-5 items-center justify-center rounded border px-1 py-px font-mono text-[10px] leading-none">
      {children}
    </kbd>
  );
}
