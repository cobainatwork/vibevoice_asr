export interface ShortcutDefinition {
  key: string; // e.g. "Space", "ArrowLeft", "/"
  meta?: boolean; // Cmd / Ctrl
  shift?: boolean;
  preventInInput?: boolean; // 預設 true：focus 在 input/textarea 時不觸發
  handler: (e: KeyboardEvent) => void;
}

export function matchShortcut(
  e: KeyboardEvent,
  s: ShortcutDefinition,
): boolean {
  const wantMeta = !!s.meta;
  const hasMeta = e.metaKey || e.ctrlKey;
  const wantShift = !!s.shift;
  if (wantMeta !== hasMeta) return false;
  if (wantShift !== e.shiftKey) return false;
  return e.key === s.key || (s.key === "Space" && e.code === "Space");
}

export function isInTextField(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    (t as HTMLElement).isContentEditable
  );
}
