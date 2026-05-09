import { create } from "zustand";

export type ToastLevel = "info" | "success" | "warning" | "error";

export interface Toast {
  id: number;
  level: ToastLevel;
  message: string;
  timeoutMs: number;
}

interface ToastState {
  toasts: Toast[];
  push: (level: ToastLevel, message: string, timeoutMs?: number) => void;
  dismiss: (id: number) => void;
}

const defaultTimeouts: Record<ToastLevel, number> = {
  info: 5000,
  success: 3000,
  warning: 5000,
  error: 8000,
};

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (level, message, timeoutMs) => {
    const id = nextId++;
    const t: Toast = {
      id,
      level,
      message,
      timeoutMs: timeoutMs ?? defaultTimeouts[level],
    };
    set((s) => ({ toasts: [...s.toasts, t].slice(-3) }));
    if (t.timeoutMs > 0) {
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
      }, t.timeoutMs);
    }
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
