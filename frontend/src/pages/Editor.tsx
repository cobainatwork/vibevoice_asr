/**
 * Correction workbench — central UX of the platform.
 *
 * See SPEC.md §8.3.6.
 * M3 milestone.
 */
import { useParams } from "react-router-dom";
import { TranscriptEditor } from "../components/TranscriptEditor";

export default function Editor() {
  const { id, itemId } = useParams();
  // TODO(M3):
  // 1. Load DatasetItem via datasetsApi.get(itemId)
  // 2. Convert label.segments (0-indexed speaker) → internal Segment (1-indexed)
  // 3. Pass audio URL = datasetsApi.audioUrl(itemId)
  // 4. On save: convert back to TrainingLabel and PUT
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-xl font-bold">校正工作台</h1>
      <div className="text-sm text-gray-500">
        Project #{id} · Dataset Item #{itemId}
      </div>
      <TranscriptEditor
        audioUrl=""
        segments={[]}
        onChange={() => { /* TODO(M3) */ }}
      />
    </div>
  );
}
