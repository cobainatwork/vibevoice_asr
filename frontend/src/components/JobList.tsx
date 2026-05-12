import { Link } from "react-router-dom";
import { Eye, Trash2 } from "lucide-react";
import { JobStatusBadge } from "./JobStatusBadge";
import type { JobOut } from "../api/types";

interface Props {
  jobs: JobOut[];
  projectId: number;
  onDelete?: (j: JobOut) => void;
  onMarkCorrected?: (j: JobOut, value: boolean) => void;
}

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec.toFixed(1)} 秒`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m} 分 ${s} 秒`;
}

export function JobList({ jobs, projectId, onDelete, onMarkCorrected }: Props) {
  if (jobs.length === 0) {
    return <div className="bg-white border border-slate-200 rounded-lg p-12 text-center text-slate-500">尚無 Job</div>;
  }
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-4 py-2 text-left">狀態</th>
            <th className="px-4 py-2 text-left">校正</th>
            <th className="px-4 py-2 text-left">時間</th>
            <th className="px-4 py-2 text-left">檔名</th>
            <th className="px-4 py-2 text-left">時長</th>
            <th className="px-4 py-2 text-left">進度</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors duration-200">
              <td className="px-4 py-2"><JobStatusBadge status={j.status} /></td>
              <td className="px-4 py-2">
                <input
                  type="checkbox"
                  checked={j.is_corrected}
                  disabled={j.status !== "done" || !onMarkCorrected}
                  title={
                    j.status !== "done"
                      ? "需先完成轉錄"
                      : j.is_corrected
                      ? "取消標記校正完成"
                      : "勾選後可在資料集「從歷史轉錄」匯入"
                  }
                  onChange={(e) => onMarkCorrected?.(j, e.target.checked)}
                  className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
                />
              </td>
              <td className="px-4 py-2 text-slate-600 font-mono text-xs">{new Date(j.created_at).toLocaleTimeString("zh-TW")}</td>
              <td className="px-4 py-2 text-slate-900 truncate max-w-[16rem]">{j.filename}</td>
              <td className="px-4 py-2 text-slate-600">{formatDuration(j.duration_sec)}</td>
              <td className="px-4 py-2 text-slate-600">
                {j.status === "running" || j.status === "queued"
                  ? <span>{j.chunks_done}/{j.chunks_total} ({Math.round(j.progress * 100)}%)</span>
                  : j.status === "failed"
                  ? <span className="text-red-600 font-mono text-xs" title={j.error ?? ""}>{j.error?.split(":")[0] ?? "—"}</span>
                  : "—"
                }
              </td>
              <td className="px-4 py-2 text-right">
                {j.status === "done" && (
                  <Link to={`/projects/${projectId}/edit/${j.id}?mode=view`} className="inline-flex items-center gap-1 text-blue-600 cursor-pointer hover:text-blue-800 transition-colors duration-200 mr-3">
                    <Eye className="w-4 h-4" /> 檢視
                  </Link>
                )}
                {onDelete && (
                  <button type="button" aria-label="刪除" onClick={() => onDelete(j)} className="text-slate-400 cursor-pointer hover:text-red-600 transition-colors duration-200">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
