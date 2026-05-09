import { useEffect, useMemo } from "react";
import { useParams } from "react-router-dom";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { datasetEditorSource } from "../lib/editorSource";
import { useProjectStore } from "../stores/projectStore";

export default function DatasetEditor() {
  const { id, itemId } = useParams();
  const projectId = Number(id);
  const project = useProjectStore((s) => s.getById(projectId));
  const refetchProjects = useProjectStore((s) => s.refetch);
  const projectsLoaded = useProjectStore((s) => s.loaded);

  useEffect(() => {
    if (!projectsLoaded) refetchProjects();
  }, [projectsLoaded, refetchProjects]);

  // editorSource 對 itemId 穩定，避免 TranscriptEditor 重複 init。
  const source = useMemo(
    () => (itemId && project ? datasetEditorSource(Number(itemId), project) : null),
    [itemId, project?.id],
  );

  if (!project || !itemId || !source) return <div className="p-6">載入中...</div>;
  return <TranscriptEditor source={source} project={project} />;
}
