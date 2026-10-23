"""Bildaufbereitung: Blatt finden, entzerren, gerade drehen, Kontrast, Kacheln.

Ziel ist ein Bild, in dem Pixel annähernd proportional zu Zentimetern sind. Dann
sind die Pixel-Hinweise für den Solver brauchbar und die Kacheln für die
Maßzahl-Erkennung scharf genug.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

MAX_SIDE = 2400


@dataclass
class Prepared:
    image: np.ndarray                 # entzerrtes Graustufenbild
    size: tuple[int, int]             # (Breite, Höhe)
    steps: list[str] = field(default_factory=list)
    quad: list[list[float]] | None = None  # gefundene Blattecken im Originalbild
    angle: float = 0.0

    @classmethod
    def load(cls, data: bytes) -> "Prepared":
        """Ein bereits aufbereitetes Bild unverändert laden. Nicht erneut prepare() aufrufen: Das schneidet,
        dreht und skaliert noch einmal, und die KI-Koordinaten passten nicht mehr zum gespeicherten Bild."""
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("Bild konnte nicht gelesen werden")
        return cls(image=img, size=(img.shape[1], img.shape[0]))

    def jpeg(self, quality: int = 90, max_side: int | None = None, ruler: bool = False) -> bytes:
        img, k = self.image, 1.0
        if max_side and max(img.shape[:2]) > max_side:
            k = max_side / max(img.shape[:2])
            img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        if ruler:
            img = with_ruler(img, 0, 0, k)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        assert ok
        return buf.tobytes()

    def tiles(self, overlap: float = 0.16, quality: int = 90, max_side: int = 1600, ruler: bool = False,
              cell: int = 1500, max_tiles: int = 16) -> list[tuple[str, bytes, tuple[int, int]]]:
        """Überlappende Ausschnitte: (Name, JPEG, Versatz im entzerrten Bild).

        Fotos (bis ca. 3000 px) ergeben 2×2. Große Bilder, z. B. gerenderte PDF-Seiten, ergeben ein feineres
        Raster, damit jeder Ausschnitt ohne Verkleinerung bei der KI ankommt und kleine Maßzahlen lesbar bleiben."""
        h, w = self.image.shape[:2]
        cols, rows = max(2, -(-w // cell)), max(2, -(-h // cell))
        while cols * rows > max_tiles:  # zu viele: Zellen vergrößern
            cols, rows = (cols - 1, rows) if cols >= rows else (cols, rows - 1)
        tw, th = min(w, int(w / cols * (1 + 2 * overlap))), min(h, int(h / rows * (1 + 2 * overlap)))
        named = {(0, 0): "oben links", (0, 1): "oben rechts", (1, 0): "unten links", (1, 1): "unten rechts"}
        out = []
        for r in range(rows):
            for c in range(cols):
                x, y = round(c * (w - tw) / (cols - 1)), round(r * (h - th) / (rows - 1))
                name = named[(r, c)] if (cols, rows) == (2, 2) else f"Zeile {r + 1}, Spalte {c + 1}"
                crop = self.image[y:y + th, x:x + tw]
                k = min(1.0, max_side / max(crop.shape[:2]))
                if k < 1:
                    crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
                if ruler:
                    crop = with_ruler(crop, x, y, k)
                ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
                out.append((name, buf.tobytes(), (x, y)))
        return out


RULER_MARGIN = 44


def with_ruler(img: np.ndarray, x0: int, y0: int, k: float, margin: int = RULER_MARGIN) -> np.ndarray:
    """Weißer Rand mit Pixel-Lineal rundherum, beschriftet in Koordinaten des ganzen entzerrten Bildes.

    Ohne Bezugspunkte schätzt die KI Pixelpositionen oft um einige Prozent daneben. Das Lineal liegt
    außerhalb des Bildes und verdeckt nichts. (x0, y0): Lage des Ausschnitts im ganzen Bild, k: Verkleinerung."""
    h, w = img.shape[:2]
    out = cv2.copyMakeBorder(img, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=255)
    font, fs = cv2.FONT_HERSHEY_SIMPLEX, 0.42

    def ticks(start: int, length: int):
        c = -(-start // 50) * 50
        while (c - start) * k <= length:
            yield c, int(round((c - start) * k)) + margin
            c += 50

    for c, p in ticks(x0, w - 1):
        big = c % 100 == 0
        for y_edge, d in ((margin - 1, -1), (margin + h, 1)):
            cv2.line(out, (p, y_edge), (p, y_edge + d * (14 if big else 7)), 0, 1)
        if big:
            tw = cv2.getTextSize(str(c), font, fs, 1)[0][0]
            cv2.putText(out, str(c), (p - tw // 2, 16), font, fs, 0, 1, cv2.LINE_AA)
            cv2.putText(out, str(c), (p - tw // 2, margin + h + 34), font, fs, 0, 1, cv2.LINE_AA)
    for c, p in ticks(y0, h - 1):
        big = c % 100 == 0
        for x_edge, d in ((margin - 1, -1), (margin + w, 1)):
            cv2.line(out, (x_edge, p), (x_edge + d * (14 if big else 7), p), 0, 1)
        if big:
            cv2.putText(out, str(c), (1, p - 3), font, fs * 0.85, 0, 1, cv2.LINE_AA)
            cv2.putText(out, str(c), (margin + w + 3, p - 3), font, fs * 0.85, 0, 1, cv2.LINE_AA)
    return out


def _order(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def find_sheet(gray: np.ndarray) -> np.ndarray | None:
    """Größtes helles Viereck (das Blatt), falls es deutlich vom Hintergrund absticht."""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:3]:
        area = cv2.contourArea(c)
        if area < 0.25 * w * h or area > 0.985 * w * h:
            continue
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            best = _order(approx.reshape(4, 2).astype(np.float32))
            break
    return best


def warp_sheet(gray: np.ndarray, quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = quad
    wd = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    ht = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    dst = np.array([[0, 0], [wd - 1, 0], [wd - 1, ht - 1], [0, ht - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(gray, M, (wd, ht), flags=cv2.INTER_CUBIC, borderValue=255)


def dominant_angle(gray: np.ndarray) -> float:
    """Kleiner Restwinkel der langen geraden Linien (Grad), für die Geraderichtung."""
    edges = cv2.Canny(gray, 50, 150)
    h, w = gray.shape
    lines = cv2.HoughLinesP(edges, 1, np.pi / 720, threshold=120, minLineLength=min(h, w) // 8, maxLineGap=6)
    if lines is None:
        return 0.0
    angs, wts = [], []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        a = ((a + 45) % 90) - 45  # auf ±45° um die nächste Achse
        if abs(a) < 8:
            angs.append(a); wts.append(np.hypot(x2 - x1, y2 - y1))
    if not angs:
        return 0.0
    order = np.argsort(angs)
    cum = np.cumsum(np.array(wts)[order])
    return float(np.array(angs)[order][np.searchsorted(cum, cum[-1] / 2)])  # gewichteter Median


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def prepare(data: bytes) -> Prepared:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Bild konnte nicht gelesen werden")
    steps = []
    k = min(1.0, MAX_SIDE / max(img.shape[:2]))
    if k < 1:
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        steps.append(f"verkleinert auf {img.shape[1]}×{img.shape[0]}")
    # Rote/farbige Schraffuren dunkel halten: Minimum der Kanäle statt Luminanz
    gray = img.min(axis=2)
    quad = find_sheet(gray)
    if quad is not None:
        gray = warp_sheet(gray, quad)
        steps.append("Blatt erkannt und perspektivisch entzerrt")
    angle = dominant_angle(gray)
    if abs(angle) > 0.15:
        gray = rotate(gray, angle)
        steps.append(f"um {angle:.2f}° gerade gedreht")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    steps.append("Kontrast ausgeglichen")
    return Prepared(gray, (gray.shape[1], gray.shape[0]), steps, quad.tolist() if quad is not None else None, angle)
