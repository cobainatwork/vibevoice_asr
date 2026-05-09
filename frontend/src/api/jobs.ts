import { api } from "./client";
import type { Job } from "./types";

export const jobsApi = {
  list: (projectId: number) =>
    api.get<Job[]>(`/api/admin/jobs?project_id=${projectId}`),
  get: (id: string) => api.get<Job>(`/api/admin/jobs/${id}`),
  upload: (projectId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("project_id", String(projectId));
    return api.upload<{ job_id: string }>("/api/admin/transcribe", fd);
  },
  cancel: (id: string) => api.post<Job>(`/api/admin/jobs/${id}/cancel`),
  delete: (id: string) => api.del(`/api/admin/jobs/${id}`),
  audioUrl: (id: string) => `/api/admin/jobs/${id}/audio`,
};
