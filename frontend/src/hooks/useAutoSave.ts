import { useEffect, useRef } from "react";

export function useAutoSave(
  isDirty: boolean,
  save: () => Promise<void> | void,
  options: { delayMs?: number; enabled?: boolean } = {},
) {
  const { delayMs = 3000, enabled = true } = options;
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (!isDirty) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      save();
    }, delayMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isDirty, delayMs, enabled]);

  // beforeunload 攔截
  useEffect(() => {
    if (!enabled) return;
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty, enabled]);

  return {
    flush: save,
  };
}
