import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Edit2, Trash2, MoreVertical } from "lucide-react";
import { ProjectFormModal } from "../components/ProjectFormModal";
import { projectsApi } from "../api/projects";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";
import type { ProjectOut } from "../api/types";

export default function Projects() {
  const { projects, loaded, refetch } = useProjectStore();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectOut | undefined>();
  const toast = useToast();

  useEffect(() => {
    if (!loaded) refetch();
  }, [loaded, refetch]);

  const onCreate = async (data: { name: string; description?: string; webhook_url?: string; hotwords: string[]; denoise_enabled?: boolean }) => {
    await projectsApi.create(data);
    toast.success(`已建立專案「${data.name}」`);
    await refetch();
  };

  const onEdit = async (data: { name: string; description?: string; webhook_url?: string; hotwords: string[]; denoise_enabled?: boolean }) => {
    if (!editing) return;
    await projectsApi.update(editing.id, data);
    toast.success(`已更新「${data.name}」`);
    setEditing(undefined);
    await refetch();
  };

  const onDelete = async (p: ProjectOut) => {
    if (!confirm(`確定刪除專案「${p.name}」？此動作無法復原。`)) return;
    try {
      await projectsApi.remove(p.id);
      toast.success(`已刪除「${p.name}」`);
      await refetch();
    } catch {
      // client.ts 已 toast
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-slate-900">專案列表</h1>
        <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 transition-colors duration-200">
          <Plus className="w-4 h-4" /> 新增專案
        </button>
      </header>

      {projects.length === 0 && loaded && (
        <div className="bg-white border border-slate-200 rounded-lg p-12 text-center">
          <p className="text-slate-600 mb-4">尚未建立任何專案</p>
          <button type="button" onClick={() => setOpen(true)} className="px-4 py-2 bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 transition-colors duration-200">建立第一個專案</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map((p) => (
          <div key={p.id} className="bg-white border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow duration-200 group relative">
            <Link to={`/projects/${p.id}/hotwords`} className="block cursor-pointer">
              <h3 className="font-semibold text-slate-900 mb-1 truncate">{p.name}</h3>
              <p className="text-sm text-slate-600 mb-3 line-clamp-2 min-h-[2.5em]">{p.description || "—"}</p>
              <div className="text-xs text-slate-500 flex gap-3">
                <span>{p.hotwords.length} hotwords</span>
                <span>更新 {new Date(p.updated_at).toLocaleDateString("zh-TW")}</span>
              </div>
            </Link>
            <ProjectMenu onEdit={() => setEditing(p)} onDelete={() => onDelete(p)} />
          </div>
        ))}
      </div>

      <ProjectFormModal
        open={open || !!editing}
        onClose={() => { setOpen(false); setEditing(undefined); }}
        initial={editing}
        onSubmit={editing ? onEdit : onCreate}
      />
    </div>
  );
}

function ProjectMenu({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="absolute top-3 right-3" onClick={(e) => e.preventDefault()}>
      <button type="button" aria-label="專案動作" onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }} className="p-1 rounded cursor-pointer text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors duration-200">
        <MoreVertical className="w-4 h-4" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg z-10 min-w-[7rem]" onMouseLeave={() => setOpen(false)}>
          <button type="button" onClick={() => { setOpen(false); onEdit(); }} className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-700 cursor-pointer hover:bg-slate-50 transition-colors duration-200"><Edit2 className="w-4 h-4" /> 編輯</button>
          <button type="button" onClick={() => { setOpen(false); onDelete(); }} className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 cursor-pointer hover:bg-red-50 transition-colors duration-200"><Trash2 className="w-4 h-4" /> 刪除</button>
        </div>
      )}
    </div>
  );
}
