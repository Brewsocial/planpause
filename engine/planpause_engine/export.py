"""Export: DXF (für CAD) und Markdown-Prüfbericht."""
from __future__ import annotations

import io
import math

import ezdxf
from ezdxf.enums import TextEntityAlignment

LAYERS = [("WAENDE", 1), ("BRANDWAND", 6), ("FENSTER", 5), ("TUEREN", 3), ("TORE", 3), ("TREPPE", 7),
          ("BAUTEILE", 8), ("ZONEN", 8), ("RAEUME", 7), ("BEMASSUNG", 8), ("PRUEFPUNKTE", 30), ("GESCHAETZT", 40)]
UNITS = {"mm": (10.0, 4), "cm": (1.0, 5), "m": (0.01, 6)}


def _simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for q in pts:
        if len(out) >= 2 and ((out[-2][0] == out[-1][0] == q[0]) or (out[-2][1] == out[-1][1] == q[1])):
            out[-1] = q
        else:
            out.append(q)
    col = lambda a, b, c: (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1])  # noqa: E731
    while len(out) >= 3 and col(out[-2], out[-1], out[0]):  # Schluss der Schleife
        out.pop()
    while len(out) >= 3 and col(out[-1], out[0], out[1]):
        out.pop(0)
    return out


def union_outlines(rects: list[list[float]]) -> list[list[tuple[float, float]]]:
    """Vereinigung achsparalleler Rechtecke als geschlossene Polygonzüge (Außenränder und Löcher).

    Wände stoßen im Modell als Einzelrechtecke aneinander oder überlappen an den Ecken. Im CAD sollen sie als
    verbundene Flächen erscheinen. Die Rechtecke werden auf ein Raster aus allen Kanten gelegt, die Randkanten
    zwischen gefüllt und leer eingesammelt und zu Schleifen verkettet (gefüllte Seite rechts in Bildkoordinaten)."""
    if not rects:
        return []
    xs = sorted({v for r in rects for v in (r[0], r[2])})
    ys = sorted({v for r in rects for v in (r[1], r[3])})
    xi, yi = {v: i for i, v in enumerate(xs)}, {v: i for i, v in enumerate(ys)}
    nx, ny = len(xs) - 1, len(ys) - 1
    filled = [[False] * ny for _ in range(nx)]
    for x0, y0, x1, y1 in rects:
        for i in range(xi[x0], xi[x1]):
            for j in range(yi[y0], yi[y1]):
                filled[i][j] = True
    f = lambda i, j: 0 <= i < nx and 0 <= j < ny and filled[i][j]  # noqa: E731
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for i in range(nx):
        for j in range(ny + 1):
            below, above = f(i, j), f(i, j - 1)
            if below != above:
                s, e = ((i, j), (i + 1, j)) if below else ((i + 1, j), (i, j))
                edges.setdefault(s, []).append(e)
    for i in range(nx + 1):
        for j in range(ny):
            right, left = f(i, j), f(i - 1, j)
            if right != left:
                s, e = ((i, j + 1), (i, j)) if right else ((i, j), (i, j + 1))
                edges.setdefault(s, []).append(e)
    loops = []
    while edges:
        start = next(iter(edges))
        loop, cur = [start], start
        while cur in edges:
            nxt = edges[cur].pop()
            if not edges[cur]:
                del edges[cur]
            if nxt == start:
                break
            loop.append(nxt)
            cur = nxt
        pts = _simplify([(xs[i], ys[j]) for i, j in loop])
        if len(pts) >= 3:
            loops.append(pts)
    return loops


def to_dxf(geom: dict, issues: list | None = None, unit: str = "mm", title: str = "", dim_print: int = 100) -> bytes:
    """dim_print = Maßstabszahl, für die die Bemaßung bemessen ist (Texte 2 mm hoch auf dem Papier, Maße in cm)."""
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

    # Wände als verbundene Flächen: ein Polygonzug je zusammenhängendem Wandstück statt überlappender Einzelrechtecke
    for layer, kinds in (("WAENDE", ("aussen", "innen")), ("BRANDWAND", ("brand",))):
        loops = union_outlines([w["rect"] for w in geom["walls"] if w["kind"] in kinds])
        if not loops:
            continue
        h = msp.add_hatch(dxfattribs={"layer": layer})
        for pts in loops:
            cad = [P(*q) for q in pts]
            msp.add_lwpolyline(cad, close=True, dxfattribs={"layer": layer})
            h.paths.add_polyline_path(cad)
    for w in geom["walls"]:
        if w["estimated"]:
            rect(w["rect"], "GESCHAETZT")
    # Fenster, Türen und Tore als Blöcke: jedes ein Objekt im CAD, mit Maßen als Attributen.
    # Fenster gleicher Größe teilen sich einen Block (waagerecht definiert, senkrechte um 90° gedreht).
    def num(v):
        return f"{v:g}".replace(".", ",")

    def block(name, layer, draw, tags):
        if name not in doc.blocks:
            b = doc.blocks.new(name)
            draw(b, {"layer": layer})
            for i, tag in enumerate(tags):
                b.add_attdef(tag, (0, -i * 10 * f), dxfattribs={"layer": layer, "height": 10 * f, "flags": 1})
        return name

    def insert(name, layer, at, rotation, values):
        ref = msp.add_blockref(name, at, dxfattribs={"layer": layer, "rotation": rotation})
        for tag, value in values.items():
            ref.add_attrib(tag, value, insert=at, dxfattribs={"layer": layer, "height": 10 * f, "flags": 1})

    doors = 0
    for o in geom["openings"]:
        x0, y0, x1, y1 = o["rect"]
        flat = x1 - x0 >= y1 - y0
        length, depth = (x1 - x0, y1 - y0) if flat else (y1 - y0, x1 - x0)
        at, rotation = (P(x0, y1), 0) if flat else (P(x1, y1), 90)  # untere linke Ecke im CAD
        info = {"BREITE": num(round(length, 1)), "HOEHE": num(o["height_stated"]) if o.get("height_stated") else "nicht im Plan",
                "QUELLE": "geschätzt" if o.get("estimated") else "Maßkette"}
        L, D = length * f, depth * f
        if o["type"] == "window":
            info["BRUESTUNG"] = num(o["sill_stated"]) if o.get("sill_stated") is not None else "nicht im Plan"

            def draw(b, a, L=L, D=D):
                b.add_lwpolyline([(0, 0), (L, 0), (L, D), (0, D)], close=True, dxfattribs=a)
                b.add_line((0, D / 2), (L, D / 2), dxfattribs=a)
            name = block(f"FENSTER_{num(round(length, 1))}x{num(round(depth, 1))}", "FENSTER", draw, list(info))
            insert(name, "FENSTER", at, rotation, info)
        elif o["type"] == "gate":
            def draw(b, a, L=L, D=D):
                b.add_line((0, D / 2), (L, D / 2), dxfattribs={**a, "linetype": "DASHED"})
            name = block(f"TOR_{num(round(length, 1))}x{num(round(depth, 1))}", "TORE", draw, list(info))
            insert(name, "TORE", at, rotation, info)
        elif o["swing"]:  # Aufschlag ist bei jeder Tür anders: eigener Block, Basispunkt am Band
            doors += 1
            sw = o["swing"]
            (hx, hy), r, a0, a1 = sw["hinge"], sw["r"], sw["a0"], sw["a1"]
            lo, hi = sorted((a0, a1))
            ex, ey = r * math.cos(math.radians(a1)), r * math.sin(math.radians(a1))

            def draw(b, a, r=r, lo=lo, hi=hi, ex=ex, ey=ey):
                b.add_arc((0, 0), r * f, start_angle=(-hi) % 360, end_angle=(-lo) % 360, dxfattribs=a)
                b.add_line((0, 0), (ex * f, -ey * f), dxfattribs=a)
            name = block(f"TUER_{doors}_{num(round(length, 1))}", "TUEREN", draw, list(info))
            insert(name, "TUEREN", P(hx, hy), 0, info)
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
    dim = {"dimscale": dim_print * f / 10, "dimtxt": 2.0, "dimasz": 1.5, "dimexo": 1.0, "dimexe": 1.0,
                                    "dimtsz": 1.0, "dimlfac": 1 / f, "dimdec": 1, "dimzin": 8, "dimdsep": ord(","), "dimgap": 0.6}
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
                d = msp.add_linear_dim(base=P(0, y), p1=P(a, y), p2=P(b, y), override=dim, dxfattribs={"layer": "BEMASSUNG"})
            else:
                x = x1 + off if "rechts" in lab else x0 - off
                d = msp.add_linear_dim(base=P(x, 0), p1=P(x, a), p2=P(x, b), angle=90, override=dim, dxfattribs={"layer": "BEMASSUNG"})
            d.render()
    for n, i in enumerate([i for i in (issues or []) if getattr(i, "at", None)], start=1):
        x, y = i.at
        msp.add_circle(P(x, y), 16 * f, dxfattribs={"layer": "PRUEFPUNKTE"})
        msp.add_text(str(n), height=14 * f, dxfattribs={"layer": "PRUEFPUNKTE"}).set_placement(P(x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    if title:
        msp.add_text(title, height=22 * f, dxfattribs={"layer": "0"}).set_placement(P((x0 + x1) / 2, y0 - 200), align=TextEntityAlignment.MIDDLE_CENTER)
    from ezdxf import bbox
    ext = bbox.extents(msp)  # damit CAD-Programme beim Öffnen auf den Plan zoomen
    if ext.has_data:
        msp.reset_extents(ext.extmin, ext.extmax)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def to_report(title: str, geom: dict, issues: list, answers: dict | None = None, checklist: list[dict] | None = None,
              annotations: list[dict] | None = None, purpose: str = "") -> str:
    from .purpose import purpose_label
    sev = {"kritisch": "Kritisch", "pruefen": "Prüfen", "info": "Hinweis"}
    out = [f"# Prüfbericht: {title}", "", "Maße in cm. Geometrie aus Maßketten berechnet (Planpause-Solver)."
           + (f" Verwendungszweck: {purpose_label(purpose)}." if purpose_label(purpose) else " Verwendungszweck: nicht festgelegt."), ""]
    if checklist:
        out += ["## Prüfung vor dem Export", ""]
        for c in checklist:
            out.append(f"- {'✔' if c['ok'] else '✘'} {c['title']}" + (f": {c['detail']}" if c.get("detail") else ""))
        if any(not c["ok"] for c in checklist):
            out.append("")
            out.append("_Nicht bestandene Punkte sind in der Nachmessliste aufgeführt. Der Plan ist bis zur Klärung nicht freigegeben._")
        out.append("")
    out += ["## Nachmessliste", ""]
    for n, i in enumerate(issues, 1):
        out.append(f"- [ ] **{n}. {i.title}** ({sev.get(i.severity, i.severity)}, {i.category}, {i.source})")
        out.append(f"  - {i.detail}")
        if i.action:
            out.append(f"  - Zu tun: {i.action}")
        for m in i.measure:
            exp = f", erwartet ca. {m.expected:g} cm" if m.expected is not None else ""
            out.append(f"  - Messen: {m.text}{exp}")
    est_walls = [w for w in geom["walls"] if w["estimated"]]
    est_open = [o for o in geom["openings"] if o["estimated"]]
    out += ["", "## Geschätzte Bauteile", ""]
    if not est_walls and not est_open:
        out.append("Keine: alle Bauteile liegen auf bemaßten Kanten.")
    kinds = {"aussen": "Außenwand", "innen": "Innenwand", "brand": "Brandwand"}
    for w in est_walls[:40]:
        x0, y0, x1, y1 = w["rect"]
        out.append(f"- {kinds.get(w['kind'], 'Wand')} bei x {x0:g}–{x1:g}, y {y0:g}–{y1:g}: keine Maßkette, Lage nur nach Zeichnung")
    if len(est_walls) > 40:
        out.append(f"- … und {len(est_walls) - 40} weitere Wände")
    names = {"window": "Fenster", "door": "Tür", "gate": "Tor", "passage": "Durchgang"}
    for o in est_open[:40]:
        x0, y0, x1, y1 = o["rect"]
        out.append(f"- {names.get(o['type'], o['type'])} bei x {x0:g}–{x1:g}, y {y0:g}–{y1:g}: Lage oder Breite nicht bemaßt")
    out += ["", "## Räume", "", "| Raum | Plan m² | aus Maßen m² |", "|---|---:|---:|"]
    for r in geom["rooms"]:
        a = f"{r['area_geom']:.2f}" if r["area_geom"] else "–"
        s = f"{r['area_stated']:.2f}" if r["area_stated"] else "–"
        out.append(f"| {r['name']}{' (Name ergänzt)' if r.get('name_assumed') else ''} | {s} | {a} |")
    out += ["", "## Maßketten", "", "| Kette | Summe | Gesamtmaß | verdächtig |", "|---|---:|---:|---|"]
    for c in geom["chains"]:
        sus = ", ".join(str(c["values"][i]) for i in c["suspect"]) or "–"
        out.append(f"| {c['label'] or c['id']} | {c['sum']:g} | {c['total'] if c['total'] is not None else '–'} | {sus} |")
    if annotations:
        kinds_a = {"handschriftlich": "handschriftlich", "stempel": "Stempel", "hoehenkote": "Höhenkote", "schraffur": "Schraffur/Material", "sonstiges": "Vermerk"}
        out += ["", "## Im Plan vermerkt, nicht gezeichnet", "", "Diese Angaben stehen im Plan und sind nicht in DXF/IFC übernommen:", ""]
        out += [f"- {kinds_a.get(a.get('kind', ''), 'Vermerk')}: {a['text']}" for a in annotations]
    if answers:
        out += ["", "## Angaben vor Ort", ""] + [f"- {k}: {v}" for k, v in answers.items()]
    out += ["", "_Rekonstruktion aus einem Bestandsplan. Vor Umbauten vor Ort nachmessen und tragende Bauteile vom Statiker bestätigen lassen._"]
    return "\n".join(out)
