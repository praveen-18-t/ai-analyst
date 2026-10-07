"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import AnswerView from "./AnswerView";

export default function History() {
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/queries").then(setItems).catch((e) => setErr(e.message)); }, []);
  return (
    <>
      <h1>Query history</h1>
      <p className="sub">Every question asked in your organization, with the SQL that was run.</p>
      {err && <p className="err">{err}</p>}
      {open && <><button className="btn ghost small" onClick={() => setOpen(null)}>Back to history</button><div className="q-bubble">{open.question}</div><AnswerView r={open} /></>}
      {!open && (
        <div className="panel">
          {items.length === 0 ? <p className="muted">No questions yet. Ask one in the Analyst tab.</p> : (
            <table className="t">
              <thead><tr><th>Question</th><th>SQL</th><th>Status</th><th>Time</th><th>Cost</th><th>When</th></tr></thead>
              <tbody>{items.map((q) => (
                <tr key={q.id} style={{ cursor: "pointer" }} onClick={() => api(`/api/queries/${q.id}`).then(setOpen)}>
                  <td style={{ maxWidth: 360 }}>{q.question}</td>
                  <td style={{ fontFamily: "var(--mono)", fontSize: 12, maxWidth: 360 }}>{q.sql[0] || ""}</td>
                  <td><span className={`pill ${q.status === "ok" ? "ok" : "bad"}`}>{q.status}</span></td>
                  <td className="num">{(q.duration_ms / 1000).toFixed(1)}s</td><td className="num">${q.cost_usd}</td>
                  <td>{new Date(q.created_at).toLocaleString()}</td>
                </tr>))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
}
