import { supabase } from "./supabase";
import type { Folder, Meta, Placement, Project, Result } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";  // leer: API unter derselben Adresse wie die Web-App
const KEY = process.env.NEXT_PUBLIC_API_KEY ?? "demo-schluessel";

async function auth(): Promise<string> {
  if (!supabase) return `Bearer ${KEY}`;
  const { data } = await supabase.auth.getSession();
  return `Bearer ${data.session?.access_token ?? ""}`;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(BASE + path, { ...init, headers: { Authorization: await auth(), ...(init.headers ?? {}) } });
  if (res.status === 401 && supabase && typeof window !== "undefined") window.location.href = "/login";
  return res;
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await send(path, init);
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* Text ohne JSON */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });

export const api = {
  health: () => call<{ ok: boolean; claude: boolean }>("/health"),
  me: () => call<{ org: string; name: string; trial_left: number | null; contact: string }>("/me"),
  signup: (body: { company: string; email: string; password: string; business: boolean }) =>
    call<{ org: string; trial_left: number }>("/signup", { method: "POST", ...json(body) }),
  list: () => call<Meta[]>("/projects"),
  get: (id: string) => call<Project>(`/projects/${id}`),
  demo: (name: "bungalow" | "darmstaedter14", folderId = "") =>
    call<Meta>(`/projects/demo/${name}${folderId ? `?folder_id=${folderId}` : ""}`, { method: "POST" }),
  pdfPages: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<{ pages: { page: number; mm: [number, number]; thumb: string }[] }>("/pdf/pages", { method: "POST", body: fd });
  },
  upload: (file: File, f: { name: string; notes?: string; folder_id?: string; floor?: string; part?: string; page?: string; crop?: string }) => {
    const fd = new FormData();
    fd.append("file", file);
    for (const [k, v] of Object.entries(f)) if (v) fd.append(k, v);
    return call<Meta>("/projects", { method: "POST", body: fd });
  },
  patchPlan: (id: string, body: { name?: string; floor?: string; part?: string; folder_id?: string }) =>
    call<Meta>(`/projects/${id}`, { method: "PATCH", ...json(body) }),
  folders: () => call<{ folders: Folder[]; unassigned: Meta[] }>("/folders"),
  folder: (id: string) => call<{ folder: Folder; plans: Meta[]; floors: string[] }>(`/folders/${id}`),
  createFolder: (name: string) => call<Folder>("/folders", { method: "POST", ...json({ name }) }),
  patchFolder: (id: string, body: { name?: string; assembly?: Record<string, Record<string, Placement>> }) =>
    call<Folder>(`/folders/${id}`, { method: "PATCH", ...json(body) }),
  removeFolder: (id: string) => call<{ ok: boolean }>(`/folders/${id}`, { method: "DELETE" }),
  floorParts: (id: string, floor: string) =>
    call<{ parts: ({ id: string; label: string } & Placement)[]; saved: boolean }>(`/folders/${id}/floors/${encodeURIComponent(floor)}/geometry`),
  analyze: (id: string) => call<Meta>(`/projects/${id}/analyze`, { method: "POST" }),
  remove: (id: string) => call<{ ok: boolean }>(`/projects/${id}`, { method: "DELETE" }),
  measure: (id: string, m: { axis: string; a: string; b: string; value: number; note?: string }) =>
    call<Result>(`/projects/${id}/measurements`, { method: "POST", ...json(m) }),
  unmeasure: (id: string, mid: string) => call<Result>(`/projects/${id}/measurements/${mid}`, { method: "DELETE" }),
  answers: (id: string, a: Record<string, string>) => call<Record<string, string>>(`/projects/${id}/answers`, { method: "PUT", ...json(a) }),
  async blob(path: string): Promise<Blob> {
    const res = await send(path);
    if (!res.ok) throw new Error(`Fehler ${res.status}`);
    return res.blob();
  },
};

export async function download(path: string, filename: string) {
  const b = await api.blob(path);
  const url = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const fmt = (v: number | null | undefined, d = 0) =>
  v == null || !isFinite(v) ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });

/** KI-Kosten eines Projekts, z. B. "0,31 $ (gesamt 1,64 $)" */
export const costText = (m: { cost_usd?: number; last_cost_usd?: number }) => {
  if (!m.cost_usd) return "";
  const usd = (v: number) => `${v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
  return m.last_cost_usd !== undefined && Math.abs(m.cost_usd - m.last_cost_usd) > 0.005
    ? `${usd(m.last_cost_usd)} (gesamt ${usd(m.cost_usd)})` : usd(m.cost_usd);
};
