"""
Docker container control — stop/start vLLM, run training jobs.

🔐 SECURITY: only operate on whitelisted images and container names.

See SPEC.md §7.5.7.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import docker
from docker.errors import NotFound

from app.config import get_settings

logger = logging.getLogger(__name__)


# Whitelist — backend can only operate on these
ALLOWED_CONTAINER_NAMES: set[str] = {"vibevoice-vllm"}
ALLOWED_IMAGE_PREFIXES: tuple[str, ...] = (
    "vllm/vllm-openai",
    "vibevoice-train",
    "nvcr.io/nvidia/pytorch",  # train base image
)


def _client() -> docker.DockerClient:
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


def _verify_container_name(name: str) -> None:
    if name not in ALLOWED_CONTAINER_NAMES:
        raise PermissionError(f"Container {name!r} not whitelisted")


def _verify_image(image: str) -> None:
    if not any(image.startswith(p) for p in ALLOWED_IMAGE_PREFIXES):
        raise PermissionError(f"Image {image!r} not whitelisted")


# ============================================================
# vLLM container lifecycle
# ============================================================


async def is_vllm_running() -> bool:
    settings = get_settings()
    try:
        c = _client().containers.get(settings.vllm_container_name)
        return bool(c.status == "running")
    except NotFound:
        return False


async def stop_vllm() -> None:
    """Stop and remove the vLLM container."""
    settings = get_settings()
    _verify_container_name(settings.vllm_container_name)
    try:
        c = _client().containers.get(settings.vllm_container_name)
        c.stop(timeout=30)
        c.remove(force=True)
        logger.info("vLLM container stopped and removed")
    except NotFound:
        logger.info("vLLM container not running, nothing to stop")


async def start_vllm(model_path: str) -> None:
    """Start the vLLM container with given model path mounted."""
    settings = get_settings()
    _verify_container_name(settings.vllm_container_name)
    _verify_image(settings.vllm_docker_image)
    # TODO(M2): docker.containers.run(...) with strategy.vllm_docker_run_args()
    raise NotImplementedError


async def restart_vllm_with_model(model_path: str, ready_timeout: int = 120) -> None:
    """Stop + start with new model. Waits for /v1/models 200."""
    await stop_vllm()
    await start_vllm(model_path)
    await wait_for_vllm_ready(ready_timeout)


async def wait_for_vllm_ready(timeout: int = 120) -> None:
    """Poll /v1/models until 200 OK or timeout."""
    # TODO(M4): import vllm_client.health and poll
    raise NotImplementedError


# ============================================================
# Training container lifecycle
# ============================================================


async def run_training_container(
    run_id: str,
    command: list[str],
    volumes: dict[str, dict],
    gpu_devices: str,
    log_path: Path,
) -> AsyncIterator[str]:
    """
    Run a one-shot training container, yielding log lines as they arrive.

    Caller awaits the iterator AND container exit. After yields complete,
    use docker_client.containers.get(...).wait() to get exit code.
    """
    settings = get_settings()
    _verify_image(settings.train_docker_image)

    # TODO(M4):
    # container = _client().containers.run(
    #     image=settings.train_docker_image,
    #     command=command,
    #     volumes=volumes,
    #     environment={"CUDA_VISIBLE_DEVICES": gpu_devices},
    #     detach=True,
    #     auto_remove=False,
    #     device_requests=[...],
    # )
    # for log_chunk in container.logs(stream=True, follow=True):
    #     line = log_chunk.decode(errors="ignore")
    #     yield line  # also append to log_path
    # exit_code = container.wait()["StatusCode"]
    raise NotImplementedError


async def run_merge_container(adapter_path: Path, output_path: Path) -> None:
    """Run a short container that merges LoRA into base model."""
    # TODO(M4): same image as training, command runs merge script
    raise NotImplementedError
