/**
 * Webhook configuration.
 *
 * See SPEC.md §8.3.x and §17.6.
 * M6 milestone.
 */
import { useParams } from "react-router-dom";

export default function Webhook() {
  const { id } = useParams();
  // TODO(M6):
  // - URL input + 儲存
  // - secret display (prefix only) + rotate
  // - 立即測試 button → POST /webhook/test → show response
  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-2xl font-bold">Webhook 設定 (專案 #{id})</h1>
      <p className="text-sm text-gray-600">
        QC 系統會在 Job 完成後收到 callback。HMAC-SHA256 簽章保護。
      </p>
      <div className="text-sm text-gray-500">TODO: M6 milestone</div>
    </div>
  );
}
