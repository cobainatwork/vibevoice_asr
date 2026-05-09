import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { TranscriptViewer } from "../components/TranscriptViewer";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { jobsApi } from "../api/jobs";
import type { JobOut } from "../api/types";

export default function Editor() {
  const { id, itemId } = useParams();
  const [params] = useSearchParams();
  const mode = params.get("mode") === "edit" ? "edit" : "view";
  const [job, setJob] = useState<JobOut | null>(null);

  useEffect(() => {
    if (!itemId) return;
    jobsApi.get(itemId).then(setJob);
  }, [itemId]);

  if (!job) return <div className="p-6">載入中...</div>;
  if (job.status !== "done") return <div className="p-6 text-amber-700">Job 尚未完成（{job.status}），無法檢視 transcript</div>;

  const audioUrl = jobsApi.audioUrl(job.id);
  const projectId = Number(id);

  return mode === "edit"
    ? <TranscriptEditor job={job} audioUrl={audioUrl} projectId={projectId} />
    : <TranscriptViewer job={job} audioUrl={audioUrl} projectId={projectId} />;
}
