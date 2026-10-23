// Cloudflare Worker für Planpause: liefert die statische Web-App aus und leitet API-Aufrufe an die
// Planpause-API weiter. Deren Adresse steht in der Variablen API_ORIGIN (Cloudflare-Dashboard →
// Worker → Einstellungen → Variablen), z. B. die Adresse des Cloudflare-Tunnels zum Mac.

// Alle Pfade der API; neue Endpunkte hier ergänzen, sonst liefert der Worker stattdessen eine Seite aus
const API_PREFIXES = ["/health", "/me", "/projects", "/folders", "/pdf", "/admin"];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const isApi = API_PREFIXES.some((p) => url.pathname === p || url.pathname.startsWith(p + "/"));
    if (!isApi) return env.ASSETS.fetch(request);

    if (!env.API_ORIGIN) return unavailable("API_ORIGIN ist nicht gesetzt.");
    const target = new URL(url.pathname + url.search, env.API_ORIGIN);
    try {
      const res = await fetch(new Request(target, request));
      // Tunnel weg (Mac aus oder im Ruhezustand): Cloudflare antwortet mit 502/530 und einer HTML-Seite
      if ([502, 503, 504, 530].includes(res.status) && !(res.headers.get("content-type") || "").includes("json")) {
        return unavailable(`Antwort ${res.status}`);
      }
      return res;
    } catch (e) {
      return unavailable(String(e));
    }
  },
};

function unavailable(reason) {
  return new Response(JSON.stringify({ detail: "Planpause ist gerade nicht erreichbar. Bitte später erneut versuchen.", reason }), {
    status: 503, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
