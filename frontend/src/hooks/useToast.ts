import { useToastStore } from "../stores/toastStore";

export function useToast() {
  const push = useToastStore((s) => s.push);
  return {
    info: (msg: string) => push("info", msg),
    success: (msg: string) => push("success", msg),
    warning: (msg: string) => push("warning", msg),
    error: (msg: string) => push("error", msg),
  };
}
