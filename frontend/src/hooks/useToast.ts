import { useMemo } from "react";
import { useToastStore } from "../stores/toastStore";

/**
 * Toast helper hook。
 *
 * useMemo 包 return object 確保 caller 加進 useEffect deps 不會每 render 觸發
 * （push 是 zustand action、identity stable）。
 */
export function useToast() {
  const push = useToastStore((s) => s.push);
  return useMemo(() => ({
    info: (msg: string) => push("info", msg),
    success: (msg: string) => push("success", msg),
    warning: (msg: string) => push("warning", msg),
    error: (msg: string) => push("error", msg),
  }), [push]);
}
