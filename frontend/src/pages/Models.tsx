/**
 * Model version management — switch active model, delete versions.
 *
 * See SPEC.md §8.3.8.
 * M4 milestone.
 */
import { useParams } from "react-router-dom";

export default function Models() {
  const { id } = useParams();
  // TODO(M4):
  // - list ModelVersions
  // - 當前使用 highlight
  // - 切換 button → confirm dialog (will restart vLLM ~60s)
  // - 刪除 button (cannot delete active)
  // - link to TrainingRun for each merged model
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-2xl font-bold">模型管理 (專案 #{id})</h1>
      <div className="text-sm text-gray-500">TODO: M4 milestone</div>
    </div>
  );
}
