import { api } from "./client";
import type { HealthOut, ProfileOut, QueueInfo, VllmStatusOut } from "./types";

const ADMIN = "/api/admin";

export const systemApi = {
  health: () => api.get<HealthOut>(`${ADMIN}/system/health`),
  vllmStatus: () => api.get<VllmStatusOut>(`${ADMIN}/system/vllm_status`),
  profile: () => api.get<ProfileOut>(`${ADMIN}/system/profile`),
  queue: () => api.get<QueueInfo>(`${ADMIN}/system/queue`),
};
