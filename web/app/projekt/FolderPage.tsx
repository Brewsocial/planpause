"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import PdfSetup, { type Crop } from "@/components/PdfSetup";
import PhotoPicker, { PhotoTips } from "@/components/PhotoPicker";
import PlanCard from "@/components/PlanCard";
import { api } from "@/lib/api";
import { floorOrder } from "@/lib/status";
import type { Folder, Meta } from "@/lib/types";

export default function FolderPage() {
  const id = useSearchParams().get("id") ?? "";
  const router = useRouter();
  const [data, setData] = useState<{ folder: Folder; plans: Meta[]; floors: string[] } | null>(null);
  const [claude, setClaude] = useState<boolean | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [floor, setFloor] = useState("EG");
  const [part, setPart] = useState("");
  const [notes, setNotes] = useState("");
  const [pdf, setPdf] = useState<{ page: number; crop: Crop | null }>({ page: 1, crop: null });

  const load = useCallback(() => api.folder(id).then(setData).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); api.health().then((h) => setClaude(h.claude)).catch(() => setClaude(false)); }, [load]);
  useEffect(() => {  // laufende Analysen: Liste aktuell halten
    if (!data?.plans.some((p) => p.status === "analyse")) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [data, load]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const isPdf = !!file && (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
  function pick(f: File | null) {
    setFile(f);
    const pdfFile = !!f && (f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    setPreview(f && !pdfFile ? URL.createObjectURL(f) : "");
  }

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !data) return;
    setBusy(true); setErr("");
    try {
      const name = part ? `${data.folder.name} – ${floor} ${part}` : `${data.folder.name} – ${floor}`;
      const p = await api.upload(file, { name, notes, folder_id: id, floor, part,
        ...(isPdf ? { page: String(pdf.page), crop: pdf.crop ? pdf.crop.map((v) => v.toFixed(4)).join(",") : "" } : {}) });
      if (claude && !p.warnings?.length) await api.analyze(p.id);  // bei Warnungen erst den Nutzer entscheiden lassen
      router.push(`/grundriss?id=${p.id}`);
    } catch (x) { setErr((x as Error).message); setBusy(false); }
  }

  async function rename() {
    if (!data) return;
    const n = prompt("Neuer Name des Projekts", data.folder.name);
    if (n && n.trim()) await api.patchFolder(id, { name: n }).then(load).catch((e) => setErr(e.message));
  }

  async function remove() {
    if (!data) return;
    const n = data.plans.length;
    if (!confirm(`Projekt „${data.folder.name}“ ${n ? `mit ${n} ${n === 1 ? "Grundriss" : "Grundrissen"} ` : ""}endgültig löschen?`)) return;
    await api.removeFolder(id).then(() => { window.location.href = "/"; }).catch((e) => setErr(e.message));
  }

  if (err && !data) return <p className="err">{err}</p>;
  if (!data) return <p className="muted">Lade Projekt …</p>;
  const { folder, plans } = data;
  const floors = floorOrder([...new Set(plans.map((p) => p.floor || "EG"))]);

  return (
    <main>
      <Link href="/" className="back">‹ Projekte</Link>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 14px", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ flex: "1 1 auto", minWidth: 0, overflowWrap: "anywhere" }}>{folder.name}</h1>
        <button className="btn small" onClick={rename}>Umbenennen</button>
        <button className="btn small danger" onClick={remove}>Löschen</button>
      </div>

      <form className="sheet newplan" onSubmit={upload}>
        <div>
          <h2>Grundriss hinzufügen</h2>
          <p className="lead">Mehrere Zeichnungen im selben Geschoss (z. B. Altbau und Anbau) lassen sich danach zusammensetzen.</p>
        </div>
        {!file ? <PhotoPicker onPick={pick} /> : (
          <div className={isPdf ? "preview pdf" : "preview"}>
            {isPdf ? <PdfSetup file={file} onChange={setPdf} /> : <img src={preview} alt="Ausgewähltes Foto" />}
            <div style={{ display: "grid", gap: 12 }}>
              <div className="row-form">
                <label className="field" style={{ minWidth: 120, flex: "0 0 auto" }}>Geschoss
                  <select value={floor} onChange={(e) => setFloor(e.target.value)}>
                    {data.floors.map((f) => <option key={f}>{f}</option>)}
                  </select>
                </label>
                <label className="field" style={{ flex: 1, minWidth: 160 }}>Bezeichnung (optional)
                  <input type="text" value={part} onChange={(e) => setPart(e.target.value)} placeholder="z. B. A – Altbau" />
                </label>
              </div>
              <details className="more">
                <summary>Hinweise zum Plan</summary>
                <label className="field" style={{ marginTop: 8 }}>
                  <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Maßstab, Einheit, Besonderheiten" />
                </label>
              </details>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn primary big" disabled={busy}>{busy ? "Wird hochgeladen …" : claude ? "Hochladen und analysieren" : "Hochladen"}</button>
                <button type="button" className="btn" disabled={busy} onClick={() => pick(null)}>{isPdf ? "Andere Datei" : "Anderes Foto"}</button>
              </div>
            </div>
          </div>
        )}
        <PhotoTips />
        {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
      </form>

      {plans.length === 0 && <div className="sheet empty" style={{ marginTop: 24 }}>Noch keine Grundrisse in diesem Projekt.</div>}
      {floors.map((fl) => {
        const own = plans.filter((p) => (p.floor || "EG") === fl)
          .sort((a, b) => (a.part || a.name).localeCompare(b.part || b.name, "de", { numeric: true }));
        const ready = own.filter((p) => p.status === "analysiert").length;
        return (
          <section key={fl}>
            <div className="section-hd">
              <h2>{fl}</h2>
              <span className="hint">{own.length} {own.length === 1 ? "Grundriss" : "Grundrisse"}</span>
              {own.length > 1 && (ready > 1
                ? <Link className="btn primary small" href={`/geschoss?projekt=${id}&g=${encodeURIComponent(fl)}`}>Geschoss zusammensetzen</Link>
                : <span className="hint">Zusammensetzen, sobald zwei Grundrisse analysiert sind</span>)}
            </div>
            <div className="cards">{own.map((p) => <PlanCard key={p.id} p={p} />)}</div>
          </section>
        );
      })}
    </main>
  );
}
