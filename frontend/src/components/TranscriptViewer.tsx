/**
 * Read-only transcript viewer with click-to-seek timestamps.
 *
 * For editing, use TranscriptEditor instead.
 *
 * See SPEC.md §8.3.6.
 * M3 milestone.
 */
import type { Segment } from "../api/types";
import { secondsToMs } from "../lib/time";
import { speakerColor } from "../lib/format";

interface Props {
  segments: Segment[];
  onSeek?: (sec: number) => void;
  currentTime?: number;
}

export function TranscriptViewer({ segments, onSeek, currentTime }: Props) {
  return (
    <div className="space-y-2">
      {segments.map((s, i) => {
        const isActive =
          currentTime !== undefined && currentTime >= s.start_time && currentTime < s.end_time;
        return (
          <div
            key={i}
            className={`p-3 rounded border ${isActive ? "border-blue-400 bg-blue-50" : "border-gray-200"}`}
          >
            <div className="flex items-center gap-2 text-sm mb-1">
              <span className={`font-semibold ${speakerColor(s.speaker_id)}`}>
                Speaker {s.speaker_id}
              </span>
              <button
                onClick={() => onSeek?.(s.start_time)}
                className="text-blue-600 hover:underline tabular-nums"
              >
                {secondsToMs(s.start_time)} — {secondsToMs(s.end_time)}
              </button>
            </div>
            <div className="text-sm">{s.text}</div>
          </div>
        );
      })}
    </div>
  );
}
