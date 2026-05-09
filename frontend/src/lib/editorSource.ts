import { jobsApi } from "../api/jobs";
import { datasetsApi } from "../api/datasets";
import type { ProjectOut, Segment } from "../api/types";

export interface EditorLoadResult {
  segments: Segment[]; // UI 內部 1-indexed speaker_id
  audioUrl: string;
  durationSec: number;
  title: string; // 標頭顯示用，例如 "audio.wav" 或 "Dataset #12"
}

export interface EditorSource {
  load(): Promise<EditorLoadResult>;
  save(snapshot: Segment[]): Promise<void>;
}

/**
 * Job 編輯來源：segments / audio / metadata 從 Job 來，
 * 存回 jobsApi.patchSegments。Job.segments 已是 UI 用 1-indexed speaker_id，
 * 無需轉換。
 */
export function jobEditorSource(jobId: string, _project: ProjectOut): EditorSource {
  return {
    async load() {
      const job = await jobsApi.get(jobId);
      return {
        segments: job.segments ?? [],
        audioUrl: jobsApi.audioUrl(jobId),
        durationSec: job.duration_sec ?? 0,
        title: job.filename,
      };
    },
    async save(snapshot) {
      await jobsApi.patchSegments(jobId, snapshot);
    },
  };
}

/**
 * Dataset 編輯來源：dataset label.segments 是 0-indexed speaker，UI 用 1-indexed。
 * Save 時：先取最新 label 完整內容（保留 audio_duration / audio_path /
 * customized_context），僅替換 segments 欄位後 PATCH。
 */
export function datasetEditorSource(itemId: number, _project: ProjectOut): EditorSource {
  return {
    async load() {
      const item = await datasetsApi.get(itemId);
      return {
        segments: item.label.segments.map((s) => ({
          speaker_id: s.speaker + 1, // 0-indexed → 1-indexed
          text: s.text,
          start_time: s.start,
          end_time: s.end,
        })),
        audioUrl: datasetsApi.audioUrl(itemId),
        durationSec: item.duration_sec,
        title: `Dataset #${itemId}`,
      };
    },
    async save(snapshot) {
      const item = await datasetsApi.get(itemId);
      const newLabel = {
        ...item.label,
        segments: snapshot.map((s) => ({
          speaker: Math.max(0, s.speaker_id - 1), // 1-indexed → 0-indexed
          text: s.text,
          start: s.start_time,
          end: s.end_time,
        })),
      };
      await datasetsApi.patch(itemId, { label: newLabel });
    },
  };
}
