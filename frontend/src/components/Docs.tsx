"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export default function Docs({ canWrite }: { canWrite: boolean }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const load = () => api("/api/docs").then(setDocs).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const upload = async () => {
    const f = file.current?.files?.[0];
    if (!f) return setErr("Choose a PDF, Markdown or text file first.");
    setBusy(true); setErr("");
    try { const fd = new FormData(); fd.append("file", f); await api("/api/docs", { method: "POST", body: fd }); if (file.current) file.current.value = ""; await load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <>
      <h1>Documents</h1>
      <p className="sub">Add policies, definitions and playbooks. The analyst reads them alongside your data, so it can answer questions like “according to our sales policy, why was this order classified as premium?”</p>
      {canWrite && (
        <div className="panel">
          <label className="f" htmlFor="doc">PDF, Markdown or text</label>
          <input id="doc" ref={file} type="file" accept=".pdf,.md,.markdown,.txt" />
          <p><button className="btn" disabled={busy} onClick={upload}>{busy ? "Indexing…" : "Add document"}</button></p>
          {err && <p className="err" role="alert">{err}</p>}
        </div>
      )}
      <div className="panel">
        {docs.length === 0 ? <p className="muted">No documents yet.</p> : (
          <table className="t"><thead><tr><th>Name</th><th>Passages</th><th>Added</th><th /></tr></thead>
            <tbody>{docs.map((d) => (
              <tr key={d.id}><td>{d.name}</td><td className="num">{d.chunks}</td><td>{new Date(d.created_at).toLocaleDateString()}</td>
                <td>{canWrite && <button className="btn danger small" onClick={async () => { await api(`/api/docs/${d.id}`, { method: "DELETE" }); load(); }}>Delete</button>}</td></tr>))}
            </tbody></table>
        )}
      </div>
    </>
  );
}
