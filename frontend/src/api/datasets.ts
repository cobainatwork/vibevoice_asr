import { api } from "./client";
import type { DatasetItem, TrainingLabel } from "./types";

export const datasetsApi = {
  list: (projectId: number) =>
    api.get<DatasetItem[]>(`/api/admin/datasets?project_id=${projectId}`),
  get: (id: number) => api.get<DatasetItem>(`/api/admin/datasets/${id}`),
  import: (projectId: number, audio: File, label: File, format: string) => {
    const fd = new FormData();
    fd.append("audio", audio);
    fd.append("label", label);
    fd.append("project_id", String(projectId));
    fd.append("format", format);
    return api.upload<DatasetItem>("/api/admin/datasets/import", fd);
  },
  fromJob: (jobId: string, notes?: string) =>
    api.post<DatasetItem>(`/api/admin/datasets/from_job/${jobId}`, { notes }),
  update: (id: number, label: TrainingLabel, notes?: string) =>
    api.put<DatasetItem>(`/api/admin/datasets/${id}`, { label, notes }),
  delete: (id: number) => api.del(`/api/admin/datasets/${id}`),
  audioUrl: (id: number) => `/api/admin/datasets/${id}/audio`,
  templateUrl: (format: string) => `/api/admin/datasets/templates/${format}`,
  exportUrl: (id: number, format: string) =>
    `/api/admin/datasets/${id}/export?format=${format}`,
};
