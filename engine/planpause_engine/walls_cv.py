"""Wände per Bildverarbeitung finden: Wandmaske, genaues Einrasten und Abgleich mit dem Planmodell.

Die KI beschreibt den Plan, schätzt Pixellagen aber nur grob und lässt in einem Durchgang Wände aus.
Wände sind im Bild dagegen gut messbar: lange, gerade, dunkle Striche, einzeln (gefüllte Wand) oder paarweise
mit Füllung oder Schraffur dazwischen. Aus dieser Wandmaske entstehen
  * die genaue Lage jeder Wandkante (snap_to_walls): jede Linie rückt auf den Rand der Wand, zu der sie gehört,
  * eine Liste von Wandflächen im Bild, die im Modell fehlen (coverage), als Hinweis für die Kontrollrunde,
  * Wände des Modells, zu denen im Bild nichts gezeichnet ist.
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import PlanModel
from .solver import estimate_scale

WORK_SCALE = 1.4       # px/cm, auf die das Bild für die Maske verkleinert wird (reicht für Wände ab 6 cm)
MAX_THICK = 52.0       # cm, dickste Wand
MIN_RUN = 25.0         # cm, kürzeste Wandkante, die als „lang und gerade“ zählt
SNAP_TOL = 14.0        # cm, so weit darf eine Linie höchstens rücken


def plan_scale(plan: PlanModel) -> float | None:
    """Pixel pro cm aus den Maßketten (Mittel beider Achsen)."""
    s = [v for v in (estimate_scale(plan, "x"), estimate_scale(plan, "y")) if v]
    if not any(c.values for c in plan.chains) or not s:
        return None
    return float(sum(s) / len(s))


def wall_mask(gray: np.ndarray, scale: float) -> tuple[np.ndarray, float]:
    """Maske der Wandflächen (0/255) in verkleinerter Auflösung und der Verkleinerungsfaktor f.
    scale: Pixel pro cm im Bild. Ein Maskenpixel (x, y) entspricht dem Bildpixel (x / f, y / f)."""
    f = min(1.0, WORK_SCALE / scale)
    g = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else gray.copy()
    s = scale * f
    g = cv2.medianBlur(g, 3)
    # Schatten und Falten ausgleichen: Papierhelligkeit lokal schätzen (Maximum über mehr als eine Wanddicke)
    kb = max(15, int(round(70 * s))) | 1
    paper = cv2.GaussianBlur(cv2.dilate(g, cv2.getStructuringElement(cv2.MORPH_RECT, (kb, kb))), (0, 0), kb / 3)
    g = np.clip(g.astype(np.float32) / np.maximum(paper.astype(np.float32), 1.0) * 200.0, 0, 255).astype(np.uint8)
    bg, dk = float(np.median(g)), float(np.percentile(g, 1.5))
    if bg - dk < 40:  # kaum Kontrast: keine verlässliche Maske
        return np.zeros_like(g), f
    strokes = (g < dk + 0.38 * (bg - dk)).astype(np.uint8) * 255
    blur = cv2.GaussianBlur(g, (0, 0), max(1.0, 1.2 * s))
    ink = strokes | ((blur < dk + 0.80 * (bg - dk)).astype(np.uint8) * 255)  # Striche, Füllungen, Schraffuren
    run, thick, k = max(9, int(round(MIN_RUN * s))), int(round(MAX_THICK * s)), max(3, int(round(5 * s))) | 1
    out = np.zeros_like(strokes)
    for horiz in (True, False):
        along = cv2.getStructuringElement(cv2.MORPH_RECT, (run, 1) if horiz else (1, run))
        across = cv2.getStructuringElement(cv2.MORPH_RECT, (1, thick) if horiz else (thick, 1))
        long_ = cv2.morphologyEx(strokes, cv2.MORPH_OPEN, along)           # lange gerade Striche
        band = cv2.morphologyEx(long_, cv2.MORPH_CLOSE, across) & ink       # Fläche zwischen zwei Strichen, falls gefüllt
        band = cv2.morphologyEx(band, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))  # dünne Linien weg
        out |= cv2.morphologyEx(band, cv2.MORPH_OPEN, along)
    # Flächen, die in beiden Richtungen dicker sind als jede Wand (Bildrand, Schatten, Fotos von Tischen)
    big = cv2.morphologyEx(out, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (thick + 3, thick + 3)))
    if big.any():
        out &= ~cv2.dilate(big, cv2.getStructuringElement(cv2.MORPH_RECT, (k + 2, k + 2)))
    return out, f


def _px(plan: PlanModel) -> dict[str, dict[str, float]]:
    return {ax: {l.id: l.px for l in plan.axes[ax] if l.px is not None} for ax in ("x", "y")}


def _box(px: dict, r) -> tuple[float, float, float, float] | None:
    try:
        x0, x1 = sorted((px["x"][r.x0], px["x"][r.x1]))
        y0, y1 = sorted((px["y"][r.y0], px["y"][r.y1]))
    except KeyError:
        return None
    return x0, y0, x1, y1


def snap_to_walls(plan: PlanModel, gray: np.ndarray, mask: np.ndarray | None = None, f: float = 1.0) -> dict:
    """Rückt jede Linie auf den Rand der Wände, die sie begrenzt.

    Für jede Linie werden alle Wände betrachtet, deren Seite auf ihr liegt. Entlang dieser Wandseiten wird in der
    Maske der Übergang „außen frei, innen Wand“ gesucht. So rastet die linke Seite einer Wand nie auf ihre rechte."""
    scale = plan_scale(plan)
    stats: dict = {"x": 0, "y": 0, "lines": {"x": len(plan.axes["x"]), "y": len(plan.axes["y"])}}
    if not scale:
        return stats
    if mask is None:
        mask, f = wall_mask(gray, scale)
    if not mask.any():
        return stats
    m = (mask > 0).astype(np.float32)
    s = scale * f
    tol, win = int(round(SNAP_TOL * s)), max(2, int(round(3 * s)))
    px = _px(plan)
    before = {ax: dict(px[ax]) for ax in ("x", "y")}
    # je Linie: (Start, Ende) der Wandseite quer zur Achse und Vorzeichen (+1: Wand liegt bei größerer Koordinate)
    sides: dict[tuple[str, str], list[tuple[float, float, int]]] = {}
    for w in plan.walls:
        b = _box(px, w)
        if not b:
            continue
        x0, y0, x1, y1 = b
        lx0, lx1 = (w.x0, w.x1) if px["x"][w.x0] <= px["x"][w.x1] else (w.x1, w.x0)
        ly0, ly1 = (w.y0, w.y1) if px["y"][w.y0] <= px["y"][w.y1] else (w.y1, w.y0)
        sides.setdefault(("x", lx0), []).append((y0, y1, 1))
        sides.setdefault(("x", lx1), []).append((y0, y1, -1))
        sides.setdefault(("y", ly0), []).append((x0, x1, 1))
        sides.setdefault(("y", ly1), []).append((x0, x1, -1))
    h, wd = m.shape
    moved: dict[tuple[str, str], float] = {}
    for (ax, lid), segs in sides.items():
        c = px[ax][lid] * f
        size = wd if ax == "x" else h
        offs = np.arange(-tol, tol + 1)
        score = np.zeros(len(offs))
        weight = 0.0
        for a, b, sign in segs:
            a, b = a * f, b * f
            trim = min(0.15 * (b - a), 3 * s)     # Ecken auslassen: dort kreuzen andere Wände
            a, b = int(round(a + trim)), int(round(b - trim))
            if b - a < 3:
                continue
            a, b = max(a, 0), min(b, (h if ax == "x" else wd) - 1)
            strip = m[a:b + 1, :] if ax == "x" else m[:, a:b + 1].T   # Zeilen = Verlauf der Wand, Spalten = quer
            prof = strip.mean(axis=0)
            cs = np.concatenate([[0.0], np.cumsum(prof)])
            for i, d in enumerate(offs):
                p = int(round(c + d))
                if p - win < 0 or p + win > size:
                    continue
                inner = (cs[p + win] - cs[p]) / win if sign > 0 else (cs[p] - cs[p - win]) / win
                outer = (cs[p] - cs[p - win]) / win if sign > 0 else (cs[p + win] - cs[p]) / win
                score[i] += (inner - outer) * (b - a)
            weight += b - a
        if weight <= 0:
            continue
        score /= weight
        score *= np.exp(-0.5 * (offs / (0.6 * tol)) ** 2) * 0.35 + 0.65   # bei gleich guten Kanten die nähere
        i = int(np.argmax(score))
        if score[i] >= 0.45:
            moved[(ax, lid)] = float(round(c + offs[i]) / f)
    for (ax, lid), v in moved.items():
        px[ax][lid] = v
    # Wände dürfen dabei nicht umklappen oder verschwinden: solche Verschiebungen zurücknehmen
    for w in plan.walls:
        for ax, a, b in (("x", w.x0, w.x1), ("y", w.y0, w.y1)):
            if a in px[ax] and b in px[ax] and a in before[ax] and b in before[ax]:
                if (px[ax][b] - px[ax][a]) * (before[ax][b] - before[ax][a]) <= 0 or abs(px[ax][b] - px[ax][a]) < 3 * scale:
                    px[ax][a], px[ax][b] = before[ax][a], before[ax][b]
    for ax in ("x", "y"):
        for l in plan.axes[ax]:
            if l.px is not None and px[ax][l.id] != before[ax][l.id]:
                l.px = px[ax][l.id]
                stats[ax] += 1
    return stats


def coverage(plan: PlanModel, mask: np.ndarray, f: float, scale: float) -> dict:
    """Vergleicht Wandmaske und Modell.

    missing: Wandflächen im Bild ohne Gegenstück im Modell, als Kästen in Bildpixeln [x0, y0, x1, y1], größte zuerst.
    unsupported: Indizes von Wänden des Modells, an deren Stelle im Bild fast nichts gezeichnet ist.
    share: Anteil der Wandmaske, der vom Modell gedeckt ist (0..1)."""
    s = scale * f
    px = _px(plan)
    h, w = mask.shape
    cover = np.zeros((h, w), np.uint8)
    pad = int(round(4 * s))
    items = [(r, True) for r in plan.walls] + [(r, False) for r in list(plan.openings) + list(plan.features)]
    unsupported = []
    m = mask > 0
    for i, (r, is_wall) in enumerate(items):
        b = _box(px, r)
        if not b:
            continue
        x0, y0, x1, y1 = (int(round(v * f)) for v in b)
        cv2.rectangle(cover, (x0 - pad, y0 - pad), (x1 + pad, y1 + pad), 255, -1)
        if is_wall and x1 > x0 and y1 > y0:
            part = m[max(y0, 0):y1, max(x0, 0):x1]
            if part.size and part.mean() < 0.3 and max(x1 - x0, y1 - y0) >= MIN_RUN * s:
                unsupported.append(i)
    left = cv2.morphologyEx(mask & ~cover, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(left, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        long_, short = max(bw, bh), min(bw, bh)
        if long_ >= MIN_RUN * s and short >= 5 * s and area >= 0.5 * bw * bh:   # gerade Streifen, keine Reste
            boxes.append((int(area), [int(round(x / f)), int(round(y / f)), int(round((x + bw) / f)), int(round((y + bh) / f))]))
    boxes.sort(reverse=True)
    total = int(m.sum())
    return {"missing": [b for _, b in boxes[:30]], "unsupported": unsupported,
            "share": round(1 - int((left > 0).sum()) / total, 3) if total else 1.0}


def open_gaps(plan: PlanModel, scale: float) -> list[dict]:
    """Lücken zwischen zwei fluchtenden Wänden (gleiche Seitenlinien), in denen keine Öffnung eingetragen ist.
    Jede solche Lücke ist im Plan eine Tür, ein Durchgang oder ein Fenster."""
    px = _px(plan)
    out = []
    op = [b for b in (_box(px, o) for o in plan.openings) if b]
    for ax in ("x", "y"):   # ax: Richtung, in der die Wand verläuft
        groups: dict[tuple[str, str], list[tuple[float, float, int]]] = {}
        for i, w in enumerate(plan.walls):
            b = _box(px, w)
            if not b or ((b[2] - b[0] >= b[3] - b[1]) != (ax == "x")):   # nur Wände, die in dieser Richtung verlaufen
                continue
            key = tuple(sorted((w.y0, w.y1))) if ax == "x" else tuple(sorted((w.x0, w.x1)))
            groups.setdefault(key, []).append((b[0], b[2], i) if ax == "x" else (b[1], b[3], i))
        for key, segs in groups.items():
            segs.sort()
            for (a0, a1, i), (b0, b1, j) in zip(segs, segs[1:]):
                gap = b0 - a1
                if not 40 * scale <= gap <= 400 * scale:
                    continue
                c0, c1 = sorted((px["y" if ax == "x" else "x"][key[0]], px["y" if ax == "x" else "x"][key[1]]))
                hit = any((o[0] < b0 and o[2] > a1 and o[1] < c1 and o[3] > c0) if ax == "x" else
                          (o[1] < b0 and o[3] > a1 and o[0] < c1 and o[2] > c0) for o in op)
                if not hit:
                    box = [a1, c0, b0, c1] if ax == "x" else [c0, a1, c1, b0]
                    out.append({"walls": [i, j], "box": [int(round(v)) for v in box], "width_cm": round(gap / scale)})
    return out
