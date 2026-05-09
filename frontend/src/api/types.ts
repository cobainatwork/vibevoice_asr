/**
 * TypeScript types matching backend schemas.py.
 *
 * Keep in sync with backend/app/schemas.py.
 */

export interface Project {
  id: number;
  name: string;
  description: string | null;
  hotwords: string[];
  active_model_id: number | null;
  webhook_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Segment {
  start_time: number;
  end_time: number;
  speaker_id: number;  // 1-indexed
  text: string;
}

export type JobStatus = "pending" | "queued" | "running" | "done" | "failed" | "cancelled";
export type JobSource = "admin_upload" | "v1_api_async" | "v1_api_sync" | "v1_api_ws";

export interface Job {
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

export type DatasetSource =
  | "uploaded"
  | "from_transcription"
  | "imported_xlsx"
  | "imported_csv"
  | "imported_srt"
  | "imported_vtt"
  | "imported_txt"
  | "imported_json";

export interface DatasetItem {
  id: number;
  project_id: number;
  audio_path: string;
  label: TrainingLabel;
  duration_sec: number;
  source: DatasetSource;
  source_job_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** Canonical training JSON format (0-indexed speaker). See SPEC.md §9.1. */
export interface TrainingLabel {
  audio_duration: number;
  audio_path: string;
  segments: TrainingSegment[];
  customized_context?: string[];
}

export interface TrainingSegment {
  speaker: number;   // 0-indexed
  text: string;
  start: number;
  end: number;
}

export type TrainingStatus =
  | "pending"
  | "preparing"
  | "training"
  | "merging"
  | "done"
  | "failed"
  | "cancelled";

export interface TrainingHyperparams {
  lora_r: number;
  lora_alpha: number;
  lora_dropout: number;
  lr: number;
  epochs: number;
  batch_size: number;
  grad_accum: number;
  warmup_ratio: number;
  weight_decay: number;
  max_audio_length: number | null;
}

export interface TrainingRun {
  id: string;
  project_id: number;
  status: TrainingStatus;
  hyperparams: TrainingHyperparams;
  dataset_item_ids: number[];
  output_path: string | null;
  merged_path: string | null;
  log_path: string;
  metrics: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export type ModelType = "base" | "merged" | "lora";

export interface ModelVersion {
  id: number;
  project_id: number | null;
  name: string;
  type: ModelType;
  path: string;
  training_run_id: string | null;
  size_gb: number | null;
  created_at: string;
}

export interface ApiKey {
  id: number;
  project_id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  /** Plain key — only returned at create/rotate time. */
  key: string;
}

export interface IntegrationCall {
  id: number;
  api_key_id: number | null;
  project_id: number;
  job_id: string | null;
  endpoint: string;
  method: string;
  status_code: number;
  duration_ms: number;
  source_ip: string | null;
  user_agent: string | null;
  error: string | null;
  created_at: string;
}
