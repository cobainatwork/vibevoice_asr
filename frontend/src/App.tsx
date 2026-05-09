import { Navigate, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { useToast } from "./hooks/useToast";

import Projects from "./pages/Projects";
import Hotwords from "./pages/Hotwords";
import Offline from "./pages/Offline";
import Editor from "./pages/Editor";
import System from "./pages/System";

function NotImplemented({ pageName }: { pageName: string }) {
  const toast = useToast();
  useEffect(() => {
    toast.info(`「${pageName}」頁面尚未開放（M3.5+ 才實作）`);
  }, [pageName]);
  return <Navigate to="/" replace />;
}

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Projects />} />
          <Route path="/projects/:id/hotwords" element={<Hotwords />} />
          <Route path="/projects/:id/offline" element={<Offline />} />
          <Route path="/projects/:id/edit/:itemId" element={<Editor />} />
          <Route path="/system" element={<System />} />

          {/* M3 不實作的頁面：toast 提示後 redirect */}
          <Route path="/projects/:id/datasets" element={<NotImplemented pageName="資料集" />} />
          <Route path="/projects/:id/training" element={<NotImplemented pageName="訓練" />} />
          <Route path="/projects/:id/training/:runId" element={<NotImplemented pageName="訓練" />} />
          <Route path="/projects/:id/models" element={<NotImplemented pageName="模型" />} />
          <Route path="/projects/:id/api_keys" element={<NotImplemented pageName="API Keys" />} />
          <Route path="/projects/:id/webhook" element={<NotImplemented pageName="Webhook" />} />
          <Route path="/projects/:id/integration_calls" element={<NotImplemented pageName="整合紀錄" />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
