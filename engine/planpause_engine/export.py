"""Export: DXF (für CAD) und Markdown-Prüfbericht."""
from __future__ import annotations

import io
import math

import ezdxf
from ezdxf.enums import TextEntityAlignment

LAYERS = [("WAENDE", 1), ("BRANDWAND", 6), ("FENSTER", 5), ("TUEREN", 3), ("TORE", 3), ("TREPPE", 7),
          ("BAUTEILE", 8), ("ZONEN", 8), ("RAEUME", 7), ("BEMASSUNG", 8), ("PRUEFPUNKTE", 30), ("GESCHAETZT", 40)]
UNITS = {"mm": (10.0, 4), "cm": (1.0, 5), "m": (0.01, 6)}


def to_dxf(geom: dict, issues: list | None = None, unit: str = "mm", title: str = "") -> bytes:
    f, code = UNITS[unit]
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = code
    for name, color in LAYERS:
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    P = lambda x, y: (x * f, -y * f)  # noqa: E731  (y nach oben im CAD)

    def rect(r, layer, fill=False):
        x0, y0, x1, y1 = r
        pts = [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
        if fill:
            h = msp.add_hatch(dxfattribs={"layer": layer})
            h.paths.add_polyline_path(pts)

    for w in geom["walls"]:
        rect(w["rect"], "BRANDWAND" if w["kind"] == "brand" else "WAENDE", fill=True)
        if w["estimated"]:
            rect(w["rect"], "GESCHAETZT")
    for o in geom["openings"]:
        x0, y0, x1, y1 = o["rect"]
        if o["type"] == "window":
            rect(o["rect"], "FENSTER")
            if x1 - x0 >= y1 - y0:
                msp.add_line(P(x0, (y0 + y1) / 2), P(x1, (y0 + y1) / 2), dxfattribs={"layer": "FENSTER"})
            else:
                msp.add_line(P((x0 + x1) / 2, y0), P((x0 + x1) / 2, y1), dxfattribs={"layer": "FENSTER"})
        elif o["type"] == "gate":
            msp.add_line(P(x0, (y0 + y1) / 2), P(x1, (y0 + y1) / 2), dxfattribs={"layer": "TORE", "linetype": "DASHED"})
        elif o["swing"]:
            s = o["swing"]
            (hx, hy), r, a0, a1 = s["hinge"], s["r"], s["a0"], s["a1"]
            lo, hi = sorted((a0, a1))
            msp.add_arc(P(hx, hy), r * f, start_angle=(-hi) % 360, end_angle=(-lo) % 360, dxfattribs={"layer": "TUEREN"})
            ex, ey = hx + r * math.cos(math.radians(a1)), hy + r * math.sin(math.radians(a1))
            msp.add_line(P(hx, hy), P(ex, ey), dxfattribs={"layer": "TUEREN"})
    for ft in geom["features"]:
        x0, y0, x1, y1 = ft["rect"]
        layer = "TREPPE" if ft["type"].lower().startswith("treppe") else "BAUTEILE"
        rect(ft["rect"], layer)
        if layer == "TREPPE":
            n = ft.get("treads") or max(2, round(max(x1 - x0, y1 - y0) / 25))
            for i in range(1, n):
                if y1 - y0 >= x1 - x0:
                    yy = y0 + (y1 - y0) * i / n
                    msp.add_line(P(x0, yy), P(x1, yy), dxfattribs={"layer": "TREPPE"})
                else:
                    xx = x0 + (x1 - x0) * i / n
                    msp.add_line(P(xx, y0), P(xx, y1), dxfattribs={"layer": "TREPPE"})
    for z in geom["zones"]:
        msp.add_lwpolyline([P(*p) for p in z["poly"]], close=True, dxfattribs={"layer": "ZONEN"})
    for r in geom["rooms"]:
        if r["poly"]:
            msp.add_lwpolyline([P(*p) for p in r["poly"]], close=True, dxfattribs={"layer": "RAEUME"})
        if r["label"]:
            lx, ly = r["label"]
            msp.add_text(r["name"], height=18 * f, dxfattribs={"layer": "RAEUME"}).set_placement(P(lx, ly), align=TextEntityAlignment.MIDDLE_CENTER)
            a = r["area_stated"] or r["area_geom"]
            if a:
                msp.add_text(f"{a:.2f} m²".replace(".", ","), height=13 * f, dxfattribs={"layer": "RAEUME"}).set_placement(P(lx, ly + 28), align=TextEntityAlignment.MIDDLE_CENTER)
    x0, y0, x1, y1 = geom["bbox"]
    for k, ch in enumerate(geom["chains"]):
        pos = ch["positions"]
        lab = (ch["label"] or ch["id"]).lower()
        off = 60 + 45 * (k % 3)
        for i in range(len(pos) - 1):
            a, b = pos[i], pos[i + 1]
            if abs(b - a) < 0.1:
                continue
            if ch["axis"] == "x":
                y = y1 + off if "unten" in lab else y0 - off
                d = msp.add_linear_dim(base=P(0, y), p1=P(a, y), p2=P(b, y), dxfattribs={"layer": "BEMASSUNG"})
            else:
                x = x1 + off if "rechts" in lab else x0 - off
                d = msp.add_linear_dim(base=P(x, 0), p1=P(x, a), p2=P(x, b), angle=90, dxfattribs={"layer": "BEMASSUNG"})
            d.render()
    for n, i in enumerate([i for i in (issues or []) if getattr(i, "at", None)], start=1):
        x, y = i.at
        msp.add_circle(P(x, y), 16 * f, dxfattribs={"layer": "PRUEFPUNKTE"})
        msp.add_text(str(n), height=14 * f, dxfattribs={"layer": "PRUEFPUNKTE"}).set_placement(P(x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    if title:
        msp.add_text(title, height=22 * f, dxfattribs={"layer": "0"}).set_placement(P((x0 + x1) / 2, y0 - 200), align=TextEntityAlignment.MIDDLE_CENTER)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def to_report(title: str, geom: dict, issues: list, answers: dict | None = None) -> str:
    sev = {"kritisch": "Kritisch", "pruefen": "Prüfen", "info": "Hinweis"}
    out = [f"# Prüfbericht: {title}", "", "Maße in cm. Geometrie aus Maßketten berechnet (Planpause-Solver).", "",
           "## Nachmessliste", ""]
    for n, i in enumerate(issues, 1):
        out.append(f"- [ ] **{n}. {i.title}** ({sev.get(i.severity, i.severity)}, {i.category}, {i.source})")
        out.append(f"  - {i.detail}")
        if i.action:
            out.append(f"  - Zu tun: {i.action}")
        for m in i.measure:
            exp = f", erwartet ca. {m.expected:g} cm" if m.expected is not None else ""
            out.append(f"  - Messen: {m.text}{exp}")
    out += ["", "## Räume", "", "| Raum | Plan m² | aus Maßen m² |", "|---|---:|---:|"]
    for r in geom["rooms"]:
        a = f"{r['area_geom']:.2f}" if r["area_geom"] else "–"
        s = f"{r['area_stated']:.2f}" if r["area_stated"] else "–"
        out.append(f"| {r['name']} | {s} | {a} |")
    out += ["", "## Maßketten", "", "| Kette | Summe | Gesamtmaß | verdächtig |", "|---|---:|---:|---|"]
    for c in geom["chains"]:
        sus = ", ".join(str(c["values"][i]) for i in c["suspect"]) or "–"
        out.append(f"| {c['label'] or c['id']} | {c['sum']:g} | {c['total'] if c['total'] is not None else '–'} | {sus} |")
    if answers:
        out += ["", "## Angaben vor Ort", ""] + [f"- {k}: {v}" for k, v in answers.items()]
    out += ["", "_Rekonstruktion aus einem Bestandsplan. Vor Umbauten vor Ort nachmessen und tragende Bauteile vom Statiker bestätigen lassen._"]
    return "\n".join(out)
