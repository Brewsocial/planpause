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
