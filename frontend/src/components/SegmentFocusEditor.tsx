import { useEffect, useRef } from "react";
import type { Segment } from "../api/types";

interface Props {
  segment: Segment;
  index: number;
  total: number;
  speakerOptions: number[];
  onChange: (partial: Partial<Segment>) => void;
  /** 任一輸入框獲得焦點時呼叫 — 校正員開始編輯，外層應暫停播放避免 active segment 跳走 */
  onEditStart?: () => void;
}

export function SegmentFocusEditor({ segment, index, total, speakerOptions, onChange, onEditStart }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // autosize
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, [segment.text]);

  return (
    <div className="bg-orange-50/60 border border-orange-200 rounded-md p-4">
      <div className="text-xs uppercase text-orange-700 font-semibold tracking-wider mb-3">
        SEGMENT {index + 1} / {total}
      </div>

      <div className="flex flex-wrap gap-2 mb-3 text-xs">
        <div className="inline-flex items-center gap-1 bg-white border border-slate-300 rounded px-2 py-1">
          <span className="text-slate-500">起</span>
          <input
            type="number"
            step="0.05"
            value={segment.start_time}
            onChange={(e) => onChange({ start_time: Number(e.target.value) })}
            onFocus={onEditStart}
            className="w-20 font-mono text-slate-900 bg-transparent outline-none"
          />
        </div>
        <div className="inline-flex items-center gap-1 bg-white border border-slate-300 rounded px-2 py-1">
          <span className="text-slate-500">迄</span>
          <input
            type="number"
            step="0.05"
            value={segment.end_time}
            onChange={(e) => onChange({ end_time: Number(e.target.value) })}
            onFocus={onEditStart}
            className="w-20 font-mono text-slate-900 bg-transparent outline-none"
          />
        </div>
        <div className="inline-flex items-center gap-1 bg-white border border-slate-300 rounded px-2 py-1">
          <span className="text-slate-500">Speaker</span>
          <select
            value={segment.speaker_id}
            onChange={(e) => onChange({ speaker_id: Number(e.target.value) })}
            onFocus={onEditStart}
            className="bg-transparent outline-none cursor-pointer text-slate-900"
          >
            {speakerOptions.map((sp) => <option key={sp} value={sp}>{sp}</option>)}
          </select>
        </div>
      </div>

      <textarea
        ref={textareaRef}
        value={segment.text}
        onChange={(e) => onChange({ text: e.target.value })}
        onFocus={onEditStart}
        className="w-full px-3 py-2 border-2 border-orange-300 rounded bg-white text-base text-slate-900 leading-relaxed resize-none outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-200 transition-colors duration-200 min-h-[120px]"
      />
    </div>
  );
}
