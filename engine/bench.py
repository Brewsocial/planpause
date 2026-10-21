"""Genauigkeits-Benchmark: künstliche Lesefehler in echten Plänen.

Für jede Maßzahl jeder Kette wird einzeln ein Fehler eingesetzt (Zahlendreher,
Ziffer vertauscht oder falsche Zehnerstelle) und geprüft:
  erkannt   – der Solver meldet einen Widerspruch
  gefunden  – der verdächtigte Wert ist der verfälschte
  korrigiert – der vorgeschlagene Wert liegt höchstens 1 cm neben dem Original
  kontrollierbar – ohne Redundanz ist ein Fehler grundsätzlich nicht erkennbar

Aufruf: python bench.py [plan.json ...]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from planpause_engine.model import PlanModel
from planpause_engine.solver import solve


def corrupt(v: float, rng: random.Random) -> float:
    s = f"{v:g}"
    digits = [i for i, c in enumerate(s) if c.isdigit()]
    for _ in range(10):
        kind = rng.choice(["swap", "digit", "shift"])
        if kind == "swap" and len(digits) >= 2:
            i = rng.randrange(len(digits) - 1)
            a, b = digits[i], digits[i + 1]
            t = list(s); t[a], t[b] = t[b], t[a]; out = float("".join(t))
        elif kind == "digit":
            i = rng.choice(digits); t = list(s); t[i] = str((int(t[i]) + rng.choice([1, 2, 3, 5, 7])) % 10); out = float("".join(t))
        else:
            out = v + rng.choice([-20, -10, 10, 20, 30])
        if out > 0 and abs(out - v) >= 3:
            return out
    return v + 10


def run(path: Path, seed: int = 1) -> dict:
    base = json.loads(path.read_text())
    plan0 = PlanModel.model_validate(base)
    sol0 = solve(plan0)
    known = {(k.chosen.constraint.ref, k.chosen.constraint.index) for ax in (sol0.x, sol0.y) for k in ax.conflicts if k.candidates}
    rng = random.Random(seed)
    stats = dict(faelle=0, erkannt=0, gefunden=0, korrigiert=0, nicht_kontrollierbar=0)
    for ci, ch in enumerate(base["chains"]):
        for vi, v in enumerate(ch["values"]):
            if (ch["id"], vi) in known:
                continue
            m = json.loads(json.dumps(base))
            m["chains"][ci]["values"][vi] = corrupt(v, rng)
            plan = PlanModel.model_validate(m)
            sol = solve(plan)
            ax = sol.x if ch["axis"] == "x" else sol.y
            new = [k for k in ax.conflicts if k.candidates and (k.chosen.constraint.ref, k.chosen.constraint.index) not in known]
            stats["faelle"] += 1
            hit = [k for k in ax.conflicts if any(c.constraint.ref == ch["id"] and c.constraint.index == vi for c in k.candidates)]
            if not ax.conflicts or len(ax.conflicts) == len([k for k in sol0.ax(ch["axis"]).conflicts]):
                stats["nicht_kontrollierbar"] += 1
                continue
            stats["erkannt"] += 1
            top = [k for k in new if k.chosen.constraint.ref == ch["id"] and k.chosen.constraint.index == vi]
            if top:
                stats["gefunden"] += 1
                if abs(top[0].chosen.suggested - v) <= 1.0:
                    stats["korrigiert"] += 1
            del hit
    return stats


if __name__ == "__main__":
    files = [Path(p) for p in sys.argv[1:]] or sorted((Path(__file__).parent / "tests" / "fixtures").glob("plan_*.json"))
    for f in files:
        s = run(f)
        k = s["faelle"] - s["nicht_kontrollierbar"]
        pct = lambda n: f"{100 * n / k:.0f} %" if k else "–"  # noqa: E731
        print(f"{f.name}: {s['faelle']} Fehler eingesetzt, {s['nicht_kontrollierbar']} ohne Kontrollmaß")
        print(f"   erkannt {pct(s['erkannt'])} · richtiger Wert verdächtigt {pct(s['gefunden'])} · korrekt verbessert {pct(s['korrigiert'])}")
