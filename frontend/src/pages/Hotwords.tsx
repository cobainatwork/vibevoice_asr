import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, Upload as UploadIcon, Save } from "lucide-react";
import { HotwordsChips } from "../components/HotwordsChips";
import { HotwordsImportModal } from "../components/HotwordsImportModal";
import { projectsApi } from "../api/projects";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";

export default function Hotwords() {
  const { id } = useParams();
  const projectId = Number(id);
  const project = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  const refetch = useProjectStore((s) => s.refetch);

  const [words, setWords] = useState<string[]>([]);
  const [original, setOriginal] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!project) refetch();
  }, [project, refetch]);

  useEffect(() => {
    if (project) {
      setWords(project.hotwords ?? []);
      setOriginal(project.hotwords ?? []);
    }
    // 故意只看 project.id / updated_at — 否則 store 內部更新時 project ref 變動
    // 會覆蓋使用者編輯到的 words。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, project?.updated_at]);

  const dirty = JSON.stringify(words) !== JSON.stringify(original);

  const save = async () => {
    setSaving(true);
    try {
      await projectsApi.setHotwords(projectId, words);
      setOriginal(words);
      toast.success("Hotwords 已儲存");
      await refetch();
    } finally {
      setSaving(false);
    }
  };

  const exportTxt = async () => {
    const blob = await projectsApi.exportHotwords(projectId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const safe = (project?.name ?? "project").replace(/[^\w-]/g, "-");
    a.download = `hotwords-${safe}-${today}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("已下載");
  };

  const onImport = async (file: File, mode: "append" | "replace") => {
    const result = await projectsApi.importHotwords(projectId, file, mode);
    setWords(result.hotwords);
    setOriginal(result.hotwords);
    await refetch();
    toast.success(
      `匯入完成：新增 ${result.added}、覆蓋 ${result.replaced}、略過 ${result.skipped_duplicates}`
    );
  };

  if (!project) return <div className="p-6">載入中...</div>;

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Hotwords</h1>
          <p className="text-sm text-slate-600 mt-1">{project.name}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={exportTxt} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200">
            <Download className="w-4 h-4" /> 匯出
          </button>
          <button type="button" onClick={() => setImportOpen(true)} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200">
            <UploadIcon className="w-4 h-4" /> 匯入
          </button>
          <button type="button" onClick={save} disabled={!dirty || saving} className="flex items-center gap-2 px-3 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200">
            <Save className="w-4 h-4" /> {saving ? "儲存中..." : "儲存"}
          </button>
        </div>
      </header>

      <HotwordsChips value={words} onChange={setWords} />

      <p className="text-xs text-slate-500 mt-2">
        共 {words.length} 個詞 · 上次更新 {new Date(project.updated_at).toLocaleString("zh-TW")}
        {dirty && <span className="ml-2 text-amber-600">· 有未儲存變更</span>}
      </p>

      <HotwordsImportModal open={importOpen} onClose={() => setImportOpen(false)} onImport={onImport} />
    </div>
  );
}
