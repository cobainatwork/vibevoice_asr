/**
 * Sidebar navigation. M3 milestone.
 */
import { Link, useLocation, useParams } from "react-router-dom";
import {
  FolderIcon,
  TagIcon,
  UploadIcon,
  DatabaseIcon,
  GraduationCapIcon,
  GitBranchIcon,
  KeyIcon,
  WebhookIcon,
  ListIcon,
  ServerIcon,
} from "lucide-react";

interface Item {
  to: string;
  label: string;
  Icon: any;
}

export function Sidebar() {
  const { pathname } = useLocation();
  const { id } = useParams();
  const projectId = id;

  const projectItems: Item[] = projectId ? [
    { to: `/projects/${projectId}/hotwords`, label: "Hotwords", Icon: TagIcon },
    { to: `/projects/${projectId}/offline`, label: "離線轉錄", Icon: UploadIcon },
    { to: `/projects/${projectId}/datasets`, label: "資料集", Icon: DatabaseIcon },
    { to: `/projects/${projectId}/training`, label: "訓練", Icon: GraduationCapIcon },
    { to: `/projects/${projectId}/models`, label: "模型管理", Icon: GitBranchIcon },
    { to: `/projects/${projectId}/api_keys`, label: "API Keys", Icon: KeyIcon },
    { to: `/projects/${projectId}/webhook`, label: "Webhook", Icon: WebhookIcon },
    { to: `/projects/${projectId}/integration_calls`, label: "呼叫紀錄", Icon: ListIcon },
  ] : [];

  return (
    <aside className="w-56 bg-white border-r border-gray-200 p-4 space-y-1">
      <Link to="/" className="block py-2 px-3 font-bold text-lg">
        VibeVoice ASR
      </Link>

      <Link
        to="/"
        className={`flex items-center gap-2 py-2 px-3 rounded ${
          pathname === "/" ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
        }`}
      >
        <FolderIcon size={16} /> 專案
      </Link>

      {projectItems.length > 0 && (
        <div className="pt-2 mt-2 border-t border-gray-100">
          <div className="px-3 py-1 text-xs text-gray-400">當前專案</div>
          {projectItems.map(({ to, label, Icon }) => (
            <Link
              key={to}
              to={to}
              className={`flex items-center gap-2 py-2 px-3 rounded text-sm ${
                pathname === to ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
              }`}
            >
              <Icon size={16} /> {label}
            </Link>
          ))}
        </div>
      )}

      <div className="pt-2 mt-2 border-t border-gray-100">
        <Link
          to="/system"
          className={`flex items-center gap-2 py-2 px-3 rounded text-sm ${
            pathname === "/system" ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
          }`}
        >
          <ServerIcon size={16} /> 系統狀態
        </Link>
      </div>
    </aside>
  );
}
