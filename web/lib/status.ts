import type { Meta } from "./types";

/** Status als farbige Plakette: [Text, Klasse] */
export function statusBadge(m: Pick<Meta, "status" | "quality">): [string, string] {
  if (m.status === "analyse") return ["Analyse läuft", "blue run"];
  if (m.status === "fehler") return ["Fehler", "crit"];
  if (m.status === "aufbereitet" || m.status === "neu") return ["Bereit zur Analyse", ""];
  if (m.quality === "nicht_auswertbar") return ["Nicht auswertbar", "crit"];
  if (m.quality === "eingeschraenkt") return ["Eingeschränkt", "warn"];
  return ["Analysiert", "ok"];
}

const FLOOR_ORDER = ["KG", "EG", "OG", "1. OG", "2. OG", "3. OG", "DG", "Spitzboden"];

/** Geschosse von unten nach oben sortieren, unbekannte Bezeichnungen ans Ende. */
export function floorOrder(floors: string[]): string[] {
  const rank = (f: string) => { const i = FLOOR_ORDER.indexOf(f); return i < 0 ? 99 : i; };
  return [...floors].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b, "de"));
}
