"use client";

import { useMemo } from "react";
import { fmt } from "@/lib/api";
import type { Geometry, Issue, Result } from "@/lib/types";

interface Props {
  geom: Geometry;
  issues: (Issue & { no: number | null })[];
  selected: string | null;
  onSelect: (id: string) => void;
  showPins: boolean;
  showChains: boolean;
  image?: { url: string; w: number; h: number; t: NonNullable<Result["image_transform"]>; opacity: number } | null;
}

const sideOf = (label: string, axis: "x" | "y") => {
  const l = label.toLowerCase();
  if (axis === "x") return l.includes("unten") ? "unten" : "oben";
  return l.includes("rechts") ? "rechts" : "links";
};

export default function PlanView({ geom, issues, selected, onSelect, showPins, showChains, image }: Props) {
  const [bx0, by0, bx1, by1] = geom.bbox;
  const span = Math.max(bx1 - bx0, by1 - by0);
  const pad = Math.max(140, span * 0.1);
  const chainRows = useMemo(() => {
    const count: Record<string, number> = {};
    return geom.chains.map((c) => {
      const side = sideOf(c.label || c.id, c.axis);
      const k = (count[side] = (count[side] ?? 0) + 1) - 1;
      return { c, side, off: 40 + k * 34 };
    });
  }, [geom.chains]);
  const extra = showChains ? Math.max(0, ...chainRows.map((r) => r.off)) + 30 : 0;
  const vb = [bx0 - pad - extra, by0 - pad - extra, bx1 - bx0 + 2 * (pad + extra), by1 - by0 + 2 * (pad + extra)];

  return (
    <svg viewBox={vb.join(" ")} role="img" aria-label="Digitalisierter Grundriss" className={image ? "ov" : undefined}>
      {image && (
        <image href={image.url} x={-image.t.x.offset / image.t.x.scale} y={-image.t.y.offset / image.t.y.scale}
               width={image.w / image.t.x.scale} height={image.h / image.t.y.scale} preserveAspectRatio="none"
               style={{ opacity: image.opacity }} />
      )}
      <g>
        {geom.zones.map((z, i) => <polygon key={i} className="p-zone" points={z.poly.map((p) => p.join(",")).join(" ")} />)}
        {geom.walls.map((w, i) => {
          const [x0, y0, x1, y1] = w.rect;
          return <rect key={i} className={`p-wall${w.kind === "brand" ? " brand" : ""}${w.estimated ? " est" : ""}`} x={x0} y={y0} width={x1 - x0} height={y1 - y0} />;
        })}
        {geom.openings.map((o, i) => {
          const [x0, y0, x1, y1] = o.rect;
          const horiz = x1 - x0 >= y1 - y0;
          if (o.type === "window") return (
            <g key={i}><rect className="p-win" x={x0} y={y0} width={x1 - x0} height={y1 - y0} />
              {horiz ? <line className="p-thin" x1={x0} x2={x1} y1={(y0 + y1) / 2} y2={(y0 + y1) / 2} /> : <line className="p-thin" y1={y0} y2={y1} x1={(x0 + x1) / 2} x2={(x0 + x1) / 2} />}</g>);
          if (o.type === "gate") return <line key={i} className="p-gate" x1={x0} x2={x1} y1={(y0 + y1) / 2} y2={(y0 + y1) / 2} />;
          if (!o.swing) return <rect key={i} className="p-door" x={x0} y={y0} width={x1 - x0} height={y1 - y0}><title>{o.type === "passage" ? "Durchgang" : "Tür"}</title></rect>;
          const { hinge: [hx, hy], r, a0, a1 } = o.swing;
          const rad = (a: number) => (a * Math.PI) / 180;
          const p0 = [hx + r * Math.cos(rad(a0)), hy + r * Math.sin(rad(a0))];
          const p1 = [hx + r * Math.cos(rad(a1)), hy + r * Math.sin(rad(a1))];
          return (
            <g key={i}>
              <path className="p-thin" d={`M${p0[0]},${p0[1]} A${r},${r} 0 0 ${a1 > a0 ? 1 : 0} ${p1[0]},${p1[1]}`} />
              <line className="p-leaf" x1={hx} y1={hy} x2={p1[0]} y2={p1[1]} />
            </g>);
        })}
        {geom.features.map((f, i) => {
          const [x0, y0, x1, y1] = f.rect;
          const stair = f.type.toLowerCase().startsWith("treppe");
          const n = f.treads ?? Math.max(2, Math.round(Math.max(x1 - x0, y1 - y0) / 25));
          const vert = y1 - y0 >= x1 - x0;
          return (
            <g key={i}>
              <rect className={stair ? "p-stair" : "p-feat"} x={x0} y={y0} width={x1 - x0} height={y1 - y0}><title>{f.type}{f.note ? `: ${f.note}` : ""}</title></rect>
              {stair && Array.from({ length: n - 1 }, (_, k) => vert
                ? <line key={k} className="p-thin" x1={x0} x2={x1} y1={y0 + ((y1 - y0) * (k + 1)) / n} y2={y0 + ((y1 - y0) * (k + 1)) / n} />
                : <line key={k} className="p-thin" y1={y0} y2={y1} x1={x0 + ((x1 - x0) * (k + 1)) / n} x2={x0 + ((x1 - x0) * (k + 1)) / n} />)}
              {/(schacht|aufzug|schornstein|kamin)/i.test(f.type) && <>
                <line className="p-thin" x1={x0} y1={y0} x2={x1} y2={y1} /><line className="p-thin" x1={x0} y1={y1} x2={x1} y2={y0} /></>}
            </g>);
        })}
        {(geom.fixtures ?? []).map((fx, i) => (
          <g key={i} className="p-fix"><title>{fx.type}</title>
            {fx.shapes.map((s, k) => s[0] === "rect" ? <rect key={k} x={s[1]} y={s[2]} width={s[3] - s[1]} height={s[4] - s[2]} />
              : s[0] === "line" ? <line key={k} x1={s[1]} y1={s[2]} x2={s[3]} y2={s[4]} />
              : <ellipse key={k} cx={s[1]} cy={s[2]} rx={Math.max(0, s[3])} ry={Math.max(0, s[4])} />)}
          </g>))}
        {(geom.marks ?? []).map((m, i) => (
          <g key={i}>
            <circle className="p-mark" cx={m.at[0]} cy={m.at[1]} r={9} />
            <line className="p-mark" x1={m.at[0] - 9} x2={m.at[0] + 9} y1={m.at[1]} y2={m.at[1]} />
            <line className="p-mark" y1={m.at[1] - 9} y2={m.at[1] + 9} x1={m.at[0]} x2={m.at[0]} />
            <text className="p-marktxt" x={m.at[0] + 14} y={m.at[1] + 5}>{m.text}</text>
          </g>))}
        {geom.rooms.map((r, i) => {
          if (!r.label) return null;
          const bad = r.area_geom != null && r.area_stated ? Math.abs(r.area_geom - r.area_stated) / r.area_stated > 0.03 : false;
          return (
            <g key={i}>
              <text className="p-room" x={r.label[0]} y={r.label[1]}>{r.name}</text>
              <text className={`p-area${bad ? " bad" : ""}`} x={r.label[0]} y={r.label[1] + 24}>
                {r.area_stated ? `${fmt(r.area_stated, 2)} m²` : r.area_geom ? `≈ ${fmt(r.area_geom, 2)} m²` : ""}
              </text>
            </g>);
        })}
      </g>
      {showChains && chainRows.map(({ c, side, off }) => {
        const pos = c.positions;
        const horiz = c.axis === "x";
        const at = side === "oben" ? by0 - off : side === "unten" ? by1 + off : side === "links" ? bx0 - off : bx1 + off;
        return (
          <g key={c.id}>
            {pos.slice(0, -1).map((a, k) => {
              const b = pos[k + 1];
              const sus = c.suspect.includes(k);
              const mid = (a + b) / 2;
              const txt = c.values[k] >= 30 || sus ? String(c.values[k]).replace(".", ",") : "";
              return horiz ? (
                <g key={k}>
                  <line className={`p-dim${sus ? " sus" : ""}`} x1={a} x2={b} y1={at} y2={at} />
                  <line className="p-dim" x1={a - 5} y1={at + 5} x2={a + 5} y2={at - 5} />
                  <text className={`p-dimtxt${sus ? " sus" : ""}`} x={mid} y={at - 6}>{txt}</text>
                </g>
              ) : (
                <g key={k}>
                  <line className={`p-dim${sus ? " sus" : ""}`} y1={a} y2={b} x1={at} x2={at} />
                  <line className="p-dim" x1={at - 5} y1={a + 5} x2={at + 5} y2={a - 5} />
                  <text className={`p-dimtxt${sus ? " sus" : ""}`} x={at - 6} y={mid} transform={`rotate(-90 ${at - 6} ${mid})`}>{txt}</text>
                </g>);
            })}
          </g>);
      })}
      {showPins && issues.map((i) => i.at && i.no ? (
        <g key={i.id} className={`pin ${i.severity}${selected === i.id ? " sel" : ""}`} role="button" tabIndex={0}
           aria-label={`Prüfpunkt ${i.no}: ${i.title}`} onClick={() => onSelect(i.id)}
           onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(i.id); } }}>
          <circle cx={i.at[0]} cy={i.at[1]} r={17} />
          <text x={i.at[0]} y={i.at[1]}>{i.no}</text>
        </g>) : null)}
    </svg>
  );
}
