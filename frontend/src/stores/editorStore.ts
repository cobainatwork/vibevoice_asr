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
    const snap = (v: number) => Math.round(v / grid) * grid;
    const segs = get().segments;
    const cur = segs[idx];
    if (!cur) return;
    const newStart = snap(start);
    const newEnd = snap(end);
    // noop guard：值幾乎不變時不寫 store，避免 wavesurfer 加 region 時誤觸 dirty
    if (
      Math.abs(cur.start_time - newStart) < 1e-6 &&
      Math.abs(cur.end_time - newEnd) < 1e-6
    ) {
      return;
    }
    const next = [...segs];
    next[idx] = { ...cur, start_time: newStart, end_time: newEnd };
    set({ segments: next });
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
