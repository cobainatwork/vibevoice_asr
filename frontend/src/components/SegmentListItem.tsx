import { useEffect, useRef } from "react";
import type { Segment } from "../api/types";
import { matchSubtitle, SIMILARITY_THRESHOLD } from "../lib/subtitleDiff";

interface Props {
  segment: Segment;
  active: boolean;
  dirty: boolean;
  refSubs?: Segment[] | null;
  onClick: () => void;
}

export function SegmentListItem({
  segment, active, dirty, refSubs, onClick,
}: Props) {
  const ref = useRef<HTMLButtonElement>(null);
  const match = refSubs ? matchSubtitle(refSubs, segment) : null;
  const isLowSim = match !== null && match.similarity < SIMILARITY_THRESHOLD;

  // active 變化時自動把這段 scroll 到 viewport 內，避免播放位移到視野外。
  // block: "nearest" 只在不可見時 scroll，不會無謂跳動已可見的項目。
  useEffect(() => {
    if (active) {
      ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [active]);

  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      className={`w-full text-left px-3 py-2 border-b border-slate-100 cursor-pointer transition-colors duration-200 ${
        active
          ? "bg-blue-50 border-l-2 border-l-blue-500 pl-2.5"
          : isLowSim
          ? "border-l-2 border-l-red-400 pl-2.5 hover:bg-slate-50"
          : "hover:bg-slate-50"
      }`}
    >
      <div className="flex items-center gap-2 text-xs text-slate-500 font-mono mb-0.5">
        <span>{segment.start_time.toFixed(2)}</span>
        <span>·</span>
        <span>Sp{segment.speaker_id}</span>
        {match && (
          <span
            className={`text-xs font-mono ${
              isLowSim ? "text-red-600 font-semibold" : "text-slate-400"
            }`}
            title={isLowSim ? "差異大,點選後右側查看完整對照" : "與 YT 字幕高度相符"}
          >
            YT {(match.similarity * 100).toFixed(0)}%
          </span>
        )}
        {dirty && (
          <span
            className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-500"
            aria-label="未儲存"
          />
        )}
      </div>
      <div className="text-sm text-slate-900 line-clamp-2">{segment.text}</div>
    </button>
  );
}
