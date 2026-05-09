import { useEffect } from "react";
import {
  isInTextField,
  matchShortcut,
  type ShortcutDefinition,
} from "../lib/keyboard";

export function useKeyboardShortcuts(
  shortcuts: ShortcutDefinition[],
  enabled: boolean = true,
) {
  useEffect(() => {
    if (!enabled) return;
    const listener = (e: KeyboardEvent) => {
      for (const s of shortcuts) {
        const inText = isInTextField(e);
        if (s.preventInInput !== false && inText) continue;
        if (matchShortcut(e, s)) {
          e.preventDefault();
          s.handler(e);
          return;
        }
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [shortcuts, enabled]);
}
