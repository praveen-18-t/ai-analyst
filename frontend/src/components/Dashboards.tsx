"use client";
import { useEffect, useState } from "react";
import { api, post } from "@/lib/api";
import ResultTable from "./ResultTable";
import VegaChart from "./VegaChart";

export default function Dashboards({ canWrite }: { canWrite: boolean }) {
  const [boards, setBoards] = useState<any[]>([]);
  const [sel, setSel] = useState<string>("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const load = () => api("/api/dashboards").then((b) => { setBoards(b); if (!sel && b[0]) setSel(b[0].id); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const cur = boards.find((b) => b.id === sel);

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(cur, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${cur.name}.json`; a.click();
  };

  return (
    <>
      <h1>Dashboards</h1>
      <p className="sub">Collect charts and tables from your analysis. Save results from the Analyst tab.</p>
      {err && <p className="err">{err}</p>}
      <div className="panel row">
        <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ width: "auto", minWidth: 200 }} aria-label="Dashboard">
          {boards.length === 0 && <option value="">No dashboards</option>}
          {boards.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        {cur && <button className="btn ghost small" onClick={exportJson}>Export JSON</button>}
        {cur && canWrite && <button className="btn danger small" onClick={async () => { await api(`/api/dashboards/${cur.id}`, { method: "DELETE" }); setSel(""); load(); }}>Delete dashboard</button>}
        <span className="grow" />
        {canWrite && (<>
          <input type="text" style={{ width: 200 }} placeholder="New dashboard name" value={name} onChange={(e) => setName(e.target.value)} aria-label="New dashboard name" />
          <button className="btn small" disabled={!name} onClick={async () => { const d = await post("/api/dashboards", { name }); setName(""); setSel(d.id); load(); }}>Create</button>
        </>)}
      </div>

      {cur && cur.widgets.length === 0 && <div className="panel muted">This dashboard is empty. Ask a question in the Analyst tab and choose “Save to dashboard”.</div>}
      <div className="grid2">
        {cur?.widgets.map((w: any) => (
          <div className="panel" key={w.id}>
            <div className="row"><h2 className="grow">{w.title}</h2>
              {canWrite && <button className="btn danger small" onClick={async () => { await api(`/api/dashboards/${cur.id}/widgets/${w.id}`, { method: "DELETE" }); load(); }}>Remove</button>}
            </div>
            {w.kind === "kpi" && <div className="kpis">{w.items.map((k: any) => <div className="kpi" key={k.label}><div className="v">{Number(k.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</div><div className="l">{k.label.replace(/_/g, " ")}</div></div>)}</div>}
            {w.vega && <VegaChart spec={w.vega} name={w.title} />}
            {w.kind === "table" && <ResultTable columns={w.columns} rows={w.rows} max={20} />}
          </div>
        ))}
      </div>
    </>
  );
}
