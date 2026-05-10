import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { TranscriptViewer } from "../components/TranscriptViewer";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { jobsApi } from "../api/jobs";
import { jobEditorSource } from "../lib/editorSource";
import { useProjectStore } from "../stores/projectStore";
import type { JobOut } from "../api/types";

export default function Editor() {
  const { id, itemId } = useParams();
  const [params] = useSearchParams();
  const mode = params.get("mode") === "edit" ? "edit" : "view";
  const projectId = Number(id);
  const project = useProjectStore((s) => s.getById(projectId));
  const refetchProjects = useProjectStore((s) => s.refetch);
  const projectsLoaded = useProjectStore((s) => s.loaded);
  const [job, setJob] = useState<JobOut | null>(null);

  useEffect(() => {
    if (!projectsLoaded) refetchProjects();
  }, [projectsLoaded, refetchProjects]);

  useEffect(() => {
    if (!itemId) return;
    jobsApi.get(itemId).then(setJob);
  }, [itemId]);

  // editorSource 對 jobId 穩定，避免 TranscriptEditor 重複 init。
  // 故意只看 .id — job / project ref 變不必重 init editor。
  const source = useMemo(
    () => (job && project ? jobEditorSource(job.id, project) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [job?.id, project?.id],
  );

  if (!job || !project) return <div className="p-6">載入中...</div>;
  if (job.status !== "done") {
    return (
      <div className="p-6 text-amber-700">
        Job 尚未完成（{job.status}），無法檢視 transcript
      </div>
    );
  }

  if (mode === "edit") {
    if (!source) return <div className="p-6">載入中...</div>;
    const viewLink = `/projects/${projectId}/edit/${job.id}?mode=view`;
    return <TranscriptEditor source={source} project={project} viewLink={viewLink} />;
  }

  const audioUrl = jobsApi.audioUrl(job.id);
  return <TranscriptViewer job={job} audioUrl={audioUrl} projectId={projectId} />;
}
