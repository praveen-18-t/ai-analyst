"""Visualization Agent: deterministic chart selection from result shape (+ LLM-written titles)."""
import re

from app import llm as llm_mod
from app.profiling_kinds import kind_of  # re-exported helper

PIE_WORDS = re.compile(r"\b(share|proportion|percent|percentage|breakdown|composition|split|mix)\b", re.I)
SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"


def _safe(c: str) -> str:
    return re.sub(r"[.\[\]\\'\"]", "_", str(c))


def choose_chart(columns: list, types: list, rows: list, question: str = "") -> dict:
    n = len(rows)
    if n == 0:
        return {"kind": "table"}
    cols = [_safe(c) for c in columns]
    kinds = [kind_of(t) for t in types]
    nums = [c for c, k in zip(cols, kinds) if k == "numeric"]
    temps = [c for c, k in zip(cols, kinds) if k == "temporal"]
    cats = [c for c, k in zip(cols, kinds) if k in ("text", "boolean", "other")]
    values = [dict(zip(cols, r)) for r in rows[:500]]

    def spec(mark, enc, extra=None, height=320):
        s = {"$schema": SCHEMA, "data": {"values": values}, "mark": mark, "encoding": enc,
             "width": "container", "height": height, "autosize": {"type": "fit", "contains": "padding"}}
        s.update(extra or {})
        return s

    if n == 1 and nums and len(cols) <= 6 and len(cats) + len(temps) <= 1:
        return {"kind": "kpi", "items": [{"label": c, "value": rows[0][cols.index(c)]} for c in nums]}
    if temps and nums and n >= 2:
        x = temps[0]
        enc = {"x": {"field": x, "type": "temporal"}}
        extra = None
        if len(cats) == 1 and len(nums) == 1:
            enc.update(y={"field": nums[0], "type": "quantitative"}, color={"field": cats[0], "type": "nominal"})
        elif len(nums) > 1:
            extra = {"transform": [{"fold": nums[:4], "as": ["series", "value"]}]}
            enc.update(y={"field": "value", "type": "quantitative", "title": None}, color={"field": "series", "type": "nominal"})
        else:
            enc["y"] = {"field": nums[0], "type": "quantitative"}
        return {"kind": "line", "vega": spec({"type": "line", "point": True}, enc, extra)}
    if len(nums) == 1 and len(cols) == 1 and n >= 10:
        return {"kind": "histogram", "vega": spec("bar", {
            "x": {"field": nums[0], "type": "quantitative", "bin": {"maxbins": 20}},
            "y": {"aggregate": "count", "type": "quantitative", "title": "count"}})}
    if cats and nums and n <= 50:
        x, y = cats[0], nums[0]
        non_neg = all((r[cols.index(y)] or 0) >= 0 for r in rows)
        if PIE_WORDS.search(question) and 2 <= n <= 8 and non_neg:
            return {"kind": "pie", "vega": spec({"type": "arc", "innerRadius": 50}, {
                "theta": {"field": y, "type": "quantitative"}, "color": {"field": x, "type": "nominal"}}, height=320)}
        if n > 8 or max(len(str(r[cols.index(x)])) for r in rows) > 12:
            enc = {"y": {"field": x, "type": "nominal", "sort": "-x"}, "x": {"field": y, "type": "quantitative"}}
            return {"kind": "bar", "vega": spec("bar", enc, height=max(200, 26 * n))}
        return {"kind": "bar", "vega": spec("bar", {"x": {"field": x, "type": "nominal", "sort": "-y"},
                                                       "y": {"field": y, "type": "quantitative"}})}
    if len(nums) >= 2 and not cats and not temps and n >= 3:
        return {"kind": "scatter", "vega": spec("point", {
            "x": {"field": nums[0], "type": "quantitative"}, "y": {"field": nums[1], "type": "quantitative"}})}
    return {"kind": "table"}


def run_viz(tasks: list[dict], question: str) -> list[dict]:
    charts = []
    for t in tasks:
        ch = choose_chart(t["columns"], t["types"], t["rows"], t["question"])
        ch.update(task_id=t["id"], title=t["question"])
        charts.append(ch)
    candidates = [c for c in charts if c["kind"] != "table"]
    if candidates:
        try:
            out = llm_mod.get_llm().complete_json(
                "[viz] You write concise chart titles (max 9 words) for business dashboards. "
                'Return JSON: {"titles": {"<task_id>": "<title>"}}',
                "Overall question: " + question + "\n" + "\n".join(
                    f'{c["task_id"]}: kind={c["kind"]}; question={next(t["question"] for t in tasks if t["id"] == c["task_id"])}; '
                    f'columns={next(t["columns"] for t in tasks if t["id"] == c["task_id"])}' for c in candidates),
                max_tokens=400)
            for c in charts:
                c["title"] = str(out.get("titles", {}).get(c["task_id"], c["title"]))[:120]
        except Exception:  # noqa: BLE001 - titles are cosmetic
            pass
    for c in charts:
        if "vega" in c:
            c["vega"]["title"] = c["title"]
    return charts
