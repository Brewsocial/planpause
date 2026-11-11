// Vor der Veröffentlichung: stoppt, solange in den fertigen Seiten Platzhalter oder Prüfmarkierungen stehen.
// Aufruf: npm run build && npm run check:release
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../out", import.meta.url));
const RULES = [
  [/check-note/, "offene [prüfen]-Markierung (Datenschutz)"],
  [/\[(?:Straße|Telefon|kontakt|Name|Ort)[^\]]*\]/i, "Platzhalter in eckigen Klammern"],
  [/localhost:\d+|trycloudflare\.com/, "Entwicklungsadresse"],
  [/Lorem ipsum|TODO|FIXME/, "Platzhaltertext"],
];

const files = (d) => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? files(p) : [p]; });
const bad = [];
for (const f of files(OUT).filter((f) => /\.(html|txt)$/.test(f))) {
  const s = readFileSync(f, "utf8");
  for (const [re, what] of RULES) if (re.test(s)) bad.push(`${f.slice(OUT.length)}: ${what}`);
}
if (bad.length) {
  console.error("Nicht bereit für die Veröffentlichung:\n- " + [...new Set(bad)].join("\n- "));
  process.exit(1);
}
console.log("Release-Check bestanden.");
