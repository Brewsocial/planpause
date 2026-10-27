import io
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANPAUSE_DATA", str(tmp_path))
    monkeypatch.setenv("PLANPAUSE_ADMIN_TOKEN", "admin")
    import importlib
    import app.storage as st
    importlib.reload(st)
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


H = {"Authorization": "Bearer demo-schluessel"}


def test_ohne_schluessel_kein_zugriff(client):
    assert client.get("/projects").status_code == 401


def test_demo_projekt_messung_und_export(client):
    p = client.post("/projects/demo/darmstaedter14", headers=H).json()
    pid = p["id"]
    d = client.get(f"/projects/{pid}", headers=H).json()
    assert d["result"]["stats"]["conflicts"] == 2
    conflict = next(i for i in d["result"]["issues"] if i["id"].startswith("konflikt-y"))
    hint = conflict["measure"][0]
    r = client.post(f"/projects/{pid}/measurements", headers=H,
                    json={"axis": hint["axis"], "a": hint["a"], "b": hint["b"], "value": 52}).json()
    k = next(i for i in r["issues"] if i["id"].startswith("konflikt-y"))
    assert "wahrscheinlich" in k["detail"]
    dxf = client.get(f"/projects/{pid}/export/dxf", headers=H)
    assert dxf.status_code == 200 and b"SECTION" in dxf.content[:200]
    md = client.get(f"/projects/{pid}/export/md", headers=H)
    assert "Nachmessliste" in md.text
    assert client.get(f"/projects/{pid}/image", headers=H).headers["content-type"] == "image/jpeg"


def test_mandanten_sind_getrennt(client):
    key = client.post("/admin/orgs", headers={"X-Admin-Token": "admin"}, json={"id": "malerbetrieb-mueller", "name": "Müller"}).json()["api_key"]
    pid = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    other = {"Authorization": f"Bearer {key}"}
    assert client.get(f"/projects/{pid}", headers=other).status_code == 404
    assert client.get("/projects", headers=other).json() == []


def test_upload_wird_aufbereitet(client):
    img = np.full((900, 1200, 3), 240, np.uint8)
    cv2.rectangle(img, (200, 150), (1000, 750), (0, 0, 0), 18)
    data = cv2.imencode(".jpg", img)[1].tobytes()
    r = client.post("/projects", headers=H, files={"file": ("plan.jpg", io.BytesIO(data), "image/jpeg")}, data={"name": "Test"})
    assert r.status_code == 200 and r.json()["status"] == "aufbereitet"
    assert client.post(f"/projects/{r.json()['id']}/analyze", headers=H).status_code == 503  # ohne API-Schlüssel


def test_pfad_manipulation(client):
    assert client.get("/projects/..%2F..%2Fetc", headers=H).status_code in (404, 422)


def test_me_zeigt_betrieb(client):
    me = client.get("/me", headers=H).json()
    assert (me["org"], me["name"], me["trial_left"]) == ("demo-betrieb", "Demo-Betrieb", None)


def test_tageslimit_und_doppelstart(client, monkeypatch):
    import app.main as main
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(main, "DAILY_ANALYSES", 1)
    monkeypatch.setattr(main, "_run_extraction", lambda o, pid: None)
    a = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    b = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    assert client.post(f"/projects/{a}/analyze", headers=H).status_code == 200
    assert client.post(f"/projects/{a}/analyze", headers=H).status_code == 409
    assert client.post(f"/projects/{b}/analyze", headers=H).status_code == 429


def test_unterbrochene_analyse_wird_zurueckgesetzt(client):
    import app.main as main
    pid = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    main.store.update_meta("demo-betrieb", pid, status="analyse")
    assert main.store.reset_stuck() == 1
    assert client.get(f"/projects/{pid}", headers=H).json()["meta"]["status"] == "fehler"


def test_kleines_bild_bekommt_warnung_und_ergebnis_eine_ampel(client):
    img = np.full((900, 1200, 3), 240, np.uint8)
    cv2.rectangle(img, (200, 150), (1000, 750), (0, 0, 0), 18)
    r = client.post("/projects", headers=H, files={"file": ("plan.jpg", io.BytesIO(cv2.imencode(".jpg", img)[1].tobytes()), "image/jpeg")}).json()
    assert r["warnings"] and "900" in r["warnings"][0]
    p = client.post("/projects/demo/bungalow", headers=H).json()
    assert p["quality"] == "gut"
    assert client.get(f"/projects/{p['id']}", headers=H).json()["result"]["quality"]["level"] == "gut"


def test_analyse_nutzt_gespeichertes_bild_unveraendert(client, monkeypatch):
    # KI-Koordinaten müssen zum angezeigten Bild passen: kein zweites Zuschneiden/Entzerren
    import app.main as main
    import planpause_engine.extract as ex
    img = np.full((1600, 1500, 3), 240, np.uint8)
    cv2.rectangle(img, (200, 150), (1300, 1400), (0, 0, 0), 18)
    pid = client.post("/projects", headers=H, files={"file": ("plan.jpg", io.BytesIO(cv2.imencode(".jpg", img)[1].tobytes()), "image/jpeg")}).json()["id"]
    stored = cv2.imdecode(np.frombuffer(main.store.read_bytes("demo-betrieb", pid, "prepared.jpg"), np.uint8), cv2.IMREAD_GRAYSCALE)
    seen = {}
    def fake_extract(prep, notes=""):
        seen["size"] = prep.size
        raise RuntimeError("stopp")
    monkeypatch.setattr(ex, "extract_plan", fake_extract)
    main._run_extraction("demo-betrieb", pid)
    assert seen["size"] == (stored.shape[1], stored.shape[0])


def test_ki_fehler_werden_verstaendlich():
    import anthropic
    import httpx
    from app.main import _friendly_error
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    def err(cls, status, msg):
        return cls(msg, response=httpx.Response(status, request=req), body=None)
    assert "Guthaben" in _friendly_error(err(anthropic.BadRequestError, 400, "Your credit balance is too low"))
    assert "ausgelastet" in _friendly_error(err(anthropic.RateLimitError, 429, "rate limit"))
    assert "ungültig" in _friendly_error(err(anthropic.AuthenticationError, 401, "invalid x-api-key"))
    assert _friendly_error(ValueError("Die KI hat die Auswertung dieses Bildes abgelehnt.")).startswith("Die KI hat")


def test_kosten_werden_am_projekt_summiert(client, monkeypatch):
    import app.main as main
    import planpause_engine.extract as ex
    from planpause_engine.model import PlanModel
    plan = PlanModel.model_validate(json.loads((main.FIXTURES / "plan_bungalow.json").read_text()))
    pid = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    monkeypatch.setattr(ex, "extract_plan", lambda prep, notes="": (plan, {"cost_usd": 0.31, "rounds": []}))
    main._run_extraction("demo-betrieb", pid)
    def fail(prep, notes=""):
        raise ex.ExtractionError("abgeschnitten", {"cost_usd": 1.33, "rounds": []})
    monkeypatch.setattr(ex, "extract_plan", fail)
    main._run_extraction("demo-betrieb", pid)
    m = client.get(f"/projects/{pid}", headers=H).json()["meta"]
    assert m["last_cost_usd"] == 1.33 and m["cost_usd"] == pytest.approx(1.64) and m["status"] == "fehler"


def test_web_app_wird_mit_ausgeliefert(tmp_path, monkeypatch):
    web = tmp_path / "out"
    (web / "_next").mkdir(parents=True)
    (web / "index.html").write_text("start"); (web / "login.html").write_text("login")
    (web / "404.html").write_text("fehlt"); (web / "_next" / "a.js").write_text("js")
    (tmp_path / "geheim.txt").write_text("nein")
    monkeypatch.setenv("PLANPAUSE_STATIC_DIR", str(web))
    monkeypatch.setenv("PLANPAUSE_DATA", str(tmp_path / "data"))
    import importlib
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        assert c.get("/").text == "start" and c.get("/login").text == "login" and c.get("/_next/a.js").text == "js"
        assert c.get("/health").json()["ok"] is True  # API-Pfade bleiben erreichbar
        assert c.get("/projects", headers=H).status_code == 200
        r = c.get("/..%2Fgeheim.txt")
        assert r.status_code == 404 and "nein" not in r.text
    monkeypatch.delenv("PLANPAUSE_STATIC_DIR")
    importlib.reload(main)


# ------------------------------------------------------------- Projekte (Ordner) und Geschosse

def test_projekt_mit_grundrissen_und_geschoss(client):
    f = client.post("/folders", headers=H, json={"name": "Haus Lindenweg 4"}).json()
    fid = f["id"]
    a = client.post(f"/projects/demo/bungalow?folder_id={fid}", headers=H).json()
    b = client.post(f"/projects/demo/darmstaedter14?folder_id={fid}", headers=H).json()
    client.patch(f"/projects/{a['id']}", headers=H, json={"part": "A – Altbau"})
    client.patch(f"/projects/{b['id']}", headers=H, json={"part": "B – Anbau"})

    lst = client.get("/folders", headers=H).json()
    mine = next(x for x in lst["folders"] if x["id"] == fid)
    assert {p["id"] for p in mine["plans"]} == {a["id"], b["id"]}
    assert all(p["id"] != fid for p in client.get("/projects", headers=H).json())  # Ordner sind keine Grundrisse

    g = client.get(f"/folders/{fid}/floors/EG/geometry", headers=H).json()
    assert {p["label"] for p in g["parts"]} == {"A – Altbau", "B – Anbau"} and not g["saved"]
    pa, pb = (next(p for p in g["parts"] if p["id"] == x["id"]) for x in (a, b))
    assert pb["bbox"][0] > pa["bbox"][2]  # ohne Anordnung nebeneinander, ohne Überlappung

    r = client.patch(f"/folders/{fid}", headers=H, json={"assembly": {"EG": {
        a["id"]: {"dx": 0, "dy": 0, "rot": 0}, b["id"]: {"dx": 3000, "dy": 50, "rot": 90}}}})
    assert r.status_code == 200
    g2 = client.get(f"/folders/{fid}/floors/EG/geometry", headers=H).json()
    assert g2["saved"] and next(p for p in g2["parts"] if p["id"] == b["id"])["rot"] == 90

    dxf = client.get(f"/folders/{fid}/floors/EG/export/dxf", headers=H)
    assert dxf.status_code == 200 and b"SECTION" in dxf.content[:200] and "Haus_Lindenweg_4_EG" in dxf.headers["content-disposition"]
    assert client.get(f"/folders/{fid}/floors/OG/geometry", headers=H).status_code == 404


def test_upload_in_projekt_und_verschieben(client):
    fid = client.post("/folders", headers=H, json={"name": "Garage"}).json()["id"]
    img = np.full((900, 1200, 3), 240, np.uint8)
    cv2.rectangle(img, (200, 150), (1000, 750), (0, 0, 0), 18)
    up = client.post("/projects", headers=H, files={"file": ("p.jpg", io.BytesIO(cv2.imencode(".jpg", img)[1].tobytes()), "image/jpeg")},
                     data={"folder_id": fid, "floor": "OG", "part": "C"}).json()
    assert (up["folder_id"], up["floor"], up["part"]) == (fid, "OG", "C")
    assert client.post("/projects", headers=H, files={"file": ("p.jpg", io.BytesIO(b"x"), "image/jpeg")},
                       data={"folder_id": "gibtsnicht"}).status_code == 404
    moved = client.patch(f"/projects/{up['id']}", headers=H, json={"folder_id": ""}).json()
    assert moved["folder_id"] is None
    assert any(p["id"] == up["id"] for p in client.get("/folders", headers=H).json()["unassigned"])


def test_projekt_loeschen_entfernt_grundrisse(client):
    d = client.post("/projects/demo/bungalow", headers=H).json()  # Beispiel legt eigenes Projekt an
    fid = d["folder_id"]
    assert client.get(f"/folders/{fid}", headers=H).json()["folder"]["name"].startswith("Beispiel")
    assert client.delete(f"/folders/{fid}", headers=H).status_code == 200
    assert client.get(f"/projects/{d['id']}", headers=H).status_code == 404


def test_fremde_projekte_bleiben_getrennt(client):
    key = client.post("/admin/orgs", headers={"X-Admin-Token": "admin"}, json={"id": "anderer-betrieb", "name": "Anders"}).json()["api_key"]
    fid = client.post("/folders", headers=H, json={"name": "Geheim"}).json()["id"]
    other = {"Authorization": f"Bearer {key}"}
    assert client.get(f"/folders/{fid}", headers=other).status_code == 404
    assert client.get("/folders", headers=other).json() == {"folders": [], "unassigned": []}
    assert client.post(f"/projects/demo/bungalow?folder_id={fid}", headers=other).status_code == 404


def test_cloudflare_worker_leitet_alle_api_pfade_weiter(client):
    # Der Worker (web/worker/index.js) liefert alles außer API-Pfaden als Seite aus. Fehlt ein neuer
    # Endpunkt in seiner Liste, funktioniert er lokal, aber nicht über Cloudflare.
    import re
    from pathlib import Path
    import app.main as main
    src = (Path(main.__file__).resolve().parents[2] / "web" / "worker" / "index.js").read_text()
    prefixes = set(re.findall(r'"(/[a-z]+)"', re.search(r"API_PREFIXES = \[(.*?)\]", src).group(1)))
    roots = {"/" + r.path.strip("/").split("/")[0] for r in main.app.routes if getattr(r, "path", "").startswith("/")
             and r.path not in ("/{path:path}",) and not r.path.startswith(("/docs", "/redoc", "/openapi"))}
    assert roots <= prefixes, f"Im Worker fehlen: {roots - prefixes}"


def _pdf_bytes(pages: int = 2) -> bytes:
    """Kleines PDF mit den Demo-Bildern als Seiten (über pypdfium2, ohne weitere Abhängigkeiten)."""
    import app.main as main
    from planpause_engine.pdf import images_to_pdf
    return images_to_pdf([cv2.imread(str(main.DEMO / n), cv2.IMREAD_GRAYSCALE) for n in ["bungalow.jpg", "darmstaedter14.jpg"][:pages]])


def test_pdf_hochladen_mit_seitenwahl_und_ausschnitt(client):
    data = _pdf_bytes(2)
    pages = client.post("/pdf/pages", headers=H, files={"file": ("plan.pdf", io.BytesIO(data), "application/pdf")}).json()["pages"]
    assert [p["page"] for p in pages] == [1, 2] and pages[0]["thumb"].startswith("data:image/jpeg;base64,")
    r = client.post("/projects", headers=H, files={"file": ("plan.pdf", io.BytesIO(data), "application/pdf")},
                    data={"page": "2", "crop": "0.1,0.1,0.9,0.8", "name": "EG aus PDF"}).json()
    assert r["status"] == "aufbereitet" and r["source"] == "pdf" and r["pdf_page"] == 2 and r["warnings"] == []
    assert max(r["image_size"]) >= 4000 and "Ausschnitt gewählt" in r["steps"]
    assert client.post("/projects", headers=H, files={"file": ("plan.pdf", io.BytesIO(data), "application/pdf")},
                       data={"page": "5"}).status_code == 422
    assert client.post("/pdf/pages", headers=H, files={"file": ("x.pdf", io.BytesIO(b"kein pdf"), "application/pdf")}).status_code == 422


def test_vorschaubild_verkleinert(client):
    pid = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    full = client.get(f"/projects/{pid}/image", headers=H).content
    small = client.get(f"/projects/{pid}/image?max=500", headers=H).content
    img = cv2.imdecode(np.frombuffer(small, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert max(img.shape) == 500 and len(small) < len(full) / 3


def test_probe_kontingent(client, monkeypatch):
    import app.main as main
    import planpause_engine.extract as ex
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    adm = {"X-Admin-Token": "admin"}
    assert client.patch("/admin/orgs/demo-betrieb", headers=adm, json={"trial_left": 1}).status_code == 200
    assert client.patch("/admin/orgs/gibt-es-nicht", headers=adm, json={"trial_left": 1}).status_code == 404
    assert client.get("/me", headers=H).json()["trial_left"] == 1
    a = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    b = client.post("/projects/demo/bungalow", headers=H).json()["id"]
    monkeypatch.setattr(main, "_run_extraction", lambda o, pid: None)
    assert client.post(f"/projects/{a}/analyze", headers=H).status_code == 200
    assert client.get("/me", headers=H).json()["trial_left"] == 0
    r = client.post(f"/projects/{b}/analyze", headers=H)
    assert r.status_code == 402 and "aufgebraucht" in r.json()["detail"]
    # Fehlgeschlagene Analyse gibt den Grundriss zurück
    monkeypatch.undo()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ex, "extract_plan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kaputt")))
    main._run_extraction("demo-betrieb", a)
    assert client.get("/me", headers=H).json()["trial_left"] == 1
    # Freischalten: ohne Begrenzung
    client.patch("/admin/orgs/demo-betrieb", headers=adm, json={"trial_left": None})
    assert client.post(f"/projects/{b}/analyze", headers=H).status_code == 200


def test_registrierung_nur_mit_supabase(client):
    assert client.post("/signup", json={"email": "a@b.de", "password": "geheim123", "company": "X GmbH", "business": True}).status_code == 501
