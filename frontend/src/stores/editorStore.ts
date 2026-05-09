import { create } from "zustand";
import type { Segment } from "../api/types";

interface EditorState {
  jobId: string | null;
  segments: Segment[];
  originalSnapshot: string; // JSON.stringify(segments) 用於 dirty 判定
  activeIdx: number;
  saving: boolean;
  lastSavedAt: Date | null;

  init: (jobId: string, segments: Segment[]) => void;
  reset: () => void;
  setActive: (idx: number) => void;
  patchSegment: (idx: number, partial: Partial<Segment>) => void;
  resizeSegment: (idx: number, start: number, end: number) => void;

  isDirty: () => boolean;
  markSaved: (segments: Segment[]) => void;
  setSaving: (b: boolean) => void;
}

export const useEditorStore = create<EditorState>((set, get) => ({
  jobId: null,
  segments: [],
  originalSnapshot: "[]",
  activeIdx: 0,
  saving: false,
  lastSavedAt: null,

  init: (jobId, segments) =>
    set({
      jobId,
      segments,
      originalSnapshot: JSON.stringify(segments),
      activeIdx: 0,
      saving: false,
      lastSavedAt: null,
    }),
  reset: () =>
    set({
      jobId: null,
      segments: [],
      originalSnapshot: "[]",
      activeIdx: 0,
      saving: false,
      lastSavedAt: null,
    }),
  setActive: (idx) => set({ activeIdx: idx }),
  patchSegment: (idx, partial) => {
    const next = [...get().segments];
    next[idx] = { ...next[idx], ...partial };
    set({ segments: next });
  },
  resizeSegment: (idx, start, end) => {
    const grid = 0.05;
    const minLen = 0.1; // 最短 segment 0.1 秒，避免拖到端點重疊
    const snap = (v: number) => Math.round(v / grid) * grid;
    const segs = get().segments;
    const cur = segs[idx];
    if (!cur) return;

    // 鄰接段邊界：不可侵入上段 end / 下段 start
    const prev = idx > 0 ? segs[idx - 1] : null;
    const nextSeg = idx < segs.length - 1 ? segs[idx + 1] : null;
    const minStart = prev ? prev.end_time : 0;
    const maxEnd = nextSeg ? nextSeg.start_time : Number.POSITIVE_INFINITY;

    // clamp 到合法區間
    let newStart = Math.max(minStart, snap(start));
    let newEnd = Math.min(maxEnd, snap(end));

    // 保證 start + minLen <= end
    if (newEnd - newStart < minLen) {
      // 偏向被使用者拖動的那一側
      if (Math.abs(start - cur.start_time) > Math.abs(end - cur.end_time)) {
        newStart = Math.max(minStart, newEnd - minLen);
      } else {
        newEnd = Math.min(maxEnd, newStart + minLen);
      }
      // 仍違反代表空間不夠，不更新
      if (newEnd - newStart < minLen) return;
    }

    // noop guard：值幾乎不變時不寫 store，避免 wavesurfer 加 region 時誤觸 dirty
    if (
      Math.abs(cur.start_time - newStart) < 1e-6 &&
      Math.abs(cur.end_time - newEnd) < 1e-6
    ) {
      return;
    }
    const out = [...segs];
    out[idx] = { ...cur, start_time: newStart, end_time: newEnd };
    set({ segments: out });
  },
  isDirty: () => JSON.stringify(get().segments) !== get().originalSnapshot,
  markSaved: (segments) =>
    set({
      originalSnapshot: JSON.stringify(segments),
      lastSavedAt: new Date(),
      saving: false,
    }),
  setSaving: (b) => set({ saving: b }),
}));
