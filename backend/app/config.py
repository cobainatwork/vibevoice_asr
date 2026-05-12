"""
Centralized configuration loaded from environment variables.

See SPEC.md §7.6 and .env.example for the full list of variables.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DeploymentProfileT = Literal["single", "single-large", "dual-split", "dual-tp", "multi"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === Deployment ===
    deployment_profile: DeploymentProfileT = "single"
    gpu_inference_devices: str = "0"
    gpu_training_devices: str = "0"
    worker_replicas: int = 1

    # === vLLM ===
    vllm_base_url: str = "http://host.docker.internal:8000"
    vllm_container_name: str = "vibevoice-vllm"
    vllm_tensor_parallel: int = 1
    vllm_data_parallel: int = 1
    vllm_max_model_len: int = 65536
    vllm_max_num_seqs: int = 64
    vllm_gpu_memory_utilization: float = 0.85
    vllm_default_model: str = "microsoft/VibeVoice-ASR"
    vllm_docker_image: str = "vllm/vllm-openai:v0.14.1"

    # === Backend ===
    backend_port: int = 8080
    backend_db_url: str = "sqlite:////data/app.db"
    backend_log_level: str = "INFO"
    backend_data_dir: Path = Path("/data")
    backend_max_upload_mb: int = 500

    # === Audio ===
    max_audio_duration_sec: int = 14400
    # 實測 vLLM 對 >60s 音檔容易陷入 repetition loop（理論上下文 65k 能吃到 55min
    # 但生成穩定性實際只到 30-60s）。預設 60s threshold + 55s chunk。
    # 長音檔被切成 N 段獨立推論再 merge。
    auto_split_threshold_sec: int = 60
    split_chunk_duration_sec: int = 55
    # === 已廢棄（silence-based 切點不需要 overlap）、保留欄位避免 .env 破 ===
    # split_overlap_sec 仍可在 .env 設、但 audio_splitter 不再讀。
    split_overlap_sec: int = 5
    sync_audio_max_duration_sec: int = 120

    # === Silence-based slicer 參數（M+1 切換點）===
    # silence detection RMS 振幅閾值（dB）。-40 是 audio-slicer 預設、適合多數錄音。
    silence_threshold_db: float = -40.0

    # 每段最短長度（ms）。audio-slicer 預設 5000 對歌曲設計；
    # ASR 場景改 2000（短句保留、避免過度合併）。
    silence_min_length_ms: int = 2000

    # silence 至少多長才視為切點（ms）。
    silence_min_interval_ms: int = 300

    # RMS 計算窗口 hop size（ms）。
    silence_hop_size_ms: int = 20

    # 切點處保留前後 silence 的最大長度（ms）。
    silence_max_kept_ms: int = 1000

    # === ASR Pipeline ===
    # 並行 chunk 推論上限（含 retry sub-chunks 共享同一 semaphore）。
    # 預設 8：vLLM max_num_seqs=64 的 1/8、留空間給 admin 同時 transcribe。
    chunk_concurrency: int = 8
    # partial chunk 偵測後遞迴切半 retry 的最大深度（0=不 retry，2=最多 4 個 sub-sub-chunks）
    chunk_retry_max_depth: int = 2

    # === Redis & Queue ===
    redis_url: str = "redis://redis:6379/0"
    worker_max_jobs: int = 8
    ws_idle_timeout_sec: int = 60

    # === Training ===
    train_docker_image: str = "vibevoice-train:latest"

    # === HuggingFace ===
    hf_home: Path = Path("/data/hf_cache")
    hf_hub_offline: bool = False

    # === Webhook ===
    webhook_timeout_sec: int = 30
    webhook_max_attempts: int = 7

    # === API Key ===
    api_key_prefix: str = "vva_"
    api_key_length: int = 32

    # === Idempotency ===
    idempotency_ttl_sec: int = 86400

    # === Observability ===
    metrics_enabled: bool = True

    # === Dev / Mock ===
    # 啟用後 vllm_client.transcribe 不打 vLLM，回固定假 segments，
    # 給 Windows dev 機（無 GPU）走完整 pipeline 用。詳見 SPEC.md §5.6。
    mock_vllm: bool = False

    # === Computed ===
    @property
    def upload_dir(self) -> Path:
        return self.backend_data_dir / "uploads"

    @property
    def datasets_dir(self) -> Path:
        return self.backend_data_dir / "datasets"

    @property
    def staging_dir(self) -> Path:
        return self.backend_data_dir / "staging"

    @property
    def loras_dir(self) -> Path:
        return self.backend_data_dir / "loras"

    @property
    def merged_dir(self) -> Path:
        return self.backend_data_dir / "merged"

    @property
    def logs_dir(self) -> Path:
        return self.backend_data_dir / "logs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def ensure_data_dirs(s: Settings) -> None:
    """Create required data subdirs on startup."""
    for d in [s.upload_dir, s.datasets_dir, s.staging_dir,
              s.loras_dir, s.merged_dir, s.logs_dir, s.hf_home]:
        d.mkdir(parents=True, exist_ok=True)
