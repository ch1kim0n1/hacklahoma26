#!/usr/bin/env python3
"""
Interactive demo for the Affection NLU model.
Run:
  python testing/demo_affection_nlu.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "pylink"))

from core.context.session import SessionContext
from core.nlu.affection_model import AffectionNLUModel


def _print_assessment(payload: dict) -> None:
    mood = payload["mood_percent"]
    risk = payload["risk_level"]
    print("\n" + "=" * 70)
    print(f"Mood: {mood:.2f}% | Risk: {risk} | Intervene: {payload['should_intervene']}")
    print("-" * 70)
    variables = payload.get("variables", {})
    top_variables = sorted(variables.items(), key=lambda item: abs(item[1]), reverse=True)[:8]
    print("Top variables:")
    for name, value in top_variables:
        print(f"  - {name}: {value:.4f}")
    if payload["should_intervene"]:
        print("\nIntervention:")
        print(f"  {payload['intervention']['message']}")
        suggestions = payload["intervention"].get("suggestions", [])
        if suggestions:
            print("  Suggestions:")
            for item in suggestions:
                print(f"    * {item}")
    print("=" * 70)


def main() -> int:
    model = AffectionNLUModel()
    session = SessionContext()

    print("\nAffection NLU demo. Type a message, or 'exit' to quit.\n")
    while True:
        raw = input("Input> ").strip()
        if not raw:
            continue
        if raw.lower() in {"exit", "quit"}:
            break
        assessment = model.analyze(raw, session)
        payload = assessment.to_dict()
        session.record_affection(payload, raw)
        _print_assessment(payload)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
