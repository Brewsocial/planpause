"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, costText } from "@/lib/api";
import { statusBadge } from "@/lib/status";
import type { Meta } from "@/lib/types";

const ACCEPT = "image/jpeg,image/png,image/webp"; // iPhones wandeln HEIC dabei automatisch in JPEG um

export default function Projects() {
  const router = useRouter();
  const [items, setItems] = useState<Meta[] | null>(null);
  const [claude, setClaude] = useState<boolean | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    api.list().then(setItems).catch((e) => setErr(e.message));
    api.health().then((h) => setClaude(h.claude)).catch(() => setErr("Planpause ist gerade nicht erreichbar. Bitte später erneut versuchen."));
  }, []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function pick(f: File | null) {
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : "");
    if (f && !name) {
      const d = new Date();
      setName(`Grundriss ${d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })} ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`);
    }
  }

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
      <form className="sheet newplan" onSubmit={submit}>
        <div>
          <h1>Neuer Grundriss</h1>
          <p className="lead">Plan fotografieren, Planpause liest die Maße und prüft sie auf Fehler.</p>
        </div>

        {!file ? (
          <div className="pick">
            <label>
              <input type="file" accept={ACCEPT} capture="environment" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
              <span className="tile">
                <span className="ico"><svg viewBox="0 0 24 24"><path d="M4 8h3l2-2.5h6L17 8h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg></span>
                <span><b>Plan fotografieren</b><span>Kamera öffnet sich</span></span>
              </span>
            </label>
            <label>
              <input type="file" accept={ACCEPT} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
              <span className="tile">
                <span className="ico alt"><svg viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><path d="M3.5 16l5-5 4 4 3-3 5 5" /><circle cx="15.5" cy="9" r="1.5" /></svg></span>
                <span><b>Aus Fotos wählen</b><span>Foto oder Scan, JPEG oder PNG</span></span>
              </span>
            </label>
          </div>
        ) : (
          <div className="preview">
            <img src={preview} alt="Ausgewähltes Foto" />
            <div style={{ display: "grid", gap: 12 }}>
              <label className="field">Objekt<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="z. B. EG Lindenweg 4" /></label>
              <details className="more">
                <summary>Hinweise zum Plan</summary>
                <label className="field" style={{ marginTop: 8 }}>
                  <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Maßstab, Einheit, Besonderheiten" />
                </label>
              </details>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn primary big" disabled={busy}>{busy ? "Wird hochgeladen …" : claude ? "Hochladen und analysieren" : "Hochladen"}</button>
                <button type="button" className="btn" disabled={busy} onClick={() => pick(null)}>Anderes Foto</button>
              </div>
            </div>
          </div>
        )}

        <ul className="tips">
          <li>Das Original gerade von oben fotografieren, bei gutem Licht und ohne Schatten.</li>
          <li>Alle Maßketten müssen im Bild sein, nur ein Grundriss pro Foto.</li>
          <li>Kopien mit Wasserzeichen und Bildschirmfotos sind oft zu klein zum Lesen.</li>
        </ul>
        {claude === false && <p className="hint">Die KI-Analyse ist gerade nicht verfügbar; hochgeladene Pläne werden nur aufbereitet.</p>}
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
      {items === null ? <p className="muted">Lade Projekte …</p> : items.length === 0 ? (
        <div className="sheet empty">Noch keine Projekte. Fotografiere oben deinen ersten Grundriss oder öffne ein Beispiel.</div>
      ) : (
        <div className="cards">
          {items.map((p) => {
            const [label, cls] = statusBadge(p);
            return (
              <Link key={p.id} href={`/projekt?id=${p.id}`} className="sheet card">
                <div className="thumb"><Thumb id={p.id} /></div>
                <div className="info">
                  <h3>{p.name}</h3>
                  <div className="badges"><span className={`badge ${cls}`}>{label}</span>{p.demo && <span className="badge">Beispiel</span>}</div>
                  <span className="hint">{new Date(p.updated * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" })}
                    {p.cost_usd ? ` · KI ${costText({ cost_usd: p.cost_usd })}` : ""}</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}

/** Vorschaubild des aufbereiteten Plans (über die API, weil Bilder nur angemeldet abrufbar sind). */
function Thumb({ id }: { id: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let u = "";
    api.blob(`/projects/${id}/image`).then((b) => { u = URL.createObjectURL(b); setUrl(u); }).catch(() => setUrl(""));
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [id]);
  return url ? <img src={url} alt="" loading="lazy" /> : <span className="hint">Kein Bild</span>;
}
