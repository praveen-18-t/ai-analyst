"""Raw file (csv/tsv/xlsx/json/parquet) -> cleaned Parquet. Column names are normalised to snake_case."""
import re
from pathlib import Path

import duckdb
import pandas as pd


def _esc(p) -> str:
    return str(p).replace("'", "''")


def clean_name(n, used: set) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(n).strip()).strip("_").lower() or "col"
    if s[0].isdigit():
        s = "c_" + s
    base, i = s, 2
    while s in used:
        s, i = f"{base}_{i}", i + 1
    used.add(s)
    return s


def _write(con: duckdb.DuckDBPyConnection, view: str, out: Path) -> None:
    cols = [r[0] for r in con.execute(f"DESCRIBE {view}").fetchall()]
    used: set = set()
    sel = ", ".join(f'"{c.replace(chr(34), chr(34) * 2)}" AS "{clean_name(c, used)}"' for c in cols)
    con.execute(f"COPY (SELECT {sel} FROM {view}) TO '{_esc(out)}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def df_to_parquet(df: pd.DataFrame, out: Path) -> None:
    con = duckdb.connect()
    try:
        con.register("src_df", df)
        con.execute("CREATE VIEW src AS SELECT * FROM src_df")
        try:
            _write(con, "src", out)
        except duckdb.Error:
            df2 = df.copy()
            for c in df2.columns:
                if df2[c].dtype == object:
                    df2[c] = df2[c].map(lambda v: None if pd.isna(v) else str(v))
            con.unregister("src_df")
            con.register("src_df", df2)
            _write(con, "src", out)
    finally:
        con.close()


def load_raw_to_parquet(raw: Path, out: Path) -> None:
    ext = raw.suffix.lower()
    out.parent.mkdir(parents=True, exist_ok=True)
    if ext in (".xlsx", ".xlsm"):
        df_to_parquet(pd.read_excel(raw, sheet_name=0), out)
        return
    con = duckdb.connect()
    try:
        if ext in (".csv", ".tsv", ".txt"):
            src = f"read_csv_auto('{_esc(raw)}', sample_size=-1, header=true, hive_partitioning=false)"
        elif ext == ".parquet":
            src = f"read_parquet('{_esc(raw)}', hive_partitioning=false)"
        elif ext in (".json", ".jsonl", ".ndjson"):
            src = f"read_json_auto('{_esc(raw)}', hive_partitioning=false)"
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        con.execute(f"CREATE VIEW src AS SELECT * FROM {src}")
        _write(con, "src", out)
    finally:
        con.close()
