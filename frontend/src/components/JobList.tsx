/**
 * Renders a list of Jobs with status, progress, and actions.
 * M3 milestone.
 */
import type { Job } from "../api/types";
import { formatDuration } from "../lib/format";

interface Props {
  jobs: Job[];
  onView?: (job: Job) => void;
  onConvertToDataset?: (job: Job) => void;
  onCancel?: (job: Job) => void;
  onDelete?: (job: Job) => void;
}

const SOURCE_BADGE: Record<string, string> = {
  admin_upload: "👤 ADMIN",
  v1_api_async: "🌐 V1-WS",
  v1_api_sync: "🌐 V1-SYNC",
  v1_api_ws: "🌐 V1-WS",
};

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  queued: "bg-blue-100 text-blue-700",
  running: "bg-yellow-100 text-yellow-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};

export function JobList({ jobs, onView, onConvertToDataset, onCancel, onDelete }: Props) {
  if (jobs.length === 0) {
    return <div className="text-gray-500 text-sm">尚無任務</div>;
  }

  return (
    <div className="border rounded bg-white divide-y">
      {jobs.map((job) => (
        <div key={job.id} className="flex items-center gap-3 p-3 text-sm">
          <span className="text-xs text-gray-400 w-20 shrink-0">
            {SOURCE_BADGE[job.source]}
          </span>
          <span className="flex-1 truncate">{job.filename}</span>
          <span className="w-16 text-right text-gray-500 tabular-nums">
            {formatDuration(job.duration_sec)}
          </span>
          <span
            className={`text-xs px-2 py-0.5 rounded ${STATUS_COLOR[job.status]}`}
          >
            {job.status}
          </span>
          {job.status === "running" && (
            <span className="w-12 text-xs tabular-nums">
              {Math.round(job.progress * 100)}%
            </span>
          )}
          <div className="flex gap-2">
            {onView && job.status === "done" && (
              <button onClick={() => onView(job)} className="text-blue-600 hover:underline">
                檢視
              </button>
            )}
            {onConvertToDataset && job.status === "done" && (
              <button onClick={() => onConvertToDataset(job)} className="text-blue-600 hover:underline">
                轉訓練
              </button>
            )}
            {onCancel && (job.status === "running" || job.status === "queued") && (
              <button onClick={() => onCancel(job)} className="text-orange-600 hover:underline">
                取消
              </button>
            )}
            {onDelete && (
              <button onClick={() => onDelete(job)} className="text-red-600 hover:underline">
                刪除
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
