"""Erzeugt Test-Planmodelle aus den zwei echten Bestandsplänen.

Die Fixtures entsprechen dem, was die KI-Extraktion liefern soll: Linien (mit
verrauschter Pixellage), Maßketten genau wie im Plan gelesen, Bauteile als
Verweise auf Linien. Koordinaten in cm dienen hier nur dazu, die Linien und
Pixel-Hinweise zu erzeugen; der Solver sieht nur Maßzahlen und Pixel.

Aufruf:  python build_fixtures.py   -> schreibt plan_*.json daneben
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).parent


def lid(axis: str, v: float) -> str:
    return f"{axis}{v:g}".replace("-", "m")


class Builder:
    def __init__(self, title, scale, off, noise, seed=7):
        self.title, self.scale, self.off, self.noise = title, scale, off, noise
        self.rng = random.Random(seed)
        self.lines = {"x": {}, "y": {}}  # id -> (pos_cm or None, px or None, label)
        self.m = {"version": 1, "title": title, "axes": {"x": [], "y": []}, "chains": [], "measurements": [],
                  "walls": [], "openings": [], "features": [], "rooms": [], "zones": [], "ai_issues": [], "questions": []}

    def line(self, axis, v, label=""):
        i = lid(axis, v)
        if i not in self.lines[axis]:
            k = 0 if axis == "x" else 1
            px = self.off[k] + v * self.scale + self.rng.gauss(0, self.noise)
            self.lines[axis][i] = (v, round(px, 1), label)
        return i

    def free(self, axis, name, px, label=""):
        self.lines[axis][name] = (None, px, label)
        return name

    def rect(self, x0, y0, x1, y1):
        return {"x0": self.line("x", x0), "y0": self.line("y", y0), "x1": self.line("x", x1), "y1": self.line("y", y1)}

    def wall(self, r, kind="innen"):
        self.m["walls"].append({**self.rect(*r), "kind": kind})

    def opening(self, r, typ, hinge=None, swing=None, width=None, sill=None, height=None):
        self.m["openings"].append({**self.rect(*r), "type": typ, "hinge": hinge, "swing": swing,
                                   "width_stated": width, "sill_stated": sill, "height_stated": height})

    def feature(self, r, typ, **kw):
        self.m["features"].append({**self.rect(*r), "type": typ, **kw})

    def room(self, name, area, r=None):
        d = {"name": name, "area_stated": area, "poly": []}
        if r:
            x0, y0, x1, y1 = r
            a, b, c, e = self.line("x", x0), self.line("y", y0), self.line("x", x1), self.line("y", y1)
            d["poly"] = [(a, b), (c, b), (c, e), (a, e)]
        self.m["rooms"].append(d)

    def chain(self, cid, axis, start, values, total=None, label="", override=None, uncertain=()):
        """override: {index_of_line: line_id} für Linien, die nicht auf der kumulierten Position liegen."""
        override = override or {}
        known = {v: i for i, (v, _, _) in self.lines[axis].items() if v is not None}
        ids, pos = [], start
        for k in range(len(values) + 1):
            if k in override:
                ids.append(override[k])
            else:
                near = sorted((abs(v - pos), i) for v, i in known.items() if abs(v - pos) <= 1.0)
                hit = near[0][1] if near else None
                ids.append(hit or self.line(axis, pos))
            if k < len(values):
                pos += values[k]
        self.m["chains"].append({"id": cid, "axis": axis, "lines": ids, "values": values, "total": total,
                                 "label": label, "uncertain": list(uncertain)})

    def done(self):
        for ax in ("x", "y"):
            self.m["axes"][ax] = [{"id": i, "px": px, "label": lab}
                                  for i, (v, px, lab) in sorted(self.lines[ax].items(), key=lambda t: t[1][1])]
        return self.m


def bungalow():
    b = Builder("Bungalow Erdgeschoss mit zwei Garagen", scale=0.629, off=(465, 290), noise=2.0)
    W = b.wall
    # Linker Block
    for r in [(0, 125, 30, 1100), (0, 125, 125, 155), (425, 125, 544, 155), (520, 155, 544, 630), (520, 720, 544, 1100),
              (30, 577.5, 415, 601.5), (503.5, 577.5, 520, 595), (282.5, 601.5, 300, 625), (282.5, 713.5, 300, 1076.5),
              (300, 745, 330, 762.5), (406, 745, 520, 762.5), (0, 1076.5, 75, 1100), (225, 1076.5, 300, 1100),
              (300, 1070, 350, 1100), (475, 1070, 544, 1100)]:
        W(r, "aussen" if r[0] == 0 or r[3] == 1100 or r[1] == 125 else "innen")
    # Mitte
    for r in [(544, 261, 656, 285), (544, 750, 790, 774), (891, 750, 956, 774), (544, 1076, 720, 1100), (950, 1076, 980, 1100)]:
        W(r, "aussen" if r[1] in (261, 1076) else "innen")
    # Rechts
    for r in [(956, 0, 1050, 30), (1450, 0, 1550, 30), (956, 30, 980, 285), (956, 515, 980, 610), (980, 515, 1090, 539),
              (956, 710, 980, 940), (956, 1016, 980, 1076), (1520, 30, 1550, 640), (1520, 790, 1550, 1070),
              (1206, 812.5, 1520, 830), (1100, 812.5, 1117.5, 1070), (980, 902.5, 1100, 920),
              (980, 1070, 1000, 1100), (1075, 1070, 1225, 1100), (1425, 1070, 1550, 1100)]:
        W(r, "aussen" if r[1] in (0, 1070) or r[0] == 1520 else "innen")
    # Garagen
    W((-325, 524, -301, 1100), "brand"); W((-325, 524, 0, 548), "aussen"); W((-24, 548, 0, 1100), "aussen")
    W((-301, 1076, -275, 1100), "aussen"); W((-50, 1076, -24, 1100), "aussen")
    W((1675, -150, 1699, 500), "aussen"); W((2001, -150, 2025, 500), "brand"); W((1699, -150, 2001, -126), "aussen")
    W((1699, 476, 1725, 500), "aussen"); W((1975, 476, 2001, 500), "aussen")
    b.opening((-275, 1076, -50, 1100), "gate", width=225); b.opening((1725, 476, 1975, 500), "gate", width=250)
    for r, br, h in [((125, 125, 425, 155), 62.5, None), ((656, 261, 956, 285), None, 212.5), ((1050, 0, 1150, 30), 62.5, 150),
                     ((1150, 0, 1450, 30), 62.5, 150), ((1520, 640, 1550, 790), 87.5, None), ((75, 1076.5, 225, 1100), 87.5, 125),
                     ((350, 1070, 475, 1100), 87.5, None), ((830, 1076, 950, 1100), None, None), ((1000, 1070, 1075, 1100), 125, None),
                     ((1225, 1070, 1425, 1100), 87.5, 125)]:
        b.opening(r, "window", sill=br, height=h)
    for r, hg, sw, wd in [((415, 577.5, 503.5, 601.5), "end", "neg", 88.5), ((282.5, 625, 300, 713.5), "start", "neg", 88.5),
                          ((330, 745, 406, 762.5), "start", "pos", 76), ((520, 630, 544, 720), "start", "neg", None),
                          ((790, 750, 891, 774), "end", "neg", 101), ((956, 610, 980, 710), "end", "neg", None),
                          ((956, 940, 980, 1016), "end", "neg", 76), ((720, 1076, 830, 1100), "start", "neg", 110),
                          ((1117.5, 812.5, 1206, 830), "start", "pos", 88.5)]:
        b.opening(r, "door", hg, sw, wd, height=208 if wd else None)
    b.feature((544, 774, 710, 1030), "Treppe", treads=13)
    b.feature((550, 300, 595, 345), "Schornstein", note="Schiedel 2 × Ø 20")
    b.feature((0, 24, 24, 48), "Stütze"); b.feature((520, 24, 544, 48), "Stütze")
    for name, area, r in [("Eltern", 20.70, (30, 155, 520, 577.5)), ("Kind", 11.99, (30, 601.5, 282.5, 1076.5)),
                          ("Flur", 3.30, (300, 595, 520, 745)), ("Bad", 6.77, (300, 762.5, 520, 1070)),
                          ("Diele", 19.16, (544, 285, 956, 750)), ("WFG", 6.75, None), ("WC", 1.80, (980, 920, 1100, 1070)),
                          ("Küche", 9.66, (1117.5, 830, 1520, 1070)), ("Wohnen", 27.46, (980, 30, 1520, 538.5)),
                          ("Essen", 14.58, (980, 538.5, 1520, 812.5)), ("Überd. Terrasse", 4.22, None),
                          ("Garage 2", 15.29, (-301, 548, -24, 1100)), ("Garage 1", 18.18, (1699, -126, 2001, 476))]:
        b.room(name, area, r)
    t = [(b.line("x", 0), b.line("y", 24)), (b.line("x", 956), b.line("y", 24)), (b.line("x", 956), b.line("y", 261)),
         (b.line("x", 544), b.line("y", 261)), (b.line("x", 544), b.line("y", 125)), (b.line("x", 0), b.line("y", 125))]
    b.m["zones"].append({"type": "Überdachte Terrasse", "poly": t})
    # Maßketten genau wie im Plan gelesen
    C = b.chain
    C("oben-licht", "x", 0, [30, 490, 24, 412, 24, 540, 30], 1550, "oben, lichte Maße Haus")
    C("oben-gesamt", "x", -325, [24, 277, 24, 30, 490, 24, 412, 24, 540, 30, 125, 24, 302, 24], 2350, "oben, gesamt")
    C("oben-achsen", "x", 0, [550, 400, 600], 1550, "oben, Achsmaße")
    C("oben-fenster-wohnen", "x", 950, [100, 100, 300, 100], None, "oben, Fenster Wohnen")
    C("unten-licht", "x", 0, [30, 252.5, 17.5, 220, 24, 412, 24, 120, 17.5, 402.5, 30], 1550, "unten, lichte Maße")
    C("unten-gesamt", "x", -325, [325, 550, 400, 600, 125, 350], 2350, "unten, gesamt")
    C("unten-oeffnungen", "x", -325, [50, 225, 50, 75, 150, 125, 125, 75, 170, 110, 120, 50, 75, 150, 200, 125], None, "unten, Öffnungen")
    C("garage1-tor", "x", 1675, [50, 250, 50], 350, "Garage 1, Tor")
    C("links-eltern-kind", "y", 0, [24, 101, 30, 422.5, 24, 475, 24], 1100, "links, Eltern/Kind")
    C("links-flur-bad", "y", 125, [30, 422.5, 17.5, 150, 17.5, 307.5, 30], None, "links, Eltern/Flur/Bad")
    C("rechts-wohnen", "y", 0, [30, 508.5], None, "rechts, Wohnen")
    C("garage1-tiefe", "y", -150, [24, 602, 24], None, "Garage 1, Tiefe")
    C("garage2-tiefe", "y", 524, [24, 552], None, "Garage 2, Tiefe")
    m = b.done()
    m.update(title="Bungalow Erdgeschoss mit zwei Garagen", floor="Erdgeschoss", image_size=[2048, 1536])
    return m


def darmstaedter():
    b = Builder("Haus Darmstädter Str. 14 – Erdgeschoss", scale=1.0, off=(638, 540), noise=3.0, seed=3)
    for r in [(0, 0, 143, 51), (195, 0, 366, 51), (503, 0, 1033, 51), (0, 678, 130, 734), (214, 678, 392, 734), (481, 678, 1033, 734),
              (0, 51, 56, 678), (977, 51, 1033, 126), (977, 265, 1033, 467), (977, 606, 1033, 678)]:
        b.wall(r, "aussen")
    for r in [(203, 51, 219, 165), (203, 240, 219, 256), (56, 256, 317, 272), (301, 272, 317, 560), (301, 640, 317, 678),
              (392, 467, 407, 479), (477, 467, 561, 479), (561, 51, 577, 560), (561, 640, 577, 678), (577, 344, 707, 360), (777, 344, 977, 360)]:
        b.wall(r)
    for r in [(143, 0, 195, 51), (366, 0, 503, 51), (130, 678, 214, 734), (977, 126, 1033, 265), (977, 467, 1033, 606)]:
        b.opening(r, "window")
    for r, hg, sw in [((203, 165, 219, 240), "end", "neg"), ((301, 560, 317, 640), "end", "neg"), ((407, 467, 477, 479), "start", "neg"),
                      ((561, 560, 577, 640), "end", "pos"), ((707, 344, 777, 360), "start", "pos"), ((392, 678, 481, 734), "start", "neg")]:
        b.opening(r, "door", hg, sw)
    b.feature((317, 272, 392, 525), "Treppe", treads=11)
    b.feature((580, 314, 610, 344), "Schornstein")
    for name, area, r in [("Bad", 3.01, (56, 51, 203, 256)), ("Zimmer", 9.95, (56, 272, 301, 678)),
                          ("Wohnzimmer", 11.72, (577, 51, 977, 344)), ("Schlafzimmer", 12.72, (577, 360, 977, 678))]:
        b.room(name, area, r)
    # Küche und Flur sind L-förmig
    L = lambda pts: [(b.line("x", x), b.line("y", y)) for x, y in pts]  # noqa: E731
    b.m["rooms"].append({"name": "Küche", "area_stated": 11.76, "poly": L([(219, 51), (561, 51), (561, 467), (392, 467), (392, 272), (317, 272), (317, 256), (219, 256)])})
    b.m["rooms"].append({"name": "Flur", "area_stated": 4.18, "poly": L([(392, 479), (561, 479), (561, 678), (317, 678), (317, 525), (392, 525)])})
    C = b.chain
    C("unten", "x", 0, [56, 74, 84, 87, 16, 75, 89, 80, 16, 400, 56], 1033, "unten")
    t1 = b.free("x", "oben_t1", 638 + 211, "Teilstrich oben")
    t2 = b.free("x", "oben_t2", 638 + 712, "Teilstrich oben")
    C("oben", "x", 0, [56, 87, 52, 16, 8, 147, 137, 58, 129, 195], 1033, "oben",
      override={4: t1, 9: t2, 10: b.line("x", 1033)}, uncertain=[3, 4, 8, 9])
    C("links", "y", 0, [51, 205, 16, 406, 56], 734, "links", uncertain=[1])
    r1 = b.free("y", "rechts_r1", 540 + 660, "Teilstrich rechts")
    r2 = b.free("y", "rechts_r2", 540 + 678, "Teilstrich rechts")
    C("rechts", "y", 0, [51, 75, 139, 79, 16, 107, 139, 70, 20, 56], None, "rechts",
      override={8: r1, 9: r2, 10: b.line("y", 734)})
    m = b.done()
    m.update(title="Haus Darmstädter Str. 14 – Erdgeschoss", floor="Erdgeschoss", scale_text="1:50", image_size=[2016, 1512])
    return m


if __name__ == "__main__":
    for name, fn in (("plan_bungalow.json", bungalow), ("plan_darmstaedter14.json", darmstaedter)):
        (HERE / name).write_text(json.dumps(fn(), ensure_ascii=False, indent=1))
        print("geschrieben:", name)
