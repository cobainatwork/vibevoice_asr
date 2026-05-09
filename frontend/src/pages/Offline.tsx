/**
 * Offline transcribe page — upload + job list.
 *
 * See SPEC.md §8.3.3.
 * M3 milestone.
 */
import { useParams } from "react-router-dom";
import { JobList } from "../components/JobList";

export default function Offline() {
  const { id } = useParams();
  // TODO(M3):
  // - upload component (drag & drop)
  // - polling jobs list every 3 seconds
  // - on view → modal with TranscriptViewer
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-2xl font-bold">離線轉錄 (專案 #{id})</h1>

      <div className="border-2 border-dashed border-gray-300 p-8 rounded text-center">
        <div className="text-gray-500 mb-2">拖放或點擊上傳音檔</div>
        <div className="text-xs text-gray-400">支援：mp3 / wav / m4a / flac / mp4 / mov / webm</div>
        {/* TODO(M3): file input + upload */}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-2">最近任務</h2>
        <JobList jobs={[]} />
      </div>
    </div>
  );
}
