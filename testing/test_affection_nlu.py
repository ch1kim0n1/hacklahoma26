#!/usr/bin/env python3
"""Targeted tests for Affection NLU scoring and runtime triggers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "pylink"))

from core.context.session import SessionContext
from core.nlu.affection_model import AffectionNLUModel
from core.runtime.orchestrator import PixelLinkRuntime


def test_positive_vs_negative_score() -> None:
    model = AffectionNLUModel()
    session = SessionContext()

    positive_assessment = model.analyze("I feel grateful, calm, and hopeful today.", session)
    positive = positive_assessment.mood_percent
    session.record_affection(positive_assessment.to_dict(), "p")
    negative = model.analyze("I am overwhelmed, hopeless, and everything is broken.", session).mood_percent
    assert positive > negative, f"Expected positive score > negative score, got {positive} <= {negative}"


def test_low_mood_intervention_trigger() -> None:
    model = AffectionNLUModel()
    session = SessionContext()
    assessment = model.analyze("I am done. Nothing works. I want to give up.", session)
    assert assessment.should_intervene, "Expected intervention for severe distress text"
    assert assessment.risk_level in {"high", "critical"}, f"Unexpected risk level: {assessment.risk_level}"


def test_history_aware_penalty() -> None:
    model = AffectionNLUModel()
    session = SessionContext()

    for text in [
        "Everything is bad and stressful.",
        "Still overwhelmed and blocked by deadlines.",
        "This is terrible and impossible.",
    ]:
        assessed = model.analyze(text, session).to_dict()
        session.record_affection(assessed, text)

    followup = model.analyze("I am overwhelmed and hopeless again.", session).to_dict()
    assert followup["variables"]["volatility_penalty"] > 0.1
    assert followup["variables"]["trend_signal"] < 0.0


def test_runtime_pauses_automation_on_critical_mood() -> None:
    runtime = PixelLinkRuntime(dry_run=True, enable_kill_switch=False, verbose=False)
    try:
        result = runtime.handle_input(
            "open Notes, this is impossible, I am hopeless and done with everything",
            source="text",
        )
    finally:
        runtime.close()

    assert result["status"] == "support_required", f"Expected support_required, got {result['status']}"
    assert result["affection"]["should_pause_automation"], "Expected pause flag for critical mood"


def main() -> int:
    tests = [
        test_positive_vs_negative_score,
        test_low_mood_intervention_trigger,
        test_history_aware_penalty,
        test_runtime_pauses_automation_on_critical_mood,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
