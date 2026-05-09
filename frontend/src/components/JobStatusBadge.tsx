import type { JobStatus } from "../api/types";

const map: Record<JobStatus, { label: string; dot: string; text: string; bg: string }> = {
  pending:   { label: "待處理", dot: "bg-slate-400", text: "text-slate-700", bg: "bg-slate-100" },
  queued:    { label: "排隊中", dot: "bg-blue-400 animate-pulse", text: "text-blue-700", bg: "bg-blue-50" },
  running:   { label: "執行中", dot: "bg-blue-500 animate-pulse", text: "text-blue-700", bg: "bg-blue-50" },
  done:      { label: "完成", dot: "bg-green-500", text: "text-green-700", bg: "bg-green-50" },
  failed:    { label: "失敗", dot: "bg-red-500", text: "text-red-700", bg: "bg-red-50" },
  cancelled: { label: "已取消", dot: "bg-slate-400", text: "text-slate-600", bg: "bg-slate-100" },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const m = map[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs ${m.bg} ${m.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}
