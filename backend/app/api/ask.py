import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import llm as llm_mod
from app.agents.pipeline import answer_question
from app.api.common import audit
from app.auth import Principal, require_role
from app.config import settings
from app.db import get_db
from app.dsinfo import DatasetInfo
from app.models import Dataset, QueryRecord, now
from app.observability import emit_metric
from app.rag.service import retrieve

router = APIRouter(prefix="/api", tags=["analyst"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    dataset_ids: list[str] | None = None
    use_docs: bool = True


@router.post("/ask")
async def ask(req: AskRequest, p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    since = now() - timedelta(days=1)
    used = db.scalar(select(func.count()).select_from(QueryRecord).where(QueryRecord.org_id == p.org_id, QueryRecord.created_at >= since))
    if used >= settings.max_questions_per_day:
        raise HTTPException(429, "Daily question limit reached for this organization")

    q = select(Dataset).where(Dataset.org_id == p.org_id, Dataset.status == "ready")
    if req.dataset_ids:
        q = q.where(Dataset.id.in_(req.dataset_ids))
    datasets = [DatasetInfo.from_orm(d) for d in db.scalars(q)]
    if not datasets:
        raise HTTPException(400, "No ready datasets. Upload a dataset and wait for processing to finish.")

    chunks = retrieve(db, p.org_id, req.question) if req.use_docs else []
    rec = QueryRecord(org_id=p.org_id, user_id=p.user_id, question=req.question)
    db.add(rec)
    db.commit()

    usage = {"in": 0, "out": 0, "calls": 0}
    llm_mod.usage_var.set(usage)
    t0 = time.perf_counter()
    try:
        result = await answer_question(req.question, datasets, p.org_id, chunks)
        rec.status = "ok" if result["tasks"] is not None and (not result["tasks"] or any(not t["error"] for t in result["tasks"])) else "failed"
    except Exception as e:  # noqa: BLE001
        rec.status = "error"
        result = {"question": req.question, "answer": f"The analysis failed: {e}", "tasks": [], "charts": [], "insights": [],
                  "recommendations": [], "review": {}, "sources": [], "trace": [], "key_findings": [], "caveats": []}
    ms = int((time.perf_counter() - t0) * 1000)
    cost = usage["in"] * settings.price_in_per_mtok / 1e6 + usage["out"] * settings.price_out_per_mtok / 1e6
    result["usage"] = {"input_tokens": usage["in"], "output_tokens": usage["out"], "llm_calls": usage["calls"], "cost_usd": round(cost, 5)}
    result["id"], result["duration_ms"] = rec.id, ms
    rec.response, rec.duration_ms = result, ms
    rec.tokens_in, rec.tokens_out, rec.cost_usd = usage["in"], usage["out"], cost
    db.commit()

    audit(db, p, "ask", {"query_id": rec.id, "status": rec.status, "sql": [t.get("sql") for t in result["tasks"]]})
    emit_metric("AskLatencyMs", ms, "Milliseconds", Status=rec.status)
    emit_metric("LLMCostUSD", cost, "None")
    emit_metric("LLMTokens", usage["in"] + usage["out"], "Count")
    return result
