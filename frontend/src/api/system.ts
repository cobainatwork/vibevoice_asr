import { api } from "./client";

export const systemApi = {
  health: () => api.get("/api/admin/system/health"),
  vllmStatus: () => api.get("/api/admin/system/vllm_status"),
  profile: () => api.get("/api/admin/system/profile"),
  gpu: () => api.get("/api/admin/system/gpu"),
  queue: () => api.get("/api/admin/system/queue"),
};
