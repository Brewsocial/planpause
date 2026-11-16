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

from .model import Axis, AxisLine, Feature, Fixture, Opening, PlanModel, Wall
from .preprocess import Prepared, with_ruler
from .walls_cv import coverage, open_gaps, plan_scale, snap_to_walls, wall_mask

TOOL = "ergaenzungen_speichern"


class Additions(BaseModel):
    new_lines: dict[Axis, list[AxisLine]] = Field(default_factory=lambda: {"x": [], "y": []},
                                                 description="Neue Linien, nur falls keine vorhandene Linie passt (mit px aus Bild 1)")
    walls: list[Wall] = Field(default_factory=list, description="Fehlende Wände")
    openings: list[Opening] = Field(default_factory=list, description="Fehlende Fenster, Türen, Tore, Durchgänge")
    features: list[Feature] = Field(default_factory=list, description="Fehlende Treppen, Schornsteine, Schächte, Stützen")
    fixtures: list[Fixture] = Field(default_factory=list, description="Fehlende Sanitär- und Küchenobjekte (Umriss in Pixeln)")
    remove_walls: list[int] = Field(default_factory=list, description="Nummern (W…) eingetragener Wände, die es im Plan nicht gibt")
    notes: str = Field("", description="Kurz: was ergänzt wurde oder warum nichts fehlt")


PROMPT = """Bild 1 zeigt das Foto eines Grundrisses. Darüber ist eingezeichnet, was bisher erfasst wurde:
rot = Wände, blau = Fenster, grün = Türen, violett = Tore und Durchgänge, grau = Treppen und Bauteile.
Bild 2 ist dasselbe Foto ohne Einzeichnungen. Beide haben ein Lineal mit Pixelkoordinaten am Rand.

Aufgabe: Finde alles, was im Foto zu sehen ist, aber NICHT eingezeichnet wurde:
- Wände, besonders kurze Innenwände, Wandvorsprünge, Schornsteine und Wände zwischen kleinen Räumen (Bad, WC, Flur, Abstellraum)
- Fenster (in der Zeichnung meist dünne Doppellinien in der Außenwand) und Türen (Aufschlagbogen)
- Treppen, Schächte, Stützen

- Badewannen, Duschen, WCs, Waschbecken, Küchenzeilen, Spülen und Herde (fixtures, Umriss direkt in Pixeln), falls noch keine eingetragen sind

Unten stehen Hinweise aus der Bildverarbeitung. Sie sind Kandidaten, keine Tatsachen: prüfe jeden im Bild.
- „Wandfläche ohne Eintrag“: dort ist im Bild etwas Wandartiges gezeichnet, das im Modell fehlt. Ist es eine Wand, trage sie ein;
  die Pixelangaben sind genau gemessen, übernimm sie für neue Linien. Treppenstufen, Möbel, Text und Maßlinien sind keine Wände.
- „Lücke ohne Öffnung“: zwischen zwei fluchtenden Wänden fehlt ein Eintrag. Das ist eine Tür (door), ein offener Durchgang (passage)
  oder ein Fenster (window); ist dort in Wirklichkeit Wand gezeichnet, trage stattdessen die Wand ein.
- „Wand ohne Zeichnung“: an der Stelle einer eingetragenen Wand ist im Bild fast nichts gezeichnet. Gibt es sie nicht
  (z. B. gestrichelte Linie, Maßlinie, Möbelkante), nenne ihre Nummer in remove_walls.

Regeln:
- Verwende vorhandene Linien (Liste unten), wo immer eine Kante darauf liegt (bis etwa 6 px Abstand). Neue Linien nur, wenn keine passt.
- Wände und Öffnungen sind Rechtecke aus vier Linien (x0 < x1, y0 < y1). Öffnungen liegen in der Wanddicke.
- Nichts doppelt eintragen. Wenn nichts fehlt, leere Listen zurückgeben.
- Antworte ausschließlich mit einem Aufruf des Werkzeugs ergaenzungen_speichern."""

COLORS = {"wall": (40, 40, 220), "window": (220, 120, 0), "door": (30, 160, 40), "gate": (170, 60, 170),
          "passage": (170, 60, 170), "feature": (120, 120, 120)}


def render_overlay(prep: Prepared, plan: PlanModel) -> bytes:
    """Foto blass, erkannter Plan farbig darüber, mit Pixel-Lineal."""
    return _encode(_overlay(prep, plan), 0, 0, 3000)


def _encode(bgr: np.ndarray, x0: int, y0: int, max_side: int) -> bytes:
    k = min(1.0, max_side / max(bgr.shape[:2]))  # große Bilder verkleinern, Lineal bleibt in Originalkoordinaten
    if k < 1:
        bgr = cv2.resize(bgr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    # with_ruler arbeitet auf einem Kanal; je Farbkanal anwenden, damit die Farben erhalten bleiben
    img = cv2.merge([with_ruler(np.ascontiguousarray(bgr[:, :, c]), x0, y0, k) for c in range(3)])
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    assert ok
    return buf.tobytes()


def overlay_tiles(prep: Prepared, plan: PlanModel, cell: int = 2200, max_tiles: int = 9, overlap: float = 0.12) -> list[tuple[str, bytes]]:
    """Kontrollbild in vergrößerten Ausschnitten, damit dünne Wände und Türen bei großen Plänen erkennbar bleiben.
    Leer bei kleinen Bildern: dort reicht das Gesamtbild."""
    h, w = prep.image.shape[:2]
    if max(h, w) <= 3200:
        return []
    img = _overlay(prep, plan)
    cols, rows = max(2, -(-w // cell)), max(2, -(-h // cell))
    while cols * rows > max_tiles:
        cols, rows = (cols - 1, rows) if cols >= rows else (cols, rows - 1)
    tw, th = min(w, int(w / cols * (1 + 2 * overlap))), min(h, int(h / rows * (1 + 2 * overlap)))
    out = []
    for r in range(rows):
        for c in range(cols):
            x, y = round(c * (w - tw) / max(cols - 1, 1)), round(r * (h - th) / max(rows - 1, 1))
            out.append((f"Zeile {r + 1}, Spalte {c + 1}", _encode(img[y:y + th, x:x + tw], x, y, 1600)))
    return out


def _overlay(prep: Prepared, plan: PlanModel) -> np.ndarray:
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
    for fx in plan.fixtures:
        x0, y0, x1, y1 = (int(round(v)) for v in fx.box)
        cv2.rectangle(out, (x0, y0), (x1, y1), (160, 150, 0), 2)
    return out


def _walls_text(plan: PlanModel) -> str:
    px = {ax: {l.id: l.px for l in plan.axes[ax] if l.px is not None} for ax in ("x", "y")}
    rows = []
    for i, w in enumerate(plan.walls):
        try:
            rows.append(f"W{i}: x {round(px['x'][w.x0])}–{round(px['x'][w.x1])}, y {round(px['y'][w.y0])}–{round(px['y'][w.y1])}")
        except KeyError:
            continue
    return "Eingetragene Wände (Nummer, Pixel):\n" + "\n".join(rows)


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
    drop = {i for i in add.remove_walls if 0 <= i < len(p.walls)}
    p.walls = [w for i, w in enumerate(p.walls) if i not in drop]
    h, wd = (plan.image_size[1], plan.image_size[0]) if plan.image_size else (10**9, 10**9)
    fixtures = [f for f in add.fixtures if 0 <= f.box[0] < f.box[2] <= wd and 0 <= f.box[1] < f.box[3] <= h]
    p.fixtures += fixtures
    walls = [w for w in add.walls if ok(w)]
    openings = [o for o in add.openings if ok(o)]
    features = [f for f in add.features if ok(f)]
    p.walls += walls
    p.openings += openings
    p.features += features
    counts = {"linien": sum(len(v) for v in add.new_lines.values()), "waende": len(walls), "oeffnungen": len(openings),
              "bauteile": len(features), "verworfen": len(add.walls) + len(add.openings) + len(add.features)
              - len(walls) - len(openings) - len(features)}
    if drop:
        counts["entfernt"] = len(drop)
    if fixtures:
        counts["einrichtung"] = len(fixtures)
    return p, counts


def cv_hints(prep: Prepared, plan: PlanModel) -> tuple[str, dict]:
    """Hinweise der Bildverarbeitung für die Kontrollrunde als Text, dazu die Zahlen fürs Protokoll."""
    scale = plan_scale(plan)
    if not scale:
        return "", {}
    mask, f = wall_mask(prep.image, scale)
    if not mask.any():
        return "", {}
    cov = coverage(plan, mask, f, scale)
    gaps = open_gaps(plan, scale)
    px = {ax: {l.id: l.px for l in plan.axes[ax] if l.px is not None} for ax in ("x", "y")}
    rows = []
    if cov["missing"]:
        rows.append("Wandfläche ohne Eintrag (Pixel; in Klammern Größe in cm):")
        rows += [f"- x {b[0]}–{b[2]}, y {b[1]}–{b[3]} ({round((b[2] - b[0]) / scale)} × {round((b[3] - b[1]) / scale)})" for b in cov["missing"]]
    if gaps:
        rows.append("Lücke ohne Öffnung (zwischen den Wänden W… und W…, Pixel, Breite):")
        rows += [f"- W{g['walls'][0]} / W{g['walls'][1]}: x {g['box'][0]}–{g['box'][2]}, y {g['box'][1]}–{g['box'][3]}, {g['width_cm']} cm" for g in gaps[:25]]
    if cov["unsupported"]:
        rows.append("Wand ohne Zeichnung:")
        for i in cov["unsupported"]:
            w = plan.walls[i]
            rows.append(f"- W{i}: x {round(px['x'][w.x0])}–{round(px['x'][w.x1])}, y {round(px['y'][w.y0])}–{round(px['y'][w.y1])}")
    stats = {"gedeckt": cov["share"], "fehlend": len(cov["missing"]), "luecken": len(gaps), "ohne_zeichnung": len(cov["unsupported"])}
    return ("Hinweise der Bildverarbeitung:\n" + "\n".join(rows)) if rows else "", stats


def review_plan(prep: Prepared, plan: PlanModel, client, model: str, max_tokens: int, request: dict[str, Any]) -> tuple[PlanModel, dict]:
    """Zweiter Durchgang. request: gemeinsame Parameter (thinking, output_config, betas, fallbacks) wie im ersten."""
    from .extract import _img  # gleiche Bildkodierung wie der erste Durchgang

    tool = {"name": TOOL, "description": "Speichert fehlende Wände, Öffnungen und Bauteile.", "input_schema": Additions.model_json_schema()}
    hints, cv_stats = cv_hints(prep, plan)
    content = [{"type": "text", "text": "Bild 1: erfasster Plan farbig über dem Foto."}, _img(render_overlay(prep, plan)),
               {"type": "text", "text": "Bild 2: dasselbe Foto ohne Einzeichnungen."},
               _img(prep.jpeg(max_side=min(max(prep.size), 3000), ruler=True))]
    for n, (name, data) in enumerate(overlay_tiles(prep, plan), start=3):
        content += [{"type": "text", "text": f"Bild {n}: Bild 1 vergrößert, Ausschnitt {name}. Lineal in Pixeln von Bild 1."}, _img(data)]
    content.append({"type": "text", "text": PROMPT + "\n\n" + _lines_text(plan) + "\n\n" + _walls_text(plan)
                    + ("\n\n" + hints if hints else "")})
    with client.beta.messages.stream(model=model, max_tokens=max_tokens, tools=[tool],
                                     messages=[{"role": "user", "content": content}],
                                     tool_choice={"type": "auto", "disable_parallel_tool_use": True}, **request) as stream:
        msg = stream.get_final_message()
    usage = msg.usage.model_dump()
    log: dict = {"stop": msg.stop_reason, "usage": usage, "cv": cv_stats}
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
    snap_to_walls(merged, prep.image)
    log.update(added=counts, notes=add.notes)
    return merged, log


def dump_overlay(prep: Prepared, plan: PlanModel, path: str) -> None:
    """Zur Fehlersuche: Kontrollbild speichern."""
    with open(path, "wb") as f:
        f.write(render_overlay(prep, plan))

