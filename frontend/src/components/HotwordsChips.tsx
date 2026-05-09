/**
 * Reusable chip-based string list editor.
 *
 * Used by:
 * - Hotwords page
 * - Editor.tsx (for customized_context per-sample)
 */
import { useState } from "react";
import { XIcon } from "lucide-react";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function HotwordsChips({ value, onChange, placeholder = "新增...", disabled }: Props) {
  const [input, setInput] = useState("");

  const add = () => {
    const v = input.trim();
    if (!v) return;
    if (value.includes(v)) {
      setInput("");
      return;
    }
    onChange([...value, v]);
    setInput("");
  };

  const remove = (i: number) => onChange(value.filter((_, idx) => idx !== i));

  return (
    <div className="flex flex-wrap gap-2 items-center p-2 border border-gray-300 rounded bg-white min-h-[3rem]">
      {value.map((v, i) => (
        <span
          key={`${v}-${i}`}
          className="inline-flex items-center gap-1 bg-blue-50 text-blue-700 px-2 py-1 rounded text-sm"
        >
          {v}
          {!disabled && (
            <button onClick={() => remove(i)} className="hover:text-blue-900">
              <XIcon size={12} />
            </button>
          )}
        </span>
      ))}
      {!disabled && (
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            } else if (e.key === "Backspace" && !input && value.length) {
              remove(value.length - 1);
            }
          }}
          onBlur={add}
          placeholder={placeholder}
          className="flex-1 min-w-[6rem] outline-none text-sm"
        />
      )}
    </div>
  );
}
