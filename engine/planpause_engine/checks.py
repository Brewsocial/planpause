"""Prüfregeln: aus Lösung und Geometrie konkrete Prüfpunkte mit Nachmess-Aufgaben machen."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .model import Axis, PlanModel
from .solver import Conflict, Solution, fmt


class MeasureHint(BaseModel):
    axis: Axis
    a: str
    b: str
    expected: float | None = None
    text: str = ""


class Issue(BaseModel):
    id: str
    severity: str  # kritisch | pruefen | info
    category: str
    title: str
    detail: str
    action: str = ""
    at: list[float] | None = None
    source: str = "Rechenprüfung"
    measure: list[MeasureHint] = Field(default_factory=list)


def _label(plan: PlanModel, axis: Axis, lid: str) -> str:
    for l in plan.axes[axis]:
        if l.id == lid and l.label:
            return l.label
    return lid


def _chain_label(plan: PlanModel, cid: str) -> str:
    for c in plan.chains:
        if c.id == cid:
            return c.label or c.id
    return cid


def _edge_at(geom: dict, axis: Axis, pos: float, hint: str) -> list[float]:
    x0, y0, x1, y1 = geom["bbox"]
    h = hint.lower()
    # Pin innerhalb der Außenwand, damit er die Maßzahlen der Kette nicht verdeckt
    if axis == "x":
        return [pos, y1 - 30 if "unten" in h else y0 + 30]
    return [x1 - 30 if "rechts" in h else x0 + 30, pos]


def conflict_issues(plan: PlanModel, sol: Solution, geom: dict) -> list[Issue]:
    out: list[Issue] = []
    for axis in ("x", "y"):
        a_sol = sol.ax(axis)
        for n, k in enumerate(a_sol.conflicts):
            out.append(_conflict_issue(plan, axis, n, k, sol, geom))
    return out


def _conflict_issue(plan: PlanModel, axis: Axis, n: int, k: Conflict, sol: Solution, geom: dict) -> Issue:
    sev = "kritisch" if k.magnitude > 20 else "pruefen"
    chain_ids = {c.id for c in plan.chains}
    names = [f"„{_chain_label(plan, r)}“" for r in k.refs if r in chain_ids]
    if any(r not in chain_ids for r in k.refs):
        names.append("deine Messung")
    chains = ", ".join(names)
    if not k.candidates:
        return Issue(id=f"konflikt-{axis}-{n}", severity=sev, category="Maßkette",
                     title=f"Mehrere Maße widersprechen sich ({fmt(k.magnitude)} cm)",
                     detail=f"Die Ketten {chains} lassen sich nicht durch einen einzelnen falschen Wert erklären.",
                     action="Die betroffenen Seiten vollständig nachmessen.")
    best = k.chosen
    c = best.constraint
    P = sol.ax(axis).pos
    mid = (P[c.a] + P[c.b]) / 2
    label = _chain_label(plan, c.ref)
    conf = {"hoch": "wahrscheinlich", "mittel": "vermutlich", "niedrig": "möglicherweise"}[k.confidence]
    alts = [x for x in k.candidates[1:4] if x.suggested > 0]
    alt_txt = ""
    if alts and k.confidence != "hoch":
        alt_txt = " Ebenfalls denkbar: " + "; ".join(f"{fmt(x.constraint.value)} → {fmt(x.suggested)}" for x in alts) + "."
    gap = "Es fehlt vermutlich ein Teilmaß. " if k.magnitude >= 50 else ""
    hints = [MeasureHint(axis=axis, a=x.constraint.a, b=x.constraint.b, expected=round(x.suggested, 1),
                         text=f"{_label(plan, axis, x.constraint.a)} bis {_label(plan, axis, x.constraint.b)}")
             for x in k.candidates[:3]]
    return Issue(
        id=f"konflikt-{axis}-{n}", severity=sev, category="Maßkette",
        title=f"Kette „{label}“: {fmt(k.magnitude)} cm Widerspruch",
        detail=(f"{gap}Die Maße der Ketten {chains} passen um {fmt(k.magnitude)} cm nicht zusammen. "
                f"{c.describe()} ist {conf} falsch; konsistent wäre {fmt(best.suggested)} cm.{alt_txt} "
                f"Der Plan wird bis zur Messung mit {fmt(best.suggested)} cm gerechnet."),
        action=f"Teilstrecke messen (laut Plan {fmt(c.value)} cm, rechnerisch {fmt(best.suggested)} cm).",
        at=_edge_at(geom, axis, mid, label), source="Solver", measure=hints)


def determinacy_issues(plan: PlanModel, sol: Solution, geom: dict) -> list[Issue]:
    out: list[Issue] = []
    X, Y = sol.x, sol.y

    def nearest_fixed(axis: Axis, lid: str) -> str | None:
        s = sol.ax(axis)
        fixed = [(abs(s.pos[o] - s.pos[lid]), o) for o, st in s.status.items() if st == "mass" and o != lid]
        return min(fixed)[1] if fixed else None

    floating: dict[tuple, list[int]] = {}
    thin: dict[tuple[str, str], int] = {}
    for i, w in enumerate(plan.walls):
        for ax, a, b in (("x", w.x0, w.x1), ("y", w.y0, w.y1)):
            st = sol.ax(ax).status
            if st[a] == "zeichnung" and st[b] == "zeichnung":
                floating.setdefault((ax, a, b), []).append(i)
            elif st[a] == "zeichnung" or st[b] == "zeichnung":
                thin[(ax, a if st[a] == "zeichnung" else b)] = i
    for n, ((ax, a, b), idxs) in enumerate(floating.items()):
        kinds = {plan.walls[i].kind for i in idxs}
        kind = "Brandwand" if "brand" in kinds else "Außenwand" if "aussen" in kinds else "Innenwand"
        g = geom["walls"][idxs[0]]["rect"]
        ref = nearest_fixed(ax, a)
        s = sol.ax(ax)
        hints = [MeasureHint(axis=ax, a=ref, b=a, expected=round(abs(s.pos[a] - s.pos[ref]), 1),
                             text=f"{_label(plan, ax, ref)} bis {_label(plan, ax, a)}")] if ref else []
        r = geom["walls"][idxs[0]]["rect"]
        thick = min(r[2] - r[0], r[3] - r[1])
        span = abs(s.pos[b] - s.pos[a])
        hints.append(MeasureHint(axis=ax, a=a, b=b, expected=round(span, 1),
                                 text="Wanddicke" if abs(span - thick) < 0.5 else "Wandlänge"))
        out.append(Issue(id=f"lage-wand-{ax}-{n}", severity="info" if kind == "Innenwand" else "pruefen", category="Unvermaßt",
                         title=f"{kind}: Lage nicht bemaßt",
                         detail=(f"Keine Maßkette legt fest, wo diese Wand {'quer' if ax == 'y' else 'längs'} liegt. "
                                 f"Sie wurde aus der Zeichnung platziert (etwa ± {fmt(s.sigma[a])} cm)."),
                         action="Abstand zur nächsten bemaßten Wand und die Wanddicke messen.",
                         at=[(g[0] + g[2]) / 2, (g[1] + g[3]) / 2], measure=hints))
    if thin:
        hints = []
        for (ax, l), i in list(thin.items())[:12]:
            ref = nearest_fixed(ax, l)
            if ref:
                s = sol.ax(ax)
                hints.append(MeasureHint(axis=ax, a=ref, b=l, expected=round(abs(s.pos[l] - s.pos[ref]), 1),
                                         text=f"{_label(plan, ax, ref)} bis {_label(plan, ax, l)}"))
        out.append(Issue(id="wanddicken", severity="info", category="Unvermaßt",
                         title=f"{len(thin)} Wandkanten nur nach Zeichnung",
                         detail=("Bei diesen Wänden ist eine Seite bemaßt, die andere nicht. Meist fehlt nur die Wanddicke; "
                                 "sie wurde aus der Zeichnung übernommen (Fehler meist unter 5 cm)."),
                         action="Wanddicken an Türlaibungen messen.", measure=hints))
    for kind, items, label in (("Öffnung", plan.openings, "Öffnungen"), ("Bauteil", plan.features, "Bauteile")):
        n = sum(1 for r in items if any(sol.ax(ax).status[l] == "zeichnung" for ax, l in (("x", r.x0), ("x", r.x1), ("y", r.y0), ("y", r.y1))))
        if n:
            out.append(Issue(id=f"lage-{kind.lower()}", severity="info", category="Unvermaßt",
                             title=f"{n} {label} nur nach Zeichnung platziert",
                             detail=f"Lage oder Größe von {n} {label} sind nicht bemaßt und wurden aus der Zeichnung übernommen.",
                             action=f"Bei Bedarf die {label} einmessen (Abstand zur nächsten Wand und Breite)."))
    derived = [c for c in sol.area_constraints]
    if derived:
        names = ", ".join(sorted({c.ref for c in derived}))
        out.append(Issue(id="aus-flaeche", severity="info", category="Abgeleitet",
                         title="Raummaße aus Flächenangaben abgeleitet",
                         detail=f"Für {names} fehlt eine Seitenlänge in den Maßketten. Sie wurde aus der Fläche im Plan berechnet.",
                         action="Die abgeleiteten Raumtiefen stichprobenartig messen."))
    return out


def room_issues(plan: PlanModel, sol: Solution, geom: dict) -> list[Issue]:
    out = []
    for i, r in enumerate(geom["rooms"]):
        a, s = r["area_geom"], r["area_stated"]
        if a is None or not s:
            continue
        dev = (a - s) / s
        if abs(dev) <= 0.03:
            continue
        out.append(Issue(id=f"flaeche-{i}", severity="kritisch" if abs(dev) > 0.10 else "pruefen", category="Fläche",
                         title=f"{r['name']}: Fläche passt nicht zu den Maßen",
                         detail=(f"Im Plan stehen {s:.2f} m², aus den Maßen ergeben sich {a:.2f} m² ".replace(".", ",") + 
                                 f"({'+' if dev > 0 else ''}{fmt(round(dev * 100, 1))} %). Entweder ist ein Maß falsch oder die Fläche "
                                 "wurde anders ermittelt, etwa ohne Treppe oder Einbauten."),
                         action=f"{r['name']} in Länge und Breite messen, bei L-Form jede Teilfläche.",
                         at=[r["label"][0] + 70, r["label"][1] - 40] if r["label"] else None))
    return out


def door_issues(plan: PlanModel, geom: dict) -> list[Issue]:
    narrow = [o for o in plan.openings if o.type == "door" and o.width_stated and o.width_stated < 101]
    if not narrow:
        return []
    ws = ", ".join(sorted({fmt(o.width_stated) for o in narrow}))
    return [Issue(id="tueren-barrierefrei", severity="info", category="Barrierefreiheit",
                  title=f"{len(narrow)} Türen unter 90 cm lichter Breite",
                  detail=(f"Die Türen sind mit {ws} cm angegeben, meist Rohbaurichtmaße. Die lichte Durchgangsbreite liegt "
                          "darunter und damit unter den 90 cm, die DIN 18040-2 für barrierefreie Wohnungen verlangt."),
                  action="Lichte Durchgangsbreite der Türen messen, wenn Barrierefreiheit ein Thema ist.")]


def drawing_issues(plan: PlanModel, sol: Solution) -> list[Issue]:
    out = []
    for axis in ("x", "y"):
        s = sol.ax(axis)
        span = (max(s.pos.values()) - min(s.pos.values())) if s.pos else 0
        bad = [l for l, d in s.prior_dev.items() if abs(d) > max(40.0, 0.06 * span)]
        if bad:
            out.append(Issue(id=f"zeichnung-{axis}", severity="info", category="Zeichnung",
                             title="Zeichnung an einigen Stellen nicht maßstäblich",
                             detail=(f"{len(bad)} Kanten liegen in der Zeichnung deutlich anders, als die Maße es verlangen. "
                                     "Gerechnet wird mit den Maßen. Bei Handzeichnungen ist das normal, kann aber auf eine falsch "
                                     "zugeordnete Maßzahl hinweisen."),
                             action="Die Überlagerung mit dem Original prüfen."))
    return out


def plausibility_issues(plan: PlanModel, sol: Solution, geom: dict) -> list[Issue]:
    """Grobe Lesefehler, die keine zweite Maßkette aufdeckt: Werte, die zur Zeichnung oder zu üblichen Bauteilgrößen nicht passen."""
    out: list[Issue] = []

    # 1. Einzelne Maßzahl gegen gezeichnete Länge (z. B. 245 statt 345 gelesen)
    suspect = {c["id"]: set(c["suspect"]) for c in geom["chains"]}
    px = {ax: {l.id: l.px for l in plan.axes[ax] if l.px is not None} for ax in ("x", "y")}
    off: list[tuple[str, float, float, MeasureHint]] = []
    for ch in plan.chains:
        scale = sol.ax(ch.axis).scale
        if not scale:
            continue
        for i, v in enumerate(ch.values):
            a, b = ch.lines[i], ch.lines[i + 1]
            if i in suspect.get(ch.id, set()) or a not in px[ch.axis] or b not in px[ch.axis]:
                continue
            drawn = (px[ch.axis][b] - px[ch.axis][a]) / scale
            if abs(drawn - v) > max(25.0, 0.35 * v):
                label = ch.label or ch.id
                off.append((label, v, drawn, MeasureHint(axis=ch.axis, a=a, b=b, text=f"{label}: {fmt(v)} cm prüfen")))
    if off:
        listed = "; ".join(f"{l}: {fmt(v)} cm, gezeichnet etwa {fmt(round(d / 5) * 5)} cm" for l, v, d, _ in off[:6])
        out.append(Issue(id="mass-gegen-zeichnung", severity="pruefen", category="Lesefehler?",
                         title=f"{len(off)} Maßzahlen passen nicht zur Zeichnung",
                         detail=(f"Diese Werte weichen stark von der gezeichneten Länge ab: {listed}. "
                                 "Häufige Ursache sind verwechselte Ziffern (3/8, 1/7) oder eine Maßzahl, die der falschen Strecke zugeordnet wurde."),
                         action="Die Zahlen im Original nachlesen oder vor Ort messen.", measure=[h for *_, h in off[:6]]))

    # 2. Wanddicken außerhalb des Üblichen (leichte Altbau-Trennwände ab etwa 5 cm, Außenwände bis etwa 50 cm)
    odd = []
    for w in geom["walls"]:
        x0, y0, x1, y1 = w["rect"]
        t = min(x1 - x0, y1 - y0)
        if t < 5 or t > 60:
            odd.append((t, w))
    if odd:
        t, w = odd[0]
        out.append(Issue(id="wanddicke-unplausibel", severity="pruefen", category="Plausibilität",
                         title=f"{len(odd)} Wände mit ungewöhnlicher Dicke",
                         detail=(f"Wände im Bestand sind etwa 5 cm (leichte Trennwand) bis 50 cm dick, hier z. B. {fmt(round(t, 1))} cm. "
                                 "Meist ist eine Wandkante der falschen Linie zugeordnet."),
                         action="Wanddicke an der Türlaibung messen.",
                         at=[(w["rect"][0] + w["rect"][2]) / 2, (w["rect"][1] + w["rect"][3]) / 2]))

    # 3. Öffnungsbreiten
    limits = {"door": (55, 250, "Tür"), "window": (30, 500, "Fenster"), "passage": (55, 600, "Durchgang")}
    for k, (o, g) in enumerate(zip(plan.openings, geom["openings"])):
        if o.type not in limits:
            continue
        lo, hi, name = limits[o.type]
        x0, y0, x1, y1 = g["rect"]
        width = o.width_stated or max(x1 - x0, y1 - y0)
        if not lo <= width <= hi:
            out.append(Issue(id=f"oeffnung-{k}", severity="pruefen", category="Plausibilität",
                             title=f"{name} mit {fmt(round(width))} cm Breite",
                             detail=f"Für eine {name.lower()} ist das ungewöhnlich (üblich {lo} bis {hi} cm). Vermutlich falsch gelesen oder falsch zugeordnet.",
                             action=f"{name}breite messen.", at=[(x0 + x1) / 2, (y0 + y1) / 2]))

    # 4. Räume, die so nicht sein können
    for i, r in enumerate(geom["rooms"]):
        if len(r["poly"]) < 3:
            continue
        xs, ys = [p[0] for p in r["poly"]], [p[1] for p in r["poly"]]
        side = min(max(xs) - min(xs), max(ys) - min(ys))
        area = r["area_geom"]
        if side < 70 or (area is not None and (area < 1.0 or area > 250)):
            what = f"nur {fmt(round(side))} cm schmal" if side < 70 else f"{fmt(round(area, 1))} m² groß"
            out.append(Issue(id=f"raum-unplausibel-{i}", severity="kritisch", category="Plausibilität",
                             title=f"{r['name']}: Raum ist {what}",
                             detail="Diese Raumgröße ist nicht plausibel. Wahrscheinlich fehlt eine Maßkette oder Wände sind den falschen Linien zugeordnet.",
                             action=f"{r['name']} in Länge und Breite messen.",
                             at=r["label"] if r["label"] else None))
    return out


def ai_issues(plan: PlanModel, sol: Solution) -> list[Issue]:
    out = []
    for i in plan.ai_issues:
        at = None
        if i.at and i.at[0] in sol.x.pos and i.at[1] in sol.y.pos:
            at = [sol.x.pos[i.at[0]], sol.y.pos[i.at[1]]]
        out.append(Issue(id=i.id, severity=i.severity, category=i.category or "Hinweis", title=i.title,
                         detail=i.detail, action=i.action, at=at, source="KI-Analyse"))
    return out


SEV = {"kritisch": 0, "pruefen": 1, "info": 2}


def run_checks(plan: PlanModel, sol: Solution, geom: dict) -> list[Issue]:
    issues = (conflict_issues(plan, sol, geom) + room_issues(plan, sol, geom) + determinacy_issues(plan, sol, geom)
              + door_issues(plan, geom) + drawing_issues(plan, sol) + plausibility_issues(plan, sol, geom) + ai_issues(plan, sol))
    issues.sort(key=lambda i: (SEV.get(i.severity, 3), i.source != "Solver"))
    return issues
