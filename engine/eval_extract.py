"""Vollständigkeit der KI-Extraktion messen: Ergebnis gegen eine von Hand erstellte Musterlösung.

Zählt, wie viel der Musterlösung die KI erfasst hat (Wände, Innenwände, Fenster, Türen, Räume, Maßzahlen). Die Vergleiche hängen nicht vom Koordinatensystem ab, deshalb funktionieren sie auch mit einem
anderen Foto desselben Plans. Maßzahlen zählen nur, wenn der Wert stimmt (nicht nur die Anzahl).

Kostenlos, vorhandenes Ergebnis bewerten:
    python eval_extract.py --plan ergebnis.json --ref tests/fixtures/plan_bungalow.json

Neuer KI-Lauf (kostet API-Guthaben), Ergebnis landet in eval_out/:
    python eval_extract.py --image prepared.jpg --ref tests/fixtures/plan_bungalow.json --effort high --budget 80000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from planpause_engine.model import PlanModel


def _norm(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def score(plan: PlanModel, ref: PlanModel) -> dict:
    """Je Kategorie: (gefunden, Soll, Quote). Mehr als das Soll wird auf 100 % gekappt."""
    ops, opr = Counter(o.type for o in plan.openings), Counter(o.type for o in ref.openings)
    rooms_hit = len({_norm(r.name) for r in plan.rooms} & {_norm(r.name) for r in ref.rooms})
    vals = Counter(v for c in plan.chains for v in c.values)
    vals_ref = Counter(v for c in ref.chains for v in c.values)
    rows = {
        "Maßzahlen": (sum((vals & vals_ref).values()), sum(vals_ref.values())),
        "Räume": (rooms_hit, len(ref.rooms)),
        "Türen": (ops["door"], opr["door"]),
        "Fenster": (ops["window"], opr["window"]),
        "Wände": (len(plan.walls), len(ref.walls)),
        "davon Innenwände": (sum(w.kind == "innen" for w in plan.walls), sum(w.kind == "innen" for w in ref.walls)),
    }
    return {k: (a, b, min(1.0, a / b) if b else 1.0) for k, (a, b) in rows.items()}


def stats(plan: PlanModel) -> dict:
    """Kennzahlen ohne Musterlösung: wie vollständig ist das Modell?"""
    from planpause_engine.pipeline import analyze
    r = analyze(plan)
    ops = Counter(o.type for o in plan.openings)
    return {"Wände": len(plan.walls), "davon Innenwände": sum(w.kind == "innen" for w in plan.walls),
            "Fenster": ops["window"], "Türen": ops["door"], "Räume": len(plan.rooms),
            "Räume mit Umriss": sum(len(x.poly) >= 3 for x in plan.rooms),
            "Maßzahlen": sum(len(c.values) for c in plan.chains),
            "Kanten vermaßt": f"{r['stats']['lines_measured']}/{r['stats']['lines_total']}",
            "Widersprüche": r["stats"]["conflicts"], "Ampel": r["quality"]["level"]}


def print_stats(s: dict, title: str) -> None:
    print(f"\n{title}")
    for k, v in s.items():
        print(f"  {k:<18} {v}")


def print_score(s: dict, title: str) -> None:
    print(f"\n{title}")
    for k, (a, b, q) in s.items():
        print(f"  {k:<18} {a:>6} / {b:<6} {q:>6.0%}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default=None, help="Musterlösung (Planmodell als JSON); ohne: nur Kennzahlen")
    ap.add_argument("--plan", help="vorhandenes KI-Ergebnis (plan.json) bewerten, kostenlos")
    ap.add_argument("--image", help="aufbereitetes Bild für einen neuen KI-Lauf (kostet Guthaben)")
    ap.add_argument("--effort", default=None, help="low | medium | high | xhigh | max")
    ap.add_argument("--budget", type=int, default=None, help="Denkbudget in Tokens (mind. 20000)")
    ap.add_argument("--notes", default="")
    ap.add_argument("--review", action="store_true", help="mit --plan und --image: nur den Vollständigkeits-Check auf ein vorhandenes Ergebnis anwenden")
    args = ap.parse_args()
    ref = PlanModel.model_validate(json.loads(Path(args.ref).read_text())) if args.ref else None

    if args.plan and args.review:
        return review_only(args, ref)
    if args.plan:
        plan = PlanModel.model_validate(json.loads(Path(args.plan).read_text()))
        print_stats(stats(plan), f"Kennzahlen von {args.plan}")
        if ref:
            print_score(score(plan, ref), f"Bewertung von {args.plan}")
        return
    if not args.image:
        sys.exit("--plan oder --image angeben")

    # Einstellungen vor dem Import setzen, extract liest sie beim Laden
    if args.effort:
        os.environ["PLANPAUSE_EFFORT"] = args.effort
    if args.budget:
        os.environ["PLANPAUSE_TASK_BUDGET"] = str(args.budget)
    from planpause_engine.extract import EFFORT, TASK_BUDGET, extract_plan
    from planpause_engine.preprocess import Prepared

    prep = Prepared.load(Path(args.image).read_bytes())
    print(f"KI-Lauf: Bild {prep.size[0]}×{prep.size[1]}, Gründlichkeit {EFFORT}, Denkbudget {TASK_BUDGET} …", flush=True)
    t = time.time()
    plan, log = extract_plan(prep, args.notes)
    out = Path(__file__).parent / "eval_out" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=1))
    (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    u = [r["usage"] for r in log["rounds"]]
    print(f"Fertig in {time.time() - t:.0f} s · {len(u)} Runde(n) · Eingabe {sum(x['input_tokens'] for x in u)} · "
          f"Ausgabe {sum(x['output_tokens'] for x in u)} Tokens · {log['cost_usd']:.2f} $ · gespeichert in {out}")
    print_stats(stats(plan), f"Kennzahlen ({EFFORT}, Budget {TASK_BUDGET})")
    if ref:
        print_score(score(plan, ref), f"Bewertung ({EFFORT}, Budget {TASK_BUDGET})")


def review_only(args, ref) -> None:
    """Vollständigkeits-Check auf ein vorhandenes Ergebnis (kostet nur den zweiten Durchgang)."""
    if not args.image:
        sys.exit("--review braucht --image")
    if args.effort:
        os.environ["PLANPAUSE_EFFORT"] = args.effort
    import anthropic
    from planpause_engine.extract import DEFAULT_MODEL, EFFORT, TASK_BUDGET, usage_cost
    from planpause_engine.preprocess import Prepared
    from planpause_engine.review import review_plan
    plan = PlanModel.model_validate(json.loads(Path(args.plan).read_text()))
    prep = Prepared.load(Path(args.image).read_bytes())
    request = dict(thinking={"type": "adaptive"}, output_config={"effort": EFFORT, "task_budget": {"type": "tokens", "total": TASK_BUDGET}},
                   betas=["server-side-fallback-2026-07-01", "task-budgets-2026-03-13"], fallbacks="default")
    t = time.time()
    merged, rlog = review_plan(prep, plan, anthropic.Anthropic(), DEFAULT_MODEL, 128000, request)
    out = Path(args.plan).parent / "review"
    out.mkdir(exist_ok=True)
    (out / "plan.json").write_text(json.dumps(merged.model_dump(mode="json"), ensure_ascii=False, indent=1))
    (out / "log.json").write_text(json.dumps(rlog, ensure_ascii=False, indent=1, default=str))
    print(f"Check fertig in {time.time() - t:.0f} s · {usage_cost(DEFAULT_MODEL, rlog.get('usage') or {}):.2f} $ · ergänzt: {rlog.get('added')} · {rlog.get('notes') or rlog.get('result')}")
    print_stats(stats(plan), "vorher")
    print_stats(stats(merged), "nach dem Vollständigkeits-Check")
    if ref:
        print_score(score(merged, ref), "Bewertung nach dem Check")


if __name__ == "__main__":
    main()
