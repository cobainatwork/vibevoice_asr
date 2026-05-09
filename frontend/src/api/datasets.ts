import { api } from "./client";
import type {
  DatasetItem,
  ExportFormat,
  ImportFormat,
  TemplateFormat,
} from "./types";

const ADMIN = "/api/admin";
const BASE = import.meta.env.VITE_API_BASE || "";

export const datasetsApi = {
  list: (projectId: number) =>
    api.get<DatasetItem[]>(`${ADMIN}/datasets`, { query: { project_id: projectId } }),

  get: (id: number) => api.get<DatasetItem>(`${ADMIN}/datasets/${id}`),

  importItem: (
    projectId: number,
    audio: File,
    label: File,
    format: ImportFormat,
  ) => {
    const fd = new FormData();
    fd.append("audio", audio);
    fd.append("label", label);
    fd.append("project_id", String(projectId));
    fd.append("format", format);
    return api.postForm<DatasetItem>(`${ADMIN}/datasets/import`, fd);
  },

  fromJob: (jobId: string, notes?: string) =>
    api.post<DatasetItem>(`${ADMIN}/datasets/from_job/${jobId}`, {
      notes: notes ?? null,
    }),

  patch: (id: number, payload: { label?: object; notes?: string }) =>
    api.put<DatasetItem>(`${ADMIN}/datasets/${id}`, payload),

  delete: (id: number) => api.del<void>(`${ADMIN}/datasets/${id}`),

  audioUrl: (id: number) => `${BASE}${ADMIN}/datasets/${id}/audio`,

  templateUrl: (format: TemplateFormat) =>
    `${BASE}${ADMIN}/datasets/templates/${format}`,

  exportUrl: (id: number, format: ExportFormat) =>
    `${BASE}${ADMIN}/datasets/${id}/export?format=${format}`,
};
