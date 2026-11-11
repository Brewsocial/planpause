"""Prüfregeln: aus Lösung und Geometrie konkrete Prüfpunkte mit Nachmess-Aufgaben machen."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .model import Axis, PlanModel
from .purpose import PURPOSES, purpose_label
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


def _center(r: list[float]) -> list[float]:
    return [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2]


def geometry_issues(geom: dict) -> list[Issue]:
    """Entartete Geometrie: Dicke, Länge oder Fläche 0, weil zwei Kanten auf derselben Linie gelandet sind."""
    bad: list[tuple[str, list[float]]] = []
    for name, items in (("Wand", geom["walls"]), ("Öffnung", geom["openings"]), ("Bauteil", geom["features"])):
        for e in items:
            x0, y0, x1, y1 = e["rect"]
            if min(x1 - x0, y1 - y0) < 0.5:
                bad.append((name, _center(e["rect"])))
    for r in geom["rooms"]:
        if len(r["poly"]) >= 3 and (r["area_geom"] or 0) < 0.01:
            bad.append((f"Raum {r['name']}", r["label"] or _center([*r["poly"][0], *r["poly"][0]])))
    if not bad:
        return []
    what = ", ".join(sorted({n for n, _ in bad}))
    return [Issue(id="geometrie-entartet", severity="kritisch", category="Geometrie",
                  title=f"{len(bad)} Bauteile ohne Ausdehnung ({what})",
                  detail="Dicke, Länge oder Fläche sind 0: zwei Kanten des Bauteils liegen auf derselben Stelle. So darf es nicht exportiert werden.",
                  action="Die Linienzuordnung dieses Bauteils prüfen; meist ist eine Kante der falschen Linie zugeordnet.", at=bad[0][1])]


def thickness_issues(plan: PlanModel, sol: Solution, geom: dict) -> list[Issue]:
    """Gleicher Wandtyp, gleiche Dicke innerhalb eines Geschosses. Ausreißer nur, wenn sie so bemaßt sind."""
    by_kind: dict[str, list[tuple[float, bool, dict]]] = {}
    for w, pw in zip(geom["walls"], plan.walls):
        x0, y0, x1, y1 = w["rect"]
        flat = x1 - x0 >= y1 - y0
        ax, a, b = ("y", pw.y0, pw.y1) if flat else ("x", pw.x0, pw.x1)
        st = sol.ax(ax).status
        by_kind.setdefault(w["kind"], []).append((min(x1 - x0, y1 - y0), st[a] == "mass" and st[b] == "mass", w))
    names = {"aussen": "Außenwände", "innen": "Innenwände", "brand": "Brandwände"}
    out = []
    for kind, items in by_kind.items():
        if len(items) < 3:
            continue
        ts = sorted(t for t, _, _ in items)
        usual = ts[len(ts) // 2]
        odd = [(t, w) for t, measured, w in items if not measured and abs(t - usual) > max(3.0, 0.25 * usual)]
        if not odd:
            continue
        listed = ", ".join(fmt(round(t, 1)) for t, _ in odd[:5])
        out.append(Issue(id=f"wanddicke-{kind}", severity="pruefen", category="Plausibilität",
                         title=f"{len(odd)} {names[kind]} mit abweichender Dicke ({listed} statt {fmt(round(usual, 1))} cm)",
                         detail=(f"Die meisten {names[kind]} dieses Geschosses sind {fmt(round(usual, 1))} cm dick. Diese Wände weichen ab, "
                                 "ohne dass eine Maßkette das belegt; ihre Dicke stammt aus der Zeichnung."),
                         action="Wanddicke an einer Laibung messen. Stimmt das übliche Maß, Wand entsprechend korrigieren.",
                         at=_center(odd[0][1]["rect"])))
    return out


def _hits(r: list[float], others: list[tuple[int, list[float]]], eps: float = 1.0) -> list[int]:
    x0, y0, x1, y1 = r
    return [i for i, o in others if o[0] < x1 + eps and o[2] > x0 - eps and o[1] < y1 + eps and o[3] > y0 - eps]


def contour_issues(geom: dict, reach: float = 300.0) -> list[Issue]:
    """Freie Wandenden: Lücke in der Außenkontur oder Innenwandöffnung ohne Tür.

    Jedes Wandende muss an eine andere Wand, eine Öffnung oder ein Bauteil anschließen. Tut es das nicht, wird in
    Wandrichtung weitergesucht: trifft der Korridor auf eine Wand, fehlt dazwischen eine Öffnung (Außenwand) oder
    ein Türsymbol (Innenwand, Lücke 40 bis 200 cm)."""
    walls = geom["walls"]
    solid = [(i, w["rect"]) for i, w in enumerate(walls)] + [(-1 - k, f["rect"]) for k, f in enumerate(geom["features"])]
    opens = [(k, o["rect"]) for k, o in enumerate(geom["openings"])]
    gaps: dict[tuple, tuple[str, float, list[float]]] = {}
    loose: list[list[float]] = []
    for i, w in enumerate(walls):
        x0, y0, x1, y1 = w["rect"]
        flat = x1 - x0 >= y1 - y0
        others = [(j, r) for j, r in solid if j != i]
        for side in (0, 1):
            if flat:
                probe = [x0 - 2, y0 + 0.5, x0, y1 - 0.5] if side == 0 else [x1, y0 + 0.5, x1 + 2, y1 - 0.5]
                corridor = [x0 - reach, y0 + 0.5, x0, y1 - 0.5] if side == 0 else [x1, y0 + 0.5, x1 + reach, y1 - 0.5]
                dist = (lambda r: x0 - r[2]) if side == 0 else (lambda r: r[0] - x1)
            else:
                probe = [x0 + 0.5, y0 - 2, x1 - 0.5, y0] if side == 0 else [x0 + 0.5, y1, x1 - 0.5, y1 + 2]
                corridor = [x0 + 0.5, y0 - reach, x1 - 0.5, y0] if side == 0 else [x0 + 0.5, y1, x1 - 0.5, y1 + reach]
                dist = (lambda r: y0 - r[3]) if side == 0 else (lambda r: r[1] - y1)
            if _hits(probe, others) or _hits(probe, opens):
                continue
            end = [x0 if side == 0 else x1, (y0 + y1) / 2] if flat else [(x0 + x1) / 2, y0 if side == 0 else y1]
            ahead = [(dist(r), j, r) for j, r in others if j in set(_hits(corridor, others, 0.0))]
            ahead = [a for a in ahead if a[0] > 0.5]
            if not ahead:
                if w["kind"] == "aussen":
                    loose.append(end)
                continue
            d, j, r = min(ahead, key=lambda a: a[0])
            opening_between = [k for k, o in opens if _hits(corridor, [(k, o)], 0.0) and dist(o) < d]
            if opening_between:
                continue
            key = (min(i, j), max(i, j))
            if key in gaps:
                continue
            mid = [end[0] + (d / 2 if flat and side == 1 else -d / 2 if flat else 0), end[1] + (d / 2 if not flat and side == 1 else -d / 2 if not flat else 0)]
            if w["kind"] == "aussen":
                gaps[key] = ("aussen", d, mid)
            elif 40 <= d <= 200:
                gaps[key] = ("innen", d, mid)
    out = []
    outer = [(d, m) for k, (kind, d, m) in gaps.items() if kind == "aussen"]
    inner = [(d, m) for k, (kind, d, m) in gaps.items() if kind == "innen"]
    for n, (d, m) in enumerate(outer):
        out.append(Issue(id=f"kontur-{n}", severity="pruefen", category="Kontur",
                         title=f"Außenkontur offen: {fmt(round(d))} cm Lücke ohne Öffnung",
                         detail="Zwischen zwei Außenwänden fehlt ein Stück: dort ist weder Wand noch Fenster, Tür oder Tor eingetragen.",
                         action="Im Original nachsehen: Fenster, Tür, Tor oder Wand ergänzen, oder die Stelle als offen kennzeichnen.", at=m))
    for n, (d, m) in enumerate(inner):
        out.append(Issue(id=f"luecke-{n}", severity="pruefen", category="Öffnung",
                         title=f"Lücke in Innenwand ohne Tür ({fmt(round(d))} cm)",
                         detail="Die Wand hat eine türbreite Lücke, aber es ist weder eine Tür noch ein Durchgang eingetragen.",
                         action="Tür mit Breite und Aufschlag eintragen oder als offenen Durchgang kennzeichnen.", at=m))
    if loose:
        out.append(Issue(id="kontur-frei", severity="info", category="Kontur",
                         title=f"{len(loose)} Außenwandenden ohne Anschluss",
                         detail=("Diese Außenwände enden frei, ohne dass in Wandrichtung eine weitere Wand folgt. Normal, wenn nur ein Teil des "
                                 "Gebäudes gezeichnet ist oder der Anbau als eigener Grundriss folgt; sonst fehlt dort eine Wand."),
                         action="Prüfen, ob der Plan an dieser Stelle vollständig ist.", at=loose[0]))
    return out


def purpose_issues(plan: PlanModel, geom: dict, purpose: str | None) -> list[Issue]:
    """Inhalte, die der Verwendungszweck braucht und die im Plan fehlen. Ein leerer Layer braucht eine Begründung."""
    p = PURPOSES.get(purpose or "")
    if not p:
        return []
    ftypes = [f["type"].lower() for f in geom["features"]]
    have = {
        "brand": any(w["kind"] == "brand" for w in geom["walls"]),
        "aussen": any(w["kind"] == "aussen" for w in geom["walls"]),
        "treppe": any("trepp" in t for t in ftypes),
        "schacht": any(k in t for t in ftypes for k in ("schacht", "aufzug", "fahrstuhl")),
        "tueren": any(o["type"] == "door" for o in geom["openings"]),
        "fenster": any(o["type"] == "window" for o in geom["openings"]),
        "raeume": any(r.name and not r.name_assumed for r in plan.rooms),
        "flaechen": any(r["area_stated"] for r in geom["rooms"]),
        "ketten": bool(geom["chains"]),
    }
    missing = [label for key, label in p["needs"] if not have.get(key)]
    if not missing:
        return []
    return [Issue(id="zweck-fehlt", severity="pruefen", category="Verwendungszweck",
                  title=f"Für {p['label']} fehlt: {', '.join(missing)}",
                  detail=("Davon wurde im Plan nichts erkannt. Entweder enthält der Plan es nicht, dann gehört die Begründung in den Bericht, "
                          "oder es wurde übersehen."),
                  action="Im Original prüfen. Fehlt es nur in der Erkennung: Hinweis zum Plan eintragen und Analyse wiederholen.")]


CHECKLIST = [
    ("ketten", "Jede Maßkette geht rechnerisch auf", ("konflikt-",)),
    ("geometrie", "Keine entartete Geometrie (Dicke, Länge, Fläche 0)", ("geometrie-entartet",)),
    ("wanddicken", "Wanddicken im plausiblen Bereich und je Wandtyp einheitlich", ("wanddicke-",)),
    ("kontur", "Außenkontur geschlossen", ("kontur-",)),
    ("oeffnungen", "Jede Innenwandöffnung ist Tür oder Durchgang", ("luecke-",)),
    ("zweck", "Inhalte für den Verwendungszweck vorhanden", ("zweck-",)),
]


def export_checklist(issues: list[Issue], purpose: str | None) -> list[dict]:
    """Selbstprüfung vor dem Export (Regel 7): je Punkt bestanden oder nicht, mit den auslösenden Prüfpunkten."""
    out = []
    for key, title, prefixes in CHECKLIST:
        hits = [i for i in issues if any(i.id.startswith(p) for p in prefixes) and i.severity != "info"]
        if key == "zweck":
            title = f"Inhalte für {purpose_label(purpose)} vorhanden" if purpose else "Verwendungszweck nicht festgelegt"
        out.append({"id": key, "title": title, "ok": not hits, "detail": "; ".join(h.title for h in hits[:3]),
                    "issues": [h.id for h in hits]})
    return out


SEV = {"kritisch": 0, "pruefen": 1, "info": 2}


def run_checks(plan: PlanModel, sol: Solution, geom: dict, purpose: str | None = None) -> list[Issue]:
    issues = (conflict_issues(plan, sol, geom) + geometry_issues(geom) + room_issues(plan, sol, geom) + determinacy_issues(plan, sol, geom)
              + door_issues(plan, geom) + drawing_issues(plan, sol) + plausibility_issues(plan, sol, geom) + thickness_issues(plan, sol, geom)
              + contour_issues(geom) + purpose_issues(plan, geom, purpose) + ai_issues(plan, sol))
    rank = PURPOSES.get(purpose or "", {}).get("rank", [])  # Prüfpunkte nach Bedeutung für den Verwendungszweck
    issues.sort(key=lambda i: (SEV.get(i.severity, 3), rank.index(i.category) if i.category in rank else len(rank), i.source != "Solver"))
    return issues
