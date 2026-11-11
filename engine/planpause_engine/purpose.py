"""Verwendungszweck eines Projekts: was der Plan dafür enthalten muss.

Ein Grundriss für den Brandschutz braucht anderes als einer fürs Aufmaß. Der Zweck steuert, worauf die KI
besonders achtet, welche Inhalte als fehlend gemeldet werden und wie die Prüfpunkte sortiert sind.
"""
from __future__ import annotations

from typing import Optional

PURPOSES: dict[str, dict] = {
    "brandschutz": {
        "label": "Brandschutz",
        "ai": ("Brandwände und Wände mit Feuerwiderstand (F30/F90, „BW“), Türen mit Feuerwiderstand (T30/T90, RS), Treppenräume, "
               "Schächte, Rettungswege und Fluchtwegbreiten. kind=brand bei jeder als Brandwand bezeichneten oder schraffierten Wand."),
        "needs": [("brand", "Brandwände"), ("treppe", "Treppen"), ("schacht", "Schächte und Aufzüge"), ("tueren", "Türen")],
        "rank": ["Brandwand", "Öffnung", "Treppe", "Schacht", "Maßkette", "Plausibilität"],
    },
    "umbau": {
        "label": "Umbau",
        "ai": "Tragende Wände, Stützen und Unterzüge, Schornsteine, Schächte, Treppen und alle Öffnungen mit Maßen.",
        "needs": [("tueren", "Türen"), ("fenster", "Fenster"), ("treppe", "Treppen")],
        "rank": ["Maßkette", "Plausibilität", "Unvermaßt", "Öffnung"],
    },
    "vermietung": {
        "label": "Vermietung",
        "ai": "Raumnamen und Raumflächen genau wie im Plan, Balkone, Terrassen und Abstellräume.",
        "needs": [("raeume", "Räume mit Namen"), ("flaechen", "Raumflächen")],
        "rank": ["Fläche", "Maßkette", "Plausibilität"],
    },
    "aufmass": {
        "label": "Aufmaß",
        "ai": "Jede Maßkette vollständig, auch Teilmaße an Öffnungen; Wanddicken an Laibungen.",
        "needs": [("ketten", "Maßketten"), ("tueren", "Türen"), ("fenster", "Fenster")],
        "rank": ["Maßkette", "Unvermaßt", "Lesefehler?", "Plausibilität"],
    },
    "energie": {
        "label": "Energieberatung",
        "ai": "Außenwände vollständig und geschlossen, alle Fenster mit Breite/Höhe/Brüstung, Außentüren, Nordpfeil, unbeheizte Räume.",
        "needs": [("aussen", "Außenwände"), ("fenster", "Fenster"), ("tueren", "Türen")],
        "rank": ["Kontur", "Öffnung", "Maßkette"],
    },
}


def purpose_label(key: Optional[str]) -> str:
    return PURPOSES.get(key or "", {}).get("label", "")


def ai_hint(key: Optional[str]) -> str:
    """Absatz für den KI-Prompt, leer wenn kein Zweck gesetzt ist."""
    p = PURPOSES.get(key or "")
    if not p:
        return ""
    return (f"\n\n## Verwendungszweck: {p['label']}\nDer Plan wird für {p['label']} gebraucht. Achte deshalb besonders auf: {p['ai']} "
            "Fehlt davon etwas im Plan, nenne es in ai_issues.")
