import { useState } from "react";
import { datasetsApi } from "../api/datasets";
import type { ImportFormat, DatasetItem } from "../api/types";
import { useToast } from "../hooks/useToast";

interface Props {
  open: boolean;
  projectId: number;
  onClose: () => void;
  onImported: (item: DatasetItem) => void;
}

const FORMATS: { value: ImportFormat; label: string }[] = [
  { value: "json", label: "JSON（訓練格式）" },
  { value: "xlsx", label: "Excel（.xlsx）" },
  { value: "srt", label: "SubRip（.srt）" },
  { value: "txt", label: "純文字（.txt）" },
];

export function DatasetImportModal({ open, projectId, onClose, onImported }: Props) {
  const [audio, setAudio] = useState<File | null>(null);
  const [label, setLabel] = useState<File | null>(null);
  const [format, setFormat] = useState<ImportFormat>("xlsx");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  if (!open) return null;

  const submit = async () => {
    if (!audio || !label) {
      setError("請選擇 audio 與 label 檔");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const item = await datasetsApi.importItem(projectId, audio, label, format);
      toast.success("匯入完成");
      onImported(item);
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "匯入失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded p-6 w-[480px] max-w-full">
        <h2 className="text-lg font-semibold mb-4">匯入 Dataset</h2>
        <div className="space-y-3">
          <label className="block">
            <span className="text-sm text-slate-700">音檔</span>
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setAudio(e.target.files?.[0] ?? null)}
              className="block w-full mt-1"
            />
          </label>
          <label className="block">
            <span className="text-sm text-slate-700">標註檔</span>
            <input
              type="file"
              onChange={(e) => setLabel(e.target.files?.[0] ?? null)}
              className="block w-full mt-1"
            />
          </label>
          <label className="block">
            <span className="text-sm text-slate-700">格式</span>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as ImportFormat)}
              className="block w-full mt-1 border rounded px-2 py-1"
            >
              {FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="px-3 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50"
          >
            {submitting ? "匯入中..." : "確定匯入"}
          </button>
        </div>
      </div>
    </div>
  );
}
