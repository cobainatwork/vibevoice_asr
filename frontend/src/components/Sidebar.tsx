import { ChevronDown, Plus, Hash, Upload, Edit3, Database, Activity, LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";

interface SubPage {
  key: string;
  label: string;
  icon: LucideIcon;
  hidden?: boolean;
}

const SUBPAGES: SubPage[] = [
  { key: "hotwords", label: "Hotwords", icon: Hash },
  { key: "offline", label: "離線轉錄", icon: Upload },
  { key: "datasets", label: "資料集", icon: Database },
  { key: "edit", label: "校正工作台", icon: Edit3, hidden: true }, // 從 Offline 進入，不直接顯示
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const { projects, loaded, refetch } = useProjectStore();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!loaded) refetch();
  }, [loaded, refetch]);

  const projectIdRaw = params.id ?? location.pathname.match(/^\/projects\/(\d+)/)?.[1];
  const projectId = projectIdRaw ? Number(projectIdRaw) : null;
  const currentProject = projectId ? projects.find((p) => p.id === projectId) : null;

  const currentSub = location.pathname.match(/^\/projects\/\d+\/(\w+)/)?.[1];
  const isSystem = location.pathname.startsWith("/system");

  return (
    <aside className="w-60 bg-slate-900 text-slate-200 flex flex-col h-screen sticky top-0 shrink-0">
      {/* brand */}
      <div className="px-4 py-4 border-b border-slate-800">
        <Link to="/" className="text-base font-semibold text-white tracking-wide cursor-pointer hover:text-blue-300 transition-colors duration-200">
          VibeVoice ASR
        </Link>
      </div>

      {/* project switcher */}
      <div className="px-2 py-3 border-b border-slate-800 relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center gap-2 px-2 py-2 rounded text-left cursor-pointer hover:bg-slate-800 transition-colors duration-200"
        >
          <span className="flex-1 truncate text-sm">
            {currentProject ? currentProject.name : "選擇專案"}
          </span>
          <ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <div className="absolute left-2 right-2 top-full mt-1 bg-slate-800 border border-slate-700 rounded shadow-lg z-10 max-h-72 overflow-auto">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setOpen(false);
                  // 切 project 維持子頁
                  const sub = currentSub && SUBPAGES.some((s) => s.key === currentSub)
                    ? currentSub
                    : "hotwords";
                  navigate(`/projects/${p.id}/${sub}`);
                }}
                className={`block w-full text-left px-3 py-2 text-sm cursor-pointer hover:bg-slate-700 transition-colors duration-200 ${currentProject?.id === p.id ? "bg-slate-700 text-white" : ""}`}
              >
                {p.name}
              </button>
            ))}
            <Link
              to="/"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-blue-400 cursor-pointer hover:bg-slate-700 transition-colors duration-200 border-t border-slate-700"
            >
              <Plus className="w-4 h-4" /> 管理 / 新增專案
            </Link>
          </div>
        )}
      </div>

      {/* 本專案子頁 */}
      <nav className="flex-1 px-2 py-2 overflow-auto">
        <div className="text-xs uppercase text-slate-500 px-2 py-1 tracking-wider">本專案</div>
        {projectId && SUBPAGES.filter((s) => !s.hidden).map((s) => {
          const active = currentSub === s.key;
          return (
            <Link
              key={s.key}
              to={`/projects/${projectId}/${s.key}`}
              className={`flex items-center gap-2 px-2 py-2 my-0.5 rounded text-sm cursor-pointer transition-colors duration-200 ${
                active ? "bg-blue-500/20 text-white border-l-2 border-blue-400 pl-1.5" : "hover:bg-slate-800"
              }`}
            >
              <s.icon className="w-4 h-4" /> {s.label}
            </Link>
          );
        })}
        {!projectId && (
          <p className="px-2 py-2 text-xs text-slate-500">未選擇專案</p>
        )}
      </nav>

      {/* System 底部 */}
      <div className="px-2 py-3 border-t border-slate-800">
        <div className="text-xs uppercase text-slate-500 px-2 py-1 tracking-wider">系統</div>
        <Link
          to="/system"
          className={`flex items-center gap-2 px-2 py-2 rounded text-sm cursor-pointer transition-colors duration-200 ${
            isSystem ? "bg-blue-500/20 text-white border-l-2 border-blue-400 pl-1.5" : "hover:bg-slate-800"
          }`}
        >
          <Activity className="w-4 h-4" /> 服務狀態
        </Link>
      </div>
    </aside>
  );
}
