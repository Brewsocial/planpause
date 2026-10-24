"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, download } from "@/lib/api";
import { outerCorners, PART_COLORS, place, placedBox, rotateInPlace } from "@/lib/floor";
import type { Geometry, Placement, Result } from "@/lib/types";

interface Part { id: string; label: string; geom: Geometry; place: Placement; color: string }
type Drag =
  | { kind: "part"; id: string; x: number; y: number; start: Placement; others: [number, number][]; vb: number[] }
  | { kind: "pan"; cx: number; cy: number; left: number; top: number };

const SNAP_PX = 22; // Fangradius in Bildschirmpixeln: Außenecken rasten aneinander ein

export default function FloorPage() {
  const q = useSearchParams();
  const fid = q.get("projekt") ?? "";
  const floor = q.get("g") ?? "EG";
  const [name, setName] = useState("");
  const [parts, setParts] = useState<Part[] | null>(null);
  const [err, setErr] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [snap, setSnap] = useState<[number, number] | null>(null);
  const drag = useRef<Drag | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
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

  const [frozenVb, setFrozenVb] = useState<number[] | null>(null);  // während des Ziehens fester Ausschnitt
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

  const toSvg = (e: React.PointerEvent) => {
    const ctm = svgRef.current!.getScreenCTM()!;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return { x: pt.x, y: pt.y, scale: ctm.a };
  };

  /** Zeichnung greifen: verschieben; leere Fläche greifen: Ansicht verschieben (wenn vergrößert) */
  function down(e: React.PointerEvent, id: string | null) {
    if (!parts || !view) return;
    e.stopPropagation();
    svgRef.current!.setPointerCapture(e.pointerId);
    if (id) {
      const p = parts.find((x) => x.id === id)!;
      const { x, y } = toSvg(e);
      const others = parts.filter((o) => o.id !== id).flatMap((o) => outerCorners(o.geom, o.place));
      drag.current = { kind: "part", id, x, y, start: p.place, others, vb: view.vb };
      setFrozenVb(view.vb); setActive(id);
    } else if (canvasRef.current) {
      drag.current = { kind: "pan", cx: e.clientX, cy: e.clientY, left: canvasRef.current.scrollLeft, top: canvasRef.current.scrollTop };
    }
  }

  function move(e: React.PointerEvent) {
    const d = drag.current;
    if (!d || !parts) return;
    if (d.kind === "pan") {
      canvasRef.current!.scrollLeft = d.left - (e.clientX - d.cx);
      canvasRef.current!.scrollTop = d.top - (e.clientY - d.cy);
      return;
    }
    const { x, y, scale } = toSvg(e);
    let next: Placement = { ...d.start, dx: d.start.dx + x - d.x, dy: d.start.dy + y - d.y };
    // Magnetisch einrasten: nächstes Paar Außenecken innerhalb des Fangradius
    const p = parts.find((q) => q.id === d.id)!;
    let best: [number, number, number, number] | null = null, bd = SNAP_PX / scale;
    for (const [mx, my] of outerCorners(p.geom, next)) for (const [ox, oy] of d.others) {
      const dist = Math.hypot(ox - mx, oy - my);
      if (dist < bd) { bd = dist; best = [mx, my, ox, oy]; }
    }
    if (best) next = { ...next, dx: next.dx + best[2] - best[0], dy: next.dy + best[3] - best[1] };
    setSnap(best ? [best[2], best[3]] : null);
    setParts((ps) => ps && ps.map((q) => (q.id === d.id ? { ...q, place: next } : q)));
    setDirty(true);
  }

  function up() {
    drag.current = null;
    setFrozenVb(null);
  }

  if (err && !parts) return <p className="err">{err}</p>;
  if (!parts || !view) return <p className="muted">Lade Geschoss …</p>;
  const s = view.span;
  const vb = frozenVb ?? view.vb;

  return (
    <main>
      <Link href={`/projekt?id=${fid}`} className="back">‹ {name}</Link>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 14px", alignItems: "center", marginBottom: 6 }}>
        <h1 style={{ flex: "1 1 auto" }}>{floor} zusammensetzen</h1>
      </div>
      <p className="lead" style={{ marginBottom: 16 }}>
        Jede Zeichnung wurde einzeln vermessen. Zieh eine Zeichnung mit dem Finger oder der Maus an ihre Stelle: Außenecken rasten aneinander ein, wenn sie sich nahekommen.
      </p>

      <div className="grid2">
        <section className="sheet sticky" aria-label="Geschoss">
          <div className="bar">
            <span className="hint">{snap ? "Eingerastet ✓" : active ? `${parts.find((p) => p.id === active)?.label}: ziehen zum Verschieben` : "Zeichnung antippen und ziehen"}</span>
            <span className="hint">Maße in cm</span>
          </div>
          <div className="zoom-wrap">
            <div className="canvas" ref={canvasRef}>
              <div style={{ width: `${zoom * 100}%` }}>
                <svg ref={svgRef} viewBox={vb.join(" ")} role="img" aria-label={`Geschoss ${floor}`}
                  style={{ touchAction: "none", cursor: drag.current?.kind === "pan" ? "grabbing" : "grab" }}
                  onPointerDown={(e) => down(e, null)} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
                  {parts.map((p) => (
                    <g key={p.id} onPointerDown={(e) => down(e, p.id)} style={{ cursor: "move" }}>
                      <PartShape p={p} active={active === p.id} />
                    </g>))}
                  {parts.map((p, i) => (
                    <g key={p.id + "l"}>
                      {p.geom.rooms.map((r, k) => r.label ? (() => { const [x, y] = place(r.label![0], r.label![1], p.place); return (
                        <text key={k} className="p-room" x={x} y={y} style={{ fontSize: s * 0.016 }}>{r.name}</text>); })() : null)}
                      <text x={view.boxes[i][0]} y={view.boxes[i][1] - s * 0.025} style={{ fontSize: s * 0.024, fontWeight: 700, fill: p.color }}>{p.label}</text>
                    </g>))}
                  {snap && <circle cx={snap[0]} cy={snap[1]} r={s * 0.012} style={{ fill: "none", stroke: "var(--ok)", strokeWidth: s * 0.004, pointerEvents: "none" }} />}
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
function PartShape({ p, active }: { p: Part; active: boolean }) {
  const g = p.geom;
  const t = `translate(${p.place.dx} ${p.place.dy}) rotate(${p.place.rot})`;
  return (
    <g transform={t} style={active ? { filter: `drop-shadow(0 0 6px ${p.color})` } : undefined}>
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
