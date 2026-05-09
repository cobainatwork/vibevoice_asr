import { useEffect, useState } from "react";
import { RefreshCw, Activity, Cpu, ListTree, Database } from "lucide-react";
import { systemApi } from "../api/system";
import type { HealthOut, ProfileOut, QueueInfo, VllmStatusOut } from "../api/types";

const POLL_MS = 10_000;

interface PanelState {
  health: HealthOut | null;
  vllm: VllmStatusOut | null;
  profile: ProfileOut | null;
  queue: QueueInfo | null;
  loading: boolean;
  lastError: string | null;
}

export default function System() {
  const [s, setS] = useState<PanelState>({
    health: null, vllm: null, profile: null, queue: null,
    loading: false, lastError: null,
  });

  const fetchAll = async () => {
    setS((p) => ({ ...p, loading: true }));
    try {
      const [h, v, p, q] = await Promise.all([
        systemApi.health().catch(() => null),
        systemApi.vllmStatus().catch(() => null),
        systemApi.profile().catch(() => null),
        systemApi.queue().catch(() => null),
      ]);
      setS({ health: h, vllm: v, profile: p, queue: q, loading: false, lastError: null });
    } catch (e) {
      setS((prev) => ({ ...prev, loading: false, lastError: String(e) }));
    }
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold text-slate-900">服務狀態</h1>
        <button type="button" onClick={fetchAll} disabled={s.loading} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50 transition-colors duration-200">
          <RefreshCw className={`w-4 h-4 ${s.loading ? "animate-spin" : ""}`} /> 重新整理
        </button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Health */}
        <Panel title="健康檢查" icon={<Activity className="w-4 h-4" />}>
          {s.health ? (
            <ul className="space-y-2 text-sm">
              <Row label="DB" value={s.health.db_status} />
              <Row label="Redis" value={s.health.redis_status} />
              <Row label="vLLM" value={s.health.vllm_status} />
              <Row label="總體" value={s.health.ok ? "ok" : "不健康"} />
            </ul>
          ) : <Loading />}
        </Panel>

        {/* vLLM */}
        <Panel title="vLLM 狀態" icon={<Cpu className="w-4 h-4" />}>
          {s.vllm ? (
            <ul className="space-y-2 text-sm">
              <Row label="狀態" value={s.vllm.status} />
              <Row label="Model" value={s.vllm.model ?? "—"} />
              <Row label="Uptime" value={s.vllm.uptime_sec != null ? `${s.vllm.uptime_sec}s` : "—"} />
              {s.vllm.status === "mock" && <li className="text-xs text-amber-600 pt-1">Mock 模式（dev 用，無真實推論）</li>}
            </ul>
          ) : <Loading />}
        </Panel>

        {/* Profile */}
        <Panel title="部署 Profile" icon={<Database className="w-4 h-4" />}>
          {s.profile ? (
            <ul className="space-y-2 text-sm">
              <Row label="Profile" value={s.profile.profile} />
              <Row label="Inference GPU" value={s.profile.gpu_inference_devices} />
              <Row label="Training GPU" value={s.profile.gpu_training_devices} />
              <Row label="TP × DP" value={`${s.profile.tensor_parallel} × ${s.profile.data_parallel}`} />
              <Row label="最大並發" value={String(s.profile.max_concurrent_requests)} />
              <Row label="可同時訓練" value={s.profile.can_concurrent_train ? "是" : "否"} />
            </ul>
          ) : <Loading />}
        </Panel>

        {/* Queue */}
        <Panel title="任務佇列" icon={<ListTree className="w-4 h-4" />}>
          {s.queue ? (
            <ul className="space-y-2 text-sm">
              <Row label="Pending" value={String(s.queue.pending)} />
              <Row label="Running" value={String(s.queue.running)} />
              <Row label="Workers" value={String(s.queue.workers)} />
              <Row label="最舊任務年齡" value={`${s.queue.oldest_age_sec}s`} />
            </ul>
          ) : <Loading />}
        </Panel>
      </div>
      <p className="text-xs text-slate-500 mt-4">每 10 秒自動更新；數值是最後一次成功的回應</p>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">{icon}{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex justify-between gap-2 text-slate-700">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-slate-900 truncate max-w-[60%] text-right">{value}</span>
    </li>
  );
}

function Loading() {
  return <p className="text-sm text-slate-400">載入中...</p>;
}
