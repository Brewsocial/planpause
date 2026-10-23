import type { Geometry, Placement } from "./types";

/** Gleiche Abbildung wie engine/combine.py: p' = R(rot) · p + (dx, dy), y zeigt nach unten (+90° = im Uhrzeigersinn). */
export function rotPt(x: number, y: number, rot: Placement["rot"]): [number, number] {
  if (rot === 90) return [-y, x];
  if (rot === 180) return [-x, -y];
  if (rot === 270) return [y, -x];
  return [x, y];
}

export function place(x: number, y: number, p: Placement): [number, number] {
  const [rx, ry] = rotPt(x, y, p.rot);
  return [rx + p.dx, ry + p.dy];
}

/** Umrandung eines Teils nach Drehen und Verschieben */
export function placedBox(g: Geometry, p: Placement): [number, number, number, number] {
  const [x0, y0, x1, y1] = g.bbox;
  const pts = [place(x0, y0, p), place(x1, y0, p), place(x0, y1, p), place(x1, y1, p)];
  const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** Um 90° weiterdrehen, ohne dass das Teil wegspringt: Mittelpunkt bleibt an seiner Stelle. */
export function rotateInPlace(g: Geometry, p: Placement): Placement {
  const [x0, y0, x1, y1] = g.bbox;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const [mx, my] = place(cx, cy, p);
  const rot = ((p.rot + 90) % 360) as Placement["rot"];
  const [rx, ry] = rotPt(cx, cy, rot);
  return { rot, dx: mx - rx, dy: my - ry };
}

/** Wandecken eines Teils in Geschoss-Koordinaten (zum Antippen beim Verbinden) */
export function corners(g: Geometry, p: Placement): [number, number][] {
  const seen = new Set<string>();
  const out: [number, number][] = [];
  for (const w of g.walls) {
    const [x0, y0, x1, y1] = w.rect;
    for (const [x, y] of [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) {
      const q = place(x, y, p);
      const k = `${Math.round(q[0])},${Math.round(q[1])}`;
      if (!seen.has(k)) { seen.add(k); out.push(q); }
    }
  }
  return out;
}

function inPoly(x: number, y: number, poly: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Außenecken des Gebäudes: Wandecken, an die kein Raum grenzt. Gebäudeteile stoßen fast immer an
 *  Außenecken aneinander; Innenecken liegen nur eine Wanddicke daneben und würden sonst leicht vertauscht.
 *  Ohne Raumumrisse im Plan: alle Ecken. */
export function outerCorners(g: Geometry, p: Placement): [number, number][] {
  const rooms = g.rooms.filter((r) => r.poly.length >= 3).map((r) => r.poly);
  if (!rooms.length) return corners(g, p);
  const inWall = (x: number, y: number) => g.walls.some(({ rect: [x0, y0, x1, y1] }) => x > x0 && x < x1 && y > y0 && y < y1);
  const inRoom = (x: number, y: number) => rooms.some((poly) => inPoly(x, y, poly));
  // Laibungen von Fenstern und Türen sind keine Gebäudeecken
  const inOpening = (x: number, y: number) => g.openings.some(({ rect: [x0, y0, x1, y1] }) => x >= x0 - 1 && x <= x1 + 1 && y >= y0 - 1 && y <= y1 + 1);
  const seen = new Set<string>();
  const out: [number, number][] = [];
  const e = 4; // cm neben der Ecke prüfen
  for (const w of g.walls) {
    const [x0, y0, x1, y1] = w.rect;
    for (const [x, y] of [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) {
      const around = [[x - e, y - e], [x + e, y - e], [x - e, y + e], [x + e, y + e]];
      const walls = around.filter(([a, b]) => inWall(a, b)).length;
      // 1 Nachbarpunkt in der Wand: vorspringende Ecke, 3: einspringende Ecke.
      // 2 wäre nur die Stoßkante zweier Wandstücke auf einer geraden Wand, also keine Ecke.
      if ((walls !== 1 && walls !== 3) || around.some(([a, b]) => inRoom(a, b) || inOpening(a, b))) continue;
      const q = place(x, y, p);
      const k = `${Math.round(q[0])},${Math.round(q[1])}`;
      if (!seen.has(k)) { seen.add(k); out.push(q); }
    }
  }
  return out.length >= 3 ? out : corners(g, p);
}

export const PART_COLORS = ["#0071e3", "#e8590c", "#2b8a3e", "#9c36b5", "#c2255c", "#0c8599"];
