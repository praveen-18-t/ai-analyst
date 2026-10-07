"""Dataset profiling & data-quality checks, computed with DuckDB directly on the Parquet file."""
from pathlib import Path

import duckdb

from app.engines import jsonable

NUMERIC = ("TINYINT", "SMALLINT", "INT", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
           "FLOAT", "DOUBLE", "DECIMAL", "REAL", "NUMERIC")


def kind_of(t: str) -> str:
    t = t.upper()
    if t.startswith(NUMERIC):
        return "numeric"
    if t.startswith(("DATE", "TIMESTAMP")):
        return "temporal"
    if t == "BOOLEAN":
        return "boolean"
    if t.startswith("VARCHAR"):
        return "text"
    return "other"


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def profile_parquet(path: Path) -> dict:
    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{str(path).replace(chr(39), chr(39) * 2)}', hive_partitioning=false)")
        cols = [(r[0], r[1]) for r in con.execute("DESCRIBE t").fetchall()]
        n = con.execute("SELECT count(*) FROM t").fetchone()[0]
        if n == 0:
            raise ValueError("Dataset is empty")
        dup = n - con.execute("SELECT count(*) FROM (SELECT DISTINCT * FROM t)").fetchone()[0]

        issues: list[dict] = []
        penalty = 0.0
        if dup > 0:
            pct = round(dup / n * 100, 2)
            issues.append({"severity": "warning", "column": None, "check": "duplicate_rows",
                           "message": f"{dup} duplicate rows ({pct}%)"})
            penalty += min(15, pct)

        out_cols = []
        for name, typ in cols:
            c, k = q(name), kind_of(typ)
            nulls, distinct = con.execute(f"SELECT count(*)-count({c}), count(DISTINCT {c}) FROM t").fetchone()
            nn = n - nulls
            info = {"name": name, "type": typ, "kind": k, "null_count": nulls,
                    "null_pct": round(nulls / n * 100, 2), "distinct_count": distinct}

            if k == "numeric" and nn:
                mn, mx, avg, sd, med, q1, q3 = con.execute(
                    f"SELECT min({c}),max({c}),avg({c}),stddev_samp({c}),median({c}),"
                    f"quantile_cont({c},0.25),quantile_cont({c},0.75) FROM t").fetchone()
                info.update(min=mn, max=mx, mean=avg, std=sd, median=med, q1=q1, q3=q3)
                neg = con.execute(f"SELECT count(*) FROM t WHERE {c} < 0").fetchone()[0]
                info["negative_count"] = neg
                if q1 is not None and q3 is not None and q3 > q1:
                    iqr = q3 - q1
                    outl = con.execute(
                        f"SELECT count(*) FROM t WHERE {c} < {q1 - 1.5 * iqr} OR {c} > {q3 + 1.5 * iqr}").fetchone()[0]
                    info["outlier_count"] = outl
                    if outl / n > 0.05:
                        issues.append({"severity": "info", "column": name, "check": "outliers",
                                       "message": f"{outl} outliers by IQR rule ({round(outl / n * 100, 1)}%)"})
            elif k == "temporal" and nn:
                mn, mx = con.execute(f"SELECT min({c}), max({c}) FROM t").fetchone()
                info.update(min=mn, max=mx)
            elif k == "text" and nn:
                info["avg_length"] = con.execute(f"SELECT avg(length({c})) FROM t").fetchone()[0]
                m = min(nn, 100000)
                num_ok, ts_ok = con.execute(
                    f"SELECT count(try_cast({c} AS DOUBLE)), count(try_cast({c} AS TIMESTAMP)) "
                    f"FROM (SELECT {c} FROM t WHERE {c} IS NOT NULL LIMIT 100000)").fetchone()
                if num_ok / m >= 0.95:
                    issues.append({"severity": "warning", "column": name, "check": "numeric_as_text",
                                   "message": "Stored as text but looks numeric"})
                    penalty += 3
                elif ts_ok / m >= 0.95:
                    issues.append({"severity": "warning", "column": name, "check": "date_as_text",
                                   "message": "Stored as text but looks like dates"})
                    penalty += 3

            if nn and (k in ("text", "boolean") or distinct <= 20):
                info["top_values"] = [
                    {"value": jsonable(v), "count": cnt} for v, cnt in con.execute(
                        f"SELECT {c}, count(*) FROM t WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY 2 DESC LIMIT 5").fetchall()]
            info["samples"] = [jsonable(r[0]) for r in con.execute(
                f"SELECT DISTINCT {c} FROM t WHERE {c} IS NOT NULL LIMIT 3").fetchall()]

            if nulls == n:
                issues.append({"severity": "error", "column": name, "check": "all_null", "message": "Column is entirely empty"})
                penalty += 5
            elif info["null_pct"] >= 50:
                issues.append({"severity": "error", "column": name, "check": "high_missing",
                               "message": f'{info["null_pct"]}% missing values'})
                penalty += 5
            elif info["null_pct"] >= 20:
                issues.append({"severity": "warning", "column": name, "check": "high_missing",
                               "message": f'{info["null_pct"]}% missing values'})
                penalty += 2
            if nn and distinct == 1 and n > 1:
                issues.append({"severity": "info", "column": name, "check": "constant", "message": "Column has a single constant value"})
            if nn == n and distinct == n and n > 1 and name.endswith("id"):
                info["likely_key"] = True
            out_cols.append(info)

        return jsonable({
            "row_count": n,
            "column_count": len(cols),
            "duplicate_rows": dup,
            "columns": out_cols,
            "quality": {"score": max(0, round(100 - penalty)), "issues": issues},
        })
    finally:
        con.close()
