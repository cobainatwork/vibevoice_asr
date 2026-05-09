import { useToastStore } from "../stores/toastStore";
import type { ApiErrorBody } from "./types";

const BASE_URL = (import.meta as any).env?.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
    public body: ApiErrorBody,
  ) {
    super(`${code}: ${detail}`);
  }
}

interface RequestOpts {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
  responseType?: "json" | "blob" | "text";
}

function _toUserMessage(status: number, body: ApiErrorBody | null): string {
  if (status === 401) return "請重新登入";
  if (status >= 500) return "服務異常，請稍後再試";
  if (body?.detail) return body.detail;
  return `錯誤 ${status}`;
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const url = new URL(BASE_URL + path, window.location.origin);
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null) url.searchParams.append(k, String(v));
    }
  }

  const init: RequestInit = {
    method: opts.method ?? "GET",
    signal: opts.signal,
  };
  if (opts.formData) {
    init.body = opts.formData;
  } else if (opts.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }

  let resp: Response;
  try {
    resp = await fetch(url.toString(), init);
  } catch (e) {
    useToastStore.getState().push("error", "網路連線失敗");
    throw e;
  }

  if (!resp.ok) {
    let body: ApiErrorBody | null = null;
    try {
      const j = await resp.json();
      body = j.detail && typeof j.detail === "object" ? (j.detail as ApiErrorBody) : null;
    } catch {
      // ignore
    }
    const code = body?.code ?? "http_error";
    const detail = body?.detail ?? `HTTP ${resp.status}`;
    useToastStore.getState().push("error", _toUserMessage(resp.status, body));
    throw new ApiError(resp.status, code, detail, body ?? { code, detail });
  }

  if (opts.responseType === "blob") return (await resp.blob()) as unknown as T;
  if (opts.responseType === "text") return (await resp.text()) as unknown as T;
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOpts, "method" | "body" | "formData">) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOpts, "method" | "body">) =>
    request<T>(path, { ...opts, method: "POST", body }),
  postForm: <T>(path: string, formData: FormData, opts?: Omit<RequestOpts, "method" | "formData">) =>
    request<T>(path, { ...opts, method: "POST", formData }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOpts, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOpts, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PUT", body }),
  del: <T>(path: string, opts?: Omit<RequestOpts, "method" | "body" | "formData">) =>
    request<T>(path, { ...opts, method: "DELETE" }),
};
