"""Aus Planmodell + Lösung konkrete Koordinaten erzeugen (für Anzeige und Export)."""
from __future__ import annotations

from .model import Opening, PlanModel
from .solver import Solution


def polygon_area(pts: list[tuple[float, float]]) -> float:
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def door_swing(o: Opening, x0: float, y0: float, x1: float, y1: float) -> dict | None:
    if o.type != "door" or not o.hinge or not o.swing:
        return None
    if (x1 - x0) >= (y1 - y0):  # Öffnung liegt in einer waagerechten Wand
        r = x1 - x0
        hx = x0 if o.hinge == "start" else x1
        hy = y1 if o.swing == "pos" else y0
        a0 = 0 if o.hinge == "start" else 180
        a1 = 90 if o.swing == "pos" else 270
    else:
        r = y1 - y0
        hy = y0 if o.hinge == "start" else y1
        hx = x1 if o.swing == "pos" else x0
        a0 = 90 if o.hinge == "start" else 270
        a1 = 0 if o.swing == "pos" else 180
    delta = ((a1 - a0 + 540) % 360) - 180
    return {"hinge": [hx, hy], "r": r, "a0": a0, "a1": a0 + delta}


def build_geometry(plan: PlanModel, sol: Solution) -> dict:
    X, Y = sol.x.pos, sol.y.pos
    est = lambda *ids_x_y: any(  # noqa: E731
        (sol.x.status.get(i) == "zeichnung") if ax == "x" else (sol.y.status.get(i) == "zeichnung") for ax, i in ids_x_y)

    def rect(r):
        x0, x1 = sorted((X[r.x0], X[r.x1]))
        y0, y1 = sorted((Y[r.y0], Y[r.y1]))
        return x0, y0, x1, y1, est(("x", r.x0), ("x", r.x1), ("y", r.y0), ("y", r.y1))

    walls = []
    for w in plan.walls:
        x0, y0, x1, y1, e = rect(w)
        walls.append({"rect": [x0, y0, x1, y1], "kind": w.kind, "estimated": e})
    openings = []
    for o in plan.openings:
        x0, y0, x1, y1, e = rect(o)
        openings.append({"type": o.type, "rect": [x0, y0, x1, y1], "estimated": e,
                         "width_stated": o.width_stated, "height_stated": o.height_stated, "sill_stated": o.sill_stated,
                         "swing": door_swing(o, x0, y0, x1, y1)})
    features = []
    for f in plan.features:
        x0, y0, x1, y1, e = rect(f)
        features.append({"type": f.type, "rect": [x0, y0, x1, y1], "estimated": e, "treads": f.treads, "note": f.note})
    rooms = []
    for r in plan.rooms:
        pts = [(X[a], Y[b]) for a, b in r.poly]
        area = polygon_area(pts) / 1e4 if len(pts) >= 3 else None
        if r.label_at:
            label = [X[r.label_at[0]], Y[r.label_at[1]]]
        elif pts:
            label = [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]
        else:
            label = None
        rooms.append({"name": r.name, "area_stated": r.area_stated, "area_geom": round(area, 3) if area else None,
                      "poly": [list(p) for p in pts], "label": label,
                      "estimated": any(est(("x", a), ("y", b)) for a, b in r.poly)})
    zones = [{"type": z.type, "poly": [[X[a], Y[b]] for a, b in z.poly]} for z in plan.zones]

    xs = [v for w in walls for v in (w["rect"][0], w["rect"][2])] or [0]
    ys = [v for w in walls for v in (w["rect"][1], w["rect"][3])] or [0]
    chains = []
    for ch in plan.chains:
        P = X if ch.axis == "x" else Y
        removed = {c.constraint.index for k in sol.ax(ch.axis).conflicts for c in k.candidates[:1]
                   if c.constraint.ref == ch.id and c.constraint.kind == "chain"}
        chains.append({"id": ch.id, "axis": ch.axis, "label": ch.label, "values": ch.values,
                       "positions": [P[l] for l in ch.lines], "total": ch.total, "sum": round(sum(ch.values), 2),
                       "suspect": sorted(removed), "uncertain": ch.uncertain})
    lines = {ax: [{"id": l.id, "pos": sol.ax(ax).pos[l.id], "status": sol.ax(ax).status[l.id],
                   "sigma": sol.ax(ax).sigma[l.id], "label": l.label} for l in plan.axes[ax]] for ax in ("x", "y")}
    return {"bbox": [min(xs), min(ys), max(xs), max(ys)], "walls": walls, "openings": openings, "features": features,
            "rooms": rooms, "zones": zones, "chains": chains, "lines": lines}
