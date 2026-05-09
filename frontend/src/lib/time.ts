/**
 * Time formatting helpers (mirrors backend/app/utils/time_utils.py).
 */

export function secondsToHms(seconds: number, withMs = true): string {
  if (!Number.isFinite(seconds)) return "00:00:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds - h * 3600 - m * 60;
  if (withMs) {
    return `${pad(h)}:${pad(m)}:${s.toFixed(2).padStart(5, "0")}`;
  }
  return `${pad(h)}:${pad(m)}:${pad(Math.floor(s))}`;
}

export function secondsToMs(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${pad(m)}:${s.toFixed(2).padStart(5, "0")}`;
}

export function parseTime(value: string): number {
  // accepts: "3.45", "0:03.45", "0:00:03.45"
  const v = value.trim();
  if (/^\d+(\.\d+)?$/.test(v)) return parseFloat(v);
  let m = v.match(/^(\d+):(\d+):(\d+)(?:\.(\d+))?$/);
  if (m) return +m[1] * 3600 + +m[2] * 60 + +m[3] + (m[4] ? parseFloat("0." + m[4]) : 0);
  m = v.match(/^(\d+):(\d+)(?:\.(\d+))?$/);
  if (m) return +m[1] * 60 + +m[2] + (m[3] ? parseFloat("0." + m[3]) : 0);
  throw new Error(`Bad time: ${value}`);
}

const pad = (n: number) => String(n).padStart(2, "0");
