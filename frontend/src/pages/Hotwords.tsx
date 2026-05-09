/**
 * Hotwords editor for current project.
 *
 * See SPEC.md §8.3.2.
 * M3 milestone.
 */
import { useParams } from "react-router-dom";
import { HotwordsChips } from "../components/HotwordsChips";

export default function Hotwords() {
  const { id } = useParams();
  // TODO(M3): load hotwords from /api/admin/projects/{id}/hotwords
  // TODO(M3): debounced auto-save on change
  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-2xl font-bold">Hotwords (專案 #{id})</h1>
      <p className="text-sm text-gray-600">
        新增專案的領域詞彙，幫模型認得專有名詞。Enter 或逗號送出。
      </p>
      <HotwordsChips
        value={[]}
        onChange={() => { /* TODO(M3) */ }}
      />
    </div>
  );
}
