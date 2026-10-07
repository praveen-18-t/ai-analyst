"use client";
import { useState } from "react";
import { signIn } from "@/lib/auth";

export default function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  return (
    <form className="panel login" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setErr("");
      try { await signIn(u, p); onDone(); } catch (x: any) { setErr(x.message || "Sign-in failed"); } finally { setBusy(false); }
    }}>
      <h1>Sign in</h1>
      <p className="sub">Use your organization account.</p>
      <label className="f" htmlFor="u">Email</label><input id="u" type="text" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} />
      <label className="f" htmlFor="p">Password</label><input id="p" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} />
      {err && <p className="err" role="alert">{err}</p>}
      <p><button className="btn" disabled={busy || !u || !p}>Sign in</button></p>
    </form>
  );
}
