/**
 * Illustration für die Startseite: derselbe kleine Grundriss einmal als Papierplan (Foto) und einmal als
 * CAD-Zeichnung, wie Planpause sie aus den Maßketten berechnet. Maßstab 1 px = 4 cm.
 */

const T = 7.5; // Außenwand 30 cm
const W = 256, H = 187; // 10,24 m × 7,49 m
const IX = 104.5; // Innenwand (11,5 cm) bei 4,18 m

const walls: [number, number, number, number][] = [
  [0, 0, W, T], [0, H - T, 200, T], [225, H - T, W - 225, T], [0, 0, T, H], [W - T, 0, T, H],
  [IX, T, 3, 120 - T], [IX, 142, 3, H - T - 142],
];
const windows: [number, number][] = [[30, 70], [150, 210]];

function Openings({ stroke }: { stroke: string }) {
  return (
    <g style={{ stroke, strokeWidth: 0.9, fill: "none" }}>
      {windows.map(([a, b]) => (
        <g key={a}>
          <rect x={a} y={0} width={b - a} height={T} style={{ fill: "#fff" }} />
          <line x1={a} y1={T / 2} x2={b} y2={T / 2} />
        </g>
      ))}
      <path d={`M${IX + 3} 120 h22 A22 22 0 0 1 ${IX + 3} 142`} />
      <path d={`M200 ${H - T} v-25 A25 25 0 0 1 225 ${H - T}`} />
    </g>
  );
}

export function PaperPlan() {
  const ink = "#3b3a36";
  return (
    <svg viewBox="-48 -52 316 256" role="img" aria-label="Fotografierter Papiergrundriss mit Maßketten">
      <rect x="-48" y="-52" width="316" height="256" style={{ fill: "#f7f1e1" }} />
      <g transform="rotate(-1.6 128 94)" style={{ fontFamily: "Georgia, serif", fontStyle: "italic" }}>
        {walls.map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} style={{ fill: "none", stroke: ink, strokeWidth: 0.9 }} />)}
        <Openings stroke={ink} />
        <g style={{ stroke: ink, strokeWidth: 0.6 }}>
          <line x1="0" y1="-16" x2={W} y2="-16" /><line x1="0" y1="-34" x2={W} y2="-34" /><line x1="-18" y1="0" x2="-18" y2={H} />
          {[0, IX + 1.5, W].map((x) => <line key={x} x1={x} y1="-20" x2={x} y2="-12" />)}
          {[0, W].map((x) => <line key={x} x1={x} y1="-38" x2={x} y2="-30" />)}
          {[0, H].map((y) => <line key={y} x1="-22" y1={y} x2="-14" y2={y} />)}
        </g>
        <g style={{ fill: ink, fontSize: 10 }} textAnchor="middle">
          <text x={(IX + 1.5) / 2} y="-19">4,24</text>
          <text x={(IX + 1.5 + W) / 2} y="-19">6,00</text>
          <text x={W / 2} y="-37">10,24</text>
          <text transform={`translate(-21 ${H / 2}) rotate(-90)`}>7,49</text>
          <text x="56" y="98" style={{ fontSize: 11 }}>Küche</text>
          <text x="178" y="98" style={{ fontSize: 11 }}>Wohnen</text>
        </g>
      </g>
      {/* Knick und Schatten wie bei einem fotografierten Blatt */}
      <path d="M140 -52 L128 204" style={{ stroke: "rgba(0,0,0,.06)", strokeWidth: 6 }} />
    </svg>
  );
}

export function CadPlan() {
  const dim = "var(--accent)";
  return (
    <svg viewBox="-48 -52 316 256" role="img" aria-label="Berechnete CAD-Zeichnung mit Wänden, Öffnungen und Bemaßung">
      <defs>
        <pattern id="lp-grid" width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M16 0H0V16" style={{ fill: "none", stroke: "#eef0f4", strokeWidth: 0.8 }} />
        </pattern>
        <pattern id="lp-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="4" style={{ stroke: "var(--wall)", strokeWidth: 1.4 }} />
        </pattern>
      </defs>
      <rect x="-48" y="-52" width="316" height="256" style={{ fill: "url(#lp-grid)" }} />
      <rect x={T} y={T} width={IX - T} height={H - 2 * T} style={{ fill: "var(--accent-soft)" }} />
      <rect x={IX + 3} y={T} width={W - T - IX - 3} height={H - 2 * T} style={{ fill: "rgba(31,138,67,.08)" }} />
      {walls.map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} style={{ fill: "url(#lp-hatch)", stroke: "var(--wall)", strokeWidth: 0.8 }} />)}
      <Openings stroke="#1d1d1f" />
      <g style={{ stroke: dim, strokeWidth: 0.8 }}>
        <line x1="0" y1="-16" x2={W} y2="-16" /><line x1="0" y1="-34" x2={W} y2="-34" /><line x1="-18" y1="0" x2="-18" y2={H} />
        {[0, IX + 1.5, W].map((x) => <line key={x} x1={x - 3} y1="-13" x2={x + 3} y2="-19" />)}
        {[0, W].map((x) => <line key={x} x1={x - 3} y1="-31" x2={x + 3} y2="-37" />)}
        {[0, H].map((y) => <line key={y} x1="-21" y1={y + 3} x2="-15" y2={y - 3} />)}
      </g>
      <g style={{ fill: dim, fontSize: 9, fontWeight: 600 }} textAnchor="middle">
        <text x={(IX + 1.5) / 2} y="-19">4,24</text>
        <text x={(IX + 1.5 + W) / 2} y="-19">6,00</text>
        <text x={W / 2} y="-37">10,24</text>
        <text transform={`translate(-21 ${H / 2}) rotate(-90)`}>7,49</text>
      </g>
      <g style={{ fill: "#1d1d1f", fontSize: 10, fontWeight: 600 }} textAnchor="middle">
        <text x="56" y="92">Küche</text><text x="56" y="105" style={{ fontSize: 8.5, fontWeight: 400, fill: "#6e6e73" }}>26,69 m²</text>
        <text x="178" y="92">Wohnen</text><text x="178" y="105" style={{ fontSize: 8.5, fontWeight: 400, fill: "#6e6e73" }}>38,80 m²</text>
      </g>
    </svg>
  );
}
