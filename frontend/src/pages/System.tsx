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
  lastFetchAt: Date | null;
}

const INITIAL_STATE: PanelState = {
  health: null, vllm: null, profile: null, queue: null,
  loading: false, lastError: null, lastFetchAt: null,
};

export default function System() {
  const [state, setState] = useState<PanelState>(INITIAL_STATE);

  const fetchAll = async () => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      const [health, vllm, profile, queue] = await Promise.all([
        systemApi.health().catch(() => null),
        systemApi.vllmStatus().catch(() => null),
        systemApi.profile().catch(() => null),
        systemApi.queue().catch(() => null),
      ]);
      setState({
        health, vllm, profile, queue,
        loading: false, lastError: null, lastFetchAt: new Date(),
      });
    } catch (e) {
      setState((prev) => ({ ...prev, loading: false, lastError: String(e) }));
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
        <button
          type="button"
          onClick={fetchAll}
          disabled={state.loading}
          className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50 transition-colors duration-200"
        >
          <RefreshCw className={`w-4 h-4 ${state.loading ? "animate-spin" : ""}`} /> 重新整理
        </button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Panel title="健康檢查" icon={<Activity className="w-4 h-4" />}>
          {state.health ? <HealthRows data={state.health} /> : <Loading />}
        </Panel>
        <Panel title="vLLM 狀態" icon={<Cpu className="w-4 h-4" />}>
          {state.vllm ? <VllmRows data={state.vllm} /> : <Loading />}
        </Panel>
        <Panel title="部署 Profile" icon={<Database className="w-4 h-4" />}>
          {state.profile ? <ProfileRows data={state.profile} /> : <Loading />}
        </Panel>
        <Panel title="任務佇列" icon={<ListTree className="w-4 h-4" />}>
          {state.queue ? <QueueRows data={state.queue} /> : <Loading />}
        </Panel>
      </div>

      <PollingStatus
        loading={state.loading}
        lastFetchAt={state.lastFetchAt}
        intervalMs={POLL_MS}
      />
    </div>
  );
}


// === Per-panel rows ===


function HealthRows({ data }: { data: HealthOut }) {
  return (
    <ul className="space-y-2 text-sm">
      <Row label="DB" value={data.db_status} />
      <Row label="Redis" value={data.redis_status} />
      <Row label="vLLM" value={data.vllm_status} />
      <Row label="總體" value={data.ok ? "ok" : "不健康"} />
    </ul>
  );
}


function VllmRows({ data }: { data: VllmStatusOut }) {
  return (
    <ul className="space-y-2 text-sm">
      <Row label="狀態" value={data.status} />
      <Row label="Model" value={data.model ?? "—"} />
      <Row label="Uptime" value={data.uptime_sec != null ? `${data.uptime_sec}s` : "—"} />
      {data.status === "mock" && (
        <li className="text-xs text-amber-600 pt-1">Mock 模式（dev 用，無真實推論）</li>
      )}
    </ul>
  );
}


function ProfileRows({ data }: { data: ProfileOut }) {
  return (
    <ul className="space-y-2 text-sm">
      <Row label="Profile" value={data.profile} />
      <Row label="Inference GPU" value={data.gpu_inference_devices} />
      <Row label="Training GPU" value={data.gpu_training_devices} />
      <Row label="TP × DP" value={`${data.tensor_parallel} × ${data.data_parallel}`} />
      <Row label="最大並發" value={String(data.max_concurrent_requests)} />
      <Row label="可同時訓練" value={data.can_concurrent_train ? "是" : "否"} />
    </ul>
  );
}


function QueueRows({ data }: { data: QueueInfo }) {
  return (
    <ul className="space-y-2 text-sm">
      <Row label="Pending" value={String(data.pending)} />
      <Row label="Running" value={String(data.running)} />
      <Row label="Workers" value={String(data.workers)} />
      <Row label="最舊任務年齡" value={`${data.oldest_age_sec}s`} />
    </ul>
  );
}


// === Generic UI ===


function Panel({ title, icon, children }: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
        {icon}{title}
      </div>
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


// === Polling status footer ===


function PollingStatus({ loading, lastFetchAt, intervalMs }: {
  loading: boolean;
  lastFetchAt: Date | null;
  intervalMs: number;
}) {
  const now = useTickEverySecond();
  const sinceLastSec = secondsSince(now, lastFetchAt);
  const nextInSec = secondsUntilNextPoll(now, lastFetchAt, intervalMs);

  return (
    <p className="text-xs text-slate-500 mt-4 flex items-center gap-2 flex-wrap">
      <span>每 {Math.floor(intervalMs / 1000)} 秒自動更新</span>
      {sinceLastSec !== null && (
        <span className="font-mono">· 上次更新 {sinceLastSec} 秒前</span>
      )}
      {nextInSec !== null && !loading && (
        <span className="font-mono">· 下次更新 {nextInSec} 秒後</span>
      )}
      {loading && (
        <span className="inline-flex items-center gap-1 text-blue-600">
          <RefreshCw className="w-3 h-3 animate-spin" /> 更新中...
        </span>
      )}
    </p>
  );
}


function useTickEverySecond(): Date {
  const [now, setNow] = useState<Date>(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}


function secondsSince(now: Date, since: Date | null): number | null {
  if (!since) return null;
  return Math.max(0, Math.floor((now.getTime() - since.getTime()) / 1000));
}


function secondsUntilNextPoll(
  now: Date, lastFetchAt: Date | null, intervalMs: number,
): number | null {
  if (!lastFetchAt) return null;
  const elapsed = now.getTime() - lastFetchAt.getTime();
  return Math.max(0, Math.ceil((intervalMs - elapsed) / 1000));
}
