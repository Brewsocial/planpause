# Planpause – Plattform

Bestandsgrundrisse (oft handgezeichnet) hochladen, digitalisieren, auf Messfehler prüfen und als DXF in CAD-Programme übernehmen. Mehrere Betriebe nutzen die Plattform getrennt voneinander.

```
planpause-platform/
├── engine/   Genauigkeits-Engine (Python): Bildaufbereitung, KI-Extraktion, Maßketten-Solver, Prüfregeln, DXF
├── api/      FastAPI-Server mit Mandantentrennung
└── web/      Web-App (Next.js)
```

## Das Prinzip: Maßzahlen statt geschätzter Koordinaten

Der erste Prototyp ließ die KI direkt Koordinaten schätzen. Das ist bei Handzeichnungen nie genauer als die Zeichnung selbst. Die Plattform trennt deshalb Lesen und Rechnen:

1. **Bildaufbereitung** (`preprocess.py`): Blatt finden, perspektivisch entzerren, gerade drehen, Kontrast ausgleichen, vier vergrößerte Ausschnitte für kleine Zahlen.
2. **KI liest nur Topologie** (`extract.py`): Claude beschreibt den Plan als Rastermodell. Jede Wandkante liegt auf einer benannten Linie, jede Maßkette ist eine Folge von Werten zwischen Linien, Bauteile verweisen auf Linien. Claude rechnet nichts aus und korrigiert nichts. Antwort über ein Werkzeug mit festem JSON-Schema; fehlerhafte Antworten gehen einmal zur Korrektur zurück.
3. **Kanten einrasten** (`lines_cv.py`): Die grob geschätzten Pixelpositionen werden auf im Bild erkannte Wandkanten geschoben.
4. **Ausgleichsrechnung** (`solver.py`): Die Lage jeder Linie in Zentimetern wird pro Achse per gewichteter Ausgleichsrechnung aus den Maßzahlen bestimmt. Gewichte: gemessener Wert 0,3 cm, gelesene Maßzahl 1 cm, schwer lesbare Zahl 6 cm, aus Raumfläche abgeleitet 3 cm, Lage aus der Zeichnung 25 cm.
5. **Fehlersuche**: Widersprüche werden über Leave-one-out-Residuen erkannt (Zuverlässigkeitsprüfung wie in der Vermessung). Der Solver sucht den einen Wert, dessen Weglassen den Widerspruch auflöst, und nennt den Wert, der konsistent wäre. Gibt es mehrere Kandidaten, entscheidet, welcher am besten zur Zeichnung passt; daraus ergibt sich die angegebene Sicherheit.
6. **Fehlende Maße**: Fehlt eine Raumseite in den Ketten, wird sie aus der Flächenangabe abgeleitet. Was gar nicht bemaßt ist, wird aus der Zeichnung übernommen und als „nur nach Zeichnung“ markiert, mit konkreter Nachmess-Aufgabe.
7. **Messwerte vor Ort** haben Vorrang. Jeder eingetragene Wert löst eine Neuberechnung aus und macht Verdachtsfälle eindeutig.

## Genauigkeit messen

```bash
cd engine && python bench.py
```

Der Benchmark setzt in die beiden echten Testpläne nacheinander in jede Maßzahl einen typischen Lesefehler ein (Zahlendreher, falsche Ziffer, falsche Zehnerstelle) und prüft, ob der Solver ihn findet und richtig korrigiert. Stand dieser Version:

| Plan | Fehler | ohne Kontrollmaß | erkannt | richtiger Wert verdächtigt | korrekt verbessert |
|---|---:|---:|---:|---:|---:|
| Bungalow (Architektenplan) | 85 | 7 | 100 % | 96 % | 96 % |
| Darmstädter Str. 14 (Handzeichnung) | 34 | 9 | 100 % | 68 % | 48 % |

„Ohne Kontrollmaß“ heißt: Der Wert steht in keiner zweiten Kette, ein Fehler ist rechnerisch nicht erkennbar. Beim handgezeichneten Plan sind die Ketten kürzer und überschneiden sich seltener, deshalb ist dort die Zeichnung öfter der Schiedsrichter. Jede Änderung an Solver oder Prompt sollte gegen diesen Benchmark laufen; mit jedem echten Kundenplan, der als Fixture dazukommt, wird er aussagekräftiger.

## Schnellstart

Voraussetzungen: Python 3.11+, Node 20+.

```bash
# Engine + API
cd api
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...          # ohne Schlüssel laufen nur die Beispielprojekte
uvicorn app.main:app --reload --port 8000

# Web-App (zweites Terminal)
cd web
cp .env.example .env.local
npm install
npm run dev                                   # http://localhost:3000 (Projektseiten: /projekt?id=…)
```

Oder mit Docker: `ANTHROPIC_API_KEY=... docker compose up --build`.

Auf der Startseite lassen sich die beiden Testpläne als Beispielprojekte öffnen, ohne dass ein API-Schlüssel nötig ist.

### Tests

```bash
cd engine && pytest        # Solver, Prüfregeln, Export, Bildaufbereitung, Extraktion mit Fake-Client
cd api && pytest           # Mandantentrennung, Upload, Messwerte, Export
```

## Testbetrieb mit Supabase

Mit Supabase gibt es echte Benutzerkonten (nur auf Einladung), Postgres für die Projektdaten und einen privaten Speicher für Fotos und Ergebnisse. Ohne `SUPABASE_URL` läuft alles wie oben lokal mit Dateiablage und Demo-Schlüssel.

Planpause kann in einem **bestehenden** Supabase-Projekt mitlaufen: Tabellen liegen im eigenen Schema `planpause`, Dateien im eigenen Bucket `planpause`, ohne Verknüpfung zu anderen Daten. Geteilt sind nur die Benutzerliste (`auth.users`) und die Auth-Einstellungen. Konten anderer Apps kommen nicht hinein, weil die API nur Benutzer mit Eintrag in `planpause.org_members` zulässt. Projektweite Auth-Einstellungen (Site URL, Registrierung) bleiben unverändert; Planpause gibt Rücksprung-Adressen in jeder Mail selbst mit.

1. **Projekt**: bestehendes nutzen oder neues anlegen (Region *Central EU (Frankfurt)*).
2. **Schema einspielen**: Inhalt von `supabase/schema.sql` im SQL Editor ausführen. Danach unter Project Settings → Data API bei „Exposed schemas“ `planpause` ergänzen.
3. **Redirect URLs** (Authentication → URL Configuration): `<Web-App>/login?setpw=1` und `<Web-App>` zur Liste hinzufügen, für lokale Tests auch `http://localhost:3000/**`. Site URL nicht ändern, wenn sie einer anderen App gehört. Ist „Allow new users to sign up“ aus, ist das zusätzlich gut, aber nicht nötig.
4. **E-Mail-Versand**: Der eingebaute Versand von Supabase schickt nur wenige Mails pro Stunde. Für Einladungen und Passwort-Links einen eigenen SMTP-Dienst eintragen (Authentication → SMTP, z. B. Brevo oder Resend). Achtung: E-Mail-Vorlagen gelten projektweit, Einladungsmails tragen also den Text der anderen App, solange er nicht neutral formuliert ist.
5. **Schlüssel** (Project Settings → API) in die `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (öffentlich, für die Web-App) und `SUPABASE_SERVICE_KEY` (geheim, nur API-Server). Dazu ein langes `PLANPAUSE_ADMIN_TOKEN`.
6. **Betrieb anlegen und Tester einladen**:

```bash
curl -X POST $API/admin/orgs -H "X-Admin-Token: $PLANPAUSE_ADMIN_TOKEN" -H "Content-Type: application/json" \
     -d '{"id":"malerbetrieb-mueller","name":"Malerbetrieb Müller"}'
curl -X POST $API/admin/orgs/malerbetrieb-mueller/invite -H "X-Admin-Token: $PLANPAUSE_ADMIN_TOKEN" \
     -H "Content-Type: application/json" -d '{"email":"anna@mueller-maler.de"}'
```

Der Tester bekommt eine E-Mail, legt über den Link ein Passwort fest und sieht nur die Projekte seines Betriebs. Pro Betrieb sind `PLANPAUSE_DAILY_ANALYSES` KI-Analysen in 24 Stunden erlaubt (Standard 20).

Ist die E-Mail-Adresse schon von der anderen App registriert, verschickt Supabase keine Einladung; die API ordnet das bestehende Konto trotzdem dem Betrieb zu (`"invited": false`), und die Person meldet sich mit ihrem bisherigen Passwort an.

**Umzug in ein eigenes Supabase-Projekt:** `pg_dump --schema=planpause` einspielen, Bucket `planpause` kopieren, Tester im neuen Projekt neu einladen und `org_members` mit den neuen Benutzer-IDs füllen. Danach nur die drei Supabase-Werte in der `.env` tauschen.

**Hosting:** Supabase betreibt die Python-API nicht. Die API läuft als Docker-Container (`api/Dockerfile`) z. B. auf Render oder Fly.io in Frankfurt oder auf einem eigenen Server; die Web-App auf Vercel oder ebenfalls als Container. `PLANPAUSE_CORS` muss die Adresse der Web-App enthalten.

## Online stellen

### Testphase: Web-App bei Cloudflare, API auf dem eigenen Mac (kostenlos)

Die Web-App läuft als Cloudflare Worker unter einer festen Adresse (`planpause.<konto>.workers.dev`). Der Worker (`web/worker/index.js`) liefert die Seiten aus und leitet API-Aufrufe an `API_ORIGIN` weiter: die Adresse eines Cloudflare-Tunnels zum Mac, auf dem `./scripts/demo.sh` läuft.

1. Cloudflare-Dashboard → *Workers & Pages → Erstellen → Repository importieren* → GitHub-Repository `planpause`.
2. Stammverzeichnis (Root directory) **`web`**, Build-Befehl `npm run build`, Deploy-Befehl `npx wrangler deploy`. Weitere Build-Variablen sind nicht nötig, die öffentlichen Supabase-Werte stehen in `web/.env.production`.
3. Nach dem ersten Deployment unter *Einstellungen → Variablen und Geheimnisse* die Variable `API_ORIGIN` mit der Tunnel-Adresse aus `./scripts/demo.sh` anlegen. Ändert sich die Tunnel-Adresse, nur diesen Wert anpassen (`keep_vars` verhindert, dass Deployments ihn überschreiben).

Ist der Mac aus, lädt die Web-App trotzdem; die API antwortet dann mit „Planpause ist gerade nicht erreichbar“.

### Später: API dauerhaft hosten (Render)

Die API kann als Docker-Container auf Render laufen (`render.yaml`, Frankfurt): *New → Blueprint*, Repository wählen, Werte eintragen (`ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `PLANPAUSE_CORS`, `PLANPAUSE_SITE_URL`). Danach `API_ORIGIN` im Worker auf die Render-Adresse setzen.

Lokal: `npm run dev` (Entwicklung) oder `npm run preview` (Worker mit statischem Export in der Cloudflare-Laufzeit).

## Mandanten (Betriebe)

Jeder Betrieb hat einen API-Schlüssel und einen eigenen Datenbereich. Neue Betriebe legt man mit dem Admin-Token an:

```bash
curl -X POST localhost:8000/admin/orgs -H "X-Admin-Token: $PLANPAUSE_ADMIN_TOKEN" \
     -H "Content-Type: application/json" -d '{"id":"malerbetrieb-mueller","name":"Malerbetrieb Müller"}'
```

Für die Entwicklung gibt es den Betrieb `demo-betrieb` mit dem Schlüssel `demo-schluessel`.

## API (Auszug)

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/projects` | Foto hochladen (multipart: file, name, notes), wird sofort aufbereitet |
| POST | `/projects/{id}/analyze` | KI-Extraktion starten (läuft im Hintergrund, Status in `meta.status`) |
| POST | `/projects/demo/{bungalow\|darmstaedter14}` | Beispielprojekt anlegen |
| GET | `/projects/{id}` | Metadaten, Planmodell, Ergebnis (Geometrie, Prüfpunkte, Kennzahlen), Antworten |
| PUT | `/projects/{id}/plan` | Planmodell ersetzen (für den künftigen Editor), rechnet neu |
| POST | `/projects/{id}/measurements` | Messwert zwischen zwei Linien eintragen, rechnet neu |
| GET | `/projects/{id}/export/dxf?unit=mm` | DXF mit Layern |
| GET | `/projects/{id}/export/md` | Prüfbericht mit Nachmessliste |

## Grenzen dieser Version

- Nur achsparallele Wände werden berechnet. Schräge Wände sind im Modell vorgesehen (`walls_poly`), aber noch nicht im Solver.
- Die KI-Extraktion ist implementiert und mit einem Fake-Client getestet, aber noch nicht gegen viele echte Pläne kalibriert. Der Prompt in `extract.py` ist die wichtigste Stellschraube; Änderungen am Prompt gegen den Benchmark und echte Pläne prüfen.
- Ablage im Dateisystem, Anmeldung über API-Schlüssel. Für den Betrieb vorgesehen: Postgres + Objektspeicher in einer EU-Region, Login pro Mitarbeiter (z. B. Auth.js oder Clerk), Auftragsverarbeitungsverträge mit allen Dienstleistern.
- Bilder werden für die KI auf etwa 1,2 Megapixel verkleinert; die vier Ausschnitte gleichen das aus. Sehr große Pläne (A1-Scans) brauchen später mehr Kacheln.

## Nächste Schritte

1. **Echte Pläne sammeln**: 20 bis 30 Bestandspläne von Testbetrieben, jeweils mit vor Ort gemessenen Kontrollmaßen. Daraus Fixtures und eine zweite Benchmark-Stufe „KI-Extraktion gegen Handablesung“.
2. **Editor**: Linien verschieben, Werte einer Kette korrigieren, Wände ergänzen. Die API (`PUT /plan`) ist dafür vorbereitet.
3. **Konto- und Rechteverwaltung**, Abrechnung pro Plan, Postgres.
4. **IFC-Export** (IfcOpenShell) für ArchiCAD und Revit, sobald Raumhöhen erfasst sind.
5. **iOS-App mit RoomPlan**: Räume vor Ort per LiDAR scannen und als Messwerte in dasselbe Modell einspielen.
