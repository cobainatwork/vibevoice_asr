/**
 * Training run detail with SSE log streaming + loss curve.
 *
 * See SPEC.md §8.3.7.
 * M4 milestone.
 */
import { useParams } from "react-router-dom";

export default function TrainingDetail() {
  const { id, runId } = useParams();
  // TODO(M4):
  // - poll TrainingRun status
  // - SSE subscribe to /api/admin/training/{runId}/log → console-style log view
  // - parse loss from log lines → recharts line chart
  // - cancel button
  // - on done: link to Models page
  return (
    <div className="space-y-4 max-w-5xl">
      <h1 className="text-xl font-bold">Training Run #{runId}</h1>
      <div className="text-sm text-gray-500">Project #{id}</div>
      <div className="text-sm text-gray-500">TODO: M4 milestone</div>
    </div>
  );
}
