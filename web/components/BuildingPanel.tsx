"use client";

import { useEffect, useState } from "react";
import { api, download, fmt, type Building } from "@/lib/api";
import type { StoreyCheck } from "@/lib/types";

import ModelView from "@/components/LazyModelView";

type Row = { floor: string; height: string; repeat: string };
const num = (s: string) => Number(s.replace(",", "."));
const NORTH = ["oben", "oben rechts", "rechts", "unten rechts", "unten", "unten links", "links", "oben links"];
const level = (cm: number) => (cm === 0 ? "±0,00" : `${cm > 0 ? "+" : "−"}${fmt(Math.abs(cm) / 100, 2)}`);

/**
 * Gebäude in 3D: die Geschosse eines Projekts übereinander, mit Geschosshöhen (z. B. aus dem Schnitt),
 * baugleichen Geschossen und Flachdach. ready = Anzahl analysierter Grundrisse (lädt neu, wenn sich etwas ändert).
 */
export default function BuildingPanel({ folderId, name, ready }: { folderId: string; name: string; ready: number }) {
  const [b, setB] = useState<Building | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [roof, setRoof] = useState(true);
  const [north, setNorth] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [version, setVersion] = useState(0);
  const [err, setErr] = useState("");
  const [checks, setChecks] = useState<StoreyCheck[]>([]);

  const take = (x: Building) => {
    setB(x);
    setRows(x.floors.map((f) => ({ floor: f.floor, height: fmt(f.height / 100, 2), repeat: String(f.repeat) })));
    setRoof(x.roof);
    setNorth(x.north ?? null);
    setDirty(false);
  };
  useEffect(() => { if (ready) api.building(folderId).then(take).catch((e) => setErr(e.message)); }, [folderId, ready]);
  useEffect(() => { if (ready) api.buildingChecks(folderId).then((c) => setChecks(c.pairs)).catch(() => setChecks([])); }, [folderId, ready, b]);

  if (!ready || !b || !b.floors.length) return null;
  const bad = rows.some((r) => !(num(r.height) >= 2 && num(r.height) <= 8) || !(+r.repeat >= 1 && +r.repeat <= 40));
  const edit = (i: number, k: "height" | "repeat", v: string) => { setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r))); setDirty(true); };

  async function save(): Promise<boolean> {
    if (!dirty) return true;
    if (bad) { setErr("Bitte Geschosshöhen zwischen 2 und 8 m und eine Anzahl von 1 bis 40 eintragen."); return false; }
    setBusy(true); setErr("");
    try {
      take(await api.saveBuilding(folderId, {
        roof, north, floors: Object.fromEntries(rows.map((r) => [r.floor, { height: Math.round(num(r.height) * 1000) / 10, repeat: +r.repeat }])),
      }));
      return true;
    } catch (e) { setErr((e as Error).message); return false; } finally { setBusy(false); }
  }

  async function view() {
    if (!(await save())) return;
    setVersion((v) => v + 1);
    setShow(true);
  }

  async function ifc(old = false) {
    if (!(await save())) return;
    await download(`/folders/${folderId}/building/export/ifc${old ? "?schema=IFC2X3" : ""}`,
      `${name} – Gebäude${old ? " (IFC2x3)" : ""}.ifc`).catch((e) => setErr(e.message));
  }

  const storeys = rows.reduce((n, r) => n + (+r.repeat || 0), 0);
  const top = [...b.floors].reverse();  // wie im Schnitt: oben das oberste Geschoss
  return (
    <section className="sheet building" aria-label="Gebäude in 3D">
      <div>
        <h2>Gebäude in 3D</h2>
        <p className="lead">Die Geschosse dieses Projekts übereinander, mit Decken und Dach. Die Geschosshöhe reicht von Fußboden zu Fußboden und steht meist im Schnitt.</p>
      </div>
      <div className="table-scroll">
        <table className="building-table">
          <thead><tr><th>Geschoss</th><th>Höhenlage</th><th>Geschosshöhe</th><th>Anzahl</th></tr></thead>
          <tbody>
            {top.map((f) => {
              const i = rows.findIndex((r) => r.floor === f.floor);
              const r = rows[i];
              return (
                <tr key={f.floor}>
                  <td><b>{f.floor}</b>{f.assumed && !dirty && <span className="hint"> · angenommen</span>}</td>
                  <td className="num">{dirty ? "…" : level(f.elevation)}</td>
                  <td><label className="unit"><input inputMode="decimal" aria-label={`Geschosshöhe ${f.floor} in m`} value={r.height} onChange={(e) => edit(i, "height", e.target.value)} /> m</label></td>
                  <td><label className="unit"><input inputMode="numeric" aria-label={`Anzahl baugleicher Geschosse ${f.floor}`} value={r.repeat} onChange={(e) => edit(i, "repeat", e.target.value)} /> ×</label></td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <label className="check"><input type="checkbox" checked={roof} onChange={(e) => { setRoof(e.target.checked); setDirty(true); }} /> Flachdach mit Attika</label>
        <label className="check">Norden liegt im Plan
          <select value={north ?? ""} onChange={(e) => { setNorth(e.target.value === "" ? null : +e.target.value); setDirty(true); }}>
            <option value="">unbekannt</option>
            {NORTH.map((t, i) => <option key={t} value={i * 45}>{t}</option>)}
          </select>
        </label>
        <span className="hint">{storeys} {storeys === 1 ? "Geschoss" : "Geschosse"}{!dirty && ` · Oberkante ${level(b.top)}`}</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn primary" disabled={busy} onClick={view}>{busy ? "Speichert …" : show ? (dirty ? "3D-Modell aktualisieren" : "3D-Modell neu laden") : "3D-Modell erstellen"}</button>
        <button className="btn" disabled={busy} onClick={() => ifc()}>IFC des Gebäudes</button>
        <button className="btn" disabled={busy} onClick={() => ifc(true)} title="Älteres IFC-Schema, z. B. für HottCAD von Hottgenroth">IFC2x3 (HottCAD)</button>
        {show && <button className="btn" onClick={() => setShow(false)}>3D schließen</button>}
      </div>
      {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
      {checks.length > 0 && (
        <ul className="hint" style={{ margin: 0, paddingLeft: 18 }} aria-label="Geschoss-Abgleich">
          {checks.map((c) => (
            <li key={`${c.lower}-${c.upper}`}>
              {c.ok ? `${c.upper} über ${c.lower}: Außenwände liegen übereinander (±2 cm).`
                : `${c.upper} über ${c.lower}: ${c.unmatched} von ${c.total} Außenwänden haben im Geschoss darunter kein Gegenstück. Vor- und Rücksprünge sind möglich, sonst die Anordnung der Geschosse prüfen.`}
            </li>))}
        </ul>)}
      {show && <ModelView key={version} path={`/folders/${folderId}/building/model`} />}
      <p className="hint" style={{ margin: 0 }}>
        Baugleiche Geschosse (etwa 1. bis 8. OG) reicht es, einmal hochzuladen und die Anzahl zu erhöhen. Liegen Gebäudeteile
        eine halbe Geschosshöhe versetzt, trägst du das beim Zusammensetzen des Geschosses unter „Höhe“ ein. Decken, Dach und
        nicht angegebene Höhen sind Annahmen und im IFC so gekennzeichnet. Das IFC enthält Außen- und Innenbauteile, Flächen und die
        Nordrichtung, damit Programme zur Energieberatung die Gebäudehülle übernehmen können.
      </p>
    </section>
  );
}
