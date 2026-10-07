"""Data-lake layout: org=<id>/dataset=<id>/{raw,data}/... Local disk is the working copy; S3 is the system of record in prod."""
import re
import shutil
from pathlib import Path

from app.config import settings


def lake_root() -> Path:
    p = (Path(settings.data_dir) / "lake").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or "file").name).strip("._") or "file"
    return n[:120]


def raw_key(org_id: str, ds_id: str, filename: str) -> str:
    return f"org={org_id}/dataset={ds_id}/raw/{safe_filename(filename)}"


def parquet_key(org_id: str, ds_id: str) -> str:
    return f"org={org_id}/dataset={ds_id}/data/data.parquet"


def local_path(key: str) -> Path:
    p = (lake_root() / key).resolve()
    if lake_root() not in p.parents:
        raise ValueError("invalid storage key")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _s3():
    import boto3

    return boto3.client("s3", region_name=settings.aws_region)


def publish(key: str) -> None:
    if settings.storage == "s3":
        _s3().upload_file(str(local_path(key)), settings.s3_bucket, key)


def ensure_local(key: str) -> Path:
    p = local_path(key)
    if not p.exists() and settings.storage == "s3":
        _s3().download_file(settings.s3_bucket, key, str(p))
    return p


def delete_dataset_files(org_id: str, ds_id: str) -> None:
    prefix = f"org={org_id}/dataset={ds_id}/"
    shutil.rmtree(lake_root() / prefix, ignore_errors=True)
    if settings.storage == "s3":
        s3 = _s3()
        pag = s3.get_paginator("list_objects_v2")
        for page in pag.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                s3.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objs})
