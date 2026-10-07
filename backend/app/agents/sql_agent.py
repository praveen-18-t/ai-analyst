"""SQL Agent: schema-aware generation, validation, read-only execution, self-correction."""
import logging

from app import llm as llm_mod
from app.config import settings
from app.dsinfo import DatasetInfo
from app.engines import QueryError, get_engine
from app.sql.validator import SQLValidationError, validate

log = logging.getLogger("app.sql_agent")

SYSTEM = """[sql_agent] You are an expert analytics engineer writing {dialect} SQL for a read-only analytics warehouse.
Return JSON only: {{"sql": "<ONE select statement>", "explanation": "<one sentence>"}}
If the question cannot be answered from the schema return {{"sql": null, "explanation": "<why>"}}.
Rules:
- Only SELECT / WITH queries over the listed tables. No DDL/DML, no file or table functions, no schema prefixes.
- Always double-quote identifiers; use only listed columns; use the sample values shown to get filters right.
- Optimize: select only needed columns, filter before joining, aggregate before joining, avoid SELECT *,
  use ORDER BY + LIMIT for top-N, no accidental cross joins.
- If there is no revenue/total column but price and quantity columns exist, compute SUM(price * quantity).
- Give computed columns clear snake_case aliases. Round money/ratios to 2 decimals."""


def schema_text(datasets: list[DatasetInfo], max_cols: int = 60) -> str:
    lines = []
    for ds in datasets:
        lines.append(f'TABLE "{ds.table_name}"  ({ds.row_count} rows)  -- {ds.name}')
        pm = {c["name"]: c for c in ds.profile.get("columns", [])}
        for c in ds.columns[:max_cols]:
            p, extra = pm.get(c["name"], {}), []
            if p.get("null_pct"):
                extra.append(f'{p["null_pct"]}% null')
            if p.get("min") is not None and p.get("kind") in ("numeric", "temporal"):
                extra.append(f'range {p["min"]} .. {p["max"]}')
            if p.get("top_values") and p.get("distinct_count", 99) <= 20:
                extra.append("values: " + ", ".join(str(v["value"]) for v in p["top_values"]))
            elif p.get("samples"):
                extra.append("e.g. " + ", ".join(map(str, p["samples"])))
            lines.append(f'  - "{c["name"]}" {c["type"]}' + (f'  -- {"; ".join(extra)}' if extra else ""))
        if len(ds.columns) > max_cols:
            lines.append(f"  ... {len(ds.columns) - max_cols} more columns omitted")
    return "\n".join(lines)


def run_sql_task(task_id: str, question: str, datasets: list[DatasetInfo], org_id: str, doc_context: str = "") -> dict:
    engine = get_engine()
    allowed = {d.table_name for d in datasets}
    base = f"SCHEMA:\n{schema_text(datasets)}\n"
    if doc_context:
        base += f"\nBUSINESS CONTEXT (from company documents):\n{doc_context}\n"
    prompt = base + f"\nQUESTION: {question}"
    attempts, empty_retried = [], False
    system = SYSTEM.format(dialect=engine.dialect)
    result = {"id": task_id, "question": question, "sql": None, "columns": [], "types": [], "rows": [],
              "row_count": 0, "truncated": False, "error": None, "explanation": "", "attempts": attempts}
    for i in range(1, settings.max_sql_retries + 1):
        try:
            out = llm_mod.get_llm().complete_json(system, prompt, max_tokens=1500)
        except Exception as e:  # noqa: BLE001
            attempts.append({"n": i, "error": f"LLM error: {e}"})
            result["error"] = f"LLM error: {e}"
            break
        sql = out.get("sql")
        result["explanation"] = out.get("explanation", "")
        if not sql:
            result["error"] = f'Cannot answer from available data: {out.get("explanation", "")}'
            attempts.append({"n": i, "sql": None, "error": result["error"]})
            break
        try:
            safe = validate(sql, allowed, engine.dialect, settings.max_rows)
            res = engine.execute(org_id, datasets, safe)
            attempts.append({"n": i, "sql": safe, "ok": True, "rows": len(res.rows)})
            if not res.rows and not empty_retried and i < settings.max_sql_retries:
                empty_retried = True
                prompt = base + (f"\nQUESTION: {question}\n\nYour previous query returned 0 rows:\n{safe}\n"
                                 "Re-check filters against the sample values above and return a corrected query.")
                continue
            result.update(sql=safe, columns=res.columns, types=res.types, rows=res.rows,
                          row_count=len(res.rows), truncated=res.truncated, error=None)
            return result
        except (SQLValidationError, QueryError) as e:
            attempts.append({"n": i, "sql": sql, "ok": False, "error": str(e)})
            result["sql"], result["error"] = sql, str(e)
            prompt = base + (f"\nQUESTION: {question}\n\nYour previous query failed.\nSQL: {sql}\nError: {e}\n"
                             "Return a corrected query that fixes this error.")
    return result
