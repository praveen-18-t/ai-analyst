"use client";
import { useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";
import ResultTable from "./ResultTable";

const statusPill = (s: string) => (s === "ready" ? "ok" : s === "failed" ? "bad" : "warn");

function Profile({ id, onClose }: { id: string; onClose: () => void }) {
  const [d, setD] = useState<any>(null);
  const [prev, setPrev] = useState<any>(null);
  useEffect(() => {
    api(`/api/datasets/${id}`).then(setD).catch(() => {});
    api(`/api/datasets/${id}/preview?limit=20`).then(setPrev).catch(() => {});
  }, [id]);
  if (!d) return <div className="panel"><span className="spin" /></div>;
  const p = d.profile || {};
  return (
    <div className="panel">
      <div className="row"><h2 className="grow">{d.name} <span className="muted">· table "{d.table_name}"</span></h2><button className="btn ghost small" onClick={onClose}>Close</button></div>
      {p.quality && (
        <p>
          Data quality <span className={`pill ${p.quality.score >= 85 ? "ok" : p.quality.score >= 60 ? "warn" : "bad"}`}>{p.quality.score}/100</span>{" "}
          <span className="muted">{p.row_count?.toLocaleString()} rows · {p.column_count} columns · {p.duplicate_rows} duplicate rows</span>
        </p>
      )}
      {p.quality?.issues?.length > 0 && (
        <ul>{p.quality.issues.map((i: any, k: number) => <li key={k}><span className={`pill ${i.severity === "error" ? "bad" : i.severity === "warning" ? "warn" : ""}`}>{i.severity}</span> {i.column ? <strong>{i.column}: </strong> : null}{i.message}</li>)}</ul>
      )}
      <h2>Columns</h2>
      <div className="scroll">
        <table className="t">
          <thead><tr><th>Column</th><th>Type</th><th>Missing</th><th>Distinct</th><th>Min</th><th>Median</th><th>Max</th><th>Top values / samples</th></tr></thead>
          <tbody>
            {(p.columns || []).map((c: any) => (
              <tr key={c.name}>
                <td>{c.name}</td><td>{c.type}</td><td>{c.null_pct}%</td><td>{c.distinct_count}</td>
                <td>{c.min != null ? String(c.min).slice(0, 19) : ""}</td><td>{c.median != null ? Number(c.median).toLocaleString(undefined, { maximumFractionDigits: 2 }) : ""}</td><td>{c.max != null ? String(c.max).slice(0, 19) : ""}</td>
                <td>{(c.top_values ? c.top_values.map((v: any) => `${v.value} (${v.count})`) : c.samples || []).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {prev && <><h2 style={{ marginTop: 16 }}>Preview</h2><ResultTable columns={prev.columns} rows={prev.rows} max={20} /></>}
    </div>
  );
}

export default function Datasets({ canWrite, isAdmin }: { canWrite: boolean; isAdmin: boolean }) {
  const [items, setItems] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [mode, setMode] = useState<"file" | "db" | "api">("file");
  const file = useRef<HTMLInputElement>(null);
  const [f, setF] = useState({ name: "", url: "", query: "", recordsPath: "", headers: "" });

  const load = () => api("/api/datasets").then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!items.some((d) => d.status === "uploaded" || d.status === "processing")) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [items]);

  const run = async (fn: () => Promise<any>) => {
    setBusy(true); setErr("");
    try { await fn(); await load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const upload = () => run(async () => {
    const file0 = file.current?.files?.[0];
    if (!file0) throw new Error("Choose a CSV, Excel, Parquet or JSON file first.");
    const fd = new FormData(); fd.append("file", file0); if (f.name) fd.append("name", f.name);
    await api("/api/datasets/upload", { method: "POST", body: fd });
    if (file.current) file.current.value = "";
  });
  const importDb = () => run(() => post("/api/datasets/import-db", { name: f.name, url: f.url, query: f.query }));
  const importApi = () => run(() => {
    let headers = {};
    try { headers = f.headers ? JSON.parse(f.headers) : {}; } catch { throw new Error("Headers must be valid JSON, e.g. {\"Authorization\": \"Bearer …\"}"); }
    return post("/api/datasets/import-api", { name: f.name, url: f.url, headers, records_path: f.recordsPath || null });
  });

  return (
    <>
      <h1>Datasets</h1>
      <p className="sub">Bring in data from a file, a PostgreSQL or MySQL query, or a web API. Each dataset is profiled and checked for quality before you can ask questions of it.</p>

      {canWrite && (
        <div className="panel">
          <div className="row" role="tablist" style={{ marginBottom: 6 }}>
            {(["file", "db", "api"] as const).map((m) => (
              <button key={m} role="tab" aria-selected={mode === m} className={`btn small ${mode === m ? "" : "ghost"}`} onClick={() => setMode(m)}>
                {m === "file" ? "File" : m === "db" ? "Database" : "API"}
              </button>
            ))}
          </div>
          <label className="f" htmlFor="dname">Dataset name {mode === "file" && <span>(optional)</span>}</label>
          <input id="dname" type="text" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="sales" />
          {mode === "file" && (<>
            <label className="f" htmlFor="file">CSV, Excel (.xlsx), Parquet or JSON</label>
            <input id="file" ref={file} type="file" accept=".csv,.tsv,.txt,.xlsx,.xlsm,.parquet,.json,.jsonl" />
            <p><button className="btn" disabled={busy} onClick={upload}>Upload</button></p>
          </>)}
          {mode === "db" && (<>
            <label className="f" htmlFor="dburl">Connection URL</label>
            <input id="dburl" type="text" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="postgresql://user:password@host:5432/dbname" />
            <label className="f" htmlFor="dbq">SELECT query to import</label>
            <textarea id="dbq" value={f.query} onChange={(e) => setF({ ...f, query: e.target.value })} placeholder="SELECT * FROM orders" />
            <p className="muted">The data is copied as a snapshot. The password is used once and never stored.</p>
            <p><button className="btn" disabled={busy || !f.name || !f.url || !f.query} onClick={importDb}>Import</button></p>
          </>)}
          {mode === "api" && (<>
            <label className="f" htmlFor="apiurl">Endpoint URL (returns JSON or CSV)</label>
            <input id="apiurl" type="text" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://api.example.com/v1/orders" />
            <label className="f" htmlFor="rp">Path to the records in the JSON (optional)</label>
            <input id="rp" type="text" value={f.recordsPath} onChange={(e) => setF({ ...f, recordsPath: e.target.value })} placeholder="data.items" />
            <label className="f" htmlFor="hd">Headers as JSON (optional)</label>
            <input id="hd" type="text" value={f.headers} onChange={(e) => setF({ ...f, headers: e.target.value })} placeholder='{"Authorization": "Bearer …"}' />
            <p><button className="btn" disabled={busy || !f.name || !f.url} onClick={importApi}>Import</button></p>
          </>)}
          {err && <p className="err" role="alert">{err}</p>}
        </div>
      )}

      {open && <Profile id={open} onClose={() => setOpen(null)} />}

      <div className="panel">
        {items.length === 0 ? <p className="muted">No datasets yet.{canWrite ? " Upload your first file above." : ""}</p> : (
          <table className="t">
            <thead><tr><th>Name</th><th>Source</th><th>Rows</th><th>Quality</th><th>Status</th><th /></tr></thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id}>
                  <td><strong>{d.name}</strong> <span className="muted">{d.table_name}</span></td>
                  <td>{d.source_type}</td><td className="num">{d.row_count?.toLocaleString()}</td>
                  <td>{d.quality_score != null ? `${d.quality_score}/100` : ""}</td>
                  <td><span className={`pill ${statusPill(d.status)}`}>{d.status}</span> {d.status === "failed" && <span className="err">{d.error}</span>}</td>
                  <td>
                    {d.status === "ready" && <button className="btn ghost small" onClick={() => setOpen(d.id)}>Profile</button>}{" "}
                    {isAdmin && <button className="btn danger small" onClick={() => confirm(`Delete ${d.name}?`) && run(() => api(`/api/datasets/${d.id}`, { method: "DELETE" }))}>Delete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
