"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PlanView from "@/components/PlanView";
import Link from "next/link";
import { api, costText, download, fmt } from "@/lib/api";
import { statusBadge } from "@/lib/status";
import type { Folder, Issue, MeasureHint, Project, Quality, Result } from "@/lib/types";

const SEV_LABEL = { kritisch: "Kritisch", pruefen: "Prüfen", info: "Hinweis" } as const;
const BASE_Q = [
  { id: "raumhoehe", topic: "Höhen", question: "Lichte Raumhöhe", why: "Grundlage für 3D-Modell, Treppe und Haustechnik.", type: "number", unit: "cm", options: [] as string[] },
  { id: "baujahr", topic: "Gebäude", question: "Baujahr (ungefähr)", why: "Leitet typische Bauweisen ab.", type: "number", unit: "", options: [] },
  { id: "wand_aussen", topic: "Material", question: "Material der Außenwände", why: "Wichtig für Dämmung, Dübel und Durchbrüche.", type: "choice", unit: "",
    options: ["Vollziegel", "Lochziegel", "Kalksandstein", "Bims / Leichtbeton", "Naturstein", "Fachwerk", "Beton", "Unbekannt"] },
  { id: "decke", topic: "Material", question: "Deckenkonstruktion", why: "Entscheidet über Spannrichtung und Belastbarkeit.", type: "choice", unit: "",
    options: ["Holzbalkendecke", "Stahlbetondecke", "Ziegel- / Kappendecke", "Unbekannt"] },
  { id: "tragend", topic: "Statik", question: "Welche Wände sind tragend?", why: "Wird im Bericht vermerkt.", type: "text", unit: "", options: [] },
];
type Tab = "pruefung" | "messwerte" | "ketten" | "raeume" | "fragen" | "export";

export default function PlanPage() {
  const id = useSearchParams().get("id") ?? "";
  const [p, setP] = useState<Project | null>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<Tab>("pruefung");
  const [sel, setSel] = useState<string | null>(null);
  const [filter, setFilter] = useState<"alle" | Issue["severity"]>("alle");
  const [view, setView] = useState<"digital" | "overlay">("digital");
  const [opacity, setOpacity] = useState(0.7);  // Deckkraft des Fotos; der Plan bleibt immer voll sichtbar
  const [pins, setPins] = useState(true);
  const [chains, setChains] = useState(true);
  const [img, setImg] = useState<{ url: string; w: number; h: number } | null>(null);
  const [unit, setUnit] = useState<"mm" | "cm" | "m">("mm");
  const [showAnyway, setShowAnyway] = useState(false);
  const [zoom, setZoom] = useState(1);
  const listRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => api.get(id).then(setP).catch((e) => setErr(e.message)), [id]);
  const [folders, setFolders] = useState<Folder[]>([]);
  useEffect(() => { api.folders().then((d) => setFolders(d.folders)).catch(() => setFolders([])); }, []);
  const folder = folders.find((f) => f.id === p?.meta.folder_id);
  const home = p?.meta.folder_id ? `/projekt?id=${p.meta.folder_id}` : "/projekte";
  useEffect(() => { load(); }, [load]);
  useEffect(() => {  // Analyse läuft: alle 4 s nachsehen
    if (p?.meta.status !== "analyse") return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [p?.meta.status, load]);
  useEffect(() => {
    let url = "";
    api.blob(`/projects/${id}/image`).then((b) => {
      url = URL.createObjectURL(b);
      const im = new Image();
      im.onload = () => setImg({ url, w: im.naturalWidth, h: im.naturalHeight });
      im.src = url;
    }).catch(() => setImg(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [id]);

  const result = p && "geometry" in p.result ? (p.result as Result) : null;
  const issues = useMemo(() => {
    let n = 0;
    return (result?.issues ?? []).map((i) => ({ ...i, no: i.at ? ++n : null }));
  }, [result]);

  const applyResult = (r: Result) => setP((old) => old ? { ...old, result: r } : old);
  const remove = () => {
    if (!p || !confirm(`Projekt „${p.meta.name}“ endgültig löschen? Foto und Ergebnisse werden entfernt.`)) return;
    api.remove(id).then(() => { window.location.href = home; }).catch((e) => setErr(e.message));
  };
  const analyze = () => api.analyze(id).then(load).catch((e) => setErr(e.message));

  if (err) return <p className="err">{err}</p>;
  if (!p) return <p className="muted">Lade Grundriss …</p>;

  const [badge, badgeCls] = statusBadge(p.meta);
  const header = (
    <>
      <Link href={home} className="back">‹ {folder ? folder.name : "Projekte"}</Link>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 14px", alignItems: "center", marginBottom: 6 }}>
        <h1 style={{ flex: "1 1 auto", minWidth: 0, overflowWrap: "anywhere" }}>{p.meta.part || p.meta.name}</h1>
        <button className="btn small danger" onClick={remove}>Löschen</button>
      </div>
      <PlanMeta meta={p.meta} folders={folders} onSaved={(m) => setP({ ...p, meta: { ...p.meta, ...m } })} />
    </>
  );

  if (!result) return (
    <main>
      {header}
      {p.meta.status === "analyse" && <Progress since={p.meta.analyses?.slice(-1)[0] ?? p.meta.updated} />}
      {p.meta.status === "fehler" && (
        <div className="sheet summary">
          <div className="badges"><span className="badge crit">Analyse fehlgeschlagen</span></div>
          <p style={{ margin: 0 }}>{p.meta.error}</p>
          {costText(p.meta) && <span className="hint">KI-Kosten bisher: {costText(p.meta)}</span>}
          <div><button className="btn primary" onClick={analyze}>Erneut versuchen</button></div>
        </div>)}
      {p.meta.status === "aufbereitet" && (
        <div className="sheet summary">
          {!!p.meta.warnings?.length && (
            <div className="banner warn" style={{ margin: 0 }}>
              <b>Bitte vor der Analyse prüfen</b>
              <ul>{p.meta.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
              <span className="hint">Jede Analyse kostet KI-Guthaben. Mit einem besseren Foto wird das Ergebnis deutlich genauer.</span>
            </div>)}
          <p className="muted" style={{ margin: 0 }}>Das Foto ist aufbereitet{p.meta.steps?.length ? `: ${p.meta.steps.join(", ")}` : ""}.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn primary big" onClick={analyze}>{p.meta.warnings?.length ? "Trotzdem analysieren" : "Analyse starten"}</button>
            {!!p.meta.warnings?.length && <Link className="btn big" href={home}>Neues Foto</Link>}
          </div>
        </div>)}
      {img && <div className="sheet" style={{ padding: 8, marginTop: 16 }}><img src={img.url} alt="Aufbereiteter Plan" style={{ width: "100%", borderRadius: 12, display: "block" }} /></div>}
    </main>);

  const s = result.stats;
  const open = { kritisch: 0, pruefen: 0, info: 0 };
  issues.forEach((i) => { open[i.severity]++; });
  const shown = filter === "alle" ? issues : issues.filter((i) => i.severity === filter);
  const measured = Math.round((100 * s.lines_measured) / Math.max(1, s.lines_total));

  const select = (iid: string) => {
    setSel((cur) => (cur === iid ? null : iid)); setTab("pruefung"); setFilter("alle");
    setTimeout(() => listRef.current?.querySelector(`[data-id="${iid}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
  };

  return (
    <main>
      {header}
      {result.quality && result.quality.level !== "gut" && <QualityBanner q={result.quality} />}
      {result.quality?.level === "nicht_auswertbar" && !showAnyway ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="btn primary big" href={home}>Neues Foto aufnehmen</Link>
          <button className="btn big" onClick={() => setShowAnyway(true)}>Ergebnis trotzdem ansehen</button>
        </div>
      ) : (<>
      <section className="sheet summary" aria-label="Zusammenfassung">
        <div className="badges">
          <span className={`badge ${badgeCls}`}>{badge}</span>
          {p.meta.demo && <span className="badge">Beispielprojekt</span>}
        </div>
        <div className="facts">
          <div className={open.kritisch ? "crit" : "ok"}><b>{open.kritisch}</b><span>kritische Punkte</span></div>
          <div className={s.conflicts ? "crit" : "ok"}><b>{s.conflicts}</b><span>Maßwidersprüche</span></div>
          <div className={measured < 50 ? "warn" : ""}><b>{measured} %</b><span>der Kanten vermaßt</span></div>
          <div className={s.rooms_checked && s.rooms_ok < s.rooms_checked ? "warn" : ""}><b>{s.rooms_ok}/{s.rooms_checked}</b><span>Raumflächen bestätigt</span></div>
        </div>
        <span className="meta">{open.pruefen} zu prüfen · {open.info} Hinweise · {s.lines_from_area} Kanten aus Flächen · {s.lines_from_drawing} nach Zeichnung{costText(p.meta) && ` · KI-Kosten ${costText(p.meta)}`}</span>
      </section>

      <div className="grid2">
        <section className="sheet sticky" aria-label="Plan">
          <div className="bar">
            <div className="seg" role="group" aria-label="Ansicht">
              <button aria-pressed={view === "digital"} onClick={() => setView("digital")}>Digital</button>
              <button aria-pressed={view === "overlay"} onClick={() => setView("overlay")} disabled={!img || !result.image_transform}>Überlagert</button>
            </div>
            {view === "overlay" && <label className="check">Foto <input type="range" min={0} max={100} value={opacity * 100} onChange={(e) => setOpacity(+e.target.value / 100)} /></label>}
            <span className="toggles">
              <button className="toggle" aria-pressed={pins} onClick={() => setPins(!pins)}>Prüfpunkte</button>
              <button className="toggle" aria-pressed={chains} onClick={() => setChains(!chains)}>Maßketten</button>
            </span>
          </div>
          <div className="zoom-wrap">
            <div className="canvas">
              <div style={{ width: `${zoom * 100}%` }}>
                <PlanView geom={result.geometry} issues={issues} selected={sel} onSelect={select} showPins={pins} showChains={chains}
                  image={view === "overlay" && img && result.image_transform ? { ...img, t: result.image_transform, opacity } : null} />
              </div>
            </div>
            <div className="zoom">
              <button aria-label="Vergrößern" onClick={() => setZoom((z) => Math.min(4, z * 1.5))}>+</button>
              <button aria-label="Verkleinern" onClick={() => setZoom((z) => Math.max(1, z / 1.5))} disabled={zoom <= 1}>−</button>
            </div>
          </div>
          <div className="legend">
            <span><i style={{ background: "repeating-linear-gradient(45deg,var(--wall) 0 1.5px,var(--wall-tint) 1.5px 5px)", border: "1px solid var(--wall)" }} />Mauerwerk</span>
            <span><i style={{ background: "var(--wall)" }} />Brandwand</span>
            <span><i style={{ border: "2px dashed var(--estimated)" }} />Lage nur nach Zeichnung</span>
            <span><i style={{ background: "var(--crit)", height: 3 }} />verdächtiges Maß</span>
            <span>Maße in cm</span>
          </div>
        </section>

        <section className="sheet" aria-label="Prüfakte">
          <div className="tabs" role="tablist">
            {([["pruefung", `Prüfpunkte (${issues.length})`], ["messwerte", `Messwerte (${p.plan.measurements?.length ?? 0})`], ["ketten", "Maßketten"], ["raeume", "Räume"], ["fragen", "Fragen"], ["export", "Export"]] as [Tab, string][]).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>))}
          </div>

          {tab === "pruefung" && (
            <div className="pane" ref={listRef}>
              <div className="filter" role="group" aria-label="Filter">
                {(["alle", "kritisch", "pruefen", "info"] as const).map((f) => (
                  <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f === "alle" ? "Alle" : SEV_LABEL[f]}</button>))}
              </div>
              {shown.map((i) => <IssueCard key={i.id} i={i} sel={sel === i.id} onSel={() => setSel(i.id)} projectId={id} onResult={(r) => { applyResult(r); load(); }} />)}
              {shown.length === 0 && <p className="hint">Keine Punkte in diesem Filter.</p>}
            </div>)}

          {tab === "messwerte" && (
            <div className="pane">
              <p className="hint">Gemessene Werte haben Vorrang vor dem Plan. Der Solver rechnet nach jeder Änderung neu.</p>
              {(p.plan.measurements ?? []).length === 0 && <p className="muted">Noch keine Messwerte. Messwerte trägst du direkt bei den Prüfpunkten ein.</p>}
              <div className="tbl"><table className="t"><tbody>
                {(p.plan.measurements ?? []).map((m) => (
                  <tr key={m.id}><td>{m.a} bis {m.b} <span className="hint">({m.axis === "x" ? "waagerecht" : "senkrecht"})</span></td>
                    <td className="n">{fmt(m.value, 1)} cm</td>
                    <td><button className="btn small danger" onClick={() => api.unmeasure(id, m.id).then(() => load())}>Entfernen</button></td></tr>))}
              </tbody></table></div>
            </div>)}

          {tab === "ketten" && (
            <div className="pane">
              <p className="hint">Rot markierte Werte hält der Solver für falsch gelesen oder falsch eingetragen. Gerechnet wird mit dem konsistenten Wert.</p>
              <div className="tbl"><table className="t">
                <thead><tr><th>Kette</th><th style={{ textAlign: "right" }}>Summe</th><th style={{ textAlign: "right" }}>Gesamt</th></tr></thead>
                <tbody>{result.geometry.chains.map((c) => (
                  <tr key={c.id}>
                    <td><b>{c.label || c.id}</b><div className="vals">{c.values.map((v, k) => <span key={k}>{k > 0 && " · "}{c.suspect.includes(k) ? <b>{v}</b> : v}{c.uncertain.includes(k) ? "?" : ""}</span>)}</div></td>
                    <td className="n">{fmt(c.sum, 1)}</td><td className="n">{c.total == null ? "–" : fmt(c.total, 1)}</td>
                  </tr>))}</tbody>
              </table></div>
            </div>)}

          {tab === "raeume" && (
            <div className="pane">
              <div className="tbl"><table className="t">
                <thead><tr><th>Raum</th><th style={{ textAlign: "right" }}>Plan m²</th><th style={{ textAlign: "right" }}>aus Maßen m²</th><th>Status</th></tr></thead>
                <tbody>{result.geometry.rooms.map((r, k) => {
                  const dev = r.area_geom != null && r.area_stated ? (r.area_geom - r.area_stated) / r.area_stated : null;
                  return (<tr key={k}><td><b>{r.name}</b>{r.estimated && <span className="hint"> · Lage geschätzt</span>}</td>
                    <td className="n">{fmt(r.area_stated, 2)}</td><td className="n">{fmt(r.area_geom, 2)}</td>
                    <td>{dev == null ? <span className="state">nicht prüfbar</span> : Math.abs(dev) <= 0.03 ? <span className="state ok">bestätigt</span>
                      : <span className={`state ${Math.abs(dev) > 0.1 ? "crit" : "warn"}`}>{dev > 0 ? "+" : ""}{fmt(dev * 100, 1)} %</span>}</td></tr>);
                })}</tbody>
              </table></div>
            </div>)}

          {tab === "fragen" && <Questions p={p} id={id} onSaved={(a) => setP({ ...p, answers: a })} />}

          {tab === "export" && (
            <div className="pane">
              <p>Die DXF enthält Layer für Wände, Brandwände, Fenster, Türen, Tore, Treppe, Räume, Bemaßung und Prüfpunkte. Geschätzte Wände liegen zusätzlich auf dem Layer GESCHAETZT.</p>
              <label className="check">DXF-Einheit
                <select value={unit} onChange={(e) => setUnit(e.target.value as typeof unit)}>
                  <option value="mm">Millimeter</option><option value="cm">Zentimeter</option><option value="m">Meter</option>
                </select></label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <button className="btn primary" onClick={() => download(`/projects/${id}/export/dxf?unit=${unit}`, `${p.meta.name}.dxf`)}>DXF herunterladen</button>
                <button className="btn" onClick={() => download(`/projects/${id}/export/md`, `${p.meta.name}_pruefbericht.md`)}>Prüfbericht</button>
                <button className="btn" onClick={() => download(`/projects/${id}/export/json`, `${p.meta.name}.json`)}>Rohdaten (JSON)</button>
              </div>
            </div>)}
        </section>
      </div>
      </>)}
    </main>
  );
}

function IssueCard({ i, sel, onSel, projectId, onResult }: { i: Issue & { no: number | null }; sel: boolean; onSel: () => void; projectId: string; onResult: (r: Result) => void }) {
  return (
    <article className={`issue ${i.severity}${sel ? " sel" : ""}`} data-id={i.id} onClick={(e) => { if (!(e.target as HTMLElement).closest("input,button")) onSel(); }}>
      <div className="stripe" />
      <div className="body">
        <div className="hd"><span className={`num${i.no ? "" : " none"}`}>{i.no ?? "–"}</span><h4>{i.title}</h4><span className="tag">{SEV_LABEL[i.severity]} · {i.category}</span></div>
        <p>{i.detail}</p>
        {i.action && <div className="todo"><b>Nachmessen / klären:</b> {i.action}</div>}
        {i.measure.map((m, k) => <MeasureRow key={k} m={m} projectId={projectId} onResult={onResult} />)}
        <span className="hint">{i.source}</span>
      </div>
    </article>);
}

function MeasureRow({ m, projectId, onResult }: { m: MeasureHint; projectId: string; onResult: (r: Result) => void }) {
  const [v, setV] = useState("");
  const [busy, setBusy] = useState(false);
  const [e, setE] = useState("");
  const save = async () => {
    const n = parseFloat(v.replace(",", "."));
    if (!(n > 0)) { setE("Wert in cm eingeben"); return; }
    setBusy(true); setE("");
    try { onResult(await api.measure(projectId, { axis: m.axis, a: m.a, b: m.b, value: n })); setV(""); }
    catch (x) { setE((x as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="mrow">
      <span>{m.text}{m.expected != null && <span className="hint"> · erwartet ca. {fmt(m.expected, 1)} cm</span>}</span>
      <input aria-label={`Messwert ${m.text}`} inputMode="decimal" placeholder="cm" value={v} onChange={(x) => setV(x.target.value)} onKeyDown={(x) => x.key === "Enter" && save()} />
      <button className="btn small" disabled={busy || !v} onClick={save}>Übernehmen</button>
      {e && <span className="err">{e}</span>}
    </div>);
}

function Questions({ p, id, onSaved }: { p: Project; id: string; onSaved: (a: Record<string, string>) => void }) {
  const qs = [...BASE_Q, ...(p.plan.questions ?? [])];
  const [a, setA] = useState<Record<string, string>>(p.answers ?? {});
  const [saved, setSaved] = useState(true);
  const set = (k: string, v: string) => { setA({ ...a, [k]: v }); setSaved(false); };
  return (
    <div className="pane">
      <p className="hint">Diese Angaben stehen selten im Plan, sind aber für CAD und Umbau nötig. Sie landen im Prüfbericht.</p>
      {qs.map((q) => (
        <label key={q.id} style={{ display: "grid", gap: 4 }}>
          <span className="tag" style={{ color: "var(--accent)" }}>{q.topic}</span>
          <b>{q.question}</b>
          {q.why && <span className="hint">{q.why}</span>}
          {q.type === "choice" ? (
            <select value={a[q.id] ?? ""} onChange={(e) => set(q.id, e.target.value)}>
              <option value="">– bitte wählen –</option>{q.options.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : <input type={q.type === "number" ? "number" : "text"} value={a[q.id] ?? ""} onChange={(e) => set(q.id, e.target.value)} />}
        </label>))}
      <div><button className="btn primary" disabled={saved} onClick={() => api.answers(id, a).then((r) => { onSaved(r); setSaved(true); })}>{saved ? "Gespeichert" : "Speichern"}</button></div>
    </div>);
}


const QUALITY_TITLE: Record<Quality["level"], string> = {
  gut: "", eingeschraenkt: "Ergebnis nur eingeschränkt verlässlich",
  nicht_auswertbar: "Dieser Plan ist nicht zuverlässig auswertbar",
};

function QualityBanner({ q }: { q: Quality }) {
  return (
    <div className={`banner ${q.level === "nicht_auswertbar" ? "crit" : "warn"}`}>
      <b>{QUALITY_TITLE[q.level]}</b>
      <ul>{q.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      {q.level === "nicht_auswertbar" && <p style={{ margin: "4px 0" }}>Der angezeigte Grundriss wäre überwiegend geschätzt und kann grob falsch sein.</p>}
      {q.tips.length > 0 && (<>
        <span className="hint">So wird es besser:</span>
        <ul className="hint">{q.tips.map((t) => <li key={t}>{t}</li>)}</ul>
      </>)}
    </div>
  );
}


/** Analyse läuft: ehrliche Schritte (der Server meldet keinen Prozentwert) und vergangene Zeit. */
function Progress({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const t = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(t); }, []);
  const sec = Math.max(0, Math.round(now - since));
  return (
    <section className="sheet progress" aria-live="polite">
      <div>
        <div className="clock">{Math.floor(sec / 60)}:{String(sec % 60).padStart(2, "0")}</div>
        <p className="lead">Die KI liest den Plan. Das dauert meist ein bis vier Minuten.</p>
      </div>
      <ol className="steps">
        <li className="done"><span className="dot">✓</span><span><b>Foto aufbereitet</b> · entzerrt, gerade gerichtet, Kontrast ausgeglichen</span></li>
        <li className="now"><span className="dot" /><span><b>Maßketten, Wände und Räume lesen</b></span></li>
        <li><span className="dot">3</span><span>Maße nachrechnen und auf Fehler prüfen</span></li>
      </ol>
      <p className="hint" style={{ margin: 0 }}>Du kannst die Seite schließen, die Analyse läuft weiter. Das Ergebnis erscheint hier automatisch.</p>
    </section>
  );
}


const FLOORS = ["KG", "EG", "OG", "1. OG", "2. OG", "3. OG", "DG", "Spitzboden"];

/** Projekt, Geschoss und Bezeichnung eines Grundrisses: kompakt anzeigen, bei Bedarf bearbeiten. */
function PlanMeta({ meta, folders, onSaved }: { meta: Project["meta"]; folders: Folder[]; onSaved: (m: Partial<Project["meta"]>) => void }) {
  const [edit, setEdit] = useState(false);
  const [floor, setFloor] = useState(meta.floor || "EG");
  const [part, setPart] = useState(meta.part || "");
  const [fid, setFid] = useState(meta.folder_id || "");
  const [err, setErr] = useState("");
  const folderName = folders.find((f) => f.id === meta.folder_id)?.name;
  const save = () => api.patchPlan(meta.id, { floor, part, folder_id: fid })
    .then((m) => { onSaved(m); setEdit(false); setErr(""); }).catch((e) => setErr(e.message));
  if (!edit) return (
    <p className="meta" style={{ margin: "0 0 16px" }}>
      {folderName ? `${folderName} · ` : "Keinem Projekt zugeordnet · "}Geschoss {meta.floor || "EG"}{meta.part ? ` · ${meta.part}` : ""}
      {" · "}<a href="#" onClick={(e) => { e.preventDefault(); setEdit(true); }}>bearbeiten</a>
    </p>);
  return (
    <div className="sheet summary" style={{ marginBottom: 16 }}>
      <div className="row-form">
        <label className="field" style={{ minWidth: 200, flex: 1 }}>Projekt
          <select value={fid} onChange={(e) => setFid(e.target.value)}>
            <option value="">– keinem Projekt –</option>
            {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
        <label className="field" style={{ minWidth: 110, flex: "0 0 auto" }}>Geschoss
          <select value={floor} onChange={(e) => setFloor(e.target.value)}>
            {[...new Set([...FLOORS, floor])].map((f) => <option key={f}>{f}</option>)}
          </select>
        </label>
        <label className="field" style={{ minWidth: 160, flex: 1 }}>Bezeichnung
          <input type="text" value={part} onChange={(e) => setPart(e.target.value)} placeholder="z. B. B – Anbau" />
        </label>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn primary" onClick={save}>Speichern</button>
        <button className="btn" onClick={() => setEdit(false)}>Abbrechen</button>
      </div>
      {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
    </div>);
}
