"""
Prometheus metrics middleware.

Counters / histograms exposed at /metrics.

M7 milestone (full); basic counters can be added in earlier milestones.
"""
from __future__ import annotations

# from prometheus_client import Counter, Histogram

# Common metrics (uncomment when implementing):
# requests_total = Counter("vva_requests_total", "Total requests", ["endpoint", "method", "status"])
# request_duration_seconds = Histogram(
#     "vva_request_duration_seconds", "Request duration", ["endpoint", "method"]
# )
# vllm_inference_seconds = Histogram(
#     "vva_vllm_inference_seconds", "vLLM inference latency", ["model", "split"]
# )
# queue_depth = Gauge("vva_queue_depth", "Arq queue depth", ["queue"])
# webhook_deliveries = Counter("vva_webhook_deliveries", "Webhook delivery results", ["status"])
