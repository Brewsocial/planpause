"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, download } from "@/lib/api";
import { outerCorners, PART_COLORS, place, placedBox, rotateInPlace } from "@/lib/floor";
import type { Geometry, Placement, Result } from "@/lib/types";

interface Part { id: string; label: string; geom: Geometry; place: Placement; color: string }
type Pick = { part: string; x: number; y: number };

export default function FloorPage() {
  const q = useSearchParams();
  const fid = q.get("projekt") ?? "";
  const floor = q.get("g") ?? "EG";
  const [name, setName] = useState("");
  const [parts, setParts] = useState<Part[] | null>(null);
  const [err, setErr] = useState("");
  const [connect, setConnect] = useState(false);
  const [anchor, setAnchor] = useState<Pick | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [unit, setUnit] = useState<"mm" | "cm" | "m">("mm");
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const [{ folder }, layout] = await Promise.all([api.folder(fid), api.floorParts(fid, floor)]);
        setName(folder.name);
        const loaded = await Promise.all(layout.parts.map(async (lp, i) => {
          const pr = await api.get(lp.id);
          return { id: lp.id, label: lp.label, geom: (pr.result as Result).geometry, place: { dx: lp.dx, dy: lp.dy, rot: lp.rot },
                   color: PART_COLORS[i % PART_COLORS.length] };
        }));
        setParts(loaded);
      } catch (e) { setErr((e as Error).message); }
    })();
  }, [fid, floor]);

  const view = useMemo(() => {
    if (!parts?.length) return null;
    const boxes = parts.map((p) => placedBox(p.geom, p.place));
    const x0 = Math.min(...boxes.map((b) => b[0])), y0 = Math.min(...boxes.map((b) => b[1]));
    const x1 = Math.max(...boxes.map((b) => b[2])), y1 = Math.max(...boxes.map((b) => b[3]));
    const span = Math.max(x1 - x0, y1 - y0, 100), pad = span * 0.08;
    return { boxes, span, vb: [x0 - pad, y0 - pad * 1.6, x1 - x0 + 2 * pad, y1 - y0 + 2.6 * pad] };
  }, [parts]);

  const update = (id: string, fn: (p: Part) => Placement) => {
    setParts((ps) => ps && ps.map((p) => (p.id === id ? { ...p, place: fn(p) } : p)));
    setDirty(true);
  };

  function pickCorner(c: Pick) {
    if (!anchor) { setAnchor(c); return; }
    if (c.part === anchor.part) { setAnchor(c); return; }  // andere Ecke im selben Teil: Anker neu wählen
    update(c.part, (p) => ({ ...p.place, dx: p.place.dx + anchor.x - c.x, dy: p.place.dy + anchor.y - c.y }));
    setAnchor(null); setConnect(false);
  }

  async function save() {
    if (!parts) return;
    setSaving(true); setErr("");
    try {
      await api.patchFolder(fid, { assembly: { [floor]: Object.fromEntries(parts.map((p) => [p.id, p.place])) } });
      setDirty(false);
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }

  async function exportDxf() {
    if (dirty) await save();
    await download(`/folders/${fid}/floors/${encodeURIComponent(floor)}/export/dxf?unit=${unit}`, `${name} – ${floor}.dxf`)
      .catch((e) => setErr(e.message));
  }

  /** Antippen irgendwo in der Nähe: nächstgelegene Ecke nehmen (Finger treffen keine kleinen Punkte) */
  function tap(e: React.MouseEvent<SVGSVGElement>) {
    if (!connect || !parts || !view || !svgRef.current) return;
    const ctm = svgRef.current.getScreenCTM();
    if (!ctm) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    let best: Pick | null = null, bd = Infinity;
    for (const p of parts) for (const [x, y] of outerCorners(p.geom, p.place)) {
      const d = Math.hypot(x - pt.x, y - pt.y);
      // zweiter Schritt: bevorzugt Ecken einer anderen Zeichnung als der Anker
      const penalty = anchor && p.id === anchor.part ? view.span * 0.01 : 0;
      if (d + penalty < bd) { bd = d + penalty; best = { part: p.id, x, y }; }
    }
    if (best && bd < view.span * 0.06) pickCorner(best);
  }

  if (err && !parts) return <p className="err">{err}</p>;
  if (!parts || !view) return <p className="muted">Lade Geschoss …</p>;
  const s = view.span;
  const label = connect ? (anchor ? "2. Jetzt dieselbe Ecke in der Zeichnung antippen, die angesetzt werden soll." : "1. Tippe eine Außenecke der Zeichnung an, die stehen bleibt. Zum genauen Tippen vorher vergrößern (+).") : "";

  return (
    <main>
      <Link href={`/projekt?id=${fid}`} className="back">‹ {name}</Link>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 14px", alignItems: "center", marginBottom: 6 }}>
        <h1 style={{ flex: "1 1 auto" }}>{floor} zusammensetzen</h1>
      </div>
      <p className="lead" style={{ marginBottom: 16 }}>
        Jede Zeichnung wurde einzeln vermessen. Verbinde sie über eine gemeinsame Ecke, z. B. die Ecke, an der Altbau und Anbau aneinanderstoßen.
      </p>

      <div className="grid2">
        <section className="sheet sticky" aria-label="Geschoss">
          <div className="bar">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className={`btn small${connect ? " primary" : ""}`} onClick={() => { setConnect(!connect); setAnchor(null); }}>
                {connect ? "Verbinden abbrechen" : "Ecken verbinden"}</button>
            </div>
            <span className="hint">{label || "Maße in cm"}</span>
          </div>
          <div className="zoom-wrap">
            <div className="canvas">
              <div style={{ width: `${zoom * 100}%` }}>
                <svg ref={svgRef} viewBox={view.vb.join(" ")} role="img" aria-label={`Geschoss ${floor}`} onClick={tap}
                  style={{ cursor: connect ? "crosshair" : "default" }}>
                  {parts.map((p) => <PartShape key={p.id} p={p} />)}
                  {parts.map((p, i) => (
                    <g key={p.id + "l"}>
                      {p.geom.rooms.map((r, k) => r.label ? (() => { const [x, y] = place(r.label![0], r.label![1], p.place); return (
                        <text key={k} className="p-room" x={x} y={y} style={{ fontSize: s * 0.016 }}>{r.name}</text>); })() : null)}
                      <text x={view.boxes[i][0]} y={view.boxes[i][1] - s * 0.025} style={{ fontSize: s * 0.024, fontWeight: 700, fill: p.color }}>{p.label}</text>
                    </g>))}
                  {connect && parts.map((p) => outerCorners(p.geom, p.place).map(([x, y], k) => {
                    const on = anchor && anchor.part === p.id && Math.abs(anchor.x - x) < 0.5 && Math.abs(anchor.y - y) < 0.5;
                    return (
                      <circle key={p.id + k} cx={x} cy={y} r={on ? s * 0.012 : s * 0.0075} aria-label="Ecke"
                        style={{ fill: on ? p.color : "var(--sheet)", stroke: p.color, strokeWidth: s * 0.002, pointerEvents: "none" }} />);
                  }))}
                </svg>
              </div>
            </div>
            <div className="zoom">
              <button aria-label="Vergrößern" onClick={() => setZoom((z) => Math.min(5, z * 1.5))}>+</button>
              <button aria-label="Verkleinern" onClick={() => setZoom((z) => Math.max(1, z / 1.5))} disabled={zoom <= 1}>−</button>
            </div>
          </div>
        </section>

        <section className="sheet pane" aria-label="Zeichnungen">
          <h3>Zeichnungen in diesem Geschoss</h3>
          {parts.map((p) => (
            <div key={p.id} className="part-row">
              <span className="swatch" style={{ background: p.color }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <b>{p.label}</b>
                <div className="hint">Drehung {p.place.rot}° · Lage {Math.round(p.place.dx) || 0} / {Math.round(p.place.dy) || 0} cm</div>
                <div className="nudge">
                  <button className="btn small" onClick={() => update(p.id, (x) => rotateInPlace(x.geom, x.place))}>↻ 90°</button>
                  <label>x <input inputMode="decimal" value={Math.round(p.place.dx)} onChange={(e) => update(p.id, (x) => ({ ...x.place, dx: +e.target.value || 0 }))} /></label>
                  <label>y <input inputMode="decimal" value={Math.round(p.place.dy)} onChange={(e) => update(p.id, (x) => ({ ...x.place, dy: +e.target.value || 0 }))} /></label>
                  <Link className="hint" href={`/grundriss?id=${p.id}`}>Grundriss öffnen</Link>
                </div>
              </div>
            </div>))}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 4 }}>
            <button className="btn primary" disabled={!dirty || saving} onClick={save}>{saving ? "Speichert …" : dirty ? "Anordnung speichern" : "Gespeichert"}</button>
            <select value={unit} onChange={(e) => setUnit(e.target.value as typeof unit)} aria-label="DXF-Einheit">
              <option value="mm">mm</option><option value="cm">cm</option><option value="m">m</option>
            </select>
            <button className="btn" onClick={exportDxf}>DXF des Geschosses</button>
          </div>
          {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
          <p className="hint" style={{ margin: 0 }}>
            Tipp: Erst „Ecken verbinden“, danach mit x/y in cm feinjustieren. Die DXF enthält alle Zeichnungen dieses Geschosses in ihrer Lage.
          </p>
        </section>
      </div>
    </main>
  );
}

/** Eine Zeichnung, gedreht und verschoben, in ihrer Farbe */
function PartShape({ p }: { p: Part }) {
  const g = p.geom;
  const t = `translate(${p.place.dx} ${p.place.dy}) rotate(${p.place.rot})`;
  return (
    <g transform={t}>
      {g.rooms.map((r, i) => r.poly.length >= 3 ? <polygon key={i} points={r.poly.map((q) => q.join(",")).join(" ")} style={{ fill: p.color, opacity: 0.06 }} /> : null)}
      {g.walls.map((w, i) => {
        const [x0, y0, x1, y1] = w.rect;
        return <rect key={i} x={x0} y={y0} width={x1 - x0} height={y1 - y0}
          style={{ fill: p.color, fillOpacity: w.estimated ? 0.25 : 0.55, stroke: p.color, strokeWidth: 1.5, strokeDasharray: w.estimated ? "6 4" : undefined }} />;
      })}
      {g.openings.map((o, i) => {
        const [x0, y0, x1, y1] = o.rect;
        if (o.type === "window") return <rect key={i} className="p-win" x={x0} y={y0} width={x1 - x0} height={y1 - y0} />;
        if (!o.swing) return null;
        const { hinge: [hx, hy], r, a0, a1 } = o.swing;
        const rad = (a: number) => (a * Math.PI) / 180;
        const p0 = [hx + r * Math.cos(rad(a0)), hy + r * Math.sin(rad(a0))], p1 = [hx + r * Math.cos(rad(a1)), hy + r * Math.sin(rad(a1))];
        return (
          <g key={i}>
            <path className="p-thin" d={`M${p0[0]},${p0[1]} A${r},${r} 0 0 ${a1 > a0 ? 1 : 0} ${p1[0]},${p1[1]}`} />
            <line className="p-leaf" x1={hx} y1={hy} x2={p1[0]} y2={p1[1]} />
          </g>);
      })}
      {g.features.map((f, i) => { const [x0, y0, x1, y1] = f.rect; return <rect key={i} className="p-feat" x={x0} y={y0} width={x1 - x0} height={y1 - y0} />; })}
    </g>
  );
}
