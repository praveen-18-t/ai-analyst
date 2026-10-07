"""Planner, Data Analyst, Insight and Reviewer agents. Each takes plain data and returns a plain dict."""
import json

from app import llm as llm_mod


def _llm():
    return llm_mod.get_llm()


def run_planner(question: str, schema: str, doc_context: str) -> dict:
    system = (
        "[planner] You break a business question into independent SQL sub-questions that can run in parallel.\n"
        'Return JSON: {"tasks": [{"id": "t1", "question": "<self-contained question answerable with one SQL query>"}]}\n'
        "Rules: 1-4 tasks; prefer 1 for simple questions; every task must be answerable from the schema alone; "
        "no task may depend on another task's result. If the question is purely about policy/definitions and the "
        'company documents answer it, return {"tasks": []}.'
    )
    user = f"SCHEMA:\n{schema}\n" + (f"\nCOMPANY DOCUMENTS:\n{doc_context}\n" if doc_context else "") + f"\nQUESTION: {question}"
    try:
        tasks = _llm().complete_json(system, user, max_tokens=600).get("tasks", [])
        tasks = [{"id": f"t{i + 1}", "question": str(t["question"])} for i, t in enumerate(tasks[:4]) if t.get("question")]
    except Exception:  # noqa: BLE001 - fall back to a single task
        tasks = [{"id": "t1", "question": question}]
    return {"tasks": tasks}


def column_stats(columns: list, types: list, rows: list) -> dict:
    """Deterministic numeric summary so the LLM does not have to do arithmetic."""
    stats = {}
    for j, (c, t) in enumerate(zip(columns, types)):
        vals = [r[j] for r in rows if isinstance(r[j], (int, float)) and not isinstance(r[j], bool)]
        if vals and len(vals) >= len(rows) * 0.9:
            stats[c] = {"sum": round(sum(vals), 2), "min": min(vals), "max": max(vals), "mean": round(sum(vals) / len(vals), 2)}
    return stats


def _compact(t: dict, n: int = 30) -> dict:
    return {"task": t["id"], "question": t["question"], "sql": t["sql"], "columns": t["columns"],
            "row_count": t["row_count"], "rows": t["rows"][:n], "stats": column_stats(t["columns"], t["types"], t["rows"])}


def run_analyst(question: str, tasks: list[dict], doc_context: str) -> dict:
    system = (
        "[analyst] You are a careful data analyst. Answer the user's question using ONLY the query results and "
        "documents provided. Quote exact numbers. Mention data caveats (truncation, empty results, failed sub-queries).\n"
        'Return JSON: {"summary": "<2-5 sentence direct answer, markdown allowed>", "key_findings": ["..."], "caveats": ["..."]}'
    )
    user = f"QUESTION: {question}\n\nRESULTS:\n{json.dumps([_compact(t) for t in tasks], default=str)}"
    if doc_context:
        user += f"\n\nCOMPANY DOCUMENTS:\n{doc_context}"
    failed = [f'{t["id"]}: {t["error"]}' for t in tasks if t["error"]]
    if failed:
        user += "\n\nFAILED SUB-QUERIES:\n" + "\n".join(failed)
    return _llm().complete_json(system, user, max_tokens=1200)


def run_insight(question: str, analysis: dict, tasks: list[dict], doc_context: str) -> dict:
    system = (
        "[insight] You are a business strategist. From the analysis, produce non-obvious, decision-relevant insights. "
        "Do not invent numbers.\n"
        'Return JSON: {"insights": [{"title": "...", "detail": "...", "impact": "high|medium|low"}], '
        '"recommendations": ["..."]}  (max 4 insights, max 3 recommendations)'
    )
    user = (f"QUESTION: {question}\nANALYSIS: {json.dumps(analysis)}\n"
            f"DATA: {json.dumps([_compact(t, 15) for t in tasks], default=str)}")
    if doc_context:
        user += f"\nCOMPANY DOCUMENTS:\n{doc_context}"
    return _llm().complete_json(system, user, max_tokens=1000)


def run_reviewer(question: str, analysis: dict, insight: dict, tasks: list[dict]) -> dict:
    system = (
        "[reviewer] You audit an analyst's answer against the raw query results. Check: numbers match the data, the "
        "question is actually answered, no unsupported claims. If wrong or unsupported, provide a corrected summary.\n"
        'Return JSON: {"approved": true|false, "issues": ["..."], "revised_summary": "<only when not approved>"}'
    )
    user = (f"QUESTION: {question}\nANSWER: {json.dumps(analysis)}\nINSIGHTS: {json.dumps(insight)}\n"
            f"DATA: {json.dumps([_compact(t, 30) for t in tasks], default=str)}")
    return _llm().complete_json(system, user, max_tokens=800)
