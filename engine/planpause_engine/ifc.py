"""Export als IFC (BIM-Bestandsmodell) mit IfcOpenShell.

Aus der Geometrie (Format wie build_geometry bzw. combine, cm, y nach unten) entsteht ein IFC4-Modell:
Wände als Körper mit Öffnungen, Fenster und Türen als Bauteile in den Öffnungen, Räume als IfcSpace mit Fläche.
Ein Grundriss enthält meist keine Höhen. Raumhöhe, Fenster- und Türhöhen sind deshalb Annahmen, solange der Plan
nichts anderes angibt. Jedes Bauteil trägt im Merkmalsatz „Planpause_Bestand“, was geschätzt oder angenommen ist.

Für ein ganzes Gebäude werden mehrere Geschosse übereinander gestapelt. Decken und Dach folgen dem Umriss, der sich
aus Wänden und Räumen ergibt (outline). Teile eines Geschosses können in der Höhe versetzt sein („dz“, z. B. bei
Häusern mit versetzten Geschossen), jedes Element trägt dann seinen Versatz.

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
SLAB = 20.0           # Deckendicke, wenn nichts angegeben ist
PARAPET = 30.0        # Attika über dem Flachdach
OUTLINE_CELL = 5.0    # Raster für den Gebäudeumriss

FEATURES = {"treppe": "IfcStair", "stütze": "IfcColumn", "stuetze": "IfcColumn", "schornstein": "IfcChimney", "kamin": "IfcChimney"}
LABELS = {"window": "Fenster", "door": "Tür", "gate": "Tor", "passage": "Durchgang"}


def _m(v: float) -> float:
    return round(v / 100.0, 4)


def _box(r: list[float]) -> tuple[float, float, float, float]:
    """Rechteck aus der Geometrie (cm, y nach unten) als (xmin, ymin, xmax, ymax) in m mit y nach oben."""
    x0, y0, x1, y1 = r
    return _m(x0), _m(-y1), _m(x1), _m(-y0)


def _matrix(x: float, y: float, z: float, vertical: bool | float) -> np.ndarray:
    """Platzierung: lokale x-Achse entlang des Bauteils. Senkrechte Bauteile um 90° gedreht (lokal y zeigt nach -x).
    Statt True/False geht auch ein Winkel im Bogenmaß."""
    m = np.eye(4)
    a = (np.pi / 2 if vertical else 0.0) if isinstance(vertical, bool) else float(vertical)
    c, s = round(np.cos(a), 12), round(np.sin(a), 12)
    m[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    m[:3, 3] = [x, y, z]
    return m


def outline(geometry: dict) -> list[tuple[float, list[tuple[float, float]]]]:
    """Gebäudeumriss je Höhenversatz: [(dz, Polygon in cm, y nach unten)], aus Wänden, Öffnungen und Räumen gerastert."""
    import cv2

    groups: dict[float, list] = {}
    for key in ("walls", "openings"):
        for e in geometry.get(key, []):
            groups.setdefault(float(e.get("dz") or 0), []).append(("rect", e["rect"]))
    for r in geometry.get("rooms", []):
        if len(r.get("poly") or []) >= 3:
            groups.setdefault(float(r.get("dz") or 0), []).append(("poly", r["poly"]))
    out = []
    for dz, items in sorted(groups.items()):
        pts = [p for kind, v in items for p in ([v[:2], v[2:]] if kind == "rect" else v)]
        x0, y0 = min(p[0] for p in pts) - 50, min(p[1] for p in pts) - 50
        x1, y1 = max(p[0] for p in pts) + 50, max(p[1] for p in pts) + 50
        c = OUTLINE_CELL
        img = np.zeros((int((y1 - y0) / c) + 1, int((x1 - x0) / c) + 1), np.uint8)
        px = lambda x, y: (int(round((x - x0) / c)), int(round((y - y0) / c)))  # noqa: E731
        for kind, v in items:
            if kind == "rect":
                cv2.rectangle(img, px(v[0], v[1]), px(v[2], v[3]), 255, -1)
            else:
                cv2.fillPoly(img, [np.array([px(*p) for p in v], np.int32)], 255)
        # kleine Lücken (Fugen, nicht gezeichnete Türen) schließen, Löcher füllen
        img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            if cv2.contourArea(cnt) * c * c < 4e4:  # unter 4 m²: Reste, keine Decke
                continue
            poly = cv2.approxPolyDP(cnt, 1.5, True)[:, 0, :]
            out.append((dz, [(round(x0 + float(p[0]) * c, 1), round(y0 + float(p[1]) * c, 1)) for p in poly]))
    return out


def _ccw(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))
    return poly if a > 0 else poly[::-1]


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
    """storeys: [{"name", "geometry", "elevation" (cm, optional), "height" (lichte Höhe in cm, optional),
    "slab" (Deckendicke unter dem Geschoss in cm, optional), "roof" (Flachdach darüber), "assumed" (Höhe angenommen)}].
    height = lichte Raumhöhe in cm, wenn ein Geschoss keine eigene hat (Annahme)."""
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

    def mark(el, **props):
        pset = api.pset.add_pset(f, product=el, name="Planpause_Bestand")
        api.pset.edit_pset(f, pset=pset, properties={"Quelle": "Planpause: aus Maßketten eines Bestandsplans berechnet", **props})

    def place(el, rep, x, y, z, vertical=False):
        api.geometry.edit_object_placement(f, product=el, matrix=_matrix(x, y, z, vertical))
        api.geometry.assign_representation(f, product=el, representation=rep)

    for n, st in enumerate(storeys):
        g = st["geometry"]
        h = _m(st.get("height") or height)
        h_assumed = st.get("assumed", True)
        base = _m(st.get("elevation", n * (height + 30.0)))  # ohne Angabe: Raumhöhe plus angenommene Decke
        storey = api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=st.get("name") or f"Geschoss {n + 1}")
        storey.Elevation = base
        api.geometry.edit_object_placement(f, product=storey, matrix=_matrix(0, 0, base, False))
        api.aggregate.assign_object(f, products=[storey], relating_object=building)
        contained = []
        zof = lambda e: base + _m(e.get("dz") or 0)  # noqa: E731 – Höhenversatz des Gebäudeteils

        for dz, poly in (outline(g) if st.get("slab") or st.get("roof") else []):
            pts = _ccw([(_m(x), _m(-y)) for x, y in poly])
            zz = base + _m(dz)
            if st.get("slab"):
                el = api.root.create_entity(f, ifc_class="IfcSlab", predefined_type="FLOOR", name="Decke")
                rep = api.geometry.add_slab_representation(f, context=body, depth=_m(st["slab"]), polyline=pts)
                place(el, rep, 0, 0, zz - _m(st["slab"]))
                mark(el, Geschaetzt=True, HoeheAngenommen=h_assumed, Hinweis="Umriss aus den Wänden, Dicke angenommen")
                contained.append(el)
            if st.get("roof"):
                d = _m(st.get("slab") or SLAB)
                el = api.root.create_entity(f, ifc_class="IfcSlab", predefined_type="ROOF", name="Flachdach")
                rep = api.geometry.add_slab_representation(f, context=body, depth=d, polyline=pts)
                place(el, rep, 0, 0, zz + h)
                mark(el, Geschaetzt=True, HoeheAngenommen=True, Hinweis="Dachform angenommen")
                contained.append(el)
                for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):  # Attika entlang des Umrisses, nach innen
                    length = float(np.hypot(xb - xa, yb - ya))
                    if length < 0.05:
                        continue
                    el = api.root.create_entity(f, ifc_class="IfcWall", name="Attika")
                    rep = api.geometry.add_wall_representation(f, context=body, length=length, height=_m(PARAPET), thickness=0.25)
                    place(el, rep, xa, ya, zz + h + d, float(np.arctan2(yb - ya, xb - xa)))
                    common = api.pset.add_pset(f, product=el, name="Pset_WallCommon")
                    api.pset.edit_pset(f, pset=common, properties={"IsExternal": True})
                    mark(el, Geschaetzt=True, HoeheAngenommen=True)
                    contained.append(el)

        def add_wall(rect, vertical, name, kind="innen", estimated=False, z0=base):
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
            mark(el, Geschaetzt=bool(estimated), HoeheAngenommen=h_assumed)
            contained.append(el)
            return {"el": el, "vertical": vertical, "thick": thick, "rect": rect, "kind": kind, "z0": z0}

        walls = []
        for i, w in enumerate(g["walls"]):
            x0, y0, x1, y1 = w["rect"]
            wall = add_wall(w["rect"], (y1 - y0) > (x1 - x0), f"Wand {i + 1}", w["kind"], w.get("estimated"), zof(w))
            if wall:
                walls.append(wall)

        for o in g["openings"]:
            kind, r = o["type"], o["rect"]
            area = (r[2] - r[0]) * (r[3] - r[1])
            z0 = zof(o)
            host = max((w for w in walls if abs(w["z0"] - z0) < 1e-6), key=lambda w: _overlap(r, w["rect"]), default=None)
            if host is None or _overlap(r, host["rect"]) < 0.5 * area:  # Öffnung liegt in einer Lücke: Wandstück einsetzen
                same = [w for w in walls if abs(w["z0"] - z0) < 1e-6]
                neighbours = [w for w in same if _overlap([r[0] - 2, r[1] - 2, r[2] + 2, r[3] + 2], w["rect"]) > 0]
                host = add_wall(r, _runs_vertical(r, same), f"Wand ({LABELS[kind]})",
                                "aussen" if any(w["kind"] in ("aussen", "brand") for w in neighbours) else "innen",
                                o.get("estimated"), z0)
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
            mark(el, Geschaetzt=bool(o.get("estimated")), HoeheAngenommen=assumed or h_assumed)
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
            place(el, rep, xa, ya, zof(ft))
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
            place(sp, rep, 0, 0, zof(r))
            if area:
                qto = api.pset.add_qto(f, product=sp, name="Qto_SpaceBaseQuantities")
                api.pset.edit_qto(f, qto=qto, properties={"NetFloorArea": round(area, 2), "Height": h,
                                                          "NetVolume": round(area * h, 2)})
            mark(sp, Geschaetzt=bool(r.get("estimated")), HoeheAngenommen=h_assumed,
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


def to_meshes(ifc: bytes) -> list[dict]:
    """Dreiecksnetze aller Bauteile eines IFC-Modells für die 3D-Ansicht der App (Weltkoordinaten in m, z nach oben)."""
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as ue

    with tempfile.TemporaryDirectory() as d:  # open() liest nur Dateien
        p = Path(d) / "modell.ifc"
        p.write_bytes(ifc)
        model = ifcopenshell.open(str(p))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    out = []
    for el in model.by_type("IfcProduct"):
        if el.Representation is None or el.is_a("IfcOpeningElement"):
            continue
        shape = ifcopenshell.geom.create_shape(settings, el)
        bestand = ue.get_psets(el).get("Planpause_Bestand", {})
        storey = ue.get_container(el) or ue.get_aggregate(el)
        psets = ue.get_psets(el)
        kind = getattr(el, "PredefinedType", None) or ""
        if el.is_a("IfcWall"):
            kind = "aussen" if psets.get("Pset_WallCommon", {}).get("IsExternal") else "innen"
        out.append({"type": el.is_a(), "name": el.Name or "", "storey": storey.Name if storey else "", "kind": str(kind),
                    "estimated": bool(bestand.get("Geschaetzt")),
                    "verts": [round(v, 3) for v in shape.geometry.verts], "faces": list(shape.geometry.faces)})
    return out
