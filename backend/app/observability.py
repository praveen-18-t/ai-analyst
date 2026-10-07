"""JSON logging, request tracing middleware and CloudWatch EMF metrics."""
import json
import logging
import sys
import time
import uuid

from fastapi import Request

from app.config import settings

log = logging.getLogger("app")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in ("request_id", "org_id", "path", "status", "ms"):
            if hasattr(record, k):
                data[k] = getattr(record, k)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def setup_logging() -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h]
    root.setLevel(settings.log_level)


def emit_metric(name: str, value: float, unit: str = "Count", **dimensions: str) -> None:
    """Embedded Metric Format: CloudWatch turns this log line into a metric automatically."""
    dims = {k: str(v) for k, v in dimensions.items()}
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "AIAnalyst",
                            "Dimensions": [list(dims.keys())] if dims else [[]],
                            "Metrics": [{"Name": name, "Unit": unit}],
                        }
                    ],
                },
                name: value,
                **dims,
            }
        ),
        flush=True,
    )


async def request_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = int((time.perf_counter() - t0) * 1000)
    response.headers["x-request-id"] = rid
    if request.url.path != "/health":
        log.info("request", extra={"request_id": rid, "path": request.url.path, "status": response.status_code, "ms": ms})
    return response
