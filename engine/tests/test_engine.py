import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import ezdxf
import numpy as np
import pytest

from planpause_engine.export import to_dxf, to_report
from planpause_engine.extract import extract_plan
from planpause_engine.model import Measurement, PlanModel
from planpause_engine.pipeline import analyze, issues_from
from planpause_engine.preprocess import Prepared, prepare
from planpause_engine.solver import solve

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> PlanModel:
    return PlanModel.model_validate(json.loads((FIX / name).read_text()))


@pytest.fixture
def bungalow():
    return load("plan_bungalow.json")


@pytest.fixture
def darmstaedter():
    return load("plan_darmstaedter14.json")


def chain(plan, cid):
    return next(c for c in plan.chains if c.id == cid)


# ------------------------------------------------------------- Solver

def test_bungalow_ist_widerspruchsfrei(bungalow):
    r = analyze(bungalow)
    assert r["stats"]["conflicts"] == 0
    assert r["stats"]["rooms_ok"] == r["stats"]["rooms_checked"] == 11
    rooms = {x["name"]: x for x in r["geometry"]["rooms"]}
    assert rooms["Wohnen"]["area_geom"] == pytest.approx(27.46, abs=0.02)
    assert rooms["Diele"]["area_geom"] == pytest.approx(19.16, abs=0.02)


def test_tippfehler_wird_gefunden_und_korrigiert(bungalow):
    c = chain(bungalow, "links-eltern-kind")
    c.values[5] = 457  # Kind: 4.75 falsch als 4.57 gelesen
    sol = solve(bungalow)
    assert len(sol.y.conflicts) == 1
    k = sol.y.conflicts[0]
    assert k.magnitude == pytest.approx(18, abs=1.0)  # Originalplan hat bereits 0,5 cm Restwiderspruch
    assert k.chosen.constraint.ref == "links-eltern-kind" and k.chosen.constraint.index == 5
    assert k.chosen.suggested == pytest.approx(475, abs=1.0)
    assert k.confidence in ("hoch", "mittel")


def test_tippfehler_in_redundanter_kette(bungalow):
    chain(bungalow, "unten-licht").values[5] = 421  # Diele 412 -> 421
    sol = solve(bungalow)
    k = sol.x.conflicts[0]
    assert k.chosen.constraint.ref == "unten-licht"
    assert k.chosen.suggested == pytest.approx(412, abs=1.0)
    assert k.confidence == "hoch"  # andere Ketten bestätigen 412 direkt


def test_darmstaedter_findet_beide_fehler(darmstaedter):
    sol = solve(darmstaedter)
    assert [round(k.magnitude) for k in sol.x.conflicts][:1] == [148]
    assert round(sol.y.conflicts[0].magnitude) == 18
    assert sol.y.conflicts[0].chosen.constraint.value == 70


def test_messung_macht_verdacht_eindeutig(darmstaedter):
    darmstaedter.measurements.append(Measurement(id="m1", axis="y", a="y606", b="rechts_r1", value=52))
    sol = solve(darmstaedter)
    k = sol.y.conflicts[0]
    assert k.chosen.constraint.value == 70 and k.confidence == "hoch"
    assert sol.y.pos["rechts_r1"] - sol.y.pos["y606"] == pytest.approx(52, abs=0.5)


def test_flaeche_liefert_fehlende_tiefe(bungalow):
    sol = solve(bungalow)
    assert sol.y.pos["y750"] - sol.y.pos["y285"] == pytest.approx(465, abs=1)
    # Die Tiefe ist bekannt, die Lage der Diele im Haus nur aus der Zeichnung
    assert sol.y.status["y750"] == "zeichnung"


def test_unbemasste_lage_wird_gemeldet(bungalow):
    issues = analyze(bungalow)["issues"]
    assert any(i["category"] == "Unvermaßt" and i["severity"] == "pruefen" for i in issues)
    assert any(i["id"] == "tueren-barrierefrei" for i in issues)


def test_flaechenabweichung_darmstaedter(darmstaedter):
    titles = [i["title"] for i in analyze(darmstaedter)["issues"]]
    assert any(t.startswith("Küche") for t in titles) and any(t.startswith("Flur") for t in titles)


def test_tueraufschlag(bungalow):
    g = analyze(bungalow)["geometry"]
    bad = [o for o in g["openings"] if o["type"] == "door" and o["width_stated"] == 76][0]
    assert bad["swing"]["r"] == pytest.approx(76, abs=0.5)
    assert abs(bad["swing"]["a1"] - bad["swing"]["a0"]) == 90


# ------------------------------------------------------------- Export

def test_dxf_export_lesbar(bungalow):
    r = analyze(bungalow)
    data = to_dxf(r["geometry"], issues_from(r), "mm", bungalow.title)
    doc = ezdxf.read(io.StringIO(data.decode()))
    layers = {l.dxf.name for l in doc.layers}
    assert {"WAENDE", "BRANDWAND", "TUEREN", "FENSTER", "BEMASSUNG"} <= layers
    assert doc.header["$INSUNITS"] == 4
    assert len(doc.modelspace().query("HATCH")) >= 40


def test_bericht(darmstaedter):
    r = analyze(darmstaedter)
    md = to_report(darmstaedter.title, r["geometry"], issues_from(r))
    assert "Nachmessliste" in md and "148" in md


# ------------------------------------------------------------- Bild

def _synthetic_plan(angle: float) -> bytes:
    img = np.full((1200, 1600, 3), 235, np.uint8)
    cv2.rectangle(img, (300, 250), (1300, 950), (20, 20, 20), 22)
    cv2.rectangle(img, (300, 250), (800, 950), (20, 20, 20), 12)
    M = cv2.getRotationMatrix2D((800, 600), angle, 1.0)
    img = cv2.warpAffine(img, M, (1600, 1200), borderValue=(235, 235, 235))
    return cv2.imencode(".jpg", img)[1].tobytes()


def test_entzerrung_dreht_gerade():
    p = prepare(_synthetic_plan(2.0))
    assert abs(abs(p.angle) - 2.0) < 0.3
    from planpause_engine.lines_cv import wall_edges
    e = wall_edges(p.image)
    assert any(abs(x - 300 + 11) < 8 or abs(x - 289) < 8 for x in e["x"])


# ------------------------------------------------------------- Extraktion (ohne echten API-Aufruf)

class FakeStream:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        if self.payload is None:  # Modell antwortet nur mit Text
            block, stop = SimpleNamespace(type="text", text="Hier ist der Plan …"), "end_turn"
        else:
            block, stop = SimpleNamespace(type="tool_use", id="tu_1", input=self.payload), "tool_use"
        return SimpleNamespace(content=[block], stop_reason=stop, usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 12000, "output_tokens": 6000}))


class FakeClient:
    def __init__(self, payloads):
        self.payloads, self.calls = list(payloads), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        self.calls.append(kw)
        return FakeStream(self.payloads.pop(0))


def test_extraktion_mit_korrekturrunde():
    good = json.loads((FIX / "plan_bungalow.json").read_text())
    broken = copy.deepcopy(good)
    broken["walls"][0]["x0"] = "x_gibt_es_nicht"
    client = FakeClient([broken, good])
    prep = Prepared(np.full((1536, 2048), 255, np.uint8), (2048, 1536))
    plan, log = extract_plan(prep, client=client)
    assert len(client.calls) == 2 and log["rounds"][0]["errors"]
    assert not plan.validate_refs()
    first = client.calls[0]
    assert first["tool_choice"]["type"] == "auto"  # erzwungene Werkzeugwahl lehnen aktuelle Modelle ab
    assert first["fallbacks"] == "default" and first["output_config"]["effort"] == "medium"
    assert first["output_config"]["task_budget"]["total"] >= 20000 and "task-budgets-2026-03-13" in first["betas"]
    assert log["cost_usd"] > 0 and len(log["rounds"]) == 2
    assert sum(1 for c in first["messages"][0]["content"] if c["type"] == "image") == 5


def test_extraktion_fordert_werkzeugaufruf_nach():
    good = json.loads((FIX / "plan_bungalow.json").read_text())
    client = FakeClient([None, good])
    prep = Prepared(np.full((1536, 2048), 255, np.uint8), (2048, 1536))
    plan, log = extract_plan(prep, client=client)
    assert len(client.calls) == 2 and log["rounds"][0]["errors"] == ["kein Werkzeugaufruf"]
    assert client.calls[1]["messages"][-1]["content"].startswith("Bitte speichere")
    assert not plan.validate_refs()


def test_achse_ohne_masskette_faellt_nicht_zusammen(bungalow):
    # Schlecht lesbare Pläne: nur waagerechte Maße erkannt. Die y-Achse übernimmt den Maßstab von x.
    bungalow.chains = [c for c in bungalow.chains if c.axis == "x"]
    r = analyze(bungalow)
    ys = r["geometry"]["lines"]["y"]
    assert "mass" not in {l["status"] for l in ys}  # nur Zeichnung oder aus Raumflächen
    assert r["geometry"]["bbox"][3] > 500  # Bungalow ist gut 10 m tief, nicht 0


def test_ueberlagerung_auch_ohne_vermasste_achse(bungalow):
    bungalow.chains = [c for c in bungalow.chains if c.axis == "x"]
    t = analyze(bungalow)["image_transform"]
    assert t and t["y"]["scale"] == pytest.approx(t["x"]["scale"], rel=0.15)


def test_qualitaet_der_testplaene_ist_gut(bungalow, darmstaedter):
    assert analyze(bungalow)["quality"]["level"] == "gut"
    assert analyze(darmstaedter)["quality"]["level"] == "gut"


def test_plan_ohne_senkrechte_masse_ist_nicht_auswertbar(bungalow):
    bungalow.chains = [c for c in bungalow.chains if c.axis == "x"]
    q = analyze(bungalow)["quality"]
    assert q["level"] == "nicht_auswertbar"
    assert any("senkrechten" in r for r in q["reasons"]) and q["tips"]


def test_falsch_gelesene_zahl_passt_nicht_zur_zeichnung(bungalow):
    # Wanddicke 24 als 174 gelesen: keine zweite Kette kontrolliert sie, aber die Zeichnung verrät den Fehler
    conflicts_before = analyze(bungalow)["stats"]["conflicts"]
    chain(bungalow, "garage1-tiefe").values[0] = 174
    r = analyze(bungalow)
    assert r["stats"]["conflicts"] == conflicts_before
    issue = next(i for i in r["issues"] if i["id"] == "mass-gegen-zeichnung")
    assert "174" in issue["detail"] and issue["measure"]


DEMO = Path(__file__).resolve().parents[2] / "api" / "demo"


@pytest.mark.parametrize("shift", [30, -45, 60])
def test_verschaetzte_ki_linien_werden_ausgerichtet(bungalow, shift):
    from planpause_engine.lines_cv import snap_lines
    gray = cv2.imread(str(DEMO / "bungalow.jpg"), cv2.IMREAD_GRAYSCALE)
    orig = {l.id: l.px for l in bungalow.axes["x"]}
    for l in bungalow.axes["x"]:
        l.px += shift
    st = snap_lines(bungalow, gray)
    assert abs(st["aligned"]["x"] + shift) <= 15
    err = sorted(abs(l.px - orig[l.id]) for l in bungalow.axes["x"])
    assert err[len(err) // 2] <= 12  # Median vorher 30–60 px, danach höchstens 0,6 % der Bildbreite


def test_genaue_linien_werden_nicht_verschoben(bungalow, darmstaedter):
    from planpause_engine.lines_cv import snap_lines
    for plan, name in ((bungalow, "bungalow"), (darmstaedter, "darmstaedter14")):
        st = snap_lines(plan, cv2.imread(str(DEMO / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE))
        assert st["aligned"] == {}


def test_lineal_um_bild_und_ausschnitte():
    from planpause_engine.preprocess import RULER_MARGIN, with_ruler
    img = np.full((300, 400), 255, np.uint8)
    out = with_ruler(img, 0, 0, 1.0)
    assert out.shape == (300 + 2 * RULER_MARGIN, 400 + 2 * RULER_MARGIN)
    assert (out[RULER_MARGIN:-RULER_MARGIN, RULER_MARGIN:-RULER_MARGIN] == img).all()  # Bild selbst unverändert
    assert out[:RULER_MARGIN].min() == 0  # Striche und Zahlen im Rand


def test_kostenberechnung():
    from planpause_engine.extract import usage_cost
    assert usage_cost("claude-opus-5-5", {"input_tokens": 13079, "output_tokens": 12991}) == pytest.approx(0.312, abs=0.001)
    assert usage_cost("claude-opus-5-5", {"input_tokens": 13000, "output_tokens": 64000}) == pytest.approx(1.332, abs=0.001)
