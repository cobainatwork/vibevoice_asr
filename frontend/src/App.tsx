/**
 * Main app router.
 *
 * See SPEC.md §8.2 for the page tree.
 *
 * M3 milestone: pages start as empty stubs.
 */
import { Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";

import Projects from "./pages/Projects";
import Hotwords from "./pages/Hotwords";
import Offline from "./pages/Offline";
import Datasets from "./pages/Datasets";
import Editor from "./pages/Editor";
import Training from "./pages/Training";
import TrainingDetail from "./pages/TrainingDetail";
import Models from "./pages/Models";
import ApiKeys from "./pages/ApiKeys";
import Webhook from "./pages/Webhook";
import IntegrationCalls from "./pages/IntegrationCalls";
import System from "./pages/System";

export default function App() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-6 overflow-auto">
        <Routes>
          <Route path="/" element={<Projects />} />
          <Route path="/projects/:id/hotwords" element={<Hotwords />} />
          <Route path="/projects/:id/offline" element={<Offline />} />
          <Route path="/projects/:id/datasets" element={<Datasets />} />
          <Route path="/projects/:id/edit/:itemId" element={<Editor />} />
          <Route path="/projects/:id/training" element={<Training />} />
          <Route path="/projects/:id/training/:runId" element={<TrainingDetail />} />
          <Route path="/projects/:id/models" element={<Models />} />
          <Route path="/projects/:id/api_keys" element={<ApiKeys />} />
          <Route path="/projects/:id/webhook" element={<Webhook />} />
          <Route path="/projects/:id/integration_calls" element={<IntegrationCalls />} />
          <Route path="/system" element={<System />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
