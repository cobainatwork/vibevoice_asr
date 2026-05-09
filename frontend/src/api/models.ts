import { api } from "./client";
import type { ModelVersion, Project } from "./types";

export const modelsApi = {
  list: (projectId: number) =>
    api.get<ModelVersion[]>(`/api/admin/projects/${projectId}/models`),
  setActive: (projectId: number, modelVersionId: number | null) =>
    api.post<Project>(`/api/admin/projects/${projectId}/active_model`, {
      model_version_id: modelVersionId,
    }),
  delete: (modelId: number) => api.del(`/api/admin/models/${modelId}`),
};
