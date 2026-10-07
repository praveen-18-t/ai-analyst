export default function ResultTable({ columns, rows, max = 200 }: { columns: string[]; rows: any[][]; max?: number }) {
  const shown = rows.slice(0, max);
  return (
    <div>
      <div className="scroll">
        <table className="t">
          <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j} className={typeof v === "number" ? "num" : ""}>
                    {v === null ? <span className="muted">null</span> : typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > max && <p className="muted">Showing first {max} of {rows.length} rows.</p>}
    </div>
  );
}
