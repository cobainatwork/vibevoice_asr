import { api } from "./client";
import type { ApiKey, ApiKeyCreated } from "./types";

export const apiKeysApi = {
  list: (projectId: number) =>
    api.get<ApiKey[]>(`/api/admin/projects/${projectId}/api_keys`),
  create: (projectId: number, name: string, expiresAt?: string) =>
    api.post<ApiKeyCreated>(`/api/admin/projects/${projectId}/api_keys`, {
      name,
      expires_at: expiresAt ?? null,
    }),
  rotate: (keyId: number) => api.post<ApiKeyCreated>(`/api/admin/api_keys/${keyId}/rotate`),
  revoke: (keyId: number) => api.del(`/api/admin/api_keys/${keyId}`),
};
