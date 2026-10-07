"use client";
import { useEffect, useState } from "react";
import { api, csvUrl, post } from "@/lib/api";
import ResultTable from "./ResultTable";
import VegaChart from "./VegaChart";

function Kpis({ items }: { items: { label: string; value: any }[] }) {
  return (
    <div className="kpis">
      {items.map((k) => (
        <div className="kpi" key={k.label}>
          <div className="v">{typeof k.value === "number" ? k.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(k.value)}</div>
          <div className="l">{k.label.replace(/_/g, " ")}</div>
        </div>
      ))}
    </div>
  );
}

function SaveToDashboard({ widget }: { widget: any }) {
  const [boards, setBoards] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { if (open) api("/api/dashboards").then(setBoards).catch(() => {}); }, [open]);
  const add = async (id?: string) => {
    try {
      let did = id;
      if (!did) did = (await post("/api/dashboards", { name: "My dashboard" })).id;
      await post(`/api/dashboards/${did}/widgets`, widget);
      setMsg("Saved to dashboard"); setOpen(false);
    } catch (e: any) { setMsg(e.message); }
  };
  return (
    <span>
      <button className="btn ghost small" onClick={() => setOpen(!open)}>Save to dashboard</button>{" "}
      {open && (
        <select onChange={(e) => add(e.target.value || undefined)} defaultValue="" aria-label="Choose dashboard" style={{ width: "auto" }}>
          <option value="" disabled>Choose…</option>
          {boards.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          <option value="">New dashboard</option>
        </select>
      )}
      {msg && <span className="muted"> {msg}</span>}
    </span>
  );
}

export default function AnswerView({ r }: { r: any }) {
  const tasks: any[] = r.tasks || [];
  return (
    <div className="panel">
      <div className="answer">{r.answer}</div>

      {r.key_findings?.length > 0 && <ul>{r.key_findings.map((k: string, i: number) => <li key={i}>{k}</li>)}</ul>}
      {r.caveats?.length > 0 && <p className="muted">Caveats: {r.caveats.join(" ")}</p>}

      {tasks.map((t) => {
        const chart = (r.charts || []).find((c: any) => c.task_id === t.id);
        return (
          <section key={t.id} style={{ marginTop: 22 }}>
            {tasks.length > 1 && <h2>{t.question}</h2>}
            {t.error && <p className="err">{t.error}</p>}
            {chart?.kind === "kpi" && <Kpis items={chart.items} />}
            {chart?.vega && <VegaChart spec={chart.vega} name={t.id} />}
            {t.rows?.length > 0 && (
              <details open={!chart || chart.kind === "table"}>
                <summary>Table ({t.row_count} rows{t.truncated ? ", truncated" : ""})</summary>
                <ResultTable columns={t.columns} rows={t.rows} />
              </details>
            )}
            {t.sql && (
              <details>
                <summary>SQL{t.attempts?.length > 1 ? ` (corrected after ${t.attempts.length - 1} failed attempt${t.attempts.length > 2 ? "s" : ""})` : ""}</summary>
                <pre className="sql">{t.sql}</pre>
                {t.explanation && <p className="muted">{t.explanation}</p>}
              </details>
            )}
            <div className="row">
              {t.rows?.length > 0 && <a className="btn ghost small" href={csvUrl(r.id, t.id)}>Download CSV</a>}
              {chart && chart.kind !== "table" && (
                <SaveToDashboard widget={{ title: chart.title, kind: chart.kind, vega: chart.vega, items: chart.items, query_id: r.id }} />
              )}
              {t.rows?.length > 0 && chart?.kind === "table" && (
                <SaveToDashboard widget={{ title: t.question, kind: "table", columns: t.columns, rows: t.rows.slice(0, 100), query_id: r.id }} />
              )}
            </div>
          </section>
        );
      })}

      {r.insights?.length > 0 && (
        <section style={{ marginTop: 22 }}>
          <h2>Insights</h2>
          {r.insights.map((i: any, k: number) => (
            <div key={k} className={`insight ${i.impact}`}><strong>{i.title}</strong><div>{i.detail}</div></div>
          ))}
          {r.recommendations?.length > 0 && (<><h2 style={{ marginTop: 14 }}>Recommended next steps</h2><ul>{r.recommendations.map((x: string, k: number) => <li key={k}>{x}</li>)}</ul></>)}
        </section>
      )}

      {r.sources?.length > 0 && (
        <details><summary>Documents used ({r.sources.length})</summary>
          {r.sources.map((s: any, i: number) => <p key={i}><span className="pill">{s.doc}</span> <span className="muted">{s.text}</span></p>)}
        </details>
      )}

      <details>
        <summary>
          How this was checked{" "}
          {r.review?.approved === true && <span className="pill ok">reviewer approved</span>}
          {r.review?.approved === false && <span className="pill warn">{r.review.revised ? "reviewer revised answer" : "reviewer flagged issues"}</span>}
        </summary>
        {r.review?.issues?.length > 0 && <ul>{r.review.issues.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>}
        <div className="trace">{(r.trace || []).map((s: any, i: number) => <span key={i}>{s.agent} {s.ms}ms{s.ok ? "" : " ✕"}</span>)}</div>
        {r.usage && <p className="muted">{r.usage.llm_calls} model calls · {r.usage.input_tokens + r.usage.output_tokens} tokens · ${r.usage.cost_usd} · {(r.duration_ms / 1000).toFixed(1)}s</p>}
      </details>
    </div>
  );
}
