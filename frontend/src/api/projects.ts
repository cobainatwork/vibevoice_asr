import { api } from "./client";
import type { Project } from "./types";

export const projectsApi = {
  list: () => api.get<Project[]>("/api/admin/projects"),
  get: (id: number) => api.get<Project>(`/api/admin/projects/${id}`),
  create: (data: Partial<Project>) => api.post<Project>("/api/admin/projects", data),
  update: (id: number, data: Partial<Project>) =>
    api.put<Project>(`/api/admin/projects/${id}`, data),
  delete: (id: number) => api.del(`/api/admin/projects/${id}`),

  getHotwords: (id: number) => api.get<string[]>(`/api/admin/projects/${id}/hotwords`),
  setHotwords: (id: number, hotwords: string[]) =>
    api.put<string[]>(`/api/admin/projects/${id}/hotwords`, hotwords),
};
