import { useRef, useState } from "react";
import { UploadCloud, Loader2, Youtube } from "lucide-react";
import { isYoutubeUrl } from "../lib/youtubeUrl";

interface Props {
  onFile: (f: File) => Promise<void>;
  onYoutubeUrl?: (url: string) => Promise<void>;
  accept?: string;
  disabled?: boolean;
}

type Tab = "file" | "youtube";

export function UploadDropzone({
  onFile,
  onYoutubeUrl,
  accept = "audio/*,video/mp4,video/webm,video/quicktime",
  disabled,
}: Props) {
  const [tab, setTab] = useState<Tab>("file");
  const [busy, setBusy] = useState(false);

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
      <div className="flex border-b border-slate-200 bg-slate-50">
        <TabButton
          active={tab === "file"}
          onClick={() => setTab("file")}
          icon={<UploadCloud className="w-4 h-4" />}
          label="檔案上傳"
        />
        {onYoutubeUrl && (
          <TabButton
            active={tab === "youtube"}
            onClick={() => setTab("youtube")}
            icon={<Youtube className="w-4 h-4" />}
            label="YouTube URL"
          />
        )}
      </div>
      <div className="p-4">
        {tab === "file" ? (
          <FileDropzonePanel
            onFile={onFile}
            accept={accept}
            disabled={disabled}
            busy={busy}
            setBusy={setBusy}
          />
        ) : (
          <YoutubeUrlPanel
            onSubmit={onYoutubeUrl!}
            disabled={disabled}
            busy={busy}
            setBusy={setBusy}
          />
        )}
      </div>
    </div>
  );
}


function TabButton({
  active, onClick, icon, label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm cursor-pointer transition-colors duration-200 ${
        active
          ? "bg-white text-blue-600 border-b-2 border-blue-500"
          : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {icon} {label}
    </button>
  );
}


function FileDropzonePanel({
  onFile, accept, disabled, busy, setBusy,
}: {
  onFile: (f: File) => Promise<void>;
  accept: string;
  disabled: boolean | undefined;
  busy: boolean;
  setBusy: (b: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

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
      <p className="text-xs text-slate-500">
        支援 wav / mp3 / m4a / mp4 / webm；上限 500 MB / 4 小時
      </p>
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


function YoutubeUrlPanel({
  onSubmit, disabled, busy, setBusy,
}: {
  onSubmit: (url: string) => Promise<void>;
  disabled: boolean | undefined;
  busy: boolean;
  setBusy: (b: boolean) => void;
}) {
  const [url, setUrl] = useState("");
  const valid = isYoutubeUrl(url);

  const submit = async () => {
    if (!valid || disabled || busy) return;
    setBusy(true);
    try { await onSubmit(url.trim()); setUrl(""); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={disabled || busy}
          className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-colors duration-200"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!valid || disabled || busy}
          className="px-4 py-2 bg-blue-500 text-white text-sm rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "開始"}
        </button>
      </div>
      <div className="text-xs text-slate-500 space-y-1">
        <p>
          請確認影片授權狀態（本功能僅供內部研究 / dataset 製作使用）。
        </p>
        <p>
          不抓取 YouTube 自動生成字幕，僅抓人工上傳字幕。
        </p>
      </div>
      {url && !valid && (
        <p className="text-xs text-red-600">
          URL 格式不符，需為 youtube.com / youtu.be 連結。
        </p>
      )}
    </div>
  );
}
