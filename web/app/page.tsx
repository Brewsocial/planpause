"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, costText } from "@/lib/api";
import type { Meta } from "@/lib/types";

const QUALITY: Record<string, [string, string]> = {
  eingeschraenkt: ["eingeschränkt verlässlich", "var(--warn)"], nicht_auswertbar: ["nicht auswertbar", "var(--crit)"],
};

const STATUS: Record<string, string> = {
  neu: "Neu", aufbereitet: "Bereit zur Analyse", analyse: "Analyse läuft …", analysiert: "Analysiert", fehler: "Fehler",
};

export default function Projects() {
  const router = useRouter();
  const [items, setItems] = useState<Meta[] | null>(null);
  const [claude, setClaude] = useState<boolean | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");

  const load = () => api.list().then(setItems).catch((e) => setErr(e.message));
  useEffect(() => {
    load();
    api.health().then((h) => setClaude(h.claude)).catch(() => setErr("Die API ist nicht erreichbar. Läuft sie unter NEXT_PUBLIC_API_URL?"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setErr("");
    try {
      const p = await api.upload(file, name, notes);
      if (claude && !p.warnings?.length) await api.analyze(p.id);  // bei Warnungen erst den Nutzer entscheiden lassen
      router.push(`/projekt?id=${p.id}`);
    } catch (x) { setErr((x as Error).message); setBusy(false); }
  }

  async function demo(which: "bungalow" | "darmstaedter14") {
    setBusy(true);
    try { const p = await api.demo(which); router.push(`/projekt?id=${p.id}`); }
    catch (x) { setErr((x as Error).message); setBusy(false); }
  }

  return (
    <main>
      <form className="sheet upload" onSubmit={submit}>
        <div style={{ gridColumn: "1 / -1" }}>
          <h2>Grundriss hochladen</h2>
          <p className="hint" style={{ margin: "2px 0 0" }}>
            Foto oder Scan, gern handgezeichnet: das Original gerade von oben fotografieren, bei gutem Licht, alle Maßketten im Bild,
            nur ein Grundriss pro Bild. Kopien mit Wasserzeichen und Bildschirmfotos sind meist zu klein zum Lesen.
            {claude === false && " Die KI-Analyse ist nicht eingerichtet (ANTHROPIC_API_KEY fehlt); hochgeladene Pläne werden nur aufbereitet."}
          </p>
        </div>
        <label>Datei<input id="file" type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <label>Objekt<input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="z. B. EG Lindenweg 4" /></label>
        <label>Hinweise zum Plan<input id="notes" type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Maßstab, Einheit, Besonderheiten" /></label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn primary" disabled={!file || busy}>{claude ? "Hochladen und analysieren" : "Hochladen"}</button>
        </div>
      </form>

      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
        <h1>Projekte</h1>
        <span className="spacer" />
        <span className="hint">Beispiele zum Ausprobieren:</span>
        <button className="btn small" disabled={busy} onClick={() => demo("bungalow")}>Bungalow</button>
        <button className="btn small" disabled={busy} onClick={() => demo("darmstaedter14")}>Darmstädter Str. 14</button>
      </div>
      {err && <p className="err">{err}</p>}
      {items === null ? <p className="muted">Lade Projekte …</p> : items.length === 0 ? (
        <p className="muted">Noch keine Projekte. Lade einen Grundriss hoch oder öffne ein Beispiel.</p>
      ) : (
        <div className="cards">
          {items.map((p) => (
            <Link key={p.id} href={`/projekt?id=${p.id}`} className="sheet card">
              <h3>{p.name}</h3>
              <span className="status" style={{ color: p.status === "fehler" ? "var(--crit)" : p.status === "analysiert" ? "var(--ok)" : "var(--muted)" }}>
                {STATUS[p.status] ?? p.status}{p.demo ? " · Beispiel" : ""}
                {p.status === "analysiert" && p.quality && QUALITY[p.quality] && <span style={{ color: QUALITY[p.quality][1] }}> · {QUALITY[p.quality][0]}</span>}
              </span>
              <span className="hint">Geändert {new Date(p.updated * 1000).toLocaleString("de-DE")}{p.cost_usd ? ` · KI-Kosten ${costText({ cost_usd: p.cost_usd })}` : ""}</span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
