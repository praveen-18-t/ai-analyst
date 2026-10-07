"""SQS worker. S3 (raw/ prefix) -> EventBridge -> SQS -> this process.  Run: python -m app.ingestion.worker"""
import json
import logging
import re
import time

import boto3

from app.config import settings
from app.db import Base, engine
from app.ingestion.pipeline import process_dataset
from app.observability import emit_metric, setup_logging

log = logging.getLogger("app.worker")
KEY_RE = re.compile(r"org=([^/]+)/dataset=([^/]+)/raw/")


def main() -> None:
    setup_logging()
    Base.metadata.create_all(engine)
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    url = __import__("os").environ["QUEUE_URL"]
    log.info("worker started")
    while True:
        resp = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=5, WaitTimeSeconds=20, VisibilityTimeout=900)
        for m in resp.get("Messages", []):
            try:
                body = json.loads(m["Body"])
                key = body["detail"]["object"]["key"]
                match = KEY_RE.match(key)
                if match:
                    t0 = time.time()
                    process_dataset(match.group(2))
                    emit_metric("IngestionSeconds", time.time() - t0, "Seconds")
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            except Exception:  # noqa: BLE001 - message returns to queue, then DLQ after maxReceiveCount
                log.exception("failed to process message")
                emit_metric("IngestionFailures", 1)


if __name__ == "__main__":
    main()
