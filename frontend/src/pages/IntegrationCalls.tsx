/**
 * Audit log of v1 API calls.
 *
 * See SPEC.md §8.3.x.
 * M6 milestone.
 */
import { useParams } from "react-router-dom";

export default function IntegrationCalls() {
  const { id } = useParams();
  // TODO(M6):
  // - GET /api/admin/integration_calls?project_id=X
  // - table view with filters (time range, status code class)
  // - link to job_id if available
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-2xl font-bold">整合呼叫紀錄 (專案 #{id})</h1>
      <div className="text-sm text-gray-500">TODO: M6 milestone</div>
    </div>
  );
}
