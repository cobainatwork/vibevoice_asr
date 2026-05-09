import { create } from "zustand";
import type { Segment } from "../api/types";

const SNAP_GRID_SEC = 0.05;
const MIN_SEGMENT_LEN_SEC = 0.1;
const NOOP_EPSILON = 1e-6;

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
  patchSegment: (idx, partial) =>
    set({ segments: replaceAt(get().segments, idx, partial) }),
  resizeSegment: (idx, start, end) => {
    const segs = get().segments;
    const cur = segs[idx];
    if (!cur) return;
    const prev = idx > 0 ? segs[idx - 1] : null;
    const next = idx < segs.length - 1 ? segs[idx + 1] : null;
    const clamped = clampSegmentBounds(start, end, cur, prev, next);
    if (!clamped) return;
    if (isNoopChange(cur, clamped.start, clamped.end)) return;
    set({
      segments: replaceAt(segs, idx, {
        start_time: clamped.start,
        end_time: clamped.end,
      }),
    });
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


// === Pure helpers ===


function replaceAt(
  segs: Segment[], idx: number, patch: Partial<Segment>,
): Segment[] {
  const out = [...segs];
  out[idx] = { ...out[idx], ...patch };
  return out;
}


function snapToGrid(v: number): number {
  return Math.round(v / SNAP_GRID_SEC) * SNAP_GRID_SEC;
}


/**
 * 把 start / end 限制在合法區間內：
 *   - 不可侵入上段 end_time / 下段 start_time
 *   - 至少維持 MIN_SEGMENT_LEN_SEC 長度
 * 仍無法滿足長度時回 null（caller 應略過此次更新）。
 */
function clampSegmentBounds(
  start: number,
  end: number,
  cur: Segment,
  prev: Segment | null,
  next: Segment | null,
): { start: number; end: number } | null {
  const minStart = prev ? prev.end_time : 0;
  const maxEnd = next ? next.start_time : Number.POSITIVE_INFINITY;
  let newStart = Math.max(minStart, snapToGrid(start));
  let newEnd = Math.min(maxEnd, snapToGrid(end));

  if (newEnd - newStart >= MIN_SEGMENT_LEN_SEC) {
    return { start: newStart, end: newEnd };
  }

  // 太短：偏向被使用者拖動的那一側補回 minLen
  const startMovedMore =
    Math.abs(start - cur.start_time) > Math.abs(end - cur.end_time);
  if (startMovedMore) {
    newStart = Math.max(minStart, newEnd - MIN_SEGMENT_LEN_SEC);
  } else {
    newEnd = Math.min(maxEnd, newStart + MIN_SEGMENT_LEN_SEC);
  }
  if (newEnd - newStart < MIN_SEGMENT_LEN_SEC) return null;
  return { start: newStart, end: newEnd };
}


/** 值幾乎不變時跳過更新，避免 wavesurfer 加 region 時誤觸 dirty。 */
function isNoopChange(cur: Segment, newStart: number, newEnd: number): boolean {
  return (
    Math.abs(cur.start_time - newStart) < NOOP_EPSILON &&
    Math.abs(cur.end_time - newEnd) < NOOP_EPSILON
  );
}
