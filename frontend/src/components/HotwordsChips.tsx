import { X } from "lucide-react";
import { useState } from "react";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
}

export function HotwordsChips({ value, onChange }: Props) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const tokens = draft.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    if (tokens.length === 0) return;
    const next = [...value];
    for (const t of tokens) if (!next.includes(t)) next.push(t);
    onChange(next);
    setDraft("");
  };

  const remove = (i: number) => {
    const next = [...value];
    next.splice(i, 1);
    onChange(next);
  };

  return (
    <div className="flex flex-wrap gap-2 p-3 border border-slate-300 rounded-md bg-white min-h-[3rem] focus-within:ring-2 focus-within:ring-blue-500">
      {value.map((w, i) => (
        <span key={`${w}-${i}`} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-900 text-sm rounded">
          {w}
          <button type="button" aria-label={`刪除 ${w}`} onClick={() => remove(i)} className="cursor-pointer text-blue-600 hover:text-blue-900 transition-colors duration-200"><X className="w-3 h-3" /></button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
            remove(value.length - 1);
          }
        }}
        onBlur={commit}
        placeholder={value.length === 0 ? "輸入 hotwords，Enter 或逗號分隔..." : "+ 新增"}
        className="flex-1 min-w-[8rem] outline-none text-sm bg-transparent"
      />
    </div>
  );
}
