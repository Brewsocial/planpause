"""Export als IFC (BIM-Bestandsmodell) mit IfcOpenShell.

Aus der Geometrie (Format wie build_geometry bzw. combine, cm, y nach unten) entsteht ein IFC4-Modell:
Wände als Körper mit Öffnungen, Fenster und Türen als Bauteile in den Öffnungen, Räume als IfcSpace mit Fläche.
Ein Grundriss enthält meist keine Höhen. Raumhöhe, Fenster- und Türhöhen sind deshalb Annahmen, solange der Plan
nichts anderes angibt. Jedes Bauteil trägt im Merkmalsatz „Planpause_Bestand“, was geschätzt oder angenommen ist.

In der Geometrie liegen Öffnungen in Lücken zwischen Wandstücken (wie in der DXF gezeichnet). Für das Modell
bekommt jede Lücke ein Wandstück in voller Höhe, in das die Öffnung geschnitten wird. So entstehen Brüstung
und Sturz.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

# Annahmen in cm, wenn der Plan keine Höhe nennt
DOOR_HEIGHT = 201.0   # Rohbaurichtmaß
WINDOW_SILL = 90.0
WINDOW_TOP = 226.0    # Sturzhöhe über Fußboden
GATE_HEIGHT = 225.0
STAIR_MARK = 2.0      # Treppen als flache Umrissmarke: Lauf und Steigung stehen nicht im Grundriss

FEATURES = {"treppe": "IfcStair", "stütze": "IfcColumn", "stuetze": "IfcColumn", "schornstein": "IfcChimney", "kamin": "IfcChimney"}
LABELS = {"window": "Fenster", "door": "Tür", "gate": "Tor", "passage": "Durchgang"}


def _m(v: float) -> float:
    return round(v / 100.0, 4)


def _box(r: list[float]) -> tuple[float, float, float, float]:
    """Rechteck aus der Geometrie (cm, y nach unten) als (xmin, ymin, xmax, ymax) in m mit y nach oben."""
    x0, y0, x1, y1 = r
    return _m(x0), _m(-y1), _m(x1), _m(-y0)


def _matrix(x: float, y: float, z: float, vertical: bool) -> np.ndarray:
    """Platzierung: lokale x-Achse entlang des Bauteils. Senkrechte Bauteile um 90° gedreht (lokal y zeigt nach -x)."""
    m = np.eye(4)
    if vertical:
        m[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    m[:3, 3] = [x, y, z]
    return m


def _overlap(a: list[float], b: list[float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def _runs_vertical(r: list[float], walls: list[dict]) -> bool:
    """Verläuft die Wand an dieser Stelle senkrecht? Entscheidend ist, wo Nachbarwände anschließen."""
    x0, y0, x1, y1 = r
    along_x = sum(_overlap([x0 - 2, y0 + 0.5, x1 + 2, y1 - 0.5], w["rect"]) > 0 for w in walls)
    along_y = sum(_overlap([x0 + 0.5, y0 - 2, x1 - 0.5, y1 + 2], w["rect"]) > 0 for w in walls)
    if along_x != along_y:
        return along_y > along_x
    return (y1 - y0) > (x1 - x0)


def to_ifc(storeys: list[dict], title: str = "", height: float = 250.0) -> bytes:
    """storeys: [{"name", "geometry", "elevation" (cm, optional)}]; height = lichte Raumhöhe in cm (Annahme)."""
    import ifcopenshell.api as api
    import ifcopenshell.api.aggregate, ifcopenshell.api.context, ifcopenshell.api.feature  # noqa: E401,F401
    import ifcopenshell.api.geometry, ifcopenshell.api.project, ifcopenshell.api.pset  # noqa: E401,F401
    import ifcopenshell.api.root, ifcopenshell.api.spatial, ifcopenshell.api.unit  # noqa: E401,F401

    f = api.project.create_file(version="IFC4")
    project = api.root.create_entity(f, ifc_class="IfcProject", name=title or "Planpause Bestandsmodell")
    api.unit.assign_unit(f)  # SI: Meter, Quadratmeter, Kubikmeter
    model = api.context.add_context(f, context_type="Model")
    body = api.context.add_context(f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model)
    site = api.root.create_entity(f, ifc_class="IfcSite", name="Grundstück")
    building = api.root.create_entity(f, ifc_class="IfcBuilding", name=title or "Gebäude")
    api.aggregate.assign_object(f, products=[site], relating_object=project)
    api.aggregate.assign_object(f, products=[building], relating_object=site)
    h = _m(height)

    def mark(el, **props):
        pset = api.pset.add_pset(f, product=el, name="Planpause_Bestand")
        api.pset.edit_pset(f, pset=pset, properties={"Quelle": "Planpause: aus Maßketten eines Bestandsplans berechnet", **props})

    def place(el, rep, x, y, z, vertical=False):
        api.geometry.edit_object_placement(f, product=el, matrix=_matrix(x, y, z, vertical))
        api.geometry.assign_representation(f, product=el, representation=rep)

    for n, st in enumerate(storeys):
        g = st["geometry"]
        z0 = _m(st.get("elevation", n * (height + 30.0)))  # ohne Angabe: Raumhöhe plus angenommene Decke
        storey = api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=st.get("name") or f"Geschoss {n + 1}")
        storey.Elevation = z0
        api.geometry.edit_object_placement(f, product=storey, matrix=_matrix(0, 0, z0, False))
        api.aggregate.assign_object(f, products=[storey], relating_object=building)
        contained = []

        def add_wall(rect, vertical, name, kind="innen", estimated=False):
            xa, ya, xb, yb = _box(rect)
            length, thick = (yb - ya, xb - xa) if vertical else (xb - xa, yb - ya)
            if length <= 0 or thick <= 0:
                return None
            el = api.root.create_entity(f, ifc_class="IfcWall", name=name)
            rep = api.geometry.add_wall_representation(f, context=body, length=length, height=h, thickness=thick)
            place(el, rep, xb if vertical else xa, ya, z0, vertical)
            common = api.pset.add_pset(f, product=el, name="Pset_WallCommon")
            api.pset.edit_pset(f, pset=common, properties={"IsExternal": kind in ("aussen", "brand"),
                                                           **({"FireRating": "Brandwand"} if kind == "brand" else {})})
            mark(el, Geschaetzt=bool(estimated), HoeheAngenommen=True)
            contained.append(el)
            return {"el": el, "vertical": vertical, "thick": thick, "rect": rect, "kind": kind}

        walls = []
        for i, w in enumerate(g["walls"]):
            x0, y0, x1, y1 = w["rect"]
            wall = add_wall(w["rect"], (y1 - y0) > (x1 - x0), f"Wand {i + 1}", w["kind"], w.get("estimated"))
            if wall:
                walls.append(wall)

        for o in g["openings"]:
            kind, r = o["type"], o["rect"]
            area = (r[2] - r[0]) * (r[3] - r[1])
            host = max(walls, key=lambda w: _overlap(r, w["rect"]), default=None)
            if host is None or _overlap(r, host["rect"]) < 0.5 * area:  # Öffnung liegt in einer Lücke: Wandstück einsetzen
                neighbours = [w for w in walls if _overlap([r[0] - 2, r[1] - 2, r[2] + 2, r[3] + 2], w["rect"]) > 0]
                host = add_wall(r, _runs_vertical(r, walls), f"Wand ({LABELS[kind]})",
                                "aussen" if any(w["kind"] in ("aussen", "brand") for w in neighbours) else "innen",
                                o.get("estimated"))
                if host is None:
                    continue
            xa, ya, xb, yb = _box(r)
            width = (yb - ya) if host["vertical"] else (xb - xa)
            stated_h = o.get("height_stated")
            if kind == "window":
                sill = o.get("sill_stated") if o.get("sill_stated") is not None else WINDOW_SILL
                oh = stated_h or (WINDOW_TOP - sill)
            else:
                sill = 0.0
                oh = stated_h or (GATE_HEIGHT if kind == "gate" else DOOR_HEIGHT)
            sill_m = _m(sill)
            oh_m = min(_m(oh), h - sill_m - 0.01)
            if width <= 0 or oh_m <= 0:
                continue
            assumed = stated_h is None or (kind == "window" and o.get("sill_stated") is None)
            hx = _box(host["rect"])
            # Öffnung etwas dicker als die Wand, damit sie sauber durchschneidet
            ox, oy = (hx[2] + 0.05, ya) if host["vertical"] else (xa, hx[1] - 0.05)
            opening = api.root.create_entity(f, ifc_class="IfcOpeningElement", name=f"Öffnung {LABELS[kind]}")
            rep = api.geometry.add_wall_representation(f, context=body, length=width, height=oh_m, thickness=host["thick"] + 0.1)
            place(opening, rep, ox, oy, z0 + sill_m, host["vertical"])
            api.feature.add_feature(f, feature=opening, element=host["el"])
            if kind == "passage":
                continue
            cls, ptype = ("IfcWindow", "WINDOW") if kind == "window" else ("IfcDoor", "GATE" if kind == "gate" else "DOOR")
            el = api.root.create_entity(f, ifc_class=cls, predefined_type=ptype, name=LABELS[kind])
            el.OverallWidth, el.OverallHeight = width, oh_m
            pane = 0.07 if kind == "window" else 0.05
            mid = (host["thick"] - pane) / 2
            px, py = (hx[2] - mid, ya) if host["vertical"] else (xa, hx[1] + mid)
            rep = api.geometry.add_wall_representation(f, context=body, length=width, height=oh_m, thickness=pane)
            place(el, rep, px, py, z0 + sill_m, host["vertical"])
            api.feature.add_filling(f, opening=opening, element=el)
            mark(el, Geschaetzt=bool(o.get("estimated")), HoeheAngenommen=assumed)
            contained.append(el)

        for ft in g["features"]:
            xa, ya, xb, yb = _box(ft["rect"])
            if xb - xa <= 0 or yb - ya <= 0:
                continue
            key = ft["type"].lower()
            cls = next((c for k, c in FEATURES.items() if key.startswith(k)), "IfcBuildingElementProxy")
            el = api.root.create_entity(f, ifc_class=cls, name=ft["type"])
            depth = _m(STAIR_MARK) if cls == "IfcStair" else h
            rep = api.geometry.add_slab_representation(f, context=body, depth=depth,
                                                       polyline=[(0, 0), (xb - xa, 0), (xb - xa, yb - ya), (0, yb - ya)])
            place(el, rep, xa, ya, z0)
            mark(el, Geschaetzt=bool(ft.get("estimated")), HoeheAngenommen=True, Hinweis=ft.get("note") or "")
            contained.append(el)

        spaces = []
        for r in g["rooms"]:
            pts = [(_m(x), _m(-y)) for x, y in r["poly"]]
            if len(pts) < 3:
                continue
            area = r.get("area_stated") or r.get("area_geom")
            sp = api.root.create_entity(f, ifc_class="IfcSpace", name=r["name"])
            sp.LongName = r["name"]
            rep = api.geometry.add_slab_representation(f, context=body, depth=h, polyline=pts)
            place(sp, rep, 0, 0, z0)
            if area:
                qto = api.pset.add_qto(f, product=sp, name="Qto_SpaceBaseQuantities")
                api.pset.edit_qto(f, qto=qto, properties={"NetFloorArea": round(area, 2), "Height": h,
                                                          "NetVolume": round(area * h, 2)})
            mark(sp, Geschaetzt=bool(r.get("estimated")), HoeheAngenommen=True,
                 FlaecheLautPlan=r.get("area_stated") or 0.0, FlaecheAusMassen=r.get("area_geom") or 0.0)
            spaces.append(sp)
        if spaces:
            api.aggregate.assign_object(f, products=spaces, relating_object=storey)
        if contained:
            api.spatial.assign_container(f, products=contained, relating_structure=storey)

    with tempfile.TemporaryDirectory() as d:  # write() schreibt nur in Dateien
        p = Path(d) / "modell.ifc"
        f.write(str(p))
        return p.read_bytes()
