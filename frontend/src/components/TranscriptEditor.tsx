import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { Eye, CheckCircle2, Loader2 } from "lucide-react";
import { WaveformPlayer, type WaveformHandle } from "./WaveformPlayer";
import { SegmentListItem } from "./SegmentListItem";
import { SegmentFocusEditor } from "./SegmentFocusEditor";
import { useEditorStore } from "../stores/editorStore";
import { useAutoSave } from "../hooks/useAutoSave";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useToast } from "../hooks/useToast";
import { jobsApi } from "../api/jobs";
import type { JobOut } from "../api/types";

interface Props {
  job: JobOut;
  audioUrl: string;
  projectId: number;
}

export function TranscriptEditor({ job, audioUrl, projectId }: Props) {
  const init = useEditorStore((s) => s.init);
  const reset = useEditorStore((s) => s.reset);
  const segments = useEditorStore((s) => s.segments);
  const activeIdx = useEditorStore((s) => s.activeIdx);
  const setActive = useEditorStore((s) => s.setActive);
  const patchSegment = useEditorStore((s) => s.patchSegment);
  const resizeSegment = useEditorStore((s) => s.resizeSegment);
  const isDirty = useEditorStore((s) => s.isDirty);
  const dirty = isDirty();
  const saving = useEditorStore((s) => s.saving);
  const lastSavedAt = useEditorStore((s) => s.lastSavedAt);
  const setSaving = useEditorStore((s) => s.setSaving);
  const markSaved = useEditorStore((s) => s.markSaved);

  const waveRef = useRef<WaveformHandle>(null);
  const toast = useToast();

  // mount: init store
  useEffect(() => {
    init(job.id, job.segments ?? []);
    return () => reset();
  }, [job.id]);

  const speakerOptions = useMemo(() => {
    const set = new Set<number>([1, 2, 3, 4, 5]);
    segments.forEach((s) => set.add(s.speaker_id));
    return Array.from(set).sort((a, b) => a - b);
  }, [segments]);

  const save = async () => {
    // 用 getState() 取最新值；setTimeout 觸發時 closure 中的 segments / dirty
    // 可能是 stale（使用者持續編輯期間值已變動）
    const state = useEditorStore.getState();
    if (state.saving) return;
    if (!state.isDirty()) return;
    const latestSegments = state.segments;
    setSaving(true);
    try {
      await jobsApi.patchSegments(job.id, latestSegments);
      markSaved(latestSegments);
    } catch {
      // client.ts 已 toast
      setSaving(false);
    }
  };

  useAutoSave(dirty, save, { delayMs: 3000 });

  const focusSegment = (i: number) => {
    if (dirty) save(); // 切段前 flush
    setActive(i);
    if (segments[i]) {
      waveRef.current?.seek(segments[i].start_time);
      waveRef.current?.play();
    }
  };

  useKeyboardShortcuts([
    { key: "Space", handler: () => waveRef.current?.toggle() },
    { key: "ArrowLeft", handler: () => waveRef.current?.jumpRelative(-5) },
    { key: "ArrowRight", handler: () => waveRef.current?.jumpRelative(5) },
    { key: "Tab", shift: false, handler: () => focusSegment(Math.min(segments.length - 1, activeIdx + 1)) },
    { key: "Tab", shift: true, handler: () => focusSegment(Math.max(0, activeIdx - 1)) },
    { key: "m", handler: () => waveRef.current?.toggleMuted() },
    { key: "M", handler: () => waveRef.current?.toggleMuted() },
    { key: "s", meta: true, preventInInput: false, handler: () => { save(); toast.info("手動儲存"); } },
    { key: "Escape", preventInInput: false, handler: () => (document.activeElement as HTMLElement | null)?.blur() },
  ], true);

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 truncate max-w-md">{job.filename}</h1>
          <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
            {saving
              ? <span className="inline-flex items-center gap-1 text-blue-600"><Loader2 className="w-3 h-3 animate-spin" /> 儲存中...</span>
              : dirty
              ? <span className="text-amber-600">有未儲存變更</span>
              : lastSavedAt
              ? <span className="inline-flex items-center gap-1 text-green-600"><CheckCircle2 className="w-3 h-3" /> 已儲存於 {lastSavedAt.toLocaleTimeString("zh-TW")}</span>
              : <span className="text-slate-500">無變更</span>
            }
          </p>
        </div>
        <Link to={`/projects/${projectId}/edit/${job.id}?mode=view`} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200">
          <Eye className="w-4 h-4" /> 檢視模式
        </Link>
      </header>

      <WaveformPlayer
        ref={waveRef}
        audioUrl={audioUrl}
        segments={segments}
        activeIdx={activeIdx}
        onRegionClick={focusSegment}
      />

      <div className="grid grid-cols-12 gap-4 mt-4">
        <div className="col-span-12 md:col-span-5 bg-white border border-slate-200 rounded-md overflow-hidden max-h-[60vh] overflow-y-auto">
          {segments.map((s, i) => (
            <SegmentListItem
              key={i}
              segment={s}
              active={i === activeIdx}
              dirty={JSON.stringify(s) !== JSON.stringify((job.segments ?? [])[i])}
              onClick={() => focusSegment(i)}
            />
          ))}
        </div>
        <div className="col-span-12 md:col-span-7">
          {segments[activeIdx] && (
            <SegmentFocusEditor
              segment={segments[activeIdx]}
              index={activeIdx}
              total={segments.length}
              speakerOptions={speakerOptions}
              onChange={(p) => {
                // 時間欄位走 resizeSegment 走 clamp（防止與鄰段重疊）
                if (p.start_time !== undefined || p.end_time !== undefined) {
                  const cur = segments[activeIdx];
                  resizeSegment(
                    activeIdx,
                    p.start_time ?? cur.start_time,
                    p.end_time ?? cur.end_time,
                  );
                } else {
                  patchSegment(activeIdx, p);
                }
              }}
            />
          )}
        </div>
      </div>

      <p className="text-xs text-slate-500 mt-4 px-2 flex flex-wrap gap-3">
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Space</kbd> 播停</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">←/→</kbd> ±5s</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Tab</kbd> 下一段</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Shift+Tab</kbd> 上一段</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">M</kbd> 靜音</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Ctrl+S</kbd> 手動存</span>
      </p>
    </div>
  );
}
