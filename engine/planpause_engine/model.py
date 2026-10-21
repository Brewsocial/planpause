"""Planmodell: Topologie statt Koordinaten.

Ein Bestandsgrundriss mit achsparallelen Wänden lässt sich vollständig über zwei
Mengen von Rasterlinien beschreiben: senkrechte Linien (Achse "x") und waagerechte
Linien (Achse "y"). Jede Wandkante, Laibung und Raumgrenze liegt auf einer solchen
Linie. Maßketten sind Folgen von Abständen zwischen aufeinanderfolgenden Linien.

Die KI-Extraktion liefert nur
  * welche Linien es gibt (mit ungefährer Pixelposition im entzerrten Bild),
  * welche Maßzahl zwischen welchen Linien steht,
  * welche Bauteile von welchen Linien begrenzt werden.
Die Lage jeder Linie in Zentimetern berechnet ausschließlich der Solver
(siehe solver.py) aus den Maßzahlen. Pixel dienen nur als schwacher Hinweis.

Alle Längen in Zentimetern, y wächst nach unten (Bildkonvention).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Axis = Literal["x", "y"]


class AxisLine(BaseModel):
    id: str
    px: Optional[float] = Field(None, description="Ungefähre Lage im entzerrten Bild (Pixel)")
    label: str = Field("", description="Was auf dieser Linie liegt, z. B. 'Außenkante links'")


class DimChain(BaseModel):
    """Maßkette: values[i] ist der Abstand zwischen lines[i] und lines[i+1]."""

    id: str
    axis: Axis
    lines: list[str]
    values: list[float]
    total: Optional[float] = Field(None, description="Gesamtmaß laut Plan, falls angegeben")
    label: str = ""
    note: str = ""
    uncertain: list[int] = Field(default_factory=list, description="Indizes schwer lesbarer Werte")

    @field_validator("values")
    @classmethod
    def _positive(cls, v: list[float]) -> list[float]:
        if any(x <= 0 for x in v):
            raise ValueError("Maße müssen positiv sein")
        return v

    def model_post_init(self, _ctx) -> None:  # noqa: D401
        if len(self.lines) != len(self.values) + 1:
            raise ValueError(f"Kette {self.id}: {len(self.values)} Werte brauchen {len(self.values) + 1} Linien")


class Measurement(BaseModel):
    """Vor Ort gemessener Abstand zwischen zwei Linien. Hat Vorrang vor dem Plan."""

    id: str
    axis: Axis
    a: str
    b: str
    value: float
    note: str = ""


class Rect(BaseModel):
    x0: str
    x1: str
    y0: str
    y1: str


class Wall(Rect):
    kind: Literal["aussen", "innen", "brand"] = "innen"


class Opening(Rect):
    type: Literal["window", "door", "gate", "passage"]
    hinge: Optional[Literal["start", "end"]] = Field(None, description="Bandseite: Anfang oder Ende der Öffnung (kleinere/größere Koordinate)")
    swing: Optional[Literal["pos", "neg"]] = Field(None, description="Aufschlagrichtung quer zur Wand: +x/+y oder -x/-y")
    width_stated: Optional[float] = Field(None, description="Breite laut Plan in cm (bei Türen meist Rohbaurichtmaß)")
    height_stated: Optional[float] = None
    sill_stated: Optional[float] = Field(None, description="Brüstungshöhe laut Plan (BR)")


class Feature(Rect):
    type: str  # Treppe, Schornstein, Stütze, Schacht, Einbau
    note: str = ""
    treads: Optional[int] = None


class Room(BaseModel):
    name: str
    area_stated: Optional[float] = Field(None, description="Fläche laut Plan in m²")
    poly: list[tuple[str, str]] = Field(default_factory=list, description="Eckpunkte als (x-Linie, y-Linie)")
    label_at: Optional[tuple[str, str]] = None


class Zone(BaseModel):
    type: str
    poly: list[tuple[str, str]]


class AiIssue(BaseModel):
    id: str
    severity: Literal["kritisch", "pruefen", "info"] = "pruefen"
    category: str = ""
    title: str
    detail: str = ""
    action: str = ""
    at: Optional[tuple[str, str]] = None


class Question(BaseModel):
    id: str
    topic: str = ""
    question: str
    why: str = ""
    type: Literal["choice", "number", "text"] = "text"
    options: list[str] = Field(default_factory=list)
    unit: str = ""


class PlanModel(BaseModel):
    version: int = 1
    title: str = ""
    floor: str = ""
    scale_text: Optional[str] = None
    image_size: Optional[tuple[int, int]] = None
    axes: dict[Axis, list[AxisLine]] = Field(default_factory=lambda: {"x": [], "y": []})
    chains: list[DimChain] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    ai_issues: list[AiIssue] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    summary: str = ""

    def line_ids(self, axis: Axis) -> set[str]:
        return {line.id for line in self.axes[axis]}

    def validate_refs(self) -> list[str]:
        """Liefert Verweise auf unbekannte Linien (leere Liste = alles gut)."""
        xs, ys = self.line_ids("x"), self.line_ids("y")
        errs: list[str] = []
        for c in self.chains:
            pool = xs if c.axis == "x" else ys
            errs += [f"Kette {c.id}: Linie {lid} fehlt" for lid in c.lines if lid not in pool]
        for m in self.measurements:
            pool = xs if m.axis == "x" else ys
            errs += [f"Messung {m.id}: Linie {lid} fehlt" for lid in (m.a, m.b) if lid not in pool]
        for kind, items in (("Wand", self.walls), ("Öffnung", self.openings), ("Bauteil", self.features)):
            for i, r in enumerate(items):
                for lid, pool in ((r.x0, xs), (r.x1, xs), (r.y0, ys), (r.y1, ys)):
                    if lid not in pool:
                        errs.append(f"{kind} {i}: Linie {lid} fehlt")
        for r in self.rooms:
            for lx, ly in r.poly:
                if lx not in xs or ly not in ys:
                    errs.append(f"Raum {r.name}: Ecke ({lx},{ly}) unbekannt")
        return errs
