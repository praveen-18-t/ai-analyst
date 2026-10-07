"""RAG: documents -> chunks -> embeddings -> vector search. Embeddings live in the app DB (JSON) and are
searched with numpy; swap for pgvector when an org has >50k chunks."""
import hashlib
import json
import re

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DocChunk, Document

DIM = 512


def _hash_embed(text: str) -> list[float]:
    """Offline fallback: hashed bag of unigrams+bigrams. Good enough for keyword-ish retrieval, no API needed."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    v = np.zeros(DIM, dtype=np.float32)
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 64) % 2 else -1.0
    n = np.linalg.norm(v)
    return (v / n if n else v).tolist()


def embed(texts: list[str]) -> list[list[float]]:
    if settings.embeddings_provider == "bedrock":
        import boto3

        br = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        out = []
        for t in texts:
            r = br.invoke_model(
                modelId=settings.bedrock_embed_model,
                body=json.dumps({"inputText": t[:8000], "dimensions": DIM, "normalize": True}),
            )
            out.append(json.loads(r["body"].read())["embedding"])
        return out
    return [_hash_embed(t) for t in texts]


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}".strip()
        else:
            if cur:
                chunks.append(cur)
            while len(p) > size:
                chunks.append(p[:size])
                p = p[size - overlap :]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def ingest_document(db: Session, org_id: str, name: str, text: str) -> Document:
    doc = Document(org_id=org_id, name=name)
    db.add(doc)
    db.flush()
    chunks = chunk_text(text)
    for i, (c, e) in enumerate(zip(chunks, embed(chunks) if chunks else [])):
        db.add(DocChunk(org_id=org_id, doc_id=doc.id, doc_name=name, idx=i, text=c, embedding=e))
    doc.chunk_count = len(chunks)
    db.commit()
    return doc


def retrieve(db: Session, org_id: str, question: str, k: int = 4, min_score: float = 0.08) -> list[dict]:
    rows = db.execute(
        select(DocChunk.doc_name, DocChunk.idx, DocChunk.text, DocChunk.embedding)
        .where(DocChunk.org_id == org_id).limit(20000)
    ).all()
    if not rows:
        return []
    mat = np.array([r.embedding for r in rows], dtype=np.float32)
    qv = np.array(embed([question])[0], dtype=np.float32)
    scores = mat @ qv
    top = np.argsort(-scores)[:k]
    return [
        {"doc": rows[i].doc_name, "chunk": rows[i].idx, "score": round(float(scores[i]), 3), "text": rows[i].text}
        for i in top if scores[i] >= min_score
    ]
