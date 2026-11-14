// lib/keyboard.ts
// Shared rules for global keyboard shortcuts.

/** Keys the app binds globally, shown in the shortcuts guide. */
export const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ["Space"], label: "Play / pause the timeline" },
  { keys: ["←"], label: "Previous burst" },
  { keys: ["→"], label: "Next burst" },
  { keys: ["?"], label: "Show keyboard shortcuts" },
  { keys: ["Esc"], label: "Close dialogs" },
];

/** Typing in a field: never steal keys. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (target instanceof HTMLElement && target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)
    return true;
  if (target instanceof HTMLInputElement) {
    // Range sliders and checkboxes don't take text; everything else does.
    return !["range", "checkbox", "radio", "button"].includes(target.type);
  }
  return false;
}

/**
 * Space already activates focused buttons, links, checkboxes and the 2D
 * markers (SVG role="button"); let it do that instead of toggling playback.
 */
export function spaceActivatesTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return !!target.closest(
    'button, a[href], summary, label, [role="button"], [role="checkbox"], input[type="checkbox"], input[type="radio"]',
  );
}

/** A modal dialog is open: shortcuts other than Esc are suspended. */
export function modalOpen(): boolean {
  return !!document.querySelector('[role="dialog"][aria-modal="true"]');
}

export function hasModifier(e: KeyboardEvent): boolean {
  return e.altKey || e.ctrlKey || e.metaKey;
}
