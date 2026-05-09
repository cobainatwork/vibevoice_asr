/**
 * Base HTTP client wrapper.
 *
 * All API modules (projects.ts, jobs.ts, ...) should use these helpers.
 */

const BASE = (import.meta as any).env?.VITE_API_BASE || "";

export class ApiError extends Error {
  status: number;
  code: string | null;
  constructor(status: number, code: string | null, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = {
    method,
    headers: body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    init.body = body instanceof FormData ? body : JSON.stringify(body);
  }
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) {
    let detail = r.statusText;
    let code: string | null = null;
    try {
      const j = await r.json();
      detail = j.detail || detail;
      code = j.code || null;
    } catch { /* ignore */ }
    throw new ApiError(r.status, code, detail);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

export const api = {
  get:    <T = any>(path: string) => request<T>("GET", path),
  post:   <T = any>(path: string, body?: unknown) => request<T>("POST", path, body),
  put:    <T = any>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del:    <T = any>(path: string) => request<T>("DELETE", path),
  upload: <T = any>(path: string, fd: FormData) => request<T>("POST", path, fd),
};

/** SSE helper for streaming endpoints (e.g., /api/admin/training/{id}/log). */
export function sse(path: string, onMessage: (data: string) => void): () => void {
  const es = new EventSource(`${BASE}${path}`);
  es.onmessage = (e) => onMessage(e.data);
  return () => es.close();
}
