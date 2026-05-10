import { useCallback } from "react";
import { findActiveSegmentIdx } from "../lib/segmentLookup";
import type { Segment } from "../api/types";

/**
 * 播放時 wavesurfer ~30Hz timeupdate event 回調：找對應 segment idx 並 dedup setActive。
 *
 * dedup（idx === activeIdx 跳過）防止高頻 setActive 觸發 region useEffect 整批重建、
 * 影響效能。Viewer / Editor 兩處共用此 hook。
 */
export function useTimeUpdateActiveSync(
  segments: Segment[],
  activeIdx: number,
  setActive: (idx: number) => void,
) {
  return useCallback(
    (currentSec: number) => {
      const idx = findActiveSegmentIdx(segments, currentSec);
      if (idx !== -1 && idx !== activeIdx) setActive(idx);
    },
    [segments, activeIdx, setActive],
  );
}
