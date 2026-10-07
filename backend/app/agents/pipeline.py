"""Multi-agent orchestration:  Planner -> [SQL x N in parallel] -> Analyst -> [Viz || Insight] -> Reviewer."""
import asyncio
import time

from app.agents import sql_agent
from app.agents.others import run_analyst, run_insight, run_planner, run_reviewer
from app.agents.viz import run_viz
from app.dsinfo import DatasetInfo

MAX_ROWS_IN_RESPONSE = 500


async def answer_question(question: str, datasets: list[DatasetInfo], org_id: str, doc_chunks: list[dict]) -> dict:
    trace: list[dict] = []
    doc_context = "\n---\n".join(f'[{c["doc"]}] {c["text"]}' for c in doc_chunks)
    schema = sql_agent.schema_text(datasets)

    async def step(agent: str, fn, *args):
        t0 = time.perf_counter()
        ok = True
        try:
            return await asyncio.to_thread(fn, *args)
        except Exception:
            ok = False
            raise
        finally:
            trace.append({"agent": agent, "ms": int((time.perf_counter() - t0) * 1000), "ok": ok})

    plan = await step("planner", run_planner, question, schema, doc_context)
    tasks_in = plan["tasks"]

    if tasks_in:
        tasks = list(await asyncio.gather(*[
            step(f"sql_agent:{t['id']}", sql_agent.run_sql_task, t["id"], t["question"], datasets, org_id, doc_context)
            for t in tasks_in
        ]))
    else:
        tasks = []
    ok_tasks = [t for t in tasks if not t["error"] and t["columns"]]

    if tasks and not ok_tasks:
        errs = "; ".join(f'{t["question"]}: {t["error"]}' for t in tasks)
        return _response(question, f"I couldn't answer this from the available data. {errs}", tasks, [], {}, {"approved": False, "issues": [errs]}, doc_chunks, trace)

    analysis = await step("data_analyst", run_analyst, question, ok_tasks, doc_context)

    async def viz():
        return await step("visualization", run_viz, ok_tasks, question) if ok_tasks else []

    charts, insight = await asyncio.gather(viz(), step("insight", run_insight, question, analysis, ok_tasks, doc_context))

    try:
        review = await step("reviewer", run_reviewer, question, analysis, insight, ok_tasks)
    except Exception as e:  # noqa: BLE001 - review failure must not lose the answer
        review = {"approved": None, "issues": [f"review unavailable: {e}"]}
    summary = analysis.get("summary", "")
    if review.get("approved") is False and review.get("revised_summary"):
        summary = review["revised_summary"]
        review["revised"] = True

    return _response(question, summary, tasks, charts, insight, review, doc_chunks, trace, analysis)


def _response(question, summary, tasks, charts, insight, review, doc_chunks, trace, analysis=None) -> dict:
    out_tasks = []
    for t in tasks:
        t = dict(t)
        t["rows"] = t["rows"][:MAX_ROWS_IN_RESPONSE]
        out_tasks.append(t)
    return {
        "question": question,
        "answer": summary,
        "key_findings": (analysis or {}).get("key_findings", []),
        "caveats": (analysis or {}).get("caveats", []),
        "tasks": out_tasks,
        "charts": charts,
        "insights": insight.get("insights", []),
        "recommendations": insight.get("recommendations", []),
        "review": review,
        "sources": [{"doc": c["doc"], "chunk": c["chunk"], "score": c["score"], "text": c["text"][:400]} for c in doc_chunks],
        "trace": trace,
    }
