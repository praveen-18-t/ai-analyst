"""Query engines behind one interface: DuckDB over Parquet (local) and Athena over Parquet in S3 (AWS)."""
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from functools import lru_cache

import duckdb

from app import storage
from app.config import settings
from app.dsinfo import DatasetInfo

log = logging.getLogger("app.engine")


class QueryError(Exception):
    pass


@dataclass
class QueryResult:
    columns: list
    types: list
    rows: list
    truncated: bool = False


def jsonable(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date, dtime)):
        return v.isoformat()
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return "<binary>"
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if hasattr(v, "item"):
        return jsonable(v.item())
    return str(v)


def _esc(s) -> str:
    return str(s).replace("'", "''")


class DuckDBEngine:
    dialect = "duckdb"

    def execute(self, org_id: str, datasets: list[DatasetInfo], sql: str, timeout_s: int | None = None, max_rows: int | None = None) -> QueryResult:
        timeout_s = timeout_s or settings.query_timeout_s
        max_rows = max_rows or settings.max_rows
        con = duckdb.connect(":memory:")
        timer = threading.Timer(timeout_s, con.interrupt)
        try:
            con.execute("SET threads=4")
            con.execute("SET memory_limit='1GB'")
            for ds in datasets:
                if ds.org_id != org_id:
                    raise QueryError("Dataset does not belong to this organization")
                path = storage.ensure_local(ds.parquet_key)
                con.execute(f"CREATE VIEW \"{ds.table_name}\" AS SELECT * FROM read_parquet('{_esc(path)}', hive_partitioning=false)")
            # Defense in depth: lock the process to this tenant's directory.
            try:
                org_dir = storage.lake_root() / f"org={org_id}"
                con.execute(f"SET allowed_directories=['{_esc(org_dir)}']")
                con.execute("SET enable_external_access=false")
                con.execute("SET lock_configuration=true")
            except duckdb.Error as e:  # older DuckDB versions
                log.warning("could not lock down duckdb: %s", e)
            timer.start()
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            types = [str(d[1]) for d in cur.description]
            fetched = cur.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            rows = [[jsonable(v) for v in r] for r in fetched[:max_rows]]
            return QueryResult(cols, types, rows, truncated)
        except duckdb.InterruptException:
            raise QueryError(f"Query exceeded the {timeout_s}s time limit")
        except duckdb.Error as e:
            raise QueryError(str(e).split("\n")[0])
        finally:
            timer.cancel()
            con.close()


def glue_db_name(org_id: str) -> str:
    return f"{settings.glue_database_prefix}_{org_id[:16]}".lower().replace("-", "_")


class AthenaEngine:
    """Runs validated SQL in a read-only, scan-limited Athena workgroup against the org's Glue database."""

    dialect = "trino"

    def execute(self, org_id: str, datasets: list[DatasetInfo], sql: str, timeout_s: int | None = None, max_rows: int | None = None) -> QueryResult:
        import boto3

        timeout_s = timeout_s or settings.query_timeout_s
        max_rows = max_rows or settings.max_rows
        ath = boto3.client("athena", region_name=settings.aws_region)
        qid = ath.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": glue_db_name(org_id)},
            WorkGroup=settings.athena_workgroup,
        )["QueryExecutionId"]
        deadline = time.time() + timeout_s
        while True:
            st = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
            if st["State"] == "SUCCEEDED":
                break
            if st["State"] in ("FAILED", "CANCELLED"):
                raise QueryError(st.get("StateChangeReason", "Athena query failed"))
            if time.time() > deadline:
                ath.stop_query_execution(QueryExecutionId=qid)
                raise QueryError(f"Query exceeded the {timeout_s}s time limit")
            time.sleep(0.5)
        cols, types, rows = [], [], []
        first = True
        for page in ath.get_paginator("get_query_results").paginate(QueryExecutionId=qid):
            if first:
                meta = page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
                cols, types = [c["Label"] for c in meta], [c["Type"] for c in meta]
            for i, r in enumerate(page["ResultSet"]["Rows"]):
                if first and i == 0:
                    continue  # header row
                rows.append([_athena_cast(d.get("VarCharValue"), types[j]) for j, d in enumerate(r["Data"])])
                if len(rows) > max_rows:
                    break
            first = False
            if len(rows) > max_rows:
                break
        return QueryResult(cols, types, rows[:max_rows], len(rows) > max_rows)


def _athena_cast(v, t):
    if v is None:
        return None
    try:
        if t in ("tinyint", "smallint", "integer", "bigint"):
            return int(v)
        if t in ("float", "double", "real", "decimal"):
            return float(v)
        if t == "boolean":
            return v == "true"
    except ValueError:
        pass
    return v


@lru_cache
def get_engine():
    return AthenaEngine() if settings.query_engine == "athena" else DuckDBEngine()
