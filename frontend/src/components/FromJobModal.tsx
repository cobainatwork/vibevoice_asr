import { useEffect, useState } from "react";
import { datasetsApi } from "../api/datasets";
import { jobsApi } from "../api/jobs";
import type { DatasetItem, JobOut } from "../api/types";
import { useToast } from "../hooks/useToast";

interface Props {
  open: boolean;
  projectId: number;
  onClose: () => void;
  onCreated: (item: DatasetItem) => void;
}

export function FromJobModal({ open, projectId, onClose, onCreated }: Props) {
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSelectedId(null);
    setNotes("");
    setLoading(true);
    jobsApi
      .list({ project_id: projectId, status: "done" })
      .then(setJobs)
      .catch(() => setError("載入失敗"))
      .finally(() => setLoading(false));
  }, [open, projectId]);

  if (!open) return null;

  const submit = async () => {
    if (!selectedId) {
      setError("請選擇一個 Job");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const item = await datasetsApi.fromJob(selectedId, notes || undefined);
      toast.success("已建立");
      onCreated(item);
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "建立失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded p-6 w-[600px] max-w-full max-h-[80vh] flex flex-col">
        <h2 className="text-lg font-semibold mb-4">從歷史轉錄建立 Dataset</h2>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="text-sm text-slate-500">載入中...</div>
          ) : jobs.length === 0 ? (
            <div className="text-sm text-slate-500">尚無已完成的 Job。</div>
          ) : (
            <ul className="space-y-1">
              {jobs.map((j) => (
                <li key={j.id}>
                  <label className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded cursor-pointer">
                    <input
                      type="radio"
                      name="job"
                      value={j.id}
                      checked={selectedId === j.id}
                      onChange={() => setSelectedId(j.id)}
                    />
                    <span className="text-sm">
                      <code className="text-xs">{j.id.slice(0, 8)}</code>
                      <span className="text-slate-600 ml-2">
                        {j.duration_sec?.toFixed(1) ?? "-"}s ·{" "}
                        {new Date(j.created_at).toLocaleString("zh-TW")}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
        <label className="block mt-4">
          <span className="text-sm text-slate-700">備註（選填）</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="block w-full mt-1 border rounded px-2 py-1 text-sm"
          />
        </label>
        {error && <div className="text-sm text-red-600 mt-2">{error}</div>}
        <div className="flex justify-end gap-2 mt-4">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || !selectedId}
            className="px-3 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50"
          >
            {submitting ? "建立中..." : "確定建立"}
          </button>
        </div>
      </div>
    </div>
  );
}
