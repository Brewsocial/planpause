"""Erkennung von Wandkanten im entzerrten Bild und Einrasten der KI-Linien darauf.

Die KI schätzt Pixelpositionen nur grob. Wandkanten sind im Bild aber als lange,
gerade Hell-Dunkel-Übergänge gut messbar. Wir suchen solche Kanten und schieben
jede KI-Linie auf die nächstgelegene Kante, wenn eine in der Nähe liegt.
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import PlanModel


def _peaks(profile: np.ndarray, min_val: float, min_dist: int) -> list[int]:
    idx = []
    p = profile.copy()
    while True:
        i = int(np.argmax(p))
        if p[i] < min_val:
            break
        idx.append(i)
        p[max(0, i - min_dist):i + min_dist + 1] = 0
    return sorted(idx)


def wall_edges(gray: np.ndarray) -> dict[str, list[int]]:
    """Kandidaten für senkrechte (x) und waagerechte (y) Wandkanten in Pixeln."""
    h, w = gray.shape
    g = cv2.medianBlur(gray, 5)  # Papierstruktur und Moiré (abfotografierte Bildschirme) dämpfen
    bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 18)
    # Schraffuren und dicke Wände zu Flächen schließen
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    # Nur dicke Strukturen behalten: Maßlinien, Text und Raster sind dünn, Wände nicht
    t = max(5, int(min(h, w) * 0.004)) | 1
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (t, t)))
    out: dict[str, list[int]] = {}
    for axis, ksize, sob in (("y", (max(25, w // 22), 1), (0, 1)), ("x", (1, max(25, h // 22)), (1, 0))):
        mask = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, ksize))
        edge = np.abs(cv2.Sobel(mask.astype(np.float32), cv2.CV_32F, *sob, ksize=3))
        prof = edge.sum(axis=1 if axis == "y" else 0)
        length = w if axis == "y" else h
        margin = int(0.015 * (w if axis == "x" else h))
        out[axis] = [p for p in _peaks(prof, min_val=0.05 * length * 255 * 4, min_dist=4)
                     if margin < p < (w if axis == "x" else h) - margin]
    return out


def align_axis(px: np.ndarray, cand: np.ndarray, dim: int, tol: float) -> float | None:
    """Sucht eine gemeinsame Verschiebung aller KI-Linien einer Achse, bei der sie auf erkannten Kanten liegen.

    Die KI verschätzt Pixelpositionen oft systematisch um einige Prozent der Bildbreite; dann liegt keine
    Linie nah genug an ihrer Kante, um einzurasten. Bewertet wird, wie nah jede Linie an einer Kante liegt.
    Angewendet wird die Verschiebung nur, wenn sie eindeutig ist: deutlich besser als ohne Verschiebung und
    als jede andere Verschiebung. Regelmäßige Wandabstände, Bildschirmraster und Wasserzeichen erzeugen
    sonst Scheinlösungen, und eine falsche Korrektur ist schlimmer als keine."""
    if len(px) < 4 or len(cand) < 3:
        return None
    sigma = 0.35 * tol
    shifts = np.arange(-0.05 * dim, 0.05 * dim + 0.5, 1.0)
    score = np.array([np.exp(-0.5 * (np.abs((px + s)[:, None] - cand[None, :]).min(axis=1) / sigma) ** 2).sum()
                      for s in shifts])
    i = int(score.argmax())
    best, ident = score[i], score[int(np.abs(shifts).argmin())]
    others = np.abs(shifts - shifts[i]) > 3 * tol
    second = score[others].max() if others.any() else 0.0
    if best >= 1.5 * ident and best - ident >= 3 and best >= score.mean() + 3 and second <= 0.7 * best:
        return float(shifts[i])
    return None


def snap_lines(plan: PlanModel, gray: np.ndarray, tol_frac: float = 0.006) -> dict:
    """Verschiebt die KI-Linien gesamthaft (falls eindeutig) und rastet sie dann auf erkannte Kanten ein.
    Gibt pro Achse die Zahl eingerasteter Linien zurück, unter "aligned" die Verschiebung in Pixeln."""
    edges = wall_edges(gray)
    h, w = gray.shape
    stats: dict = {"aligned": {}}
    for axis in ("x", "y"):
        cand = np.array(edges[axis])
        dim = w if axis == "x" else h
        tol = tol_frac * dim
        lines = [l for l in plan.axes[axis] if l.px is not None]
        shift = align_axis(np.array([l.px for l in lines]), cand, dim, tol) if lines else None
        if shift:
            for l in lines:
                l.px += shift
            stats["aligned"][axis] = round(shift, 1)
        n = 0
        if len(cand):
            for line in plan.axes[axis]:
                if line.px is None:
                    continue
                d = np.abs(cand - line.px)
                j = int(np.argmin(d))
                if d[j] <= tol:
                    line.px = float(cand[j]); n += 1
        stats[axis] = n
    return stats
