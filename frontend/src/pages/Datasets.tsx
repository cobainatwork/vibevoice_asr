/**
 * Dataset management.
 *
 * See SPEC.md §8.3.5.
 * M3.5 milestone.
 */
import { useParams } from "react-router-dom";

export default function Datasets() {
  const { id } = useParams();
  // TODO(M3.5):
  // - list dataset items
  // - + 上傳音檔+標註 modal (multi-format import)
  // - + 從歷史轉錄匯入 (select Job → datasets/from_job)
  // - bulk select → 加入訓練 (jumps to Training new run with pre-selected items)
  // - 範本下載 dropdown (xlsx/csv/srt/vtt/txt/json)
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-2xl font-bold">資料集 (專案 #{id})</h1>
      <div className="text-sm text-gray-500">TODO: M3.5 milestone</div>
    </div>
  );
}
