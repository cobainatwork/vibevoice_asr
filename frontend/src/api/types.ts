// 與 backend/app/schemas.py 對齊
// 變更時兩邊必須同步

// === Common ===

export interface Segment {
  start_time: number;
  end_time: number;
  speaker_id: number;
  text: string;
}

export interface ApiErrorBody {
  code: string;
  detail: string;
  [key: string]: unknown;
}

// === Project ===

export interface ProjectIn {
  name: string;
  description?: string;
  hotwords?: string[];
  webhook_url?: string;
}

export interface ProjectPatch {
  name?: string;
  description?: string;
  hotwords?: string[];
  webhook_url?: string;
}

export interface ProjectOut {
  id: number;
  name: string;
  description: string | null;
  hotwords: string[];
  active_model_id: number | null;
  webhook_url: string | null;
  created_at: string;
  updated_at: string;
}

// === Job ===

export type JobStatus = "pending" | "queued" | "running" | "done" | "failed" | "cancelled";
export type JobSource = "admin_upload" | "v1_api_async" | "v1_api_sync" | "v1_api_ws";

export interface JobOut {
  id: string;
  project_id: number;
  source: JobSource;
  filename: string;
  duration_sec: number | null;
  status: JobStatus;
  progress: number;
  chunks_total: number;
  chunks_done: number;
  segments: Segment[] | null;
  raw_text: string | null;
  error: string | null;
  used_hotwords: string[];
  used_model_id: number | null;
  callback_url: string | null;
  metadata_extra: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobCreatedOut {
  job_id: string;
}

// === System ===

export interface HealthOut {
  ok: boolean;
  vllm_status: string;
  redis_status: string;
  db_status: string;
}

export interface VllmStatusOut {
  status: string;
  model: string | null;
  uptime_sec: number | null;
}

export interface ProfileOut {
  profile: string;
  gpu_inference_devices: string;
  gpu_training_devices: string;
  tensor_parallel: number;
  data_parallel: number;
  max_concurrent_requests: number;
  can_concurrent_train: boolean;
  mock_vllm: boolean;
}

export interface QueueInfo {
  pending: number;
  running: number;
  workers: number;
  oldest_age_sec: number;
}

// === Hotwords I/O ===

export type HotwordsImportMode = "append" | "replace";

export interface HotwordsImportResult {
  hotwords: string[];
  added: number;
  replaced: number;
  skipped_duplicates: number;
}
