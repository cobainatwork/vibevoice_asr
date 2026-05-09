import { CheckCircle2, Info, AlertTriangle, XCircle, X } from "lucide-react";
import { useToastStore, type Toast as ToastT } from "../stores/toastStore";

const styles: Record<ToastT["level"], { bg: string; icon: JSX.Element; text: string }> = {
  info: { bg: "bg-blue-50 border-blue-200", text: "text-blue-900",
          icon: <Info className="w-5 h-5 text-blue-500" /> },
  success: { bg: "bg-green-50 border-green-200", text: "text-green-900",
             icon: <CheckCircle2 className="w-5 h-5 text-green-500" /> },
  warning: { bg: "bg-amber-50 border-amber-200", text: "text-amber-900",
             icon: <AlertTriangle className="w-5 h-5 text-amber-500" /> },
  error: { bg: "bg-red-50 border-red-200", text: "text-red-900",
           icon: <XCircle className="w-5 h-5 text-red-500" /> },
};

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-md">
      {toasts.map((t) => {
        const s = styles[t.level];
        return (
          <div
            key={t.id}
            role="status"
            className={`flex items-start gap-3 ${s.bg} ${s.text} border rounded-md px-4 py-3 shadow-md`}
          >
            {s.icon}
            <span className="flex-1 text-sm leading-relaxed whitespace-pre-wrap">
              {t.message}
            </span>
            <button
              type="button"
              aria-label="關閉通知"
              onClick={() => dismiss(t.id)}
              className="cursor-pointer text-current opacity-60 hover:opacity-100 transition-colors duration-200"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
