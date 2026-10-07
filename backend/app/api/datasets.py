import asyncio
from pathlib import Path

import httpx
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import storage
from app.api.common import assert_public_host, audit, new_dataset_id, new_table_name
from app.auth import Principal, require_role
from app.config import settings
from app.db import get_db
from app.dsinfo import DatasetInfo
from app.engines import QueryError, get_engine
from app.ingestion.loaders import df_to_parquet
from app.ingestion.pipeline import process_dataset
from app.models import Dataset

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
ALLOWED_EXT = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".parquet", ".json", ".jsonl", ".ndjson"}


def dataset_out(ds: Dataset, full: bool = False) -> dict:
    d = {
        "id": ds.id, "name": ds.name, "table_name": ds.table_name, "source_type": ds.source_type,
        "source_meta": ds.source_meta, "status": ds.status, "error": ds.error, "row_count": ds.row_count,
        "columns": ds.columns, "created_at": ds.created_at.isoformat(),
        "quality_score": (ds.profile or {}).get("quality", {}).get("score"),
    }
    if full:
        d["profile"] = ds.profile
    return d


def _register(db: Session, p: Principal, ds_id: str, name: str, source_type: str, meta: dict, filename: str) -> Dataset:
    ds = Dataset(
        id=ds_id, org_id=p.org_id, name=name, table_name=new_table_name(db, p.org_id, name),
        source_type=source_type, source_meta=meta, status="uploaded",
        raw_key=storage.raw_key(p.org_id, ds_id, filename), created_by=p.user_id,
    )
    db.add(ds)
    db.commit()
    return ds


def _dispatch(background: BackgroundTasks, ds: Dataset) -> None:
    storage.publish(ds.raw_key)
    if settings.storage == "s3":
        return  # S3 -> EventBridge -> SQS -> worker picks it up
    background.add_task(process_dataset, ds.id)


@router.post("/upload", status_code=202)
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    p: Principal = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    ds_id = new_dataset_id()
    path = storage.local_path(storage.raw_key(p.org_id, ds_id, file.filename or f"upload{ext}"))
    size, limit = 0, settings.max_upload_mb * 1024 * 1024
    with open(path, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                f.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
            f.write(chunk)
    ds = _register(db, p, ds_id, name or Path(file.filename).stem, "file", {"filename": file.filename, "bytes": size}, file.filename)
    audit(db, p, "dataset.upload", {"dataset_id": ds.id, "filename": file.filename})
    _dispatch(background, ds)
    return dataset_out(ds)


class DBImport(BaseModel):
    name: str
    url: str  # postgresql://user:pass@host/db  or  mysql://user:pass@host/db
    query: str
    max_rows: int = 1_000_000


def _fetch_db(url: str, query: str, max_rows: int) -> pd.DataFrame:
    import sqlglot
    from sqlalchemy import create_engine, text

    tree = sqlglot.parse_one(query)
    if not isinstance(tree, (sqlglot.exp.Select, sqlglot.exp.Union)):
        raise ValueError("Only SELECT queries can be imported")
    eng = create_engine(url, connect_args={"connect_timeout": 10})
    try:
        with eng.connect() as con:
            chunks = list(_limited(pd.read_sql_query(text(query), con, chunksize=50_000), max_rows))
            return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    finally:
        eng.dispose()


def _limited(chunks, max_rows):
    total = 0
    for c in chunks:
        yield c
        total += len(c)
        if total >= max_rows:
            break


@router.post("/import-db", status_code=202)
async def import_db(body: DBImport, background: BackgroundTasks, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    try:
        u = make_url(body.url)
    except Exception:
        raise HTTPException(400, "Invalid database URL")
    if u.get_backend_name() not in ("postgresql", "mysql"):
        raise HTTPException(400, "Only postgresql:// and mysql:// sources are supported")
    url = body.url.replace("postgresql://", "postgresql+psycopg://", 1).replace("mysql://", "mysql+pymysql://", 1)
    assert_public_host(u.host)
    try:
        df = await asyncio.to_thread(_fetch_db, url, body.query, min(body.max_rows, 5_000_000))
    except Exception as e:
        raise HTTPException(400, f"Import failed: {str(e)[:300]}")
    ds_id = new_dataset_id()
    path = storage.local_path(storage.raw_key(p.org_id, ds_id, "import.parquet"))
    await asyncio.to_thread(df_to_parquet, df, path)
    meta = {"url": u.render_as_string(hide_password=True), "query": body.query}
    ds = _register(db, p, ds_id, body.name, u.get_backend_name(), meta, "import.parquet")
    audit(db, p, "dataset.import_db", {"dataset_id": ds.id, "backend": u.get_backend_name(), "host": u.host})
    _dispatch(background, ds)
    return dataset_out(ds)


class ApiImport(BaseModel):
    name: str
    url: str
    headers: dict[str, str] = {}
    records_path: str | None = None  # dotted path to the list of records inside JSON responses


def _fetch_api(body: ApiImport) -> tuple[str, bytes]:
    r = httpx.get(body.url, headers=body.headers, timeout=30, follow_redirects=False)
    r.raise_for_status()
    if len(r.content) > 50 * 1024 * 1024:
        raise ValueError("Response larger than 50 MB")
    ctype = r.headers.get("content-type", "")
    if "json" in ctype or r.text.lstrip()[:1] in "[{":
        data = r.json()
        for part in filter(None, (body.records_path or "").split(".")):
            data = data[part]
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        df = pd.json_normalize(data)
        import io

        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        return "api.csv", buf.getvalue()
    return "api.csv", r.content


@router.post("/import-api", status_code=202)
async def import_api(body: ApiImport, background: BackgroundTasks, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    host = httpx.URL(body.url).host
    if httpx.URL(body.url).scheme not in ("http", "https"):
        raise HTTPException(400, "Only http(s) URLs are supported")
    assert_public_host(host)
    try:
        fname, content = await asyncio.to_thread(_fetch_api, body)
    except Exception as e:
        raise HTTPException(400, f"Import failed: {str(e)[:300]}")
    ds_id = new_dataset_id()
    storage.local_path(storage.raw_key(p.org_id, ds_id, fname)).write_bytes(content)
    ds = _register(db, p, ds_id, body.name, "api", {"url": body.url.split("?")[0], "records_path": body.records_path}, fname)
    audit(db, p, "dataset.import_api", {"dataset_id": ds.id, "host": host})
    _dispatch(background, ds)
    return dataset_out(ds)


@router.get("")
def list_datasets(p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Dataset).where(Dataset.org_id == p.org_id).order_by(Dataset.created_at.desc()))
    return [dataset_out(d) for d in rows]


def _get(db: Session, p: Principal, ds_id: str) -> Dataset:
    ds = db.scalar(select(Dataset).where(Dataset.id == ds_id, Dataset.org_id == p.org_id))
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds


@router.get("/{ds_id}")
def get_dataset(ds_id: str, p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return dataset_out(_get(db, p, ds_id), full=True)


@router.get("/{ds_id}/preview")
def preview(ds_id: str, limit: int = 50, p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    ds = _get(db, p, ds_id)
    if ds.status != "ready":
        raise HTTPException(409, f"Dataset is {ds.status}")
    try:
        res = get_engine().execute(p.org_id, [DatasetInfo.from_orm(ds)], f'SELECT * FROM "{ds.table_name}" LIMIT {max(1, min(limit, 500))}')
    except QueryError as e:
        raise HTTPException(400, str(e))
    return {"columns": res.columns, "rows": res.rows}


@router.delete("/{ds_id}", status_code=204)
def delete_dataset(ds_id: str, p: Principal = Depends(require_role("admin")), db: Session = Depends(get_db)):
    ds = _get(db, p, ds_id)
    storage.delete_dataset_files(ds.org_id, ds.id)
    if settings.query_engine == "athena":
        from app.ingestion import glue

        glue.drop_table(ds.org_id, ds.table_name)
    db.delete(ds)
    db.commit()
    audit(db, p, "dataset.delete", {"dataset_id": ds_id})
