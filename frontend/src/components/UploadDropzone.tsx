import { useRef, useState } from "react";
import { UploadCloud, Loader2 } from "lucide-react";

interface Props {
  onFile: (f: File) => Promise<void>;
  accept?: string;
  disabled?: boolean;
}

export function UploadDropzone({ onFile, accept = "audio/*,video/mp4,video/webm,video/quicktime", disabled }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  const handle = async (file: File) => {
    setBusy(true);
    try { await onFile(file); }
    finally { setBusy(false); }
  };

  return (
    <div
      onClick={() => !disabled && !busy && ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault(); setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !disabled) handle(f);
      }}
      className={`flex flex-col items-center justify-center gap-2 px-6 py-8 border-2 border-dashed rounded-lg transition-colors duration-200 cursor-pointer ${
        over ? "border-blue-500 bg-blue-50" : "border-slate-300 hover:border-blue-400 hover:bg-slate-50"
      } ${disabled || busy ? "opacity-60 cursor-not-allowed" : ""}`}
    >
      {busy
        ? <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        : <UploadCloud className="w-8 h-8 text-slate-400" />
      }
      <p className="text-sm text-slate-700">
        {busy ? "上傳中..." : "拖入音檔，或點擊選擇"}
      </p>
      <p className="text-xs text-slate-500">支援 wav / mp3 / m4a / mp4 / webm；上限 500 MB / 4 小時</p>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handle(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
