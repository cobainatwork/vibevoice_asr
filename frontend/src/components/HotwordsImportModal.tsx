import { useState } from "react";
import { X, Upload } from "lucide-react";
import type { HotwordsImportMode } from "../api/types";

interface Props {
  open: boolean;
  onClose: () => void;
  onImport: (file: File, mode: HotwordsImportMode) => Promise<void>;
}

export function HotwordsImportModal({ open, onClose, onImport }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<HotwordsImportMode>("append");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const submit = async () => {
    if (!file) return;
    setSubmitting(true);
    try {
      await onImport(file, mode);
      setFile(null);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="bg-white rounded-lg shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900">匯入 Hotwords</h3>
          <button type="button" aria-label="關閉" onClick={onClose} className="cursor-pointer text-slate-500 hover:text-slate-700 transition-colors duration-200"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-slate-700 mb-2">選擇檔案（.txt，一詞一行 UTF-8，上限 1 MB）</label>
            <input type="file" accept=".txt,text/plain" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm cursor-pointer file:mr-3 file:px-3 file:py-1 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 file:cursor-pointer hover:file:bg-blue-100 file:transition-colors file:duration-200" />
          </div>
          <fieldset>
            <legend className="text-sm text-slate-700 mb-2">模式</legend>
            <label className="flex items-start gap-2 mb-2 cursor-pointer">
              <input type="radio" name="mode" value="append" checked={mode === "append"} onChange={() => setMode("append")} className="mt-1 cursor-pointer" />
              <span className="text-sm">
                <strong>Append</strong>：與現有 list 合併，重複詞自動略過
              </span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="radio" name="mode" value="replace" checked={mode === "replace"} onChange={() => setMode("replace")} className="mt-1 cursor-pointer" />
              <span className="text-sm">
                <strong>Replace</strong>：清空現有 list 後整批換新（不可復原）
              </span>
            </label>
          </fieldset>
        </div>
        <div className="flex justify-end gap-2 pt-4 mt-4 border-t border-slate-200">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 cursor-pointer hover:text-slate-900 transition-colors duration-200">取消</button>
          <button type="button" onClick={submit} disabled={!file || submitting} className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200">
            <Upload className="w-4 h-4" /> {submitting ? "上傳中..." : "匯入"}
          </button>
        </div>
      </div>
    </div>
  );
}
