import type { Segment } from "../api/types";

/**
 * 依當前播放時間找對應的 segment index。
 *
 * 行為：
 *   1. 優先回傳「t 落在 [start_time, end_time) 內」的 segment
 *   2. 若 t 落在 segments 之間的 gap（例如 vLLM 輸出有空隙）
 *      → fallback 回最後一個 start_time <= t 的 segment
 *      （讓 transcript 高亮停留在上一段，不會閃回 -1）
 *   3. 完全找不到（t 在第一段 start 之前）→ 回 -1
 *
 * caller 必須 dedup：idx === activeIdx 時不重複觸發 setActive，
 * 否則 wavesurfer 30Hz timeupdate 會引發大量 re-render。
 */
export function findActiveSegmentIdx(
  segments: Segment[],
  currentSec: number,
): number {
  const exact = segments.findIndex(
    (s) => currentSec >= s.start_time && currentSec < s.end_time,
  );
  if (exact !== -1) return exact;

  let lastBefore = -1;
  for (let i = 0; i < segments.length; i++) {
    if (segments[i].start_time <= currentSec) lastBefore = i;
    else break;
  }
  return lastBefore;
}
