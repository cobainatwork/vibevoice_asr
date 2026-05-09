/**
 * Project list / management.
 *
 * See SPEC.md §8.3.1.
 * M3 milestone.
 */
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";

export default function Projects() {
  const { projects, loading, load } = useProjectStore();

  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">專案</h1>
        {/* TODO(M3): + 新專案 button → modal */}
        <button className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          + 新專案
        </button>
      </div>

      {loading ? (
        <div>載入中...</div>
      ) : projects.length === 0 ? (
        <div className="text-gray-500">尚無專案，點上方建立第一個</div>
      ) : (
        <div className="grid gap-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/projects/${p.id}/offline`}
              className="block p-4 border rounded bg-white hover:bg-gray-50"
            >
              <div className="font-semibold">{p.name}</div>
              <div className="text-sm text-gray-500 mt-1">
                {p.hotwords.length} hotwords ·{" "}
                {p.active_model_id ? `model #${p.active_model_id}` : "base model"}
              </div>
              {p.description && <div className="text-sm text-gray-600 mt-1">{p.description}</div>}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
