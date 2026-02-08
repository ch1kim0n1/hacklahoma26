"""Hybrid NLU routing: fast rule parser with bounded LLM fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.nlu.intents import Intent
from core.nlu.llm_brain import parse_with_llm
from core.nlu.parser import parse_intent


@dataclass
class NLUResult:
    intent: Intent
    mode: str = "rules"


_REQUIRED_ENTITIES: dict[str, tuple[str, ...]] = {
    "open_app": ("app",),
    "focus_app": ("app",),
    "close_app": ("app",),
    "open_website": ("url",),
    "search_web": ("query",),
    "search_youtube": ("query",),
    "open_file": ("path",),
    "type_text": ("content",),
    "press_key": ("key",),
    "search_file": ("query",),
    "login": ("service",),
}


class HybridIntentParser:
    def __init__(self) -> None:
        self.enabled = _env_bool("PIXELINK_ENABLE_HYBRID_NLU", default=True)
        self.confidence_threshold = float(os.getenv("PIXELINK_NLU_CONFIDENCE_THRESHOLD", "0.78"))
        self.timeout_ms_text = int(os.getenv("PIXELINK_LLM_TIMEOUT_MS_TEXT", "450"))
        self.timeout_ms_voice = int(os.getenv("PIXELINK_LLM_TIMEOUT_MS_VOICE", "700"))

    def parse(self, text: str, context=None, *, source: str = "text") -> NLUResult:
        rule_intent = parse_intent(text, context)
        if not self.enabled:
            return NLUResult(intent=rule_intent, mode="rules")

        if not self._should_fallback(rule_intent):
            return NLUResult(intent=rule_intent, mode="rules")

        timeout_ms = self.timeout_ms_voice if source == "voice" else self.timeout_ms_text
        llm_context = {"last_intent": getattr(context, "last_intent", None)}
        llm_intent = parse_with_llm(text, llm_context, timeout_ms=timeout_ms)
        if self._is_better_fallback(rule_intent, llm_intent):
            return NLUResult(intent=llm_intent, mode="llm_fallback")
        return NLUResult(intent=rule_intent, mode="rules")

    def _should_fallback(self, intent: Intent) -> bool:
        if intent.name == "unknown":
            return True
        if intent.confidence < self.confidence_threshold:
            return True
        return self._missing_required_entities(intent)

    def _missing_required_entities(self, intent: Intent) -> bool:
        required = _REQUIRED_ENTITIES.get(intent.name, ())
        if not required:
            return False
        for key in required:
            value = intent.entities.get(key, "")
            if value is None:
                return True
            if isinstance(value, str) and not value.strip():
                return True
        return False

    def _is_better_fallback(self, rule_intent: Intent, llm_intent: Intent) -> bool:
        if llm_intent.name == "unknown":
            return False
        if llm_intent.confidence < 0.4:
            return False
        if self._missing_required_entities(llm_intent):
            return False
        if rule_intent.name == "unknown":
            return True
        return llm_intent.confidence >= max(rule_intent.confidence, self.confidence_threshold)


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
