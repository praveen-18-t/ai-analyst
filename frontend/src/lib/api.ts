import { currentToken } from "./auth";

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as any) };
  const token = await currentToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const post = (path: string, body: any) => api(path, { method: "POST", body: JSON.stringify(body) });
export const csvUrl = (qid: string, taskId: string) => `${BASE}/api/queries/${qid}/export.csv?task_id=${taskId}`;
