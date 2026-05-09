import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X } from "lucide-react";
import type { ProjectOut } from "../api/types";

const schema = z.object({
  name: z.string().min(1, "必填").max(100),
  description: z.string().optional(),
  webhook_url: z.string().url("格式不正確").optional().or(z.literal("")),
  hotwords_text: z.string().optional(), // 逗號或換行分隔
});

type FormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  onClose: () => void;
  initial?: ProjectOut;
  onSubmit: (data: { name: string; description?: string; webhook_url?: string; hotwords: string[] }) => Promise<void>;
}

function parseHotwords(text: string | undefined): string[] {
  if (!text) return [];
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ProjectFormModal({ open, onClose, initial, onSubmit }: Props) {
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (open) {
      reset({
        name: initial?.name ?? "",
        description: initial?.description ?? "",
        webhook_url: initial?.webhook_url ?? "",
        hotwords_text: (initial?.hotwords ?? []).join("\n"),
      });
    }
  }, [open, initial, reset]);

  if (!open) return null;

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      name: values.name.trim(),
      description: values.description?.trim() || undefined,
      webhook_url: values.webhook_url?.trim() || undefined,
      hotwords: parseHotwords(values.hotwords_text),
    });
    onClose();
  });

  return (
    <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900">{initial ? "編輯專案" : "新增專案"}</h3>
          <button type="button" aria-label="關閉" onClick={onClose} className="cursor-pointer text-slate-500 hover:text-slate-700 transition-colors duration-200"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm text-slate-700 mb-1">名稱</label>
            <input {...register("name")} className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-1">描述（選填）</label>
            <textarea {...register("description")} rows={2} className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-1">Webhook URL（選填）</label>
            <input {...register("webhook_url")} className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            {errors.webhook_url && <p className="text-xs text-red-600 mt-1">{errors.webhook_url.message}</p>}
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-1">Hotwords（逗號或換行分隔，可在 Hotwords 頁細部編輯）</label>
            <textarea {...register("hotwords_text")} rows={3} className="w-full border border-slate-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="微軟, VibeVoice, ..." />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 cursor-pointer hover:text-slate-900 transition-colors duration-200">取消</button>
            <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200">{isSubmitting ? "儲存中..." : "儲存"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
