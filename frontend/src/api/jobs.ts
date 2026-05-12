import { api } from "./client";
import type { JobCreatedOut, JobOut, Segment } from "./types";

const ADMIN = "/api/admin";

export const jobsApi = {
  list: (opts: { project_id?: number; status?: string; limit?: number; offset?: number } = {}) =>
    api.get<JobOut[]>(`${ADMIN}/jobs`, { query: opts }),
  get: (id: string) => api.get<JobOut>(`${ADMIN}/jobs/${id}`),
  cancel: (id: string) => api.post<JobOut>(`${ADMIN}/jobs/${id}/cancel`),
  remove: (id: string) => api.del<void>(`${ADMIN}/jobs/${id}`),
  audioUrl: (id: string) => `${import.meta.env.VITE_API_BASE || ""}${ADMIN}/jobs/${id}/audio`,

  upload: (file: File, projectId: number) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("project_id", String(projectId));
    return api.postForm<JobCreatedOut>(`${ADMIN}/transcribe`, fd);
  },

  transcribeFromYoutube: (url: string, projectId: number) =>
    api.post<JobCreatedOut>(`${ADMIN}/transcribe/from_youtube`, {
      url,
      project_id: projectId,
    }),

  patchSegments: (id: string, segments: Segment[]) =>
    api.patch<JobOut>(`${ADMIN}/jobs/${id}/segments`, { segments }),
};
