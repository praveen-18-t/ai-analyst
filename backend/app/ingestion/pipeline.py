"""Upload -> (S3) -> processing -> profiling -> metadata."""
import logging

from app import storage
from app.config import settings
from app.db import SessionLocal
from app.ingestion.loaders import load_raw_to_parquet
from app.ingestion.profiling import profile_parquet
from app.models import Dataset

log = logging.getLogger("app.ingestion")


def process_dataset(dataset_id: str) -> None:
    with SessionLocal() as db:
        ds = db.get(Dataset, dataset_id)
        if not ds:
            return
        try:
            ds.status, ds.error = "processing", ""
            db.commit()
            raw = storage.ensure_local(ds.raw_key)
            pkey = storage.parquet_key(ds.org_id, ds.id)
            out = storage.local_path(pkey)
            load_raw_to_parquet(raw, out)
            prof = profile_parquet(out)
            ds.columns = [{"name": c["name"], "type": c["type"]} for c in prof["columns"]]
            ds.row_count = prof["row_count"]
            ds.profile = prof
            ds.parquet_key = pkey
            storage.publish(pkey)
            if settings.query_engine == "athena":
                from app.ingestion import glue

                glue.register_table(ds.org_id, ds.id, ds.table_name, ds.columns)
            ds.status = "ready"
            log.info("dataset ready", extra={"org_id": ds.org_id})
        except Exception as e:  # noqa: BLE001 - surfaced to the user via status/error
            log.exception("dataset processing failed")
            ds.status, ds.error = "failed", str(e)[:500]
        db.commit()
