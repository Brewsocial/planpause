"""KI-Extraktion mit Claude: Topologie und Maßzahlen lesen, keine Koordinaten raten.

Ablauf
  1. entzerrtes Gesamtbild + vier vergrößerte Ausschnitte an Claude
  2. Antwort über ein Werkzeug mit festem JSON-Schema (PlanModel)
  3. Prüfung auf fehlende Linienverweise; bei Fehlern eine Korrekturrunde
  4. Pixelpositionen auf erkannte Wandkanten einrasten (lines_cv)
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from pydantic import ValidationError

from .lines_cv import snap_lines
from .model import PlanModel
from .preprocess import Prepared

DEFAULT_MODEL = os.environ.get("PLANPAUSE_MODEL", "claude-opus-5-5")
TOOL_NAME = "planmodell_speichern"
# Gründlichkeit und Denkbudget. "high" erkennt deutlich mehr als "medium" (Bungalow-Foto: Wände 100 % statt 73 %,
# Maßzahlen 95 % statt 85 %, siehe eval_extract.py) bei etwa doppelten Kosten. Das Budget hält das Modell davon ab,
# ins max_tokens-Limit zu laufen (abgebrochene Läufe kosten trotzdem). max_tokens bleibt als harte Obergrenze.
EFFORT = os.environ.get("PLANPAUSE_EFFORT", "high")
TASK_BUDGET = int(os.environ.get("PLANPAUSE_TASK_BUDGET", "80000"))
# Zweiter Durchgang: KI prüft den erkannten Plan auf einem Kontrollbild und ergänzt Fehlendes (review.py)
OVERVIEW_SIDE = 3000  # Gesamtbild höchstens so groß schicken; Details kommen über die Ausschnitte
REVIEW = os.environ.get("PLANPAUSE_REVIEW", "1") == "1"  # Bensheim-EG: ergänzte eine fehlende Tür für 0,12 $
# US-Dollar pro Million Tokens (Eingabe, Ausgabe); für die Kostenanzeige
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-fable-5-1": (10.0, 50.0)}


def usage_cost(model: str, usage: dict) -> float:
    """Kosten eines API-Aufrufs in US-Dollar (Cache-Schreiben 1,25×, Cache-Lesen 0,05× Eingabepreis)."""
    pin, pout = PRICES.get(model, PRICES["claude-opus-5-5"])
    tokens_in = (usage.get("input_tokens") or 0) + 1.25 * (usage.get("cache_creation_input_tokens") or 0) \
        + 0.05 * (usage.get("cache_read_input_tokens") or 0)
    return round((tokens_in * pin + (usage.get("output_tokens") or 0) * pout) / 1e6, 4)

INSTRUCTIONS = """Du bist Architekt für Bestandsaufnahmen und überträgst einen Bestandsgrundriss (oft handgezeichnet) in ein Rastermodell.
Du rechnest NICHTS aus und korrigierst keine Maßzahlen. Du beschreibst, was im Plan steht. Die Lage jeder Wand berechnet anschließend ein Programm aus den Maßzahlen.

VOLLSTÄNDIGKEIT GEHT VOR: Erfasse ALLE Wände, Türen, Fenster und Räume, die im Bild zu sehen sind, auch kurze Innenwände
(Bad, WC, Dusche, Flur, Abstellraum, Küche) und auch dort, wo kein Maß steht oder die Maße unleserlich sind. Für solche
Bauteile genügt die Pixellage (px) ihrer Linien; das Programm kennzeichnet sie automatisch als „nur nach Zeichnung“.
Ein fehlendes Bauteil ist schlimmer als eines mit ungenauer Lage.

## Das Rastermodell
- Jede senkrechte Kante im Plan (Wandseite, Laibung, Gebäudeecke) liegt auf einer x-Linie, jede waagerechte auf einer y-Linie.
- Liegen mehrere Bauteile auf derselben Flucht (z. B. Innenseite der Außenwand und Kante einer Trennwand), benutzen sie DIESELBE Linie. Das ist entscheidend: nur so werden Maße aus verschiedenen Ketten miteinander verknüpft.
- Gib jeder Linie eine sprechende ID (z. B. "x_aussen_links", "x_bad_innen_rechts", "y_kueche_unten") und ein kurzes label ("Außenkante links").
- px ist die Lage der Linie in Bild 1 in Pixeln (x-Linien: waagerechter Pixel, y-Linien: senkrechter Pixel). Lies px am Lineal ab, nicht geschätzt: suche die Kante, gehe senkrecht bzw. waagerecht zum Lineal und interpoliere zwischen den Strichen. Am genauesten geht das in den vergrößerten Ausschnitten.

## Maßketten
- Erfasse JEDE Maßkette einzeln, in Leserichtung links→rechts bzw. oben→unten.
- values in Zentimetern genau wie geschrieben. Pläne in Metern umrechnen (2.77 → 277). Hochgestellte 5 bedeutet halbe Zentimeter: 2.52⁵ → 252.5, 88⁵ → 88.5. Kleine Zahlen ohne Punkt in Meter-Plänen sind Zentimeter (24 → 24).
- lines hat genau einen Eintrag mehr als values: die Linie jedes Teilstrichs. Ordne jeden Teilstrich der Bauteilkante zu, auf die er zeigt. Zeigt er auf keine Kante, lege eine eigene Linie an.
- NICHT korrigieren, auch wenn die Summe nicht aufgeht. Schwer lesbare Werte: Index in uncertain eintragen.
- total nur, wenn ein Gesamtmaß über genau dieser Strecke steht.
- Fensterangaben wie "1.50/1.25" bedeuten Breite/Höhe: nur die Breite gehört in die Kette, die Höhe in height_stated der Öffnung.

## Bauteile
- walls: Rechtecke aus vier Linien (x0 < x1, y0 < y1). kind: aussen, innen oder brand (wenn "Brandwand" dransteht). Öffnungen sind Lücken zwischen Wandrechtecken.
  Jede im Bild gezeichnete Wand gehört hinein, jede Innenwand einzeln. Grenzen zwei Baukörper aneinander (z. B. Garage, Anbau),
  haben sie meist je eine eigene Wand; eine kleine Zahl wie „2“ zwischen zwei Maßketten ist dann die Fuge zwischen den beiden Wänden.
- openings: Fenster (window), Türen (door), Tore (gate), Durchgänge (passage) als Rechteck über die Wanddicke.
  Türen: hinge = Bandseite ("start" = kleinere Koordinate der Öffnung, "end" = größere), swing = Richtung, in die die Tür aufschlägt ("pos" = +x bzw. +y, "neg" = -x bzw. -y; y wächst nach unten).
  width_stated/height_stated/sill_stated aus Angaben wie "88⁵/2.08" oder "BR 87⁵" in cm.
- features: Treppe (mit treads = Anzahl Stufen), Schornstein, Schacht, Stütze, Einbau.
- rooms: Name, area_stated in m² (das Zeichen # oder qm hinter Zahlen steht für m²), poly als Ecken der Innenkontur [x-Linie, y-Linie] im Uhrzeigersinn.
  Gib für jeden Raum den Umriss an, der sich aus den umgebenden Wänden ergibt (auch wenn diese Wände nur nach Zeichnung liegen). poly nur leer lassen, wenn der Raum im Bild wirklich keine erkennbare Begrenzung hat.
- zones: Terrassen, Balkone und ähnliche Flächen außerhalb der Wände.

## Fachliche Prüfung
- ai_issues: nur, was ein Programm NICHT aus den Zahlen nachrechnen kann: unleserliche Stellen, vermutlich tragende Wände, Brandwände, Schornsteine, Schächte, fehlende Höhen, Treppen ohne Steigungsmaß, Flächenberechnung nach alter Norm, Barrierefreiheit. at = [x-Linie, y-Linie] in der Nähe, falls sinnvoll. Kurz und sachlich, auf Deutsch.
- questions: 2 bis 6 Rückfragen, die nur der Eigentümer vor Ort beantworten kann (nicht: Raumhöhe, Baujahr, Wand- und Deckenmaterial, tragende Wände; die stellt die Anwendung selbst).
- summary: zwei Sätze zur Qualität und Lesbarkeit des Plans.

Antworte ausschließlich, indem du das Werkzeug planmodell_speichern genau einmal mit dem vollständigen Modell aufrufst. Schreibe keinen Text außerhalb des Werkzeugaufrufs."""
NUDGE = "Bitte speichere das vollständige Rastermodell jetzt mit dem Werkzeug planmodell_speichern."


def _schema() -> dict:
    s = PlanModel.model_json_schema()
    for k in ("measurements", "version", "image_size"):
        s.get("properties", {}).pop(k, None)
    return s


def _img(data: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(data).decode()}}


def build_messages(prep: Prepared, notes: str = "") -> list[dict]:
    w, h = prep.size
    content: list[dict] = [{"type": "text", "text": (f"Bild 1: ganzer Plan, {w} × {h} Pixel. Alle px-Angaben beziehen sich auf dieses Bild. "
                                                     "Am Rand ist ein Lineal mit Pixelkoordinaten (Striche alle 50 px, Zahlen alle 100 px); "
                                                     "der weiße Rand gehört nicht zum Bild.")},
                           _img(prep.jpeg(max_side=min(max(w, h), OVERVIEW_SIDE), ruler=True))]
    for n, (name, data, (ox, oy)) in enumerate(prep.tiles(ruler=True), start=2):
        content += [{"type": "text", "text": (f"Bild {n}: vergrößerter Ausschnitt {name}. Sein Lineal zeigt die Pixelkoordinaten von Bild 1, "
                                              "daran lassen sich px-Werte genau ablesen.")},
                    _img(data)]
    text = INSTRUCTIONS + (f"\n\nHinweise des Nutzers: {notes}" if notes else "")
    content.append({"type": "text", "text": text})
    return [{"role": "user", "content": content}]


def _parse(tool_input: dict[str, Any], size: tuple[int, int]) -> tuple[PlanModel | None, list[str]]:
    try:
        plan = PlanModel.model_validate({**tool_input, "image_size": list(size)})
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:30]]
    return plan, plan.validate_refs()


class ExtractionError(ValueError):
    """Verständliche Fehlermeldung plus Protokoll der bisherigen Runden (Tokenverbrauch) zur Fehlersuche."""

    def __init__(self, message: str, log: dict):
        super().__init__(message)
        self.log = log


def extract_plan(prep: Prepared, notes: str = "", client=None, model: str | None = None, max_tokens: int = 128000,
                 review: bool | None = None) -> tuple[PlanModel, dict]:
    """Ruft Claude auf und liefert ein geprüftes PlanModel (Pixel bereits eingerastet)."""
    import anthropic  # erst hier, damit Engine-Tests ohne SDK laufen

    client = client or anthropic.Anthropic()
    model = model or DEFAULT_MODEL
    tool = {"name": TOOL_NAME, "description": "Speichert das Rastermodell des Grundrisses.", "input_schema": _schema()}
    messages = build_messages(prep, notes)
    log: dict = {"model": model, "effort": EFFORT, "task_budget": TASK_BUDGET, "review": REVIEW if review is None else review,
                 "rounds": [], "cost_usd": 0.0}
    # gemeinsam für beide Durchgänge
    request = dict(thinking={"type": "adaptive"},
                   output_config={"effort": EFFORT, "task_budget": {"type": "tokens", "total": TASK_BUDGET}},
                   betas=["server-side-fallback-2026-07-01", "task-budgets-2026-03-13"], fallbacks="default")
    plan = None
    nudged = False

    def record(msg, errors: list[str]) -> None:
        usage = msg.usage.model_dump()
        log["rounds"].append({"stop": msg.stop_reason, "errors": errors, "usage": usage, "cost_usd": usage_cost(model, usage)})
        log["cost_usd"] = round(sum(r["cost_usd"] for r in log["rounds"]), 4)

    for round_ in range(3):
        # Erzwungene Werkzeugwahl gibt es bei aktuellen Modellen nicht mehr: "auto" + Anweisung im Prompt.
        # fallbacks: lehnt das Modell fälschlich ab, übernimmt serverseitig ein Ersatzmodell.
        with client.beta.messages.stream(
            model=model, max_tokens=max_tokens, tools=[tool], messages=messages,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True}, **request,
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason in ("refusal", "max_tokens"):
            record(msg, [])
            raise ExtractionError("Die KI hat die Auswertung dieses Bildes abgelehnt." if msg.stop_reason == "refusal" else
                                  "Die KI-Antwort war zu lang und wurde abgeschnitten. Bitte den Plan in Teilen hochladen.", log)
        use = next((b for b in msg.content if b.type == "tool_use"), None)
        if use is None:  # nur Text geantwortet: einmal nachfordern
            record(msg, ["kein Werkzeugaufruf"])
            if nudged:
                break
            nudged = True
            messages += [{"role": "assistant", "content": msg.content}, {"role": "user", "content": NUDGE}]
            continue
        plan, errors = _parse(use.input, prep.size)
        record(msg, errors)
        if plan and not errors:
            break
        if sum(1 for r in log["rounds"] if r["errors"] != ["kein Werkzeugaufruf"]) >= 2:
            break  # eine Korrekturrunde reicht; Reste entfernt drop_broken
        messages += [{"role": "assistant", "content": msg.content},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use.id, "is_error": True,
                                                   "content": "Bitte korrigieren und vollständig neu speichern:\n" + "\n".join(errors)}]}]
    if plan is None:
        raise ExtractionError("Die KI-Antwort ließ sich nicht in ein Planmodell übertragen.", log)
    if plan.validate_refs():
        plan = drop_broken(plan)
    log["px_raw"] = {ax: {l.id: l.px for l in plan.axes[ax]} for ax in ("x", "y")}  # vor dem Einrasten, zur Fehlersuche
    log["snapped"] = snap_lines(plan, prep.image)
    if log["review"]:
        from .review import review_plan
        try:
            plan, rlog = review_plan(prep, plan, client, model, max_tokens, request)
        except Exception as e:  # noqa: BLE001 – der Check ist eine Verbesserung, kein Muss
            rlog = {"result": f"Fehler im Vollständigkeits-Check: {str(e)[:200]}", "usage": {}}
        rlog["cost_usd"] = usage_cost(model, rlog.get("usage") or {})
        log["review_round"] = rlog
        log["cost_usd"] = round(log["cost_usd"] + rlog["cost_usd"], 4)
    return plan, log


def drop_broken(plan: PlanModel) -> PlanModel:
    """Entfernt Elemente mit unbekannten Linien, statt den ganzen Plan zu verwerfen."""
    xs, ys = plan.line_ids("x"), plan.line_ids("y")
    ok = lambda r: r.x0 in xs and r.x1 in xs and r.y0 in ys and r.y1 in ys  # noqa: E731
    plan.walls = [w for w in plan.walls if ok(w)]
    plan.openings = [o for o in plan.openings if ok(o)]
    plan.features = [f for f in plan.features if ok(f)]
    plan.chains = [c for c in plan.chains if all(l in (xs if c.axis == "x" else ys) for l in c.lines)]
    for r in plan.rooms:
        if any(a not in xs or b not in ys for a, b in r.poly):
            r.poly = []
    plan.zones = [z for z in plan.zones if all(a in xs and b in ys for a, b in z.poly)]
    return plan


def dump_request(prep: Prepared, notes: str = "") -> str:
    """Für Fehlersuche: Anfrage ohne Bilddaten als JSON."""
    msgs = build_messages(prep, notes)
    for c in msgs[0]["content"]:
        if c["type"] == "image":
            c["source"]["data"] = f"<{len(c['source']['data'])} Zeichen>"
    return json.dumps({"messages": msgs, "tool_schema": _schema()}, ensure_ascii=False, indent=1)
