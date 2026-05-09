/**
 * Editable transcript / waveform editor — the "校正工作台".
 *
 * Features (per SPEC.md §8.3.6):
 * - Wavesurfer + Regions plugin synced with segment list
 * - Drag region boundaries → updates start_time/end_time
 * - Click region → select / play that segment
 * - Edit text inline
 * - Change speaker_id (1-9 keyboard shortcut)
 * - Split/merge segments
 * - Auto-save (3s debounce)
 * - Validation: overlap warning, empty text error
 *
 * Keyboard shortcuts:
 *   Space     play/pause
 *   ←/→       skip 3s
 *   Tab       next segment
 *   1-9       set speaker for selected
 *   M         merge into previous
 *   /         split at cursor
 *   Delete    remove segment
 *
 * M3 milestone.
 */
import { useState } from "react";
import type { Segment } from "../api/types";
import { TranscriptViewer } from "./TranscriptViewer";
import { WaveformPlayer } from "./WaveformPlayer";

interface Props {
  audioUrl: string;
  segments: Segment[];
  onChange: (next: Segment[]) => void;
  customizedContext?: string[];
  onContextChange?: (next: string[]) => void;
  onSave?: () => void;
}

export function TranscriptEditor({
  audioUrl,
  segments,
  onChange,
  customizedContext,
  onContextChange,
  onSave,
}: Props) {
  const [currentTime, setCurrentTime] = useState(0);

  // TODO(M3):
  //  - debounced auto-save
  //  - keyboard shortcut handlers
  //  - region <-> segment list two-way binding
  //  - split/merge actions
  //  - per-segment edit mode

  const regions = segments.map((s, i) => ({
    id: String(i),
    start: s.start_time,
    end: s.end_time,
    color: `rgba(59, 130, 246, ${0.2 + ((s.speaker_id - 1) % 8) * 0.05})`,
    label: `Sp${s.speaker_id}`,
  }));

  return (
    <div className="space-y-4">
      <WaveformPlayer
        audioUrl={audioUrl}
        regions={regions}
        onSeek={setCurrentTime}
      />

      <TranscriptViewer segments={segments} onSeek={setCurrentTime} currentTime={currentTime} />

      <div className="text-xs text-gray-400">
        TODO: TranscriptEditor full implementation — see SPEC.md §8.3.6
      </div>
    </div>
  );
}
