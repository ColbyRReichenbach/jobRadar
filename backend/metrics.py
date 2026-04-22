import os
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


REQUEST_COUNT = Counter(
    "apptrail_http_requests_total",
    "Total HTTP requests processed by AppTrail.",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "apptrail_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)
REQUESTS_IN_PROGRESS = Gauge(
    "apptrail_http_requests_in_progress",
    "In-flight HTTP requests.",
)
AI_TASK_RUNS = Counter(
    "apptrail_ai_task_runs_total",
    "Total AI task runs by task/model/outcome.",
    ["task", "model", "outcome"],
)
AI_TASK_DURATION = Histogram(
    "apptrail_ai_task_duration_seconds",
    "AI task duration in seconds.",
    ["task", "model", "outcome"],
)
AI_TASK_FALLBACKS = Counter(
    "apptrail_ai_task_fallbacks_total",
    "Total AI task fallbacks by task and reason.",
    ["task", "reason"],
)


def metrics_payload() -> bytes:
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest()


def metrics_headers() -> dict[str, str]:
    return {"Content-Type": CONTENT_TYPE_LATEST}


def observe_request(method: str, path: str, status_code: int, started_at: float) -> None:
    duration = time.perf_counter() - started_at
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration)


def observe_ai_task(task: str, model: str, outcome: str, duration_seconds: float) -> None:
    AI_TASK_RUNS.labels(task=task, model=model, outcome=outcome).inc()
    AI_TASK_DURATION.labels(task=task, model=model, outcome=outcome).observe(duration_seconds)


def observe_ai_fallback(task: str, reason: str) -> None:
    AI_TASK_FALLBACKS.labels(task=task, reason=reason).inc()
