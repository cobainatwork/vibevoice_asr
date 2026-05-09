import { useEffect, useMemo, useRef, type RefObject } from "react";
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
import type { JobOut, Segment } from "../api/types";

const AUTOSAVE_DELAY_MS = 3000;
const SEEK_STEP_SEC = 5;

interface Props {
  job: JobOut;
  audioUrl: string;
  projectId: number;
}

export function TranscriptEditor({ job, audioUrl, projectId }: Props) {
  const { segments, activeIdx, saving, lastSavedAt, dirty } = useEditorSelectors();
  const { init, reset, setActive, patchSegment, resizeSegment, setSaving, markSaved } =
    useEditorStore.getState();

  const waveRef = useRef<WaveformHandle>(null);
  const toast = useToast();
  const speakerOptions = useSpeakerOptions(segments);

  useEffect(() => {
    init(job.id, job.segments ?? []);
    return () => reset();
  }, [job.id]);

  const save = async () => {
    const state = useEditorStore.getState();
    if (state.saving || !state.isDirty()) return;
    const snapshot = state.segments;
    setSaving(true);
    try {
      await jobsApi.patchSegments(job.id, snapshot);
      markSaved(snapshot);
    } catch {
      setSaving(false); // client.ts 已 toast
    }
  };

  useAutoSave(dirty, save, { delayMs: AUTOSAVE_DELAY_MS });

  const focusSegment = (i: number) => {
    if (dirty) save();
    setActive(i);
    const seg = segments[i];
    if (seg) {
      waveRef.current?.seek(seg.start_time);
      waveRef.current?.play();
    }
  };

  const handleSegmentChange = (patch: Partial<Segment>) => {
    if (patch.start_time !== undefined || patch.end_time !== undefined) {
      const cur = segments[activeIdx];
      resizeSegment(
        activeIdx,
        patch.start_time ?? cur.start_time,
        patch.end_time ?? cur.end_time,
      );
    } else {
      patchSegment(activeIdx, patch);
    }
  };

  useEditorShortcuts({
    waveRef,
    segmentCount: segments.length,
    activeIdx,
    focusSegment,
    onManualSave: () => { save(); toast.info("手動儲存"); },
  });

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 truncate max-w-md">
            {job.filename}
          </h1>
          <SaveStatusBadge saving={saving} dirty={dirty} lastSavedAt={lastSavedAt} />
        </div>
        <Link
          to={`/projects/${projectId}/edit/${job.id}?mode=view`}
          className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200"
        >
          <Eye className="w-4 h-4" /> 檢視模式
        </Link>
      </header>

      <WaveformPlayer
        ref={waveRef}
        audioUrl={audioUrl}
        segments={segments}
        activeIdx={activeIdx}
        editable
        onRegionClick={focusSegment}
        onRegionResize={resizeSegment}
      />

      <div className="grid grid-cols-12 gap-4 mt-4">
        <div className="col-span-12 md:col-span-5 bg-white border border-slate-200 rounded-md overflow-hidden max-h-[60vh] overflow-y-auto">
          {segments.map((seg, i) => (
            <SegmentListItem
              key={i}
              segment={seg}
              active={i === activeIdx}
              dirty={isSegmentDirty(seg, (job.segments ?? [])[i])}
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
              onChange={handleSegmentChange}
            />
          )}
        </div>
      </div>

      <ShortcutHints />
    </div>
  );
}


// === Sub-components ===


function SaveStatusBadge({ saving, dirty, lastSavedAt }: {
  saving: boolean;
  dirty: boolean;
  lastSavedAt: Date | null;
}) {
  if (saving) {
    return (
      <p className="text-xs mt-1">
        <span className="inline-flex items-center gap-1 text-blue-600">
          <Loader2 className="w-3 h-3 animate-spin" /> 儲存中...
        </span>
      </p>
    );
  }
  if (dirty) {
    return <p className="text-xs mt-1 text-amber-600">有未儲存變更</p>;
  }
  if (lastSavedAt) {
    return (
      <p className="text-xs mt-1">
        <span className="inline-flex items-center gap-1 text-green-600">
          <CheckCircle2 className="w-3 h-3" />
          已儲存於 {lastSavedAt.toLocaleTimeString("zh-TW")}
        </span>
      </p>
    );
  }
  return <p className="text-xs mt-1 text-slate-500">無變更</p>;
}


const HINT_ITEMS = [
  { keys: "Space", label: "播停" },
  { keys: "←/→", label: `±${SEEK_STEP_SEC}s` },
  { keys: "Tab", label: "下一段" },
  { keys: "Shift+Tab", label: "上一段" },
  { keys: "M", label: "靜音" },
  { keys: "Ctrl+S", label: "手動存" },
];


function ShortcutHints() {
  return (
    <p className="text-xs text-slate-500 mt-4 px-2 flex flex-wrap gap-3">
      {HINT_ITEMS.map((h) => (
        <span key={h.keys}>
          <kbd className="font-mono bg-slate-100 px-1 rounded">{h.keys}</kbd> {h.label}
        </span>
      ))}
    </p>
  );
}


// === Hooks ===


function useEditorSelectors() {
  const segments = useEditorStore((s) => s.segments);
  const activeIdx = useEditorStore((s) => s.activeIdx);
  const saving = useEditorStore((s) => s.saving);
  const lastSavedAt = useEditorStore((s) => s.lastSavedAt);
  const isDirty = useEditorStore((s) => s.isDirty);
  return { segments, activeIdx, saving, lastSavedAt, dirty: isDirty() };
}


function useSpeakerOptions(segments: Segment[]): number[] {
  return useMemo(() => {
    const set = new Set<number>([1, 2, 3, 4, 5]);
    segments.forEach((s) => set.add(s.speaker_id));
    return Array.from(set).sort((a, b) => a - b);
  }, [segments]);
}


interface ShortcutDeps {
  waveRef: RefObject<WaveformHandle>;
  segmentCount: number;
  activeIdx: number;
  focusSegment: (i: number) => void;
  onManualSave: () => void;
}


function useEditorShortcuts(d: ShortcutDeps) {
  useKeyboardShortcuts(
    [
      { key: "Space", handler: () => d.waveRef.current?.toggle() },
      { key: "ArrowLeft", handler: () => d.waveRef.current?.jumpRelative(-SEEK_STEP_SEC) },
      { key: "ArrowRight", handler: () => d.waveRef.current?.jumpRelative(SEEK_STEP_SEC) },
      { key: "Tab", shift: false, handler: () =>
          d.focusSegment(Math.min(d.segmentCount - 1, d.activeIdx + 1)) },
      { key: "Tab", shift: true, handler: () =>
          d.focusSegment(Math.max(0, d.activeIdx - 1)) },
      { key: "m", handler: () => d.waveRef.current?.toggleMuted() },
      { key: "M", handler: () => d.waveRef.current?.toggleMuted() },
      { key: "s", meta: true, preventInInput: false, handler: d.onManualSave },
      { key: "Escape", preventInInput: false,
        handler: () => (document.activeElement as HTMLElement | null)?.blur() },
    ],
    true,
  );
}


// === Pure helpers ===


function isSegmentDirty(cur: Segment, original: Segment | undefined): boolean {
  return JSON.stringify(cur) !== JSON.stringify(original);
}
