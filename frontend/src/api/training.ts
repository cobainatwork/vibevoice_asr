import { api } from "./client";
import type { TrainingHyperparams, TrainingRun } from "./types";

export const trainingApi = {
  list: (projectId: number) =>
    api.get<TrainingRun[]>(`/api/admin/training?project_id=${projectId}`),
  get: (runId: string) => api.get<TrainingRun>(`/api/admin/training/${runId}`),
  start: (
    projectId: number,
    datasetItemIds: number[],
    hyperparams: TrainingHyperparams,
  ) =>
    api.post<TrainingRun>("/api/admin/training", {
      project_id: projectId,
      dataset_item_ids: datasetItemIds,
      hyperparams,
    }),
  cancel: (runId: string) => api.post<TrainingRun>(`/api/admin/training/${runId}/cancel`),
  logUrl: (runId: string) => `/api/admin/training/${runId}/log`,
};
