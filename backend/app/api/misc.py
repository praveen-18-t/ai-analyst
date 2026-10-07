import csv
import io
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.common import audit
from app.auth import Principal, get_principal, require_role
from app.db import get_db
from app.models import AuditLog, Dashboard, DocChunk, Document, QueryRecord, new_id
from app.rag.service import ingest_document

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/me")
def me(p: Principal = Depends(get_principal)):
    return {"user_id": p.user_id, "org_id": p.org_id, "role": p.role, "email": p.email}


# ---- query history -------------------------------------------------------------------------------
@router.get("/queries")
def list_queries(limit: int = 50, p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    rows = db.scalars(select(QueryRecord).where(QueryRecord.org_id == p.org_id).order_by(QueryRecord.created_at.desc()).limit(min(limit, 200)))
    return [{
        "id": r.id, "question": r.question, "status": r.status, "duration_ms": r.duration_ms,
        "cost_usd": round(r.cost_usd, 5), "created_at": r.created_at.isoformat(),
        "sql": [t.get("sql") for t in (r.response or {}).get("tasks", []) if t.get("sql")],
    } for r in rows]


def _get_query(db: Session, p: Principal, qid: str) -> QueryRecord:
    r = db.scalar(select(QueryRecord).where(QueryRecord.id == qid, QueryRecord.org_id == p.org_id))
    if not r:
        raise HTTPException(404, "Query not found")
    return r


@router.get("/queries/{qid}")
def get_query(qid: str, p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return _get_query(db, p, qid).response


@router.get("/queries/{qid}/export.csv")
def export_csv(qid: str, task_id: str = "t1", p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    task = next((t for t in _get_query(db, p, qid).response.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        raise HTTPException(404, "Task not found")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(task["columns"])
    w.writerows(task["rows"])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{qid}-{task_id}.csv"'})


# ---- dashboards ----------------------------------------------------------------------------------
class DashboardIn(BaseModel):
    name: str


class WidgetIn(BaseModel):
    title: str
    kind: str
    vega: dict | None = None
    items: list | None = None
    columns: list | None = None
    rows: list | None = None
    query_id: str | None = None


def _dash(db: Session, p: Principal, did: str) -> Dashboard:
    d = db.scalar(select(Dashboard).where(Dashboard.id == did, Dashboard.org_id == p.org_id))
    if not d:
        raise HTTPException(404, "Dashboard not found")
    return d


def _dash_out(d: Dashboard) -> dict:
    return {"id": d.id, "name": d.name, "widgets": d.widgets or [], "created_at": d.created_at.isoformat()}


@router.get("/dashboards")
def list_dashboards(p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return [_dash_out(d) for d in db.scalars(select(Dashboard).where(Dashboard.org_id == p.org_id).order_by(Dashboard.created_at.desc()))]


@router.post("/dashboards", status_code=201)
def create_dashboard(body: DashboardIn, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    d = Dashboard(org_id=p.org_id, name=body.name[:200], widgets=[])
    db.add(d)
    db.commit()
    return _dash_out(d)


@router.post("/dashboards/{did}/widgets", status_code=201)
def add_widget(did: str, w: WidgetIn, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    d = _dash(db, p, did)
    d.widgets = [*(d.widgets or []), {"id": new_id()[:10], **w.model_dump(exclude_none=True)}]
    db.commit()
    return _dash_out(d)


@router.delete("/dashboards/{did}/widgets/{wid}")
def remove_widget(did: str, wid: str, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    d = _dash(db, p, did)
    d.widgets = [w for w in (d.widgets or []) if w["id"] != wid]
    db.commit()
    return _dash_out(d)


@router.get("/dashboards/{did}/export")
def export_dashboard(did: str, p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    d = _dash(db, p, did)
    return Response(_json(_dash_out(d)), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="dashboard-{did}.json"'})


def _json(o) -> str:
    import json

    return json.dumps(o, indent=2, default=str)


@router.delete("/dashboards/{did}", status_code=204)
def delete_dashboard(did: str, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    db.delete(_dash(db, p, did))
    db.commit()


# ---- RAG documents -------------------------------------------------------------------------------
@router.post("/docs", status_code=201)
async def upload_doc(file: UploadFile = File(...), p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Document exceeds 10 MB")
    name = file.filename or "document"
    if name.lower().endswith(".pdf"):
        from pypdf import PdfReader

        text = "\n\n".join((pg.extract_text() or "") for pg in PdfReader(BytesIO(raw)).pages)
    elif name.lower().endswith((".txt", ".md", ".markdown", ".csv")):
        text = raw.decode("utf-8", errors="replace")
    else:
        raise HTTPException(400, "Supported documents: .pdf .txt .md")
    if not text.strip():
        raise HTTPException(400, "No extractable text in document")
    doc = ingest_document(db, p.org_id, name, text)
    audit(db, p, "doc.upload", {"doc_id": doc.id, "name": name})
    return {"id": doc.id, "name": doc.name, "chunks": doc.chunk_count}


@router.get("/docs")
def list_docs(p: Principal = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return [{"id": d.id, "name": d.name, "chunks": d.chunk_count, "created_at": d.created_at.isoformat()}
            for d in db.scalars(select(Document).where(Document.org_id == p.org_id).order_by(Document.created_at.desc()))]


@router.delete("/docs/{doc_id}", status_code=204)
def delete_doc(doc_id: str, p: Principal = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == doc_id, Document.org_id == p.org_id))
    if not doc:
        raise HTTPException(404, "Document not found")
    db.execute(delete(DocChunk).where(DocChunk.doc_id == doc_id, DocChunk.org_id == p.org_id))
    db.delete(doc)
    db.commit()


# ---- audit log -----------------------------------------------------------------------------------
@router.get("/audit")
def audit_log(limit: int = 100, p: Principal = Depends(require_role("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.org_id == p.org_id).order_by(AuditLog.id.desc()).limit(min(limit, 500)))
    return [{"id": r.id, "user_id": r.user_id, "action": r.action, "detail": r.detail, "created_at": r.created_at.isoformat()} for r in rows]
