import { useEffect, useRef } from "react";

/**
 * 3 秒 idle debounce 自動儲存 + beforeunload 攔截。
 *
 * save 用 ref 模式持有最新 callback，避免 caller 沒包 useCallback 時
 * 每 render 觸發 setTimeout 不斷重設。
 */
export function useAutoSave(
  isDirty: boolean,
  save: () => Promise<void> | void,
  options: { delayMs?: number; enabled?: boolean } = {},
) {
  const { delayMs = 3000, enabled = true } = options;
  const timerRef = useRef<number | null>(null);
  const saveRef = useRef(save);

  // saveRef 永遠指最新 save，不觸發 effect 重跑
  useEffect(() => {
    saveRef.current = save;
  });

  useEffect(() => {
    if (!enabled) return;
    if (!isDirty) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      saveRef.current();
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
    flush: () => saveRef.current(),
  };
}
