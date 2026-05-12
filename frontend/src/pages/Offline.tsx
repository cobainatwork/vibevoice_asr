import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { UploadDropzone } from "../components/UploadDropzone";
import { JobList } from "../components/JobList";
import { jobsApi } from "../api/jobs";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";
import type { JobOut } from "../api/types";

const ACTIVE_STATUSES = new Set(["pending", "queued", "running"]);

export default function Offline() {
  const { id } = useParams();
  const projectId = Number(id);
  const project = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  const refetchProjects = useProjectStore((s) => s.refetch);

  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [loading, setLoading] = useState(false);
  const toast = useToast();
  const pollRef = useRef<number | null>(null);

  useEffect(() => { if (!project) refetchProjects(); }, [project, refetchProjects]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const list = await jobsApi.list({ project_id: projectId, limit: 50 });
      setJobs(list);
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // active job 時 polling 每 2 秒
  useEffect(() => {
    const hasActive = jobs.some((j) => ACTIVE_STATUSES.has(j.status));
    if (!hasActive) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = window.setInterval(fetchJobs, 2000);
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [jobs, fetchJobs]);

  const onUpload = async (file: File) => {
    try {
      await jobsApi.upload(file, projectId);
      toast.success("Job 已建立，等待處理");
      await fetchJobs();
    } catch {
      // client.ts 已 toast
    }
  };

  const onYoutubeUrl = async (url: string) => {
    try {
      await jobsApi.transcribeFromYoutube(url, projectId);
      toast.success("已啟動 YouTube 下載，完成後自動進入 ASR 排程");
      await fetchJobs();
    } catch {
      // client.ts 已 toast
    }
  };

  const onDelete = async (j: JobOut) => {
    if (!confirm(`確定刪除 Job ${j.filename}？此動作會一併刪除原始音檔。`)) return;
    try {
      await jobsApi.remove(j.id);
      toast.success("已刪除");
      await fetchJobs();
    } catch { /* toast in client */ }
  };

  if (!project) return <div className="p-6">載入中...</div>;

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">離線轉錄</h1>
          <p className="text-sm text-slate-600 mt-1">{project.name}</p>
        </div>
        <button type="button" onClick={fetchJobs} disabled={loading} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50 transition-colors duration-200">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> 重新整理
        </button>
      </header>

      <UploadDropzone onFile={onUpload} onYoutubeUrl={onYoutubeUrl} />

      <h2 className="text-sm font-semibold text-slate-700 mt-6 mb-3">最近 Job（{jobs.length}）</h2>
      <JobList jobs={jobs} projectId={projectId} onDelete={onDelete} />
    </div>
  );
}
