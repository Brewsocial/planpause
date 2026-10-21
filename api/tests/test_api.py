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
    assert client.get("/me", headers=H).json() == {"org": "demo-betrieb", "name": "Demo-Betrieb"}


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
