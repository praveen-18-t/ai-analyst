import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(DATA_DIR=_tmp, DATABASE_URL=f"sqlite:///{_tmp}/test.db", AUTH_MODE="dev", ENV="dev", QUERY_ENGINE="duckdb")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class FakeLLM:
    """Scripted LLM: dispatches on the [role] tag at the start of each agent's system prompt."""

    def __init__(self):
        self.sql_calls = 0

    def complete_json(self, system, user, max_tokens=0):
        if system.startswith("[planner]"):
            return {"tasks": [{"id": "t1", "question": "Top products by revenue"}]}
        if system.startswith("[sql_agent]"):
            self.sql_calls += 1
            if "previous query failed" not in user:  # first attempt: wrong column -> must self-correct
                return {"sql": 'SELECT "product", SUM("revenu") AS total_revenue FROM "sales" GROUP BY 1', "explanation": "bad"}
            return {"sql": 'SELECT "product", SUM("revenue") AS total_revenue FROM "sales" GROUP BY 1 ORDER BY 2 DESC', "explanation": "ok"}
        if system.startswith("[analyst]"):
            return {"summary": "Widget leads with 300 in revenue.", "key_findings": ["Widget is #1"], "caveats": []}
        if system.startswith("[viz]"):
            return {"titles": {"t1": "Revenue by product"}}
        if system.startswith("[insight]"):
            return {"insights": [{"title": "Concentration", "detail": "One product dominates", "impact": "high"}], "recommendations": ["Diversify"]}
        if system.startswith("[reviewer]"):
            return {"approved": True, "issues": []}
        raise AssertionError(system[:40])


@pytest.fixture()
def fake_llm(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr("app.llm.get_llm", lambda: f)
    return f
