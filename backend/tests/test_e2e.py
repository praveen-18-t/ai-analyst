import time

CSV = b"""Order ID,Product,Quantity,Revenue,Order Date
1,Widget,3,100.5,2024-01-03
2,Widget,2,199.5,2024-01-09
3,Gadget,1,50,2024-02-01
4,Gizmo,5,75,2024-02-11
5,Gadget,1,60,2024-03-05
5,Gadget,1,60,2024-03-05
"""


def upload(client, name="sales", headers=None):
    r = client.post("/api/datasets/upload", files={"file": ("sales.csv", CSV, "text/csv")}, data={"name": name}, headers=headers or {})
    assert r.status_code == 202, r.text
    return r.json()


def test_upload_profile_ask_flow(client, fake_llm):
    ds = upload(client)
    for _ in range(20):  # background task runs inline in TestClient, but be tolerant
        d = client.get(f"/api/datasets/{ds['id']}").json()
        if d["status"] in ("ready", "failed"):
            break
        time.sleep(0.2)
    assert d["status"] == "ready", d
    assert d["row_count"] == 6
    assert [c["name"] for c in d["columns"]] == ["order_id", "product", "quantity", "revenue", "order_date"]
    prof = d["profile"]
    assert prof["duplicate_rows"] == 1
    assert any(i["check"] == "duplicate_rows" for i in prof["quality"]["issues"])
    assert client.get(f"/api/datasets/{ds['id']}/preview").json()["rows"]

    r = client.post("/api/ask", json={"question": "What were our top products by revenue?"})
    assert r.status_code == 200, r.text
    out = r.json()
    t = out["tasks"][0]
    assert t["error"] is None and t["rows"][0][0] == "Widget"
    assert len(t["attempts"]) == 2  # first failed, self-corrected
    assert out["charts"][0]["kind"] == "bar" and out["charts"][0]["title"] == "Revenue by product"
    assert out["insights"] and out["review"]["approved"] is True
    assert {s["agent"] for s in out["trace"]} >= {"planner", "data_analyst", "visualization", "insight", "reviewer"}

    assert client.get("/api/queries").json()[0]["id"] == out["id"]
    assert client.get(f"/api/queries/{out['id']}/export.csv").text.startswith("product,total_revenue")
    assert any(a["action"] == "ask" for a in client.get("/api/audit").json())


def test_tenant_isolation_and_roles(client):
    a = {"x-dev-org": "org-a", "x-dev-role": "admin"}
    b = {"x-dev-org": "org-b", "x-dev-role": "admin"}
    ds = upload(client, "private", a)
    assert client.get(f"/api/datasets/{ds['id']}", headers=b).status_code == 404
    assert client.get("/api/datasets", headers=b).json() == []
    viewer = {"x-dev-org": "org-a", "x-dev-role": "viewer"}
    r = client.post("/api/datasets/upload", files={"file": ("x.csv", CSV)}, headers=viewer)
    assert r.status_code == 403
    assert client.delete(f"/api/datasets/{ds['id']}", headers=viewer).status_code == 403


def test_dashboard_and_docs(client):
    d = client.post("/api/dashboards", json={"name": "Main"}).json()
    d = client.post(f"/api/dashboards/{d['id']}/widgets", json={"title": "KPI", "kind": "kpi", "items": [{"label": "x", "value": 1}]}).json()
    assert len(d["widgets"]) == 1
    doc = client.post("/api/docs", files={"file": ("policy.md", b"Refund policy: orders above 100 dollars are classified as premium.\n\nShipping is free.", "text/markdown")})
    assert doc.status_code == 201 and doc.json()["chunks"] >= 1
    from app.db import SessionLocal
    from app.rag.service import retrieve
    me = client.get("/api/me").json()
    with SessionLocal() as db:
        hits = retrieve(db, me["org_id"], "why is an order classified as premium?")
    assert hits and "premium" in hits[0]["text"]
