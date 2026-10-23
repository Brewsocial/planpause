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


def pdf_pages(data: bytes, thumb_side: int = 420) -> list[dict]:
    """Vorschau aller Seiten: Nummer, Größe in mm und ein kleines JPEG (Base64) für die Seitenauswahl."""
    doc = _open(data)
    out = []
    for i in range(min(len(doc), MAX_PAGES)):
        page = doc[i]
        w, h = page.get_size()  # Punkte (1/72 Zoll)
        scale = thumb_side / max(w, h)
        img = page.render(scale=scale, grayscale=True).to_numpy()
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        out.append({"page": i + 1, "mm": [round(w / 72 * 25.4), round(h / 72 * 25.4)],
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
