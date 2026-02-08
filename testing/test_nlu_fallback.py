from __future__ import annotations

import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pylink"))
sys.path.insert(0, str(ROOT))

from core.context.session import SessionContext
from core.nlu.hybrid_parser import HybridIntentParser
from core.nlu.intents import Intent
from core.nlu.llm_brain import parse_with_llm


def test_hybrid_uses_llm_for_unknown(monkeypatch) -> None:
    parser = HybridIntentParser()

    def fake_llm(text, context, timeout_ms=450):
        return Intent(name="open_app", entities={"app": "Notes"}, confidence=0.95, raw_text=text)

    monkeypatch.setattr("core.nlu.hybrid_parser.parse_with_llm", fake_llm)

    session = SessionContext()
    result = parser.parse("gibberish not matching anything", session, source="text")
    assert result.mode == "llm_fallback"
    assert result.intent.name == "open_app"


def test_hybrid_keeps_rules_when_confident(monkeypatch) -> None:
    parser = HybridIntentParser()

    called = {"value": False}

    def fake_llm(text, context, timeout_ms=450):
        called["value"] = True
        return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)

    monkeypatch.setattr("core.nlu.hybrid_parser.parse_with_llm", fake_llm)

    session = SessionContext()
    result = parser.parse("open Notes", session, source="text")
    assert result.intent.name == "open_app"
    assert result.mode == "rules"
    assert called["value"] is False


def test_hybrid_fails_closed_when_llm_unknown(monkeypatch) -> None:
    parser = HybridIntentParser()

    def fake_llm(text, context, timeout_ms=450):
        return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)

    monkeypatch.setattr("core.nlu.hybrid_parser.parse_with_llm", fake_llm)

    session = SessionContext()
    result = parser.parse("do a weird thing", session, source="text")
    assert result.intent.name == "unknown"
    assert result.mode == "rules"


def test_parse_with_llm_timeout_fail_closed(monkeypatch) -> None:
    class SlowBrain:
        def parse(self, text, context=None):
            time.sleep(0.1)
            return Intent(name="open_app", entities={"app": "Notes"}, confidence=0.9, raw_text=text)

    monkeypatch.setattr("core.nlu.llm_brain.get_brain", lambda: SlowBrain())
    result = parse_with_llm("open notes", timeout_ms=1)
    assert result.name == "unknown"
