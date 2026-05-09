/**
 * Wraps wavesurfer.js + Regions plugin.
 *
 * M3 milestone — implement first; central to the editor experience.
 *
 * See SPEC.md §8.4.3.
 */
import { useEffect, useRef } from "react";

interface Region {
  id: string;
  start: number;
  end: number;
  color: string;
  label?: string;
}

interface Props {
  audioUrl: string;
  regions: Region[];
  onRegionDrag?: (id: string, start: number, end: number) => void;
  onRegionClick?: (id: string) => void;
  onSeek?: (time: number) => void;
}

export function WaveformPlayer({ audioUrl, regions, onRegionDrag, onRegionClick, onSeek }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    // TODO(M3):
    //   import WaveSurfer from "wavesurfer.js";
    //   import RegionsPlugin from "wavesurfer.js/dist/plugins/regions";
    //   const ws = WaveSurfer.create({ container: containerRef.current, url: audioUrl, ... });
    //   const regionsPlugin = ws.registerPlugin(RegionsPlugin.create());
    //   regions.forEach(r => regionsPlugin.addRegion({ ... }));
    //   bind drag/click events
    //   return () => ws.destroy();
  }, [audioUrl]);

  // TODO(M3): sync regions prop changes (add/remove/update without remount)

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="w-full h-32 border rounded bg-white" />
      <div className="text-xs text-gray-400">
        TODO: WaveformPlayer (wavesurfer.js + Regions plugin) — see SPEC.md §8.4.3
      </div>
    </div>
  );
}
