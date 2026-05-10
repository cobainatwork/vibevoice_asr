import { useEffect, useMemo, useRef, type RefObject } from "react";
import { Link } from "react-router-dom";
import { Eye, CheckCircle2, Loader2 } from "lucide-react";
import { WaveformPlayer, type WaveformHandle } from "./WaveformPlayer";
import { SegmentListItem } from "./SegmentListItem";
import { SegmentFocusEditor } from "./SegmentFocusEditor";
import { useEditorStore } from "../stores/editorStore";
import { useAutoSave } from "../hooks/useAutoSave";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useTimeUpdateActiveSync } from "../hooks/useTimeUpdateActiveSync";
import { useToast } from "../hooks/useToast";
import type { EditorSource } from "../lib/editorSource";
import type { ProjectOut, Segment } from "../api/types";

const AUTOSAVE_DELAY_MS = 3000;
const SEEK_STEP_SEC = 5;

interface Props {
  source: EditorSource;
  project: ProjectOut;
  /** 可選：標頭右上「檢視模式」按鈕的目標路徑。dataset editor 無此概念可省略。 */
  viewLink?: string;
}

export function TranscriptEditor({ source, project: _project, viewLink }: Props) {
  const { segments, activeIdx, saving, lastSavedAt, dirty, audioUrl, title } =
    useEditorSelectors();
  const { init, reset, setActive, patchSegment, resizeSegment } =
    useEditorStore.getState();

  const waveRef = useRef<WaveformHandle>(null);
  const toast = useToast();
  const speakerOptions = useSpeakerOptions(segments);

  useEffect(() => {
    init(source);
    return () => reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  // 直接委派給 store.save —— store 內守 §4.12 兩條 invariant。
  const save = () => useEditorStore.getState().save();

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

  const handleTimeUpdate = useTimeUpdateActiveSync(segments, activeIdx, setActive);

  useEditorShortcuts({
    waveRef,
    segmentCount: segments.length,
    activeIdx,
    focusSegment,
    onManualSave: () => { save(); toast.info("手動儲存"); },
  });

  const originalSegments = useOriginalSegments();

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 truncate max-w-md">
            {title}
          </h1>
          <SaveStatusBadge saving={saving} dirty={dirty} lastSavedAt={lastSavedAt} />
        </div>
        {viewLink && (
          <Link
            to={viewLink}
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200"
          >
            <Eye className="w-4 h-4" /> 檢視模式
          </Link>
        )}
      </header>

      <WaveformPlayer
        ref={waveRef}
        audioUrl={audioUrl}
        segments={segments}
        activeIdx={activeIdx}
        editable
        onRegionClick={focusSegment}
        onRegionResize={resizeSegment}
        onTimeUpdate={handleTimeUpdate}
      />

      <div className="grid grid-cols-12 gap-4 mt-4">
        <div className="col-span-12 md:col-span-5 bg-white border border-slate-200 rounded-md overflow-hidden max-h-[60vh] overflow-y-auto">
          {segments.map((seg, i) => (
            <SegmentListItem
              key={i}
              segment={seg}
              active={i === activeIdx}
              dirty={isSegmentDirty(seg, originalSegments[i])}
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
  const audioUrl = useEditorStore((s) => s.audioUrl);
  const title = useEditorStore((s) => s.title);
  return {
    segments, activeIdx, saving, lastSavedAt, audioUrl, title,
    dirty: isDirty(),
  };
}


/**
 * 從 originalSnapshot 還原成 Segment[]，給 SegmentListItem 的 dirty dot 用
 * （比對「目前段」與「最近一次儲存的對應段」是否相同）。
 */
function useOriginalSegments(): Segment[] {
  const snapshot = useEditorStore((s) => s.originalSnapshot);
  return useMemo(() => {
    try {
      return JSON.parse(snapshot) as Segment[];
    } catch {
      return [];
    }
  }, [snapshot]);
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
