import { useCallback, useMemo, useRef, useState } from "react";
import { Edit3 } from "lucide-react";
import { Link } from "react-router-dom";
import { WaveformPlayer, type WaveformHandle } from "./WaveformPlayer";
import { SegmentListItem } from "./SegmentListItem";
import { findActiveSegmentIdx } from "../lib/segmentLookup";
import type { JobOut } from "../api/types";

interface Props {
  job: JobOut;
  audioUrl: string;
  projectId: number;
}

export function TranscriptViewer({ job, audioUrl, projectId }: Props) {
  // useMemo 防止 ?? [] 每次 render 新建空陣列、進而 invalidate handleTimeUpdate 的 useCallback deps
  const segments = useMemo(() => job.segments ?? [], [job.segments]);
  const [active, setActive] = useState<number>(segments.length > 0 ? 0 : -1);
  const waveRef = useRef<WaveformHandle>(null);

  const focusSegment = (i: number) => {
    setActive(i);
    waveRef.current?.seek(segments[i].start_time);
    waveRef.current?.play();
  };

  // 播放時跟隨同步 active segment；dedup 避免 region useEffect 高頻重建。
  const handleTimeUpdate = useCallback(
    (t: number) => {
      const idx = findActiveSegmentIdx(segments, t);
      if (idx !== -1 && idx !== active) setActive(idx);
    },
    [segments, active],
  );

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 truncate max-w-md">{job.filename}</h1>
          <p className="text-xs text-slate-500 mt-1">
            時長 {(job.duration_sec ?? 0).toFixed(1)} 秒 · {segments.length} 段 · hotwords {job.used_hotwords.length} 詞
          </p>
        </div>
        <Link to={`/projects/${projectId}/edit/${job.id}?mode=edit`} className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white text-sm rounded cursor-pointer hover:bg-blue-600 transition-colors duration-200">
          <Edit3 className="w-4 h-4" /> 編輯模式
        </Link>
      </header>

      <WaveformPlayer
        ref={waveRef}
        audioUrl={audioUrl}
        segments={segments}
        activeIdx={active}
        onRegionClick={focusSegment}
        onTimeUpdate={handleTimeUpdate}
      />

      <div className="grid grid-cols-12 gap-4 mt-4">
        <div className="col-span-12 md:col-span-5 bg-white border border-slate-200 rounded-md overflow-hidden max-h-[60vh] overflow-y-auto">
          {segments.map((s, i) => (
            <SegmentListItem
              key={i}
              segment={s}
              active={i === active}
              dirty={false}
              onClick={() => focusSegment(i)}
            />
          ))}
        </div>
        <div className="col-span-12 md:col-span-7 bg-white border border-slate-200 rounded-md p-4">
          {active >= 0 && segments[active] ? (
            <>
              <div className="text-xs text-slate-500 mb-2">
                <span className="font-mono">{segments[active].start_time.toFixed(2)} → {segments[active].end_time.toFixed(2)}</span>
                {" · "}Speaker {segments[active].speaker_id}
              </div>
              <p className="text-base text-slate-900 leading-relaxed whitespace-pre-wrap">
                {segments[active].text}
              </p>
            </>
          ) : (
            <p className="text-sm text-slate-500">此 Job 沒有 segments</p>
          )}
        </div>
      </div>
    </div>
  );
}
