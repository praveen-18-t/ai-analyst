import pytest

from app.agents.viz import choose_chart
from app.engines import DuckDBEngine, QueryError


def test_engine_blocks_file_access_even_without_validator(client):
    """Defense in depth: bypass the validator and try to read files directly."""
    from tests.test_e2e import upload

    ds = upload(client, "locktest", {"x-dev-org": "lock-org"})
    from app.db import SessionLocal
    from app.dsinfo import DatasetInfo
    from app.models import Dataset

    with SessionLocal() as db:
        info = DatasetInfo.from_orm(db.get(Dataset, ds["id"]))
    eng = DuckDBEngine()
    assert eng.execute(info.org_id, [info], 'SELECT count(*) FROM "locktest"').rows[0][0] == 6
    for evil in ["SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM read_text('/etc/hostname')"]:
        with pytest.raises(QueryError):
            eng.execute(info.org_id, [info], evil)
    with pytest.raises(QueryError):
        eng.execute(info.org_id, [info], "SET enable_external_access=true")


@pytest.mark.parametrize("cols,types,rows,q,kind", [
    (["total"], ["DOUBLE"], [[42.0]], "", "kpi"),
    (["month", "revenue"], ["DATE", "DOUBLE"], [["2024-01-01", 1], ["2024-02-01", 2]], "", "line"),
    (["p", "r"], ["VARCHAR", "DOUBLE"], [["a", 1], ["b", 2]], "", "bar"),
    (["p", "r"], ["VARCHAR", "DOUBLE"], [["a", 1], ["b", 2], ["c", 3]], "revenue share by product", "pie"),
    (["x", "y"], ["DOUBLE", "DOUBLE"], [[1, 2], [2, 3], [3, 5]], "", "scatter"),
    (["v"], ["DOUBLE"], [[i] for i in range(30)], "", "histogram"),
    (["a", "b"], ["VARCHAR", "VARCHAR"], [["x", "y"]], "", "table"),
    ([], [], [], "", "table"),
])
def test_chart_selection(cols, types, rows, q, kind):
    assert choose_chart(cols, types, rows, q)["kind"] == kind
