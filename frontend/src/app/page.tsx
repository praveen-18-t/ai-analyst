"use client";
import { useEffect, useState } from "react";
import Chat from "@/components/Chat";
import Dashboards from "@/components/Dashboards";
import Datasets from "@/components/Datasets";
import Docs from "@/components/Docs";
import History from "@/components/History";
import Login from "@/components/Login";
import { api } from "@/lib/api";
import { authEnabled, currentToken, signOut } from "@/lib/auth";

const TABS = [
  ["chat", "Analyst"], ["datasets", "Datasets"], ["history", "Query history"], ["dashboards", "Dashboards"], ["docs", "Documents"],
] as const;

export default function Page() {
  const [tab, setTab] = useState<string>("chat");
  const [me, setMe] = useState<any>(null);
  const [needLogin, setNeedLogin] = useState(false);
  const [err, setErr] = useState("");

  const boot = async () => {
    if (authEnabled && !(await currentToken())) return setNeedLogin(true);
    setNeedLogin(false);
    api("/api/me").then(setMe).catch((e) => setErr(e.message));
  };
  useEffect(() => { boot(); }, []);

  if (needLogin) return <Login onDone={boot} />;
  if (!me) return <main className="main">{err ? <p className="err">Cannot reach the API: {err}</p> : <span className="spin" />}</main>;
  const canWrite = me.role === "analyst" || me.role === "admin";

  return (
    <div className="shell">
      <nav className="rail" aria-label="Main">
        <div className="brand">Analyst</div>
        {TABS.map(([id, label]) => (
          <button key={id} className="nav" aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>{label}</button>
        ))}
        <div className="who">
          {me.email}<br /><span className="muted">{me.role}</span>
          {authEnabled && <><br /><button onClick={() => { signOut(); location.reload(); }}>Sign out</button></>}
        </div>
      </nav>
      <main className="main">
        {tab === "chat" && <Chat />}
        {tab === "datasets" && <Datasets canWrite={canWrite} isAdmin={me.role === "admin"} />}
        {tab === "history" && <History />}
        {tab === "dashboards" && <Dashboards canWrite={canWrite} />}
        {tab === "docs" && <Docs canWrite={canWrite} />}
      </main>
    </div>
  );
}
