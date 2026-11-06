"""PDF-Plan: der Grundriss wie im DXF, maßstäblich auf A4/A3 mit Plankopf und Maßstabsleiste.

Gezeichnet wird mit dem Zeichen-Add-on von ezdxf (Texte als Umrisse), geschrieben wird die PDF ohne
weitere Bibliotheken. Plan-Inhalt in Graustufen, geschätzte Bauteile orange."""
from __future__ import annotations

import io
import math
import zlib
from datetime import date

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, recorder
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration, LineweightPolicy
from ezdxf.math import Matrix44
from ezdxf.path import Command

from .export import to_dxf

PAPERS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}  # quer, in mm
SCALES = [(50, "A4"), (100, "A4"), (100, "A3"), (200, "A3"), (250, "A3"), (500, "A3"), (1000, "A3")]
PRINT_COLORS = {"WAENDE": 250, "BRANDWAND": 250, "FENSTER": 7, "TUEREN": 7, "TORE": 7, "TREPPE": 7, "BAUTEILE": 8,
                "ZONEN": 9, "RAEUME": 7, "BEMASSUNG": 7, "GESCHAETZT": 30}
LEFT, MARGIN, HEAD = 20.0, 10.0, 34.0  # Heftrand, Rand, Höhe des Plankopfs (mm)
PT = 72 / 25.4


def _fit(w: float, h: float, scale: int | None, start: int = 0) -> tuple[int, str, bool] | None:
    """Kleinster Maßstab (größte Darstellung) ab start und Papier, auf dem w × h mm Platz haben. portrait = hochkant."""
    for s, paper in SCALES:
        if (scale and s != scale) or s < start:
            continue
        pw, ph = PAPERS[paper]
        for portrait in (False, True):
            W, H = (ph, pw) if portrait else (pw, ph)
            if w / s <= W - LEFT - MARGIN - 8 and h / s <= H - 2 * MARGIN - HEAD - 8:
                return s, paper, portrait
    return None


def _record(geom: dict, s: int):
    """Grundriss mit Bemaßung für Maßstab 1:s zeichnen; Ergebnis in Modell-mm."""
    doc = ezdxf.read(io.StringIO(to_dxf(geom, [], "mm", dim_print=s).decode("utf-8")))
    for layer in doc.layers:
        if layer.dxf.name in PRINT_COLORS:
            layer.color = PRINT_COLORS[layer.dxf.name]
    rec = recorder.Recorder()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR,
                        lineweight_policy=LineweightPolicy.ABSOLUTE)
    Frontend(RenderContext(doc), rec, config=cfg).draw_layout(doc.modelspace(), finalize=True)
    player = rec.player()
    box = player.bbox()
    return player, (box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y)


class _Pdf:
    """Eine Seite, Koordinaten in mm (Ursprung unten links)."""

    def __init__(self, w: float, h: float):
        self.w, self.h, self.ops = w, h, []

    def op(self, s: str):
        self.ops.append(s)

    def color(self, rgb: tuple[float, float, float], stroke: bool):
        self.op("{:.3f} {:.3f} {:.3f} {}".format(*rgb, "RG" if stroke else "rg"))

    def text(self, x: float, y: float, s: str, size: float, bold=False, right=False):
        enc = s.encode("cp1252", "replace")
        if right:  # grobe Breite für Helvetica
            x -= len(s) * size * 0.52 / PT
        esc = enc.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        self.ops.append(f"BT /{'F2' if bold else 'F1'} {size:.1f} Tf {x * PT:.2f} {y * PT:.2f} Td (".encode("latin-1") + esc + b") Tj ET")

    def line(self, x0, y0, x1, y1, width=0.25):
        self.op(f"{width * PT:.2f} w {x0 * PT:.2f} {y0 * PT:.2f} m {x1 * PT:.2f} {y1 * PT:.2f} l S")

    def rect(self, x, y, w, h, width=0.25, fill=False):
        self.op(f"{width * PT:.2f} w {x * PT:.2f} {y * PT:.2f} {w * PT:.2f} {h * PT:.2f} re {'f' if fill else 'S'}")

    def bytes(self, title: str) -> bytes:
        content = zlib.compress(b"\n".join(o if isinstance(o, bytes) else o.encode("latin-1") for o in self.ops))
        meta = title.encode("utf-16-be")
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.w * PT:.2f} {self.h * PT:.2f}] "
            f"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>".encode(),
            f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode() + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Title <FEFF" + meta.hex().upper().encode() + b"> /Producer (Planpause) >>",
        ]
        out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
        for i, o in enumerate(objs, 1):
            offs.append(len(out))
            out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {len(objs)} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def _rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def _path_ops(path, close: bool) -> str:
    k = PT
    d = [f"{path.start.x * k:.2f} {path.start.y * k:.2f} m"]
    for cmd in path.commands():
        e = cmd.end
        if cmd.type == Command.MOVE_TO:
            d.append(f"{e.x * k:.2f} {e.y * k:.2f} m")
        elif cmd.type == Command.LINE_TO:
            d.append(f"{e.x * k:.2f} {e.y * k:.2f} l")
        elif cmd.type == Command.CURVE4_TO:
            d.append(f"{cmd.ctrl1.x * k:.2f} {cmd.ctrl1.y * k:.2f} {cmd.ctrl2.x * k:.2f} {cmd.ctrl2.y * k:.2f} {e.x * k:.2f} {e.y * k:.2f} c")
        elif cmd.type == Command.CURVE3_TO:  # quadratisch → kubisch
            c = cmd.ctrl
            d.append(f"{c.x * k:.2f} {c.y * k:.2f} {c.x * k:.2f} {c.y * k:.2f} {e.x * k:.2f} {e.y * k:.2f} c")
    if close:
        d.append("h")
    return " ".join(d)


def to_pdf(geom: dict, title: str = "", floor: str = "", scale: int | None = None, north: float | None = None) -> bytes:
    """Grundriss als PDF. scale = Maßstabszahl (z. B. 100); ohne Angabe der größte, der auf A4 oder A3 passt."""
    gx0, gy0, gx1, gy1 = geom["bbox"]
    s = (_fit((gx1 - gx0) * 10, (gy1 - gy0) * 10, scale) or (scale or 1000, "", False))[0]
    while True:  # Maßketten und Texte hängen vom Maßstab ab: zeichnen, prüfen, ggf. kleiner
        player, (x0, y0, x1, y1) = _record(geom, s)
        fit = _fit(x1 - x0, y1 - y0, s)
        nxt = None if (fit or scale) else _fit(x1 - x0, y1 - y0, None, start=s + 1)
        if fit or not nxt:
            s, paper, portrait = fit or (s, "A3", False)
            break
        s = nxt[0]
    W, H = PAPERS[paper][::-1] if portrait else PAPERS[paper]
    pdf = _Pdf(W, H)
    pdf.op("1 J 1 j")

    # Plan mittig im Zeichenfeld, Modell in mm → Papier in mm
    fx0, fy0, fx1, fy1 = LEFT, MARGIN + HEAD, W - MARGIN, H - MARGIN
    cx, cy = (fx0 + fx1) / 2 - (x0 + x1) / 2 / s, (fy0 + fy1) / 2 - (y0 + y1) / 2 / s
    player.transform(Matrix44.scale(1 / s, 1 / s, 1) @ Matrix44.translate(cx, cy, 0))
    for record, p in player.recordings():
        rgb = _rgb(p.color)
        lw = max(0.13, p.lineweight) if p.lineweight > 0 else 0.18
        if isinstance(record, recorder.FilledPathsRecord):
            pdf.color(rgb, False)
            pdf.op(" ".join(_path_ops(q, True) for q in record.paths if len(q)) + " f*")
        elif isinstance(record, recorder.PathRecord):
            pdf.color(rgb, True)
            pdf.op(f"{lw * PT:.2f} w " + _path_ops(record.path, False) + " S")
        elif isinstance(record, recorder.SolidLinesRecord):
            v = record.lines.vertices()
            pdf.color(rgb, True)
            pdf.op(f"{lw * PT:.2f} w " + " ".join(f"{a.x * PT:.2f} {a.y * PT:.2f} m {b.x * PT:.2f} {b.y * PT:.2f} l"
                                                  for a, b in zip(v[::2], v[1::2])) + " S")
        elif isinstance(record, recorder.PointsRecord):
            v = record.points.vertices()
            if len(v) > 2:
                pdf.color(rgb, False)
                pdf.op(" ".join(f"{a.x * PT:.2f} {a.y * PT:.2f} {'m' if i == 0 else 'l'}" for i, a in enumerate(v)) + " h f")
            elif len(v) == 2:
                pdf.color(rgb, True)
                pdf.line(v[0].x, v[0].y, v[1].x, v[1].y, lw)

    # Rahmen und Plankopf
    pdf.color((0, 0, 0), True)
    pdf.color((0, 0, 0), False)
    pdf.rect(LEFT, MARGIN, W - LEFT - MARGIN, H - 2 * MARGIN, 0.5)
    pdf.line(LEFT, MARGIN + HEAD, W - MARGIN, MARGIN + HEAD, 0.35)
    tx, ty = LEFT + 4, MARGIN + HEAD
    pdf.text(tx, ty - 8, title or "Grundriss", 13, bold=True)
    pdf.text(tx, ty - 14.5, " · ".join(x for x in (f"Grundriss {floor}" if floor else "Grundriss", f"Maßstab 1:{s} (bei Druck auf {paper})",
                                                  date.today().strftime("%d.%m.%Y")) if x), 9)
    pdf.text(tx, ty - 21, "Aus einem Bestandsplan berechnet (Planpause). Maße stammen aus den Maßketten des Plans; vor Verwendung am Bau prüfen.", 7)
    if any(w.get("estimated") for w in geom["walls"]) or any(o.get("estimated") for o in geom["openings"]):
        pdf.color((1.0, 0.5, 0.0), True)
        pdf.rect(tx, ty - 28.6, 5, 2.6, 0.4)
        pdf.text(tx + 7, ty - 28, "orange umrandet: geschätzt, nicht aus einer Maßkette", 7)

    # Maßstabsleiste 0–5 m (bei kleinen Maßstäben 0–10/20 m)
    m = 5 if s <= 100 else 10 if s <= 250 else 20 if s <= 500 else 50
    seg = m / 5 * 1000 / s
    bx, by = W - MARGIN - 6 - 5 * seg, MARGIN + 9
    pdf.color((0, 0, 0), True)
    for i in range(5):
        pdf.rect(bx + i * seg, by, seg, 2, 0.25, fill=i % 2 == 0)
        pdf.rect(bx + i * seg, by, seg, 2, 0.25)
    pdf.text(bx - 1, by + 3.5, "0", 7)
    pdf.text(bx + 5 * seg + 1.2, by + 3.5, f"{m} m", 7, right=True)
    pdf.text(bx, by - 4, f"1:{s}", 8, bold=True)

    if north is not None:  # Nordpfeil über der Maßstabsleiste
        nx, ny, r = W - MARGIN - 12, MARGIN + HEAD - 12, 6.0
        a = math.radians(north)
        dx, dy = math.sin(a), math.cos(a)
        tip = (nx + dx * r, ny + dy * r)
        l = (nx - dy * r * 0.35 - dx * r * 0.6, ny + dx * r * 0.35 - dy * r * 0.6)
        rr = (nx + dy * r * 0.35 - dx * r * 0.6, ny - dx * r * 0.35 - dy * r * 0.6)
        pdf.op(" ".join(f"{x * PT:.2f} {y * PT:.2f} {c}" for (x, y), c in ((tip, "m"), (l, "l"), ((nx, ny), "l"), (rr, "l"))) + " h f")
        pdf.text(tip[0] - 1.2 + dx * 2.5, tip[1] - 1.2 + dy * 2.5, "N", 8, bold=True)
    return pdf.bytes(f"{title} – {floor}" if floor else title)
