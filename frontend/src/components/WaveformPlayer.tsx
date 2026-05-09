import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import { Play, Pause, Volume2, VolumeX } from "lucide-react";
import type { Segment } from "../api/types";

export interface WaveformHandle {
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (time: number) => void;
  jumpRelative: (deltaSec: number) => void;
  setMuted: (muted: boolean) => void;
  toggleMuted: () => void;
}

interface Props {
  audioUrl: string;
  segments: Segment[];
  activeIdx: number | null;
  editable?: boolean;
  onRegionClick?: (idx: number) => void;
  onRegionResize?: (idx: number, newStart: number, newEnd: number) => void;
}

export const WaveformPlayer = forwardRef<WaveformHandle, Props>(function WaveformPlayer(
  { audioUrl, segments, activeIdx, editable, onRegionClick, onRegionResize },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsPluginRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // create wavesurfer
  useEffect(() => {
    if (!containerRef.current) return;
    const regions = RegionsPlugin.create();
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "#94a3b8",
      progressColor: "#3b82f6",
      cursorColor: "#0f172a",
      height: 64,
      barWidth: 2,
      barGap: 1,
      plugins: [regions],
    });
    ws.load(audioUrl);
    ws.on("play", () => setPlaying(true));
    ws.on("pause", () => setPlaying(false));
    ws.on("timeupdate", (t) => setTime(t));
    ws.on("ready", () => setDuration(ws.getDuration()));
    wsRef.current = ws;
    regionsPluginRef.current = regions;
    return () => { ws.destroy(); };
  }, [audioUrl]);

  // sync segments → regions
  useEffect(() => {
    const regions = regionsPluginRef.current;
    if (!regions) return;
    regions.clearRegions();
    segments.forEach((s, i) => {
      const isActive = i === activeIdx;
      const r = regions.addRegion({
        start: s.start_time,
        end: s.end_time,
        color: isActive ? "rgba(249, 115, 22, 0.25)" : "rgba(59, 130, 246, 0.18)",
        drag: false,
        resize: !!editable,
      });
      r.on("click", (e) => {
        e?.stopPropagation?.();
        onRegionClick?.(i);
      });
      if (editable) {
        r.on("update-end", () => {
          onRegionResize?.(i, r.start, r.end);
        });
      }
    });
  }, [segments, activeIdx, editable, onRegionClick, onRegionResize]);

  // expose imperative API
  useImperativeHandle(ref, () => ({
    play: () => wsRef.current?.play(),
    pause: () => wsRef.current?.pause(),
    toggle: () => wsRef.current?.playPause(),
    seek: (t) => { const d = wsRef.current?.getDuration() ?? 0; if (d > 0) wsRef.current?.seekTo(t / d); },
    jumpRelative: (delta) => {
      const ws = wsRef.current; if (!ws) return;
      const d = ws.getDuration(); if (!d) return;
      const next = Math.max(0, Math.min(d, ws.getCurrentTime() + delta));
      ws.seekTo(next / d);
    },
    setMuted: (m) => { wsRef.current?.setMuted(m); setMuted(m); },
    toggleMuted: () => { const m = !muted; wsRef.current?.setMuted(m); setMuted(m); },
  }), [muted]);

  return (
    <div className="bg-slate-900 rounded-md p-3">
      <div ref={containerRef} className="rounded" />
      <div className="flex items-center gap-3 mt-2 text-slate-300 text-xs">
        <button type="button" aria-label={playing ? "暫停" : "播放"} onClick={() => wsRef.current?.playPause()} className="cursor-pointer text-white hover:text-blue-300 transition-colors duration-200">
          {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
        </button>
        <span className="font-mono">{formatTime(time)} / {formatTime(duration)}</span>
        <button type="button" aria-label={muted ? "取消靜音" : "靜音"} onClick={() => { const m = !muted; wsRef.current?.setMuted(m); setMuted(m); }} className="ml-auto cursor-pointer text-slate-300 hover:text-white transition-colors duration-200">
          {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
});

function formatTime(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 100);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}.${String(ms).padStart(2, "0")}`;
}
