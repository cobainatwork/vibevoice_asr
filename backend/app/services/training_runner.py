"""
LoRA training orchestration.

See SPEC.md §10.
M4 milestone.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def prepare_dataset(project_id: int, dataset_item_ids: list[int],
                    staging_dir: Path) -> Path:
    """
    Materialize a training-ready dataset directory.

    For each dataset_item:
      - symlink audio file as {idx}.{ext}
      - write {idx}.json with audio_path = {idx}.{ext}

    Returns staging_dir.
    """
    # TODO(M4)
    raise NotImplementedError


def build_torchrun_cmd(hyperparams: dict, nproc_per_node: int = 1) -> list[str]:
    """Construct torchrun command for vendor lora_finetune.py."""
    return [
        "torchrun", f"--nproc_per_node={nproc_per_node}",
        "/app/finetuning-asr/lora_finetune.py",
        "--model_path", "microsoft/VibeVoice-ASR",
        "--data_dir", "/data",
        "--output_dir", "/output",
        "--num_train_epochs", str(hyperparams["epochs"]),
        "--per_device_train_batch_size", str(hyperparams["batch_size"]),
        "--gradient_accumulation_steps", str(hyperparams["grad_accum"]),
        "--learning_rate", str(hyperparams["lr"]),
        "--lora_r", str(hyperparams["lora_r"]),
        "--lora_alpha", str(hyperparams["lora_alpha"]),
        "--lora_dropout", str(hyperparams["lora_dropout"]),
        "--warmup_ratio", str(hyperparams["warmup_ratio"]),
        "--weight_decay", str(hyperparams["weight_decay"]),
        *(["--max_audio_length", str(hyperparams["max_audio_length"])]
          if hyperparams.get("max_audio_length") else []),
        "--gradient_checkpointing",
        "--bf16",
        "--logging_steps", "5",
        "--save_steps", "100",
        "--save_total_limit", "2",
        "--report_to", "none",
    ]


async def run_training(run_id: str) -> None:
    """
    Worker entrypoint.

    1. PREPARING: prepare staging directory
    2. (if !concurrent) stop vLLM
    3. TRAINING: docker run train container, tail logs
    4. MERGING: docker run merge container
    5. Register ModelVersion
    6. (if !concurrent) start vLLM (with current active model)
    7. status=DONE
    """
    # TODO(M4)
    raise NotImplementedError


async def run_merge(adapter_path: Path, output_path: Path) -> None:
    """
    Run a short container that loads base + adapter, merge_and_unload, save.

    Uses train.Dockerfile image. Command:
        python -c "<merge script>"
    """
    # TODO(M4)
    raise NotImplementedError
