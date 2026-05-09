import { api } from "./client";
import type {
  HotwordsImportMode,
  HotwordsImportResult,
  ProjectIn,
  ProjectOut,
  ProjectPatch,
} from "./types";

const BASE = "/api/admin/projects";

export const projectsApi = {
  list: () => api.get<ProjectOut[]>(BASE),
  get: (id: number) => api.get<ProjectOut>(`${BASE}/${id}`),
  create: (data: ProjectIn) => api.post<ProjectOut>(BASE, data),
  update: (id: number, data: ProjectPatch) =>
    api.put<ProjectOut>(`${BASE}/${id}`, data),
  remove: (id: number) => api.del<void>(`${BASE}/${id}`),

  // hotwords
  getHotwords: (id: number) => api.get<string[]>(`${BASE}/${id}/hotwords`),
  setHotwords: (id: number, words: string[]) =>
    api.put<string[]>(`${BASE}/${id}/hotwords`, words),

  exportHotwords: async (id: number): Promise<Blob> => {
    return api.get<Blob>(`${BASE}/${id}/hotwords/export`, {
      query: { format: "txt" },
      responseType: "blob",
    });
  },

  importHotwords: (id: number, file: File, mode: HotwordsImportMode) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode);
    return api.postForm<HotwordsImportResult>(
      `${BASE}/${id}/hotwords/import`,
      fd,
    );
  },
};
