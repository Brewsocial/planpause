#!/bin/bash
# Startet die Planpause-Demo vom Mac aus: API + Web-App auf Port 3000 und einen Cloudflare Quick Tunnel.
# Aufruf aus dem Projektordner:  ./scripts/demo.sh        (Strg+C beendet alles)
# Optional vorher neu bauen:      ./scripts/demo.sh --build
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
CLOUDFLARED="${CLOUDFLARED:-$HOME/.local/cloudflared/cloudflared}"

[ -f .env ] || { echo "Fehlt: .env (siehe .env.example)"; exit 1; }
[ -x .venv/bin/python ] || { echo "Fehlt: .venv (Python-Umgebung, siehe README)"; exit 1; }
[ -x "$CLOUDFLARED" ] || { echo "Fehlt: cloudflared unter $CLOUDFLARED"; exit 1; }

if [ "${1:-}" = "--build" ] || [ ! -d web/out ]; then
  echo "Baue die Web-App …"
  (cd web && NEXT_PUBLIC_API_URL= npm run build >/dev/null)
fi

if lsof -ti :3000 -sTCP:LISTEN >/dev/null; then
  echo "Port 3000 ist belegt. Läuft die Demo schon?"; exit 1
fi

set -a; . ./.env; set +a
export PLANPAUSE_STATIC_DIR="$ROOT/web/out"

(cd api && exec ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 3000 --log-level warning) &
SERVER=$!
trap 'kill $SERVER $TUNNEL 2>/dev/null; echo; echo "Demo beendet."' EXIT

for _ in $(seq 1 30); do curl -s -o /dev/null localhost:3000/health && break; sleep 1; done
echo "Server läuft: http://localhost:3000"

LOG=$(mktemp -t planpause-tunnel)
"$CLOUDFLARED" tunnel --no-autoupdate --url http://localhost:3000 >"$LOG" 2>&1 &
TUNNEL=$!
for _ in $(seq 1 45); do URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$LOG" | head -1 || true); [ -n "$URL" ] && break; sleep 1; done

echo
echo "  Planpause ist erreichbar unter:  ${URL:-(Tunnel-Adresse nicht gefunden, siehe $LOG)}"
echo
echo "  Feste Adresse: https://planpause.info-brewsocial.workers.dev"
echo "  Hat sich die Tunnel-Adresse geändert, API_ORIGIN in wrangler.jsonc und web/wrangler.jsonc"
echo "  anpassen und pushen (oder sofort im Cloudflare-Dashboard unter Settings → Variables and Secrets)."
echo
echo "  Der Mac darf nicht schlafen: am Netzteil lassen und den Deckel offen halten."
echo "  Strg+C beendet Server und Tunnel."

# Verhindert das automatische Einschlafen, solange die Demo läuft (Deckel zu im Akkubetrieb schläft trotzdem)
caffeinate -i -w $SERVER
