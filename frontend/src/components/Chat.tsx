"use client";
import { useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";
import AnswerView from "./AnswerView";

type Turn = { q: string; r?: any; err?: string };

export default function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { api("/api/datasets").then((d) => setDatasets(d.filter((x: any) => x.status === "ready"))).catch(() => {}); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  const ask = async (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true); setQ("");
    setTurns((t) => [...t, { q: text }]);
    try {
      const r = await post("/api/ask", { question: text, dataset_ids: selected.length ? selected : null });
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, r } : x)));
    } catch (e: any) {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, err: e.message } : x)));
    } finally { setBusy(false); }
  };

  const suggestions = datasets.length ? ["What are the main trends in this data?", "Which categories drive the most revenue?", "Show the monthly trend of revenue"] : [];

  return (
    <>
      <h1>Analyst</h1>
      <p className="sub">Ask a question about your data. The analyst plans the work, writes and checks the SQL, then explains what it found.</p>

      {datasets.length > 0 && (
        <div className="row" style={{ marginBottom: 8 }}>
          <span className="muted">Data:</span>
          {datasets.map((d) => (
            <label key={d.id} className="pill" style={{ cursor: "pointer", opacity: selected.length && !selected.includes(d.id) ? 0.5 : 1 }}>
              <input type="checkbox" style={{ marginRight: 4 }} checked={selected.includes(d.id)}
                onChange={() => setSelected((s) => (s.includes(d.id) ? s.filter((x) => x !== d.id) : [...s, d.id]))} />
              {d.name}
            </label>
          ))}
          <span className="muted">{selected.length ? "" : "(all datasets)"}</span>
        </div>
      )}
      {datasets.length === 0 && <div className="panel">No datasets are ready yet. Add one under <strong>Datasets</strong> to start asking questions.</div>}

      {turns.map((t, i) => (
        <div key={i}>
          <div className="q-bubble">{t.q}</div>
          {t.r && <AnswerView r={t.r} />}
          {t.err && <p className="err">{t.err}</p>}
          {!t.r && !t.err && <p className="muted"><span className="spin" /> Planning, querying and checking…</p>}
        </div>
      ))}
      <div ref={end} />

      <form className="panel" style={{ position: "sticky", bottom: 12 }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <div className="row">
          <input className="grow" type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. What were our top 10 products by revenue?" aria-label="Your question" />
          <button className="btn" disabled={busy || !q.trim()}>{busy ? "Working…" : "Ask"}</button>
        </div>
        {turns.length === 0 && <div className="suggest">{suggestions.map((s) => <button type="button" key={s} onClick={() => ask(s)}>{s}</button>)}</div>}
      </form>
    </>
  );
}
