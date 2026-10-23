"""Gesamtablauf: Planmodell -> Solver -> Geometrie -> Prüfpunkte."""
from __future__ import annotations

from .checks import Issue, run_checks
from .geometry import build_geometry
from .model import PlanModel
from .solver import solve


def analyze(plan: PlanModel) -> dict:
    sol = solve(plan)
    geom = build_geometry(plan, sol)
    issues = run_checks(plan, sol, geom)
    lines = geom["lines"]["x"] + geom["lines"]["y"]
    rooms = [r for r in geom["rooms"] if r["area_stated"] and r["area_geom"]]
    stats = {
        "lines_total": len(lines),
        "lines_measured": sum(1 for l in lines if l["status"] == "mass"),
        "lines_from_area": sum(1 for l in lines if l["status"] == "flaeche"),
        "lines_from_drawing": sum(1 for l in lines if l["status"] == "zeichnung"),
        "chains_total": len(geom["chains"]),
        "chains_suspect": sum(1 for c in geom["chains"] if c["suspect"]),
        "conflicts": len(sol.x.conflicts) + len(sol.y.conflicts),
        "rooms_checked": len(rooms),
        "rooms_ok": sum(1 for r in rooms if abs(r["area_geom"] - r["area_stated"]) / r["area_stated"] <= 0.03),
        "scale_px_per_cm": [sol.x.scale, sol.y.scale],
    }
    return {"geometry": geom, "issues": [i.model_dump() for i in issues], "stats": stats,
            "image_transform": image_transform(plan, geom), "quality": assess_quality(plan, stats)}


PHOTO_TIPS = [
    "Original statt Kopie oder Bildschirmfoto verwenden, ohne Wasserzeichen.",
    "Gerade von oben fotografieren, bei Tageslicht, ohne Schatten und Blendung.",
    "Alle Maßketten müssen im Bild sein; große Pläne lieber in zwei Hälften fotografieren.",
    "Nur einen Grundriss pro Bild, andere Planteile abdecken oder wegschneiden.",
]


def assess_quality(plan: PlanModel, stats: dict) -> dict:
    """Ampel für das Gesamtergebnis: gut | eingeschraenkt | nicht_auswertbar, mit Begründung.

    Verhindert, dass ein kaum lesbarer Plan wie ein fertiger Grundriss aussieht."""
    blocking, limiting = [], []
    values = {ax: [v for c in plan.chains if c.axis == ax for v in c.values] for ax in ("x", "y")}
    n_values = len(values["x"]) + len(values["y"])
    n_uncertain = sum(len(c.uncertain) for c in plan.chains)
    share = stats["lines_measured"] / stats["lines_total"] if stats["lines_total"] else 0.0

    if not plan.walls:
        blocking.append("Es wurden keine Wände erkannt.")
    if not values["x"] and not values["y"]:
        blocking.append("Kein Maßstab erkennbar: Ohne lesbare Maßzahl sind alle Größen nur aus der Zeichnung geschätzt und nicht in Zentimetern belastbar.")
    for ax, name in (("x", "waagerechten"), ("y", "senkrechten")):
        if not values[ax]:
            blocking.append(f"Es sind keine {name} Maße lesbar. In dieser Richtung ist der Plan nur geschätzt.")
    if share < 0.25:
        blocking.append(f"Nur {round(share * 100)} % der Kanten sind durch Maße festgelegt.")
    elif share < 0.5:
        limiting.append(f"Nur {round(share * 100)} % der Kanten sind durch Maße festgelegt, der Rest stammt aus der Zeichnung.")
    if n_values and n_uncertain / n_values >= 0.5:
        limiting.append(f"{n_uncertain} von {n_values} Maßzahlen waren schwer lesbar.")
    if stats["conflicts"] >= 3 and stats["conflicts"] > stats["chains_total"] / 2:
        limiting.append(f"{stats['conflicts']} Maßketten widersprechen sich.")

    level = "nicht_auswertbar" if blocking else "eingeschraenkt" if limiting else "gut"
    return {"level": level, "reasons": blocking + limiting, "tips": PHOTO_TIPS if level != "gut" else []}


def image_transform(plan: PlanModel, geom: dict) -> dict | None:
    """Lineare Abbildung cm -> Pixel des entzerrten Bildes je Achse (für die Überlagerung)."""
    out = {}
    for ax in ("x", "y"):
        pairs = []
        # bevorzugt vermaßte Linien; fehlen sie (schlecht lesbarer Plan), alle Linien mit Bildlage
        for ok in (lambda st: st == "mass", lambda st: True):
            pos = {l["id"]: l["pos"] for l in geom["lines"][ax] if ok(l["status"])}
            pairs = [(pos[l.id], l.px) for l in plan.axes[ax] if l.px is not None and l.id in pos]
            if len(pairs) >= 2:
                break
        if len(pairs) < 2:
            return None
        n = len(pairs)
        mx = sum(p for p, _ in pairs) / n
        my = sum(q for _, q in pairs) / n
        sxx = sum((p - mx) ** 2 for p, _ in pairs)
        if sxx == 0:
            return None
        s = sum((p - mx) * (q - my) for p, q in pairs) / sxx
        out[ax] = {"scale": s, "offset": my - s * mx}
    return out


def issues_from(result: dict) -> list[Issue]:
    return [Issue.model_validate(i) for i in result["issues"]]
