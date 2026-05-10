/**
 * Dataset management.
 *
 * See SPEC.md §8.3.5.
 * M3.5 milestone.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download, Upload as UploadIcon, FileText, Trash2, Edit3, History } from "lucide-react";
import { datasetsApi } from "../api/datasets";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";
import { DatasetImportModal } from "../components/DatasetImportModal";
import { FromJobModal } from "../components/FromJobModal";
import type { DatasetItem, ExportFormat, TemplateFormat } from "../api/types";

const TEMPLATE_FORMATS: TemplateFormat[] = ["json", "xlsx", "srt", "txt"];
const EXPORT_FORMATS: ExportFormat[] = ["json", "srt", "xlsx"];

export default function Datasets() {
  const { id } = useParams();
  const projectId = Number(id);
  const project = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  const refetch = useProjectStore((s) => s.refetch);
  const [items, setItems] = useState<DatasetItem[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [fromJobOpen, setFromJobOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await datasetsApi.list(projectId));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!project) refetch();
  }, [project, refetch]);

  useEffect(() => {
    if (project) reload();
    // 故意只看 project.id — store list 變化導致 project ref 變不必重 fetch dataset。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, reload]);

  const onDelete = async (item: DatasetItem) => {
    if (!window.confirm(`確定刪除 dataset #${item.id}?`)) return;
    await datasetsApi.delete(item.id);
    toast.success("已刪除");
    reload();
  };

  const formatSource = (item: DatasetItem) => {
    if (item.source === "from_transcription") {
      return `來自 Job ${item.source_job_id?.slice(0, 8) ?? "?"}`;
    }
    if (item.source.startsWith("imported_")) {
      return `匯入 (${item.source.replace("imported_", "").toUpperCase()})`;
    }
    return item.source;
  };

  if (!project) return <div className="p-6">載入中...</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">資料集</h1>
          <p className="text-sm text-slate-600 mt-1">{project.name}</p>
        </div>
        <div className="flex gap-2">
          <details className="relative">
            <summary className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 list-none">
              <FileText className="w-4 h-4" /> 範本下載
            </summary>
            <div className="absolute right-0 mt-1 bg-white border border-slate-200 rounded shadow-md z-10 min-w-[160px]">
              {TEMPLATE_FORMATS.map((f) => (
                <a
                  key={f}
                  href={datasetsApi.templateUrl(f)}
                  download
                  className="block px-3 py-2 text-sm hover:bg-slate-50 cursor-pointer"
                >
                  {f.toUpperCase()}
                </a>
              ))}
            </div>
          </details>
          <button
            type="button"
            onClick={() => setFromJobOpen(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50"
          >
            <History className="w-4 h-4" /> 從歷史轉錄
          </button>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600"
          >
            <UploadIcon className="w-4 h-4" /> 匯入
          </button>
        </div>
      </header>

      {loading ? (
        <div className="text-sm text-slate-500">載入中...</div>
      ) : items.length === 0 ? (
        <div className="text-sm text-slate-500 p-8 text-center border border-dashed rounded">
          尚無資料集。點右上「匯入」開始建立。
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-slate-600 border-b">
            <tr>
              <th className="py-2 px-2">ID</th>
              <th className="py-2 px-2">來源</th>
              <th className="py-2 px-2">段數</th>
              <th className="py-2 px-2">時長</th>
              <th className="py-2 px-2">建立時間</th>
              <th className="py-2 px-2">動作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b hover:bg-slate-50">
                <td className="py-2 px-2">#{item.id}</td>
                <td className="py-2 px-2">{formatSource(item)}</td>
                <td className="py-2 px-2">{item.label.segments.length}</td>
                <td className="py-2 px-2">{item.duration_sec.toFixed(1)} s</td>
                <td className="py-2 px-2">
                  {new Date(item.created_at).toLocaleString("zh-TW")}
                </td>
                <td className="py-2 px-2 flex gap-2">
                  <Link
                    to={`/projects/${projectId}/datasets/${item.id}/editor`}
                    className="flex items-center gap-1 text-blue-600 hover:text-blue-800 cursor-pointer"
                  >
                    <Edit3 className="w-4 h-4" /> 編輯
                  </Link>
                  <details className="relative">
                    <summary className="flex items-center gap-1 text-slate-700 hover:text-slate-900 cursor-pointer list-none">
                      <Download className="w-4 h-4" /> 匯出
                    </summary>
                    <div className="absolute right-0 mt-1 bg-white border border-slate-200 rounded shadow-md z-10 min-w-[120px]">
                      {EXPORT_FORMATS.map((f) => (
                        <a
                          key={f}
                          href={datasetsApi.exportUrl(item.id, f)}
                          download
                          className="block px-3 py-2 text-sm hover:bg-slate-50 cursor-pointer"
                        >
                          {f.toUpperCase()}
                        </a>
                      ))}
                    </div>
                  </details>
                  <button
                    type="button"
                    onClick={() => onDelete(item)}
                    className="flex items-center gap-1 text-red-600 hover:text-red-800 cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" /> 刪除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <DatasetImportModal
        open={importOpen}
        projectId={projectId}
        onClose={() => setImportOpen(false)}
        onImported={() => reload()}
      />
      <FromJobModal
        open={fromJobOpen}
        projectId={projectId}
        onClose={() => setFromJobOpen(false)}
        onCreated={() => reload()}
      />
    </div>
  );
}
