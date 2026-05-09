/**
 * Training runs list + start new run.
 *
 * See SPEC.md §8.3.7.
 * M4 milestone.
 */
import { useParams } from "react-router-dom";

export default function Training() {
  const { id } = useParams();
  // TODO(M4):
  // - list TrainingRuns
  // - 啟動新訓練 modal (dataset selection, hyperparams form)
  // - link to TrainingDetail by run_id
  // - profile-aware warning (will pause vLLM?)
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-2xl font-bold">訓練 (專案 #{id})</h1>
      <div className="text-sm text-gray-500">TODO: M4 milestone</div>
    </div>
  );
}
