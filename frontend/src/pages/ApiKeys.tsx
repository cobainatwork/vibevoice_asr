/**
 * API Keys management — for QC integration.
 *
 * See SPEC.md §8.3.x and §17.2.
 * M6 milestone.
 *
 * 🌟 Plain key only displayed once on create/rotate.
 */
import { useParams } from "react-router-dom";

export default function ApiKeys() {
  const { id } = useParams();
  // TODO(M6):
  // - list api keys (prefix masked)
  // - + 新增 modal → on success show ApiKeyDisplay (one-time plain key)
  // - rotate / revoke per row
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-2xl font-bold">API Keys (專案 #{id})</h1>
      <p className="text-sm text-gray-600">
        給外部系統（例如 QC 應用）呼叫 /api/v1/* 用的金鑰。
      </p>
      <div className="text-sm text-gray-500">TODO: M6 milestone</div>
    </div>
  );
}
