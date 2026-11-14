"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Kbd, Tooltip } from "@/components/Tooltip";
import { SHORTCUTS, hasModifier, isTypingTarget, modalOpen } from "@/lib/keyboard";

/** Header button + modal listing the global keyboard shortcuts. Also opens with "?". */
export function ShortcutsButton() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "?" || hasModifier(e) || isTypingTarget(e.target) || modalOpen())
        return;
      e.preventDefault();
      setOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <>
      <Tooltip
        content={
          <>
            Keyboard shortcuts <Kbd>?</Kbd>
          </>
        }
        side="bottom"
      >
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          aria-label="Shortcuts"
          className="text-muted ring-line hover:bg-hover hover:text-ink flex items-center gap-1 rounded px-1.5 py-1 text-[11px] ring-1 transition-colors sm:gap-1.5 sm:px-2 sm:text-sm"
        >
          <KeyboardIcon />
          <span className="max-sm:sr-only">Shortcuts</span>
        </button>
      </Tooltip>
      {open && <ShortcutsDialog onClose={close} />}
    </>
  );
}

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="border-line bg-raised text-ink w-full max-w-sm rounded-lg border p-5 text-sm shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-ink text-base font-semibold tracking-wide">
            Keyboard shortcuts
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="text-muted ring-line hover:bg-hover hover:text-ink rounded px-2 py-1 text-xs ring-1"
          >
            Close
          </button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2.5">
          {SHORTCUTS.map((s) => (
            <div key={s.label} className="contents">
              <dt className="flex gap-1">
                {s.keys.map((k) => (
                  <Kbd key={k}>{k}</Kbd>
                ))}
              </dt>
              <dd className="text-ink">{s.label}</dd>
            </div>
          ))}
        </dl>
        <p className="text-muted mt-4 text-[11px] leading-relaxed">
          Shortcuts pause while you type in a field or while a dialog is open.
        </p>
      </div>
    </div>
  );
}

function KeyboardIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" strokeLinecap="round" />
    </svg>
  );
}
