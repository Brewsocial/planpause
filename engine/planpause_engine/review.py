"""Vollständigkeits-Check: zweiter KI-Durchgang über ein Kontrollbild.

Ein großes Planmodell in einem Zug vollständig zu beschreiben, gelingt der KI bei kleinteiligen Plänen
nicht immer: kurze Innenwände, einzelne Fenster oder Türen fehlen. Fehlendes auf einem Bild zu finden
ist dagegen leicht. Deshalb wird der erkannte Plan farbig über das Foto gezeichnet, und die KI liefert
nur Ergänzungen, die auf vorhandene Linien verweisen (oder neue Linien mit Pixellage anlegen).
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field, ValidationError

from .lines_cv import snap_lines
from .model import Axis, AxisLine, Feature, Opening, PlanModel, Wall
from .preprocess import Prepared, with_ruler

TOOL = "ergaenzungen_speichern"


class Additions(BaseModel):
    new_lines: dict[Axis, list[AxisLine]] = Field(default_factory=lambda: {"x": [], "y": []},
                                                 description="Neue Linien, nur falls keine vorhandene Linie passt (mit px aus Bild 1)")
    walls: list[Wall] = Field(default_factory=list, description="Fehlende Wände")
    openings: list[Opening] = Field(default_factory=list, description="Fehlende Fenster, Türen, Tore, Durchgänge")
    features: list[Feature] = Field(default_factory=list, description="Fehlende Treppen, Schornsteine, Schächte, Stützen")
    notes: str = Field("", description="Kurz: was ergänzt wurde oder warum nichts fehlt")


PROMPT = """Bild 1 zeigt das Foto eines Grundrisses. Darüber ist eingezeichnet, was bisher erfasst wurde:
rot = Wände, blau = Fenster, grün = Türen, violett = Tore und Durchgänge, grau = Treppen und Bauteile.
Bild 2 ist dasselbe Foto ohne Einzeichnungen. Beide haben ein Lineal mit Pixelkoordinaten am Rand.

Aufgabe: Finde alles, was im Foto zu sehen ist, aber NICHT eingezeichnet wurde:
- Wände, besonders kurze Innenwände, Wandvorsprünge, Schornsteine und Wände zwischen kleinen Räumen (Bad, WC, Flur, Abstellraum)
- Fenster (in der Zeichnung meist dünne Doppellinien in der Außenwand) und Türen (Aufschlagbogen)
- Treppen, Schächte, Stützen

Regeln:
- Verwende vorhandene Linien (Liste unten), wo immer eine Kante darauf liegt. Neue Linien nur, wenn keine passt; dann mit px am Lineal ablesen.
- Wände und Öffnungen sind Rechtecke aus vier Linien (x0 < x1, y0 < y1). Öffnungen liegen in der Wanddicke.
- Nichts doppelt eintragen und Eingezeichnetes nicht verändern. Wenn nichts fehlt, leere Listen zurückgeben.
- Antworte ausschließlich mit einem Aufruf des Werkzeugs ergaenzungen_speichern."""

COLORS = {"wall": (40, 40, 220), "window": (220, 120, 0), "door": (30, 160, 40), "gate": (170, 60, 170),
          "passage": (170, 60, 170), "feature": (120, 120, 120)}


def render_overlay(prep: Prepared, plan: PlanModel) -> bytes:
    """Foto blass, erkannter Plan farbig darüber, mit Pixel-Lineal."""
    base = cv2.cvtColor(prep.image, cv2.COLOR_GRAY2BGR)
    base = cv2.addWeighted(base, 0.55, np.full_like(base, 255), 0.45, 0)
    px = {ax: {l.id: l.px for l in plan.axes[ax] if l.px is not None} for ax in ("x", "y")}

    def box(r):
        try:
            x0, x1 = sorted((px["x"][r.x0], px["x"][r.x1]))
            y0, y1 = sorted((px["y"][r.y0], px["y"][r.y1]))
        except KeyError:
            return None
        return int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))

    fill = base.copy()
    items = [(w, "wall") for w in plan.walls] + [(o, o.type) for o in plan.openings] + [(f, "feature") for f in plan.features]
    for r, kind in items:
        b = box(r)
        if b:
            cv2.rectangle(fill, b[:2], b[2:], COLORS[kind], -1)
    out = cv2.addWeighted(fill, 0.45, base, 0.55, 0)
    for r, kind in items:
        b = box(r)
        if b:
            cv2.rectangle(out, b[:2], b[2:], COLORS[kind], 2)
    k = min(1.0, 3000 / max(out.shape[:2]))  # große Bilder (PDF) verkleinern, Lineal bleibt in Originalkoordinaten
    if k < 1:
        out = cv2.resize(out, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    # with_ruler arbeitet auf einem Kanal; je Farbkanal anwenden, damit die Farben erhalten bleiben
    img = cv2.merge([with_ruler(np.ascontiguousarray(out[:, :, c]), 0, 0, k) for c in range(3)])
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    assert ok
    return buf.tobytes()


def _lines_text(plan: PlanModel) -> str:
    rows = [f"{ax} {l.id} px={round(l.px) if l.px is not None else '?'} {l.label}".rstrip()
            for ax in ("x", "y") for l in plan.axes[ax]]
    return "Vorhandene Linien (Achse, ID, Pixellage, Bezeichnung):\n" + "\n".join(rows)


def merge(plan: PlanModel, add: Additions) -> tuple[PlanModel, dict[str, int]]:
    """Ergänzungen übernehmen; Elemente mit unbekannten Linien werden verworfen."""
    p = plan.model_copy(deep=True)
    for ax in ("x", "y"):
        have = {l.id for l in p.axes[ax]}
        p.axes[ax] += [l for l in add.new_lines.get(ax, []) if l.id not in have]
    xs, ys = p.line_ids("x"), p.line_ids("y")
    ok = lambda r: r.x0 in xs and r.x1 in xs and r.y0 in ys and r.y1 in ys  # noqa: E731
    walls = [w for w in add.walls if ok(w)]
    openings = [o for o in add.openings if ok(o)]
    features = [f for f in add.features if ok(f)]
    p.walls += walls
    p.openings += openings
    p.features += features
    return p, {"linien": sum(len(v) for v in add.new_lines.values()), "waende": len(walls), "oeffnungen": len(openings),
               "bauteile": len(features), "verworfen": len(add.walls) + len(add.openings) + len(add.features)
               - len(walls) - len(openings) - len(features)}


def review_plan(prep: Prepared, plan: PlanModel, client, model: str, max_tokens: int, request: dict[str, Any]) -> tuple[PlanModel, dict]:
    """Zweiter Durchgang. request: gemeinsame Parameter (thinking, output_config, betas, fallbacks) wie im ersten."""
    from .extract import _img  # gleiche Bildkodierung wie der erste Durchgang

    tool = {"name": TOOL, "description": "Speichert fehlende Wände, Öffnungen und Bauteile.", "input_schema": Additions.model_json_schema()}
    content = [{"type": "text", "text": "Bild 1: erfasster Plan farbig über dem Foto."}, _img(render_overlay(prep, plan)),
               {"type": "text", "text": "Bild 2: dasselbe Foto ohne Einzeichnungen."},
               _img(prep.jpeg(max_side=min(max(prep.size), 3000), ruler=True)),
               {"type": "text", "text": PROMPT + "\n\n" + _lines_text(plan)}]
    with client.beta.messages.stream(model=model, max_tokens=max_tokens, tools=[tool],
                                     messages=[{"role": "user", "content": content}],
                                     tool_choice={"type": "auto", "disable_parallel_tool_use": True}, **request) as stream:
        msg = stream.get_final_message()
    usage = msg.usage.model_dump()
    log: dict = {"stop": msg.stop_reason, "usage": usage}
    use = next((b for b in msg.content if b.type == "tool_use"), None)
    if use is None or msg.stop_reason in ("refusal", "max_tokens"):
        log["result"] = "keine Ergänzungen übernommen"
        return plan, log
    try:
        add = Additions.model_validate(use.input)
    except ValidationError as e:
        log["result"] = f"ungültig: {e.errors()[:3]}"
        return plan, log
    merged, counts = merge(plan, add)
    snap_lines(merged, prep.image)
    log.update(added=counts, notes=add.notes)
    return merged, log


def dump_overlay(prep: Prepared, plan: PlanModel, path: str) -> None:
    """Zur Fehlersuche: Kontrollbild speichern."""
    with open(path, "wb") as f:
        f.write(render_overlay(prep, plan))

