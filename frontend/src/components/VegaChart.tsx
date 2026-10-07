"use client";
import { useEffect, useRef } from "react";

export default function VegaChart({ spec, name = "chart" }: { spec: any; name?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const viewRef = useRef<any>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const embed = (await import("vega-embed")).default;
      if (!alive || !ref.current) return;
      const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const res = await embed(ref.current, spec, {
        actions: false,
        renderer: "svg",
        theme: dark ? "dark" : undefined,
        config: { font: "IBM Plex Sans", background: "transparent", range: { category: ["#1b6b86", "#d98f2b", "#4e9a6f", "#8a5fb5", "#c4544c", "#6b7f89"] } },
      });
      viewRef.current = res.view;
    })().catch(() => {});
    return () => { alive = false; viewRef.current?.finalize?.(); };
  }, [spec]);

  const png = async () => {
    const url = await viewRef.current?.toImageURL("png", 2);
    if (!url) return;
    const a = document.createElement("a");
    a.href = url; a.download = `${name}.png`; a.click();
  };

  return (
    <div>
      <div ref={ref} className="chart" />
      <button className="btn ghost small" onClick={png}>Download PNG</button>
    </div>
  );
}
