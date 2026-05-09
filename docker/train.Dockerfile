# Training container — used on-demand for LoRA fine-tuning
# Image is built once, container runs per training job
FROM nvcr.io/nvidia/pytorch:24.07-py3

WORKDIR /app

# 上游 VibeVoice 在 docker run 時掛載到 /app
# 此 image 只裝 PEFT + 必要套件
RUN pip install --no-cache-dir \
        peft==0.12.0 \
        "transformers>=4.45.0,<4.50.0" \
        accelerate==0.34.0 \
        librosa==0.10.2 \
        soundfile==0.12.1

# entrypoint 由 docker run 指定 command（torchrun ... lora_finetune.py）
