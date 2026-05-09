"""
Deployment strategies — abstract over single/dual/multi GPU configurations.

See SPEC.md §4 (profiles) and §7.5.6.
"""
from __future__ import annotations

from typing import Protocol

from app.config import get_settings


class DeploymentStrategy(Protocol):
    profile: str

    def vllm_docker_run_args(self, model_path: str) -> list[str]: ...
    def vllm_command(self) -> list[str]: ...
    def can_concurrent_train(self) -> bool: ...
    def training_gpu_devices(self) -> str: ...
    def training_nproc_per_node(self) -> int: ...
    def vllm_max_concurrent_requests(self) -> int: ...


class _Base:
    """Shared helpers."""
    def vllm_command(self) -> list[str]:
        return ["python3", "/app/vllm_plugin/scripts/start_server.py"]


class SingleGPU(_Base):
    profile = "single"

    def vllm_docker_run_args(self, model_path: str) -> list[str]:
        return ["--gpus", "all"]

    def can_concurrent_train(self) -> bool:
        return False

    def training_gpu_devices(self) -> str:
        return "0"

    def training_nproc_per_node(self) -> int:
        return 1

    def vllm_max_concurrent_requests(self) -> int:
        return 16


class SingleLargeGPU(_Base):
    """Single GPU with ≥80 GB VRAM — can serve + train concurrently."""
    profile = "single-large"

    def vllm_docker_run_args(self, model_path: str) -> list[str]:
        # Reserve ~half of memory for vLLM, leaving rest for training
        return ["--gpus", "all", "-e", "VLLM_GPU_MEMORY_UTILIZATION=0.5"]

    def can_concurrent_train(self) -> bool:
        return True

    def training_gpu_devices(self) -> str:
        return "0"

    def training_nproc_per_node(self) -> int:
        return 1

    def vllm_max_concurrent_requests(self) -> int:
        return 32


class DualSplit(_Base):
    """GPU 0 = inference, GPU 1 = training."""
    profile = "dual-split"

    def vllm_docker_run_args(self, model_path: str) -> list[str]:
        return ["--gpus", '"device=0"']

    def can_concurrent_train(self) -> bool:
        return True

    def training_gpu_devices(self) -> str:
        return "1"

    def training_nproc_per_node(self) -> int:
        return 1

    def vllm_max_concurrent_requests(self) -> int:
        return 32


class DualTP(_Base):
    """Both GPUs serve via Tensor Parallel; training pauses vLLM."""
    profile = "dual-tp"

    def vllm_docker_run_args(self, model_path: str) -> list[str]:
        return ["--gpus", '"device=0,1"']

    def vllm_command(self) -> list[str]:
        return ["python3", "/app/vllm_plugin/scripts/start_server.py", "--tp", "2"]

    def can_concurrent_train(self) -> bool:
        return False

    def training_gpu_devices(self) -> str:
        return "0,1"

    def training_nproc_per_node(self) -> int:
        return 2

    def vllm_max_concurrent_requests(self) -> int:
        return 64


class Multi(_Base):
    """Generic multi-GPU. Configure via env vars."""
    profile = "multi"

    def vllm_docker_run_args(self, model_path: str) -> list[str]:
        s = get_settings()
        return ["--gpus", f'"device={s.gpu_inference_devices}"']

    def vllm_command(self) -> list[str]:
        s = get_settings()
        cmd = ["python3", "/app/vllm_plugin/scripts/start_server.py"]
        if s.vllm_tensor_parallel > 1:
            cmd += ["--tp", str(s.vllm_tensor_parallel)]
        if s.vllm_data_parallel > 1:
            cmd += ["--dp", str(s.vllm_data_parallel)]
        return cmd

    def can_concurrent_train(self) -> bool:
        # If training GPUs are disjoint from inference GPUs → can concurrent
        s = get_settings()
        infer = set(s.gpu_inference_devices.split(","))
        train = set(s.gpu_training_devices.split(","))
        return infer.isdisjoint(train)

    def training_gpu_devices(self) -> str:
        return get_settings().gpu_training_devices

    def training_nproc_per_node(self) -> int:
        return len(get_settings().gpu_training_devices.split(","))

    def vllm_max_concurrent_requests(self) -> int:
        s = get_settings()
        return 32 * max(1, s.vllm_data_parallel)


_STRATEGIES = {
    "single": SingleGPU,
    "single-large": SingleLargeGPU,
    "dual-split": DualSplit,
    "dual-tp": DualTP,
    "multi": Multi,
}


def make_strategy() -> DeploymentStrategy:
    """Factory based on env DEPLOYMENT_PROFILE."""
    profile = get_settings().deployment_profile
    cls = _STRATEGIES.get(profile)
    if cls is None:
        raise ValueError(
            f"Unknown DEPLOYMENT_PROFILE={profile!r}. "
            f"Valid: {list(_STRATEGIES.keys())}"
        )
    return cls()
