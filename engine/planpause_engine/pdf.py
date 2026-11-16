"""Grundrisse aus PDF-Dateien (CAD-Pläne, eingescannte Bauakten).

Eine PDF-Seite wird direkt in hoher Auflösung gerendert, statt sie abzufotografieren: kein Bildschirmraster,
keine Schräglage, gestochen scharfe Maßzahlen. Optional nur ein Ausschnitt (z. B. Grundriss ohne Plankopf).
Bibliothek: pypdfium2 (PDFium aus Chrome, Apache/BSD-Lizenz).
"""
from __future__ import annotations

import base64

import cv2
import numpy as np
import pypdfium2 as pdfium

from .preprocess import Prepared

TARGET_SIDE = 6000        # Pixel an der langen Seite des gewählten Bereichs
MAX_PIXELS = 40_000_000   # Obergrenze für das gerenderte Bild (Speicher, Übertragung)
MAX_PAGES = 60


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _open(data: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise ValueError("PDF konnte nicht gelesen werden (beschädigt oder passwortgeschützt).") from e


def find_plans(gray: np.ndarray) -> list[list[float]]:
    """Mehrere Grundrisse auf einem Blatt finden (z. B. alle Geschosse nebeneinander).

    Jeder Grundriss ist ein dichter Fleck aus Wänden, umgeben von seinen Maßketten; dazwischen liegt freies Papier.
    Liefert Ausschnitte als Anteile der Seite [x0, y0, x1, y1], von links oben nach rechts unten, oder eine leere
    Liste, wenn nur ein Grundriss (oder nichts Eindeutiges) zu sehen ist. Wird jeder einzeln ausgewertet, kommt er
    in voller Auflösung bei der KI an statt als Viertel eines Blatts."""
    h, w = gray.shape[:2]
    k = 2000 / max(h, w)
    g = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else gray
    g = cv2.medianBlur(g, 3)
    gh, gw = g.shape
    bg, dk = float(np.median(g)), float(np.percentile(g, 1.0))
    if bg - dk < 40:
        return []
    side = max(gh, gw)
    # Blatt ohne Scannerrand: größte helle Fläche, etwas eingerückt
    paper = (cv2.GaussianBlur(g, (0, 0), side * 0.01) > (bg + dk) / 2).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(paper, connectivity=8)
    if n > 1:
        i = 1 + int(np.argmax(st[1:, 4]))
        inset = int(0.012 * side)
        sx, sy, sw, sh = st[i][:4]
        sx, sy, sw, sh = sx + inset, sy + inset, max(1, sw - 2 * inset), max(1, sh - 2 * inset)
    else:
        sx, sy, sw, sh = 0, 0, gw, gh
    ink = np.zeros_like(g)
    ink[sy:sy + sh, sx:sx + sw] = (g[sy:sy + sh, sx:sx + sw] < dk + 0.5 * (bg - dk)).astype(np.uint8) * 255
    # Wände sind die dicksten Striche: dünne Maßlinien und Schrift fallen weg, übrig bleibt je Grundriss ein Fleck
    t = max(3, int(0.0022 * side)) | 1
    core = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (t, t)))
    kc = max(9, int(0.03 * side)) | 1
    blob = cv2.morphologyEx(core, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kc, kc)))
    n, _, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
    boxes = [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
             if st[i][2] > 0.08 * gw and st[i][3] > 0.1 * gh and st[i][4] > 0.006 * gw * gh and st[i][2] < 0.9 * sw]
    if len(boxes) < 2:
        return []
    out = []
    for x, y, bw, bh in boxes:   # Rand für die Maßketten rundherum, aber nicht in den Nachbarn hinein
        px, py = 0.3 * bw, 0.6 * bh
        x0, y0, x1, y1 = max(sx, x - px), max(sy, y - py), min(sx + sw, x + bw + px), min(sy + sh, y + bh + py)
        for ox, oy, ow, oh in boxes:
            if (ox, oy, ow, oh) == (x, y, bw, bh) or not (oy < y + bh and oy + oh > y):
                continue
            if ox >= x + bw:
                x1 = min(x1, (x + bw + ox) / 2)
            elif ox + ow <= x:
                x0 = max(x0, (ox + ow + x) / 2)
        for ox, oy, ow, oh in boxes:
            if (ox, oy, ow, oh) == (x, y, bw, bh) or not (ox < x + bw and ox + ow > x):
                continue
            if oy >= y + bh:
                y1 = min(y1, (y + bh + oy) / 2)
            elif oy + oh <= y:
                y0 = max(y0, (oy + oh + y) / 2)
        out.append([round(float(max(0.0, x0 / gw)), 4), round(float(max(0.0, y0 / gh)), 4), round(float(min(1.0, x1 / gw)), 4), round(float(min(1.0, y1 / gh)), 4)])
    out.sort(key=lambda b: (round(b[1] * 4), b[0]))
    return out


def pdf_pages(data: bytes, thumb_side: int = 420) -> list[dict]:
    """Vorschau aller Seiten: Nummer, Größe in mm, ein kleines JPEG (Base64) für die Seitenauswahl und, falls
    mehrere Grundrisse auf der Seite liegen, deren Ausschnitte (plans)."""
    doc = _open(data)
    out = []
    for i in range(min(len(doc), MAX_PAGES)):
        page = doc[i]
        w, h = page.get_size()  # Punkte (1/72 Zoll)
        scale = thumb_side / max(w, h)
        img = page.render(scale=scale, grayscale=True).to_numpy()
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        plans = find_plans(page.render(scale=1400 / max(w, h), grayscale=True).to_numpy()) if i < 12 else []
        out.append({"page": i + 1, "mm": [round(w / 72 * 25.4), round(h / 72 * 25.4)], "plans": plans,
                    "thumb": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()})
    return out


def render_page(data: bytes, page: int = 1, crop: tuple[float, float, float, float] | None = None) -> np.ndarray:
    """Seite (1-basiert) als Graustufenbild. crop: Ausschnitt als Anteile der Seite (x0, y0, x1, y1), 0..1."""
    doc = _open(data)
    if not 1 <= page <= len(doc):
        raise ValueError(f"Die PDF hat {len(doc)} Seite(n); Seite {page} gibt es nicht.")
    p = doc[page - 1]
    w, h = p.get_size()
    x0, y0, x1, y1 = crop or (0.0, 0.0, 1.0, 1.0)
    x0, x1 = sorted((min(max(x0, 0.0), 1.0), min(max(x1, 0.0), 1.0)))
    y0, y1 = sorted((min(max(y0, 0.0), 1.0), min(max(y1, 0.0), 1.0)))
    if (x1 - x0) < 0.02 or (y1 - y0) < 0.02:
        raise ValueError("Der gewählte Ausschnitt ist zu klein.")
    cw, ch = (x1 - x0) * w, (y1 - y0) * h
    scale = TARGET_SIDE / max(cw, ch)
    scale = min(scale, (MAX_PIXELS / (cw * ch)) ** 0.5)
    # PDFium schneidet in Punkten ab (links, unten, rechts, oben)
    img = p.render(scale=scale, grayscale=True,
                   crop=(x0 * w, (1 - y1) * h, (1 - x1) * w, y0 * h)).to_numpy()
    return np.ascontiguousarray(img)


def images_to_pdf(images: list[np.ndarray], px_per_pt: float = 2.0) -> bytes:
    """PDF mit je einem Bild pro Seite (für Tests und zum Zusammenfassen von Scans)."""
    import io
    doc = pdfium.PdfDocument.new()
    for img in images:
        h, w = img.shape[:2]
        pw, ph = w / px_per_pt, h / px_per_pt
        page = doc.new_page(pw, ph)
        obj = pdfium.PdfImage.new(doc)
        obj.load_jpeg(io.BytesIO(cv2.imencode(".jpg", img)[1].tobytes()))
        obj.set_matrix(pdfium.PdfMatrix().scale(pw, ph))
        page.insert_obj(obj)
        page.gen_content()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def prepare_pdf(data: bytes, page: int = 1, crop: tuple[float, float, float, float] | None = None) -> Prepared:
    img = render_page(data, page, crop)
    h, w = img.shape[:2]
    steps = [f"PDF-Seite {page} gerendert ({w} × {h} Pixel)"]
    if crop and crop != (0.0, 0.0, 1.0, 1.0):
        steps.append("Ausschnitt gewählt")
    return Prepared(image=img, size=(w, h), steps=steps)
