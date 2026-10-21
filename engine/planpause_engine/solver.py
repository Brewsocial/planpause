"""Maßketten-Solver.

Pro Achse werden die Lagen aller Rasterlinien per gewichteter Ausgleichsrechnung
bestimmt. Harte Bedingungen sind Maßzahlen (Ketten, Gesamtmaße, Messungen,
abgeleitete Raumtiefen aus Flächen). Weiche Bedingungen sind die Pixelpositionen
aus der Zeichnung; sie halten nur Linien fest, die sonst durch kein Maß bestimmt sind,
und entscheiden zwischen gleichwertigen Fehlererklärungen.

Widersprechen sich Maßzahlen, sucht der Solver den einen Wert, dessen Weglassen
den Widerspruch auflöst (Leave-one-out). Gibt es mehrere solche Werte, entscheidet,
welche Erklärung am besten zur Zeichnung passt. Der Wert wird als vermutlich falsch
gemeldet, inklusive des Werts, der konsistent wäre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

import numpy as np

from .model import Axis, PlanModel

SIGMA_PLAN = 1.0        # cm, gelesene Maßzahl
SIGMA_UNCERTAIN = 6.0   # cm, schwer lesbare Maßzahl
SIGMA_MEASURED = 0.3    # cm, vor Ort gemessen
SIGMA_AREA = 3.0        # cm, aus Fläche abgeleitet
SIGMA_PRIOR = 25.0      # cm, Lage aus der Zeichnung
TOL = 3.0               # cm, Schließfehler ab dem ein Maß als widersprüchlich gilt


@dataclass
class Constraint:
    kind: str            # chain | total | measure | area | prior
    a: str
    b: Optional[str]     # None bei prior
    value: float
    sigma: float
    ref: str = ""        # Ketten-ID / Mess-ID / Raumname
    index: Optional[int] = None  # Index in der Kette
    label: str = ""

    @property
    def hard(self) -> bool:
        return self.kind != "prior"

    @property
    def candidate(self) -> bool:
        """Darf als Fehlerursache verdächtigt werden (Messungen nie)."""
        return self.kind in ("chain", "total", "opening")

    def describe(self) -> str:
        if self.kind == "chain":
            return f"Wert {fmt(self.value)} in Kette „{self.ref}“ (Position {self.index + 1})"
        if self.kind == "total":
            return f"Gesamtmaß {fmt(self.value)} der Kette „{self.ref}“"
        if self.kind == "opening":
            return f"Breitenangabe {fmt(self.value)} der Öffnung „{self.ref}“"
        if self.kind == "area":
            return f"aus Fläche abgeleitete Tiefe von {self.ref}"
        if self.kind == "measure":
            return f"Messung „{self.ref}“"
        return self.label or self.kind


def fmt(v: float) -> str:
    return (f"{v:.1f}".rstrip("0").rstrip(".")).replace(".", ",")


@dataclass
class Candidate:
    constraint: Constraint
    suggested: float
    prior_rms: float


@dataclass
class Conflict:
    axis: Axis
    magnitude: float
    refs: list[str]
    candidates: list[Candidate]
    confidence: str  # hoch | mittel | niedrig

    @property
    def chosen(self) -> Candidate:
        return self.candidates[0]


@dataclass
class AxisSolution:
    axis: Axis
    pos: dict[str, float]
    status: dict[str, str]          # mass | flaeche | zeichnung
    sigma: dict[str, float]
    residuals: list[tuple[Constraint, float]]
    conflicts: list[Conflict]
    scale: Optional[float]          # px pro cm
    prior_dev: dict[str, float] = field(default_factory=dict)  # Abweichung Zeichnung vs. Maß


@dataclass
class Solution:
    x: AxisSolution
    y: AxisSolution
    area_constraints: list[Constraint]

    def ax(self, a: Axis) -> AxisSolution:
        return self.x if a == "x" else self.y

    def p(self, lx: str, ly: str) -> tuple[float, float]:
        return self.x.pos[lx], self.y.pos[ly]


# ---------------------------------------------------------------- Hilfen

class _UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _components(ids: list[str], cons: list[Constraint]) -> dict[str, str]:
    uf = _UF(ids)
    for c in cons:
        if c.hard and c.b is not None:
            uf.union(c.a, c.b)
    return {i: uf.find(i) for i in ids}


def estimate_scale(plan: PlanModel, axis: Axis) -> Optional[float]:
    """Pixel pro cm aus den Maßketten der Achse. Ohne Maßkette auf dieser Achse gilt der Maßstab
    der anderen: Das Bild ist entzerrt, ein Zentimeter ist waagerecht und senkrecht gleich lang.
    Sonst fiele die ganze Achse auf 0 zusammen."""
    return _axis_scale(plan, axis) or _axis_scale(plan, "y" if axis == "x" else "x")


def _axis_scale(plan: PlanModel, axis: Axis) -> Optional[float]:
    px = {l.id: l.px for l in plan.axes[axis] if l.px is not None}
    sure, unsure = [], []
    for ch in plan.chains:
        if ch.axis != axis:
            continue
        for i, v in enumerate(ch.values):
            a, b = ch.lines[i], ch.lines[i + 1]
            if v >= 50 and a in px and b in px and px[b] > px[a]:
                (unsure if i in ch.uncertain else sure).append((px[b] - px[a]) / v)
    ratios = sure or unsure  # schwer lesbare Werte nur, wenn es nichts Besseres gibt
    return median(ratios) if ratios else None


def build_constraints(plan: PlanModel, axis: Axis, extra: list[Constraint] | None = None) -> list[Constraint]:
    cons: list[Constraint] = []
    for ch in plan.chains:
        if ch.axis != axis:
            continue
        for i, v in enumerate(ch.values):
            cons.append(Constraint("chain", ch.lines[i], ch.lines[i + 1], v,
                                   SIGMA_UNCERTAIN if i in ch.uncertain else SIGMA_PLAN, ch.id, i))
        if ch.total is not None:
            cons.append(Constraint("total", ch.lines[0], ch.lines[-1], ch.total, SIGMA_PLAN, ch.id))
    px = {l.id: l.px for l in plan.axes["x"]}
    py = {l.id: l.px for l in plan.axes["y"]}
    for k, o in enumerate(plan.openings):
        if not o.width_stated:
            continue
        if None in (px.get(o.x0), px.get(o.x1), py.get(o.y0), py.get(o.y1)):
            continue
        along = "x" if abs(px[o.x1] - px[o.x0]) >= abs(py[o.y1] - py[o.y0]) else "y"
        if along == axis:
            a, b = (o.x0, o.x1) if axis == "x" else (o.y0, o.y1)
            cons.append(Constraint("opening", a, b, o.width_stated, 2.0, f"{o.type} {k + 1}"))
    for m in plan.measurements:
        if m.axis == axis:
            cons.append(Constraint("measure", m.a, m.b, m.value, SIGMA_MEASURED, m.id, label=m.note))
    cons += [c for c in (extra or [])]
    scale = estimate_scale(plan, axis)
    if scale:
        for line in plan.axes[axis]:
            if line.px is not None:
                cons.append(Constraint("prior", line.id, None, line.px / scale, SIGMA_PRIOR, label=line.label))
    return cons


def _solve(ids: list[str], cons: list[Constraint]) -> tuple[dict[str, float], np.ndarray, list[Constraint]]:
    """Gewichtete kleinste Quadrate. Unbekannte: Linienlagen + ein Versatz für die Zeichnung."""
    idx = {lid: i for i, lid in enumerate(ids)}
    n = len(ids) + 1  # letzter Eintrag: Versatz der Zeichnung
    rows, rhs, w = [], [], []
    used: list[Constraint] = []
    for c in cons:
        r = np.zeros(n)
        if c.kind == "prior":
            r[idx[c.a]] = 1.0
            r[-1] = -1.0
        else:
            r[idx[c.b]] = 1.0
            r[idx[c.a]] = -1.0
        rows.append(r); rhs.append(c.value); w.append(1.0 / c.sigma); used.append(c)
    # Eichung: jede Komponente ohne Prior bekommt einen Anker bei 0 (sehr schwach)
    for i in range(n):
        r = np.zeros(n); r[i] = 1.0
        rows.append(r); rhs.append(0.0); w.append(1e-6)
    A = np.array(rows) * np.array(w)[:, None]
    b = np.array(rhs) * np.array(w)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    pos = {lid: float(sol[idx[lid]]) for lid in ids}
    res = np.array([(pos[c.b] - pos[c.a] - c.value) if c.kind != "prior" else (pos[c.a] - sol[-1] - c.value)
                    for c in used])
    return pos, res, used, _loo(ids, used)


def _loo(ids: list[str], cons: list[Constraint]) -> np.ndarray:
    """Leave-one-out-Residuen nur aus Maßzahlen (Zeichnung bleibt außen vor).

    r_loo = r / (1 - h_ii): der Widerspruch, den ein Maß hätte, wenn man es wegließe.
    Bei fehlender Redundanz (h_ii ~ 1) ist ein Maß nicht kontrollierbar und bekommt 0.
    """
    idx = {lid: i for i, lid in enumerate(ids)}
    hard = [(k, c) for k, c in enumerate(cons) if c.hard]
    out = np.zeros(len(cons))
    if not hard:
        return out
    n = len(ids)
    rows, rhs, w = [], [], []
    for _, c in hard:
        r = np.zeros(n); r[idx[c.b]] = 1.0; r[idx[c.a]] = -1.0
        rows.append(r); rhs.append(c.value); w.append(1.0 / c.sigma)
    for i in range(n):
        r = np.zeros(n); r[i] = 1.0
        rows.append(r); rhs.append(0.0); w.append(1e-6)
    A = np.array(rows) * np.array(w)[:, None]
    b = np.array(rhs) * np.array(w)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    k = len(hard)
    H = A @ np.linalg.pinv(A.T @ A) @ A.T
    red = 1.0 - np.clip(np.diag(H)[:k], 0.0, 1.0)
    res = (A @ x - b)[:k] / np.array(w[:k])
    loo = np.where(red > 0.02, res / np.maximum(red, 1e-9), 0.0)
    for (pos, _), v in zip(hard, loo):
        out[pos] = v
    return out


def _hard_cost(res: np.ndarray, cons: list[Constraint], loo: np.ndarray) -> tuple[float, float]:
    """(gewichtete Fehlerquadratsumme der harten Bedingungen, größter Leave-one-out-Widerspruch)."""
    hard = [(r, c, l) for r, c, l in zip(res, cons, loo) if c.hard]
    if not hard:
        return 0.0, 0.0
    return float(sum((r / c.sigma) ** 2 for r, c, _ in hard)), float(max(abs(l) for *_, l in hard))


def _prior_rms(res: np.ndarray, cons: list[Constraint], only: set[str] | None = None) -> float:
    pr = [r for r, c in zip(res, cons) if c.kind == "prior" and (only is None or c.a in only)]
    return float(np.sqrt(np.mean(np.square(pr)))) if pr else 0.0


def solve_axis(plan: PlanModel, axis: Axis, extra: list[Constraint] | None = None, max_conflicts: int = 4) -> AxisSolution:
    ids = [l.id for l in plan.axes[axis]]
    cons = build_constraints(plan, axis, extra)
    scale = estimate_scale(plan, axis)
    removed: list[Constraint] = []
    conflicts: list[Conflict] = []

    for _ in range(max_conflicts):
        active = [c for c in cons if not any(c is r for r in removed)]
        pos, res, used, loo = _solve(ids, active)
        cost, worst = _hard_cost(res, used, loo)
        if worst <= TOL:
            break
        violated = {c.ref for l, c in zip(loo, used) if c.hard and abs(l) > TOL}
        local = {lid for c, l in zip(used, loo) if c.hard and abs(l) > TOL for lid in (c.a, c.b)}
        trials = []
        for c in active:
            if not c.candidate:
                continue
            trial = [k for k in active if k is not c]
            p2, r2, u2, l2 = _solve(ids, trial)
            cst, wst = _hard_cost(r2, u2, l2)
            trials.append((cst, wst, _prior_rms(r2, u2, local), c, p2[c.b] - p2[c.a]))
        if not trials:
            break
        feasible = [t for t in trials if t[1] <= TOL]
        if feasible:
            equiv = feasible
        else:  # mehrere Fehler: den Wert nehmen, der am meisten erklärt, dann weitersuchen
            best_cost = min(t[0] for t in trials)
            if best_cost >= cost * 0.9:
                conflicts.append(Conflict(axis, worst, sorted(violated), [], "niedrig"))
                break
            equiv = [t for t in trials if t[0] <= best_cost * 1.1 + 1.0]
        equiv.sort(key=lambda t: t[2])
        cands = [Candidate(t[3], t[4], t[2]) for t in equiv[:5]]
        if len(cands) == 1 or not scale:
            conf = "hoch" if len(cands) == 1 else "niedrig"
        else:
            gap = cands[1].prior_rms - cands[0].prior_rms
            conf = "hoch" if gap > 6 else "mittel" if gap > 2 else "niedrig"
        conflicts.append(Conflict(axis, worst, sorted(violated), cands, conf))
        removed.append(cands[0].constraint)

    active = [c for c in cons if not any(c is r for r in removed)]
    pos, res, used, _ = _solve(ids, active)

    # Bestimmtheit: Linien in der größten Komponente harter Bedingungen gelten als vermaßt
    comp = _components(ids, active)
    sizes: dict[str, int] = {}
    for root in comp.values():
        sizes[root] = sizes.get(root, 0) + 1
    main = max(sizes, key=sizes.get) if sizes else None
    area_lines = {c.a for c in active if c.kind == "area"} | {c.b for c in active if c.kind == "area"}
    prior_res = [abs(r) for r, c in zip(res, used) if c.kind == "prior" and comp[c.a] == main]
    spread = float(np.sqrt(np.mean(np.square(prior_res)))) if prior_res else SIGMA_PRIOR
    status, sigma, prior_dev = {}, {}, {}
    for lid in ids:
        if comp[lid] == main:
            status[lid] = "flaeche" if lid in area_lines and _only_area(lid, active) else "mass"
            sigma[lid] = SIGMA_AREA if status[lid] == "flaeche" else SIGMA_PLAN
        else:
            status[lid] = "zeichnung"
            sigma[lid] = round(max(spread, 5.0), 1)
    for r, c in zip(res, used):
        if c.kind == "prior" and comp[c.a] == main:
            prior_dev[c.a] = float(r)

    # Ursprung: kleinste Lage = 0
    m0 = min(pos.values()) if pos else 0.0
    pos = {k: round(v - m0, 2) for k, v in pos.items()}
    residuals = [(c, float(r)) for r, c in zip(res, used) if c.hard]
    return AxisSolution(axis, pos, status, sigma, residuals, conflicts, scale, prior_dev)


def _only_area(lid: str, cons: list[Constraint]) -> bool:
    return not any(c.hard and c.kind != "area" and lid in (c.a, c.b) for c in cons)


def _span_determined(sol: AxisSolution, a: str, b: str) -> bool:
    return sol.status.get(a) in ("mass", "flaeche") and sol.status.get(b) in ("mass", "flaeche")


def area_constraints(plan: PlanModel, xs: AxisSolution, ys: AxisSolution) -> list[Constraint]:
    """Rechteckräume mit Flächenangabe: fehlt eine Seite, wird sie aus Fläche / andere Seite abgeleitet."""
    out = []
    for r in plan.rooms:
        if not r.area_stated or len(r.poly) != 4:
            continue
        lx = sorted({p[0] for p in r.poly}, key=lambda i: xs.pos[i])
        ly = sorted({p[1] for p in r.poly}, key=lambda i: ys.pos[i])
        if len(lx) != 2 or len(ly) != 2:
            continue
        x_ok, y_ok = _span_determined(xs, *lx), _span_determined(ys, *ly)
        area = r.area_stated * 1e4
        if x_ok and not y_ok:
            w = xs.pos[lx[1]] - xs.pos[lx[0]]
            if w > 0:
                out.append(Constraint("area", ly[0], ly[1], area / w, SIGMA_AREA, r.name, label="y"))
        elif y_ok and not x_ok:
            h = ys.pos[ly[1]] - ys.pos[ly[0]]
            if h > 0:
                out.append(Constraint("area", lx[0], lx[1], area / h, SIGMA_AREA, r.name, label="x"))
    return out


def solve(plan: PlanModel) -> Solution:
    errs = plan.validate_refs()
    if errs:
        raise ValueError("Planmodell unvollständig: " + "; ".join(errs[:8]))
    xs, ys = solve_axis(plan, "x"), solve_axis(plan, "y")
    extra: list[Constraint] = []
    for _ in range(2):
        new = [c for c in area_constraints(plan, xs, ys) if not any(e.ref == c.ref and e.label == c.label for e in extra)]
        if not new:
            break
        extra += new
        xs = solve_axis(plan, "x", [c for c in extra if c.label == "x"])
        ys = solve_axis(plan, "y", [c for c in extra if c.label == "y"])
    return Solution(xs, ys, extra)
