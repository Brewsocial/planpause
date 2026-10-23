"""Mehrere Grundrisse eines Geschosses zu einem Plan zusammensetzen.

Getrennte Zeichnungen (z. B. Altbau, Anbau, Garage) werden einzeln analysiert und nachgerechnet, jede in
ihrem eigenen Koordinatensystem (cm, y nach unten). Für das Geschoss wird jede Zeichnung um ein Vielfaches
von 90° gedreht und verschoben: p' = R(rot) · p + (dx, dy). Achsparallele Bauteile bleiben dabei achsparallel.
"""
from __future__ import annotations

import copy

ROTATIONS = (0, 90, 180, 270)


def _rot(x: float, y: float, rot: int) -> tuple[float, float]:
    # y zeigt nach unten: +90° dreht im Bild im Uhrzeigersinn
    if rot == 90:
        return -y, x
    if rot == 180:
        return -x, -y
    if rot == 270:
        return y, -x
    return x, y


def _pt(p, rot: int, dx: float, dy: float) -> list[float]:
    x, y = _rot(p[0], p[1], rot)
    return [round(x + dx, 3), round(y + dy, 3)]


def _rect(r, rot: int, dx: float, dy: float) -> list[float]:
    (ax, ay), (bx, by) = _pt(r[:2], rot, dx, dy), _pt(r[2:], rot, dx, dy)
    return [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]


def _axis_map(axis: str, rot: int, dx: float, dy: float):
    """Wohin eine Lage auf einer Achse wandert: (neue Achse, Abbildung der Koordinate)."""
    if rot in (0, 180):
        sign = 1 if rot == 0 else -1
        return axis, (lambda v: round(sign * v + (dx if axis == "x" else dy), 3))
    if rot == 90:  # x -> y, y -> -x
        return ("y", lambda v: round(v + dy, 3)) if axis == "x" else ("x", lambda v: round(-v + dx, 3))
    return ("y", lambda v: round(-v + dy, 3)) if axis == "x" else ("x", lambda v: round(v + dx, 3))  # 270


def transform_geometry(geom: dict, dx: float = 0.0, dy: float = 0.0, rot: int = 0) -> dict:
    """Gibt eine gedrehte und verschobene Kopie der Geometrie zurück (Format wie build_geometry)."""
    if rot not in ROTATIONS:
        raise ValueError(f"Drehung muss 0, 90, 180 oder 270 Grad sein, nicht {rot}")
    g = copy.deepcopy(geom)
    for w in g["walls"]:
        w["rect"] = _rect(w["rect"], rot, dx, dy)
    for o in g["openings"]:
        o["rect"] = _rect(o["rect"], rot, dx, dy)
        if o.get("swing"):
            s = o["swing"]
            s["hinge"] = _pt(s["hinge"], rot, dx, dy)
            s["a0"], s["a1"] = s["a0"] + rot, s["a1"] + rot
    for f in g["features"]:
        f["rect"] = _rect(f["rect"], rot, dx, dy)
    for r in g["rooms"]:
        r["poly"] = [_pt(p, rot, dx, dy) for p in r["poly"]]
        if r.get("label"):
            r["label"] = _pt(r["label"], rot, dx, dy)
    for z in g["zones"]:
        z["poly"] = [_pt(p, rot, dx, dy) for p in z["poly"]]
    for c in g["chains"]:
        axis, f = _axis_map(c["axis"], rot, dx, dy)
        pos = [f(v) for v in c["positions"]]
        if pos and pos[0] > pos[-1]:  # Kette in Leserichtung halten (links→rechts, oben→unten)
            pos, c["values"] = pos[::-1], c["values"][::-1]
            n = len(c["values"])
            c["suspect"] = sorted(n - 1 - i for i in c["suspect"])
            c["uncertain"] = sorted(n - 1 - i for i in c["uncertain"])
        c["axis"], c["positions"] = axis, pos
    lines = {"x": [], "y": []}
    for ax in ("x", "y"):
        for l in g["lines"][ax]:
            new_ax, f = _axis_map(ax, rot, dx, dy)
            lines[new_ax].append({**l, "pos": f(l["pos"])})
    g["lines"] = lines
    g["bbox"] = bbox_of(g)
    return g


def bbox_of(g: dict) -> list[float]:
    xs = [v for w in g["walls"] for v in (w["rect"][0], w["rect"][2])]
    ys = [v for w in g["walls"] for v in (w["rect"][1], w["rect"][3])]
    if not xs:
        return list(g.get("bbox") or [0, 0, 0, 0])
    return [min(xs), min(ys), max(xs), max(ys)]


def default_layout(sizes: list[tuple[float, float]], gap: float = 150.0) -> list[dict]:
    """Ohne gespeicherte Anordnung: Teile nebeneinander, damit nichts überlappt."""
    out, x = [], 0.0
    for w, _h in sizes:
        out.append({"dx": x, "dy": 0.0, "rot": 0})
        x += w + gap
    return out


def combine(parts: list[dict]) -> dict:
    """Setzt Teile zu einem Geschoss zusammen.

    parts: [{"id", "label", "geometry", "dx", "dy", "rot"}]. Jedes Element des Ergebnisses trägt "part" (die id),
    damit Anzeige und Export die Teile unterscheiden können.
    """
    merged = {"walls": [], "openings": [], "features": [], "rooms": [], "zones": [], "chains": [], "lines": {"x": [], "y": []}}
    meta = []
    for p in parts:
        g = transform_geometry(p["geometry"], p.get("dx", 0.0), p.get("dy", 0.0), p.get("rot", 0))
        for key in ("walls", "openings", "features", "rooms", "zones"):
            merged[key] += [{**e, "part": p["id"]} for e in g[key]]
        merged["chains"] += [{**c, "id": f"{p['id']}:{c['id']}", "part": p["id"]} for c in g["chains"]]
        for ax in ("x", "y"):
            merged["lines"][ax] += [{**l, "id": f"{p['id']}:{l['id']}", "part": p["id"]} for l in g["lines"][ax]]
        meta.append({"id": p["id"], "label": p.get("label", ""), "bbox": g["bbox"],
                     "dx": p.get("dx", 0.0), "dy": p.get("dy", 0.0), "rot": p.get("rot", 0)})
    merged["bbox"] = bbox_of(merged) if merged["walls"] else [0, 0, 0, 0]
    merged["parts"] = meta
    return merged
