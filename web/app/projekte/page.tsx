"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import PlanCard from "@/components/PlanCard";
import Thumb from "@/components/Thumb";
import { api } from "@/lib/api";
import { floorOrder } from "@/lib/status";
import type { Folder, Meta } from "@/lib/types";

export default function Projects() {
  const router = useRouter();
  const [data, setData] = useState<{ folders: Folder[]; unassigned: Meta[] } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [me, setMe] = useState<{ trial_left: number | null; contact: string } | null>(null);
  const [welcome, setWelcome] = useState(false);

  useEffect(() => {
    api.folders().then(setData).catch((e) => setErr(e.message));
    api.me().then(setMe).catch(() => setMe(null));
    setWelcome(new URLSearchParams(window.location.search).has("neu"));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true); setErr("");
    try { const f = await api.createFolder(name); router.push(`/projekt?id=${f.id}`); }
    catch (x) { setErr((x as Error).message); setBusy(false); }
  }

  async function demo(which: "bungalow" | "darmstaedter14") {
    setBusy(true);
    try { const p = await api.demo(which); router.push(`/projekt?id=${p.folder_id}`); }
    catch (x) { setErr((x as Error).message); setBusy(false); }
  }

  return (
    <main>
      <form className="sheet newplan" onSubmit={create}>
        <div>
          <h1>{welcome ? "Willkommen bei Planpause" : "Neues Projekt"}</h1>
          <p className="lead">{welcome ? "Dein Konto ist angelegt. Leg jetzt dein erstes Projekt an, z. B. für ein Haus, und lade darin deinen ersten Grundriss hoch." :
            "Ein Projekt bündelt alle Grundrisse eines Gebäudes, auch mehrere Zeichnungen pro Geschoss."}</p>
          {me?.trial_left != null && (
            <p className={me.trial_left > 0 ? "hint" : "err"} style={{ margin: "8px 0 0" }}>
              {me.trial_left > 0 ? `Noch ${me.trial_left} kostenlose${me.trial_left === 1 ? "r" : ""} Grundriss${me.trial_left === 1 ? "" : "e"} zum Ausprobieren.` :
                <>Deine kostenlosen Grundrisse sind aufgebraucht. Für weitere schreib uns an <a href={`mailto:${me.contact}`}>{me.contact}</a>.</>}
            </p>
          )}
        </div>
        <div className="row-form">
          <label className="field" style={{ flex: 1 }}>Name des Projekts
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="z. B. Haus Lindenweg 4" autoFocus={welcome} />
          </label>
          <button className="btn primary big" disabled={busy || !name.trim()}>Projekt anlegen</button>
        </div>
        {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
      </form>

      <div className="section-hd">
        <h2>Projekte</h2>
        <div className="demos">
          <span className="hint">Beispiele:</span>
          <button className="btn small" disabled={busy} onClick={() => demo("bungalow")}>Bungalow</button>
          <button className="btn small" disabled={busy} onClick={() => demo("darmstaedter14")}>Darmstädter Str. 14</button>
        </div>
      </div>
      {data === null ? <p className="muted">Lade Projekte …</p> : data.folders.length === 0 ? (
        <div className="sheet empty">Noch keine Projekte. Lege oben dein erstes Projekt an oder öffne ein Beispiel.</div>
      ) : (
        <div className="cards">
          {data.folders.map((f) => {
            const plans = f.plans ?? [];
            const floors = floorOrder([...new Set(plans.map((p) => p.floor || "EG"))]);
            const running = plans.some((p) => p.status === "analyse");
            return (
              <Link key={f.id} href={`/projekt?id=${f.id}`} className="sheet card">
                <div className="thumb">{plans[0] ? <Thumb id={plans[0].id} /> : <span className="hint">Noch kein Grundriss</span>}</div>
                <div className="info">
                  <h3>{f.name}</h3>
                  <div className="badges">
                    <span className="badge">{plans.length} {plans.length === 1 ? "Grundriss" : "Grundrisse"}</span>
                    {floors.map((fl) => <span key={fl} className="badge">{fl}</span>)}
                    {running && <span className="badge blue run">Analyse läuft</span>}
                  </div>
                  <span className="hint">{new Date(f.updated * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" })}</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {data && data.unassigned.length > 0 && (<>
        <div className="section-hd"><h2>Einzelne Grundrisse</h2><span className="hint">noch keinem Projekt zugeordnet</span></div>
        <div className="cards">
          {data.unassigned.map((p) => <PlanCard key={p.id} p={p} />)}
        </div>
      </>)}
    </main>
  );
}
