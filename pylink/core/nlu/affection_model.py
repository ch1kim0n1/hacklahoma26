from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


POSITIVE_TERMS = {
    "good",
    "great",
    "awesome",
    "nice",
    "excellent",
    "happy",
    "joy",
    "love",
    "calm",
    "relaxed",
    "grateful",
    "hopeful",
    "progress",
    "better",
    "proud",
    "thankful",
    "win",
}

NEGATIVE_TERMS = {
    "bad",
    "awful",
    "terrible",
    "sad",
    "angry",
    "upset",
    "anxious",
    "depressed",
    "frustrated",
    "stressed",
    "hate",
    "lonely",
    "tired",
    "overwhelmed",
    "burned",
    "burnout",
    "worthless",
    "hopeless",
    "exhausted",
}

AFFECTION_TERMS = {
    "care",
    "caring",
    "support",
    "supported",
    "hug",
    "kind",
    "kindness",
    "warm",
    "safe",
    "connection",
    "connected",
    "close",
    "compassion",
}

GRATITUDE_TERMS = {"thanks", "thank", "appreciate", "grateful", "gratitude"}

STRESS_TERMS = {
    "deadline",
    "urgent",
    "asap",
    "pressure",
    "panic",
    "stuck",
    "late",
    "behind",
    "can't",
    "cannot",
    "failure",
    "failing",
    "broken",
    "blocked",
    "impossible",
}

RECOVERY_TERMS = {
    "breathe",
    "break",
    "rest",
    "recover",
    "walk",
    "hydrate",
    "pause",
    "step back",
    "reset",
    "regroup",
}

HELP_SEEKING_TERMS = {
    "help",
    "assist",
    "support",
    "can you",
    "please",
    "guide",
    "advise",
}

HOPELESSNESS_TERMS = {
    "give up",
    "done",
    "can't do this",
    "nothing works",
    "no point",
    "worthless",
    "hopeless",
}

HOSTILITY_TERMS = {"idiot", "stupid", "useless", "shut up", "hate you"}


@dataclass
class AffectionAssessment:
    mood_percent: float
    risk_level: str
    should_intervene: bool
    should_pause_automation: bool
    variables: dict[str, float]
    detected_signals: dict[str, float]
    intervention: dict[str, Any]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mood_percent": round(self.mood_percent, 2),
            "risk_level": self.risk_level,
            "should_intervene": self.should_intervene,
            "should_pause_automation": self.should_pause_automation,
            "variables": {key: round(value, 4) for key, value in self.variables.items()},
            "detected_signals": {key: round(value, 4) for key, value in self.detected_signals.items()},
            "intervention": self.intervention,
            "generated_at": self.generated_at,
        }


class AffectionNLUModel:
    """
    Multi-signal mood model tuned for conversational inputs.
    Score output is 0..100 where lower values represent lower emotional state.
    """

    def __init__(self, low_threshold: float = 42.0, critical_threshold: float = 25.0) -> None:
        self.low_threshold = low_threshold
        self.critical_threshold = critical_threshold

    def analyze(self, text: str, session=None) -> AffectionAssessment:
        normalized_text = " ".join((text or "").split())
        lowered = normalized_text.lower()
        tokens = re.findall(r"[a-zA-Z']+", lowered)
        token_count = max(1, len(tokens))

        positive_hits = _match_terms(lowered, POSITIVE_TERMS)
        negative_hits = _match_terms(lowered, NEGATIVE_TERMS)
        affection_hits = _match_terms(lowered, AFFECTION_TERMS)
        gratitude_hits = _match_terms(lowered, GRATITUDE_TERMS)
        stress_hits = _match_terms(lowered, STRESS_TERMS)
        recovery_hits = _match_terms(lowered, RECOVERY_TERMS)
        help_hits = _match_terms(lowered, HELP_SEEKING_TERMS)
        hopeless_hits = _match_terms(lowered, HOPELESSNESS_TERMS)
        hostility_hits = _match_terms(lowered, HOSTILITY_TERMS)

        sentiment_balance = _bounded(
            ((positive_hits - negative_hits) / token_count) * 6.0,
            -1.0,
            1.0,
        )
        affection_density = _bounded(((affection_hits + gratitude_hits) / token_count) * 8.0, 0.0, 1.0)
        stress_density = _bounded(((stress_hits + hopeless_hits) / token_count) * 9.0, 0.0, 1.0)
        hostility_density = _bounded((hostility_hits / token_count) * 8.0, 0.0, 1.0)
        recovery_density = _bounded((recovery_hits / token_count) * 10.0, 0.0, 1.0)
        help_seeking_density = _bounded((help_hits / token_count) * 7.0, 0.0, 1.0)
        hopelessness_density = _bounded((hopeless_hits / token_count) * 10.0, 0.0, 1.0)

        exclamation_count = normalized_text.count("!")
        question_count = normalized_text.count("?")
        uppercase_ratio = _uppercase_ratio(normalized_text)
        elongated_ratio = _elongated_word_ratio(tokens)
        punctuation_intensity = _bounded(
            (exclamation_count * 0.12) + (uppercase_ratio * 0.75) + (elongated_ratio * 0.65),
            0.0,
            1.0,
        )
        urgency_density = _bounded(
            ((1 if "asap" in lowered else 0) + len(re.findall(r"\burgent\b", lowered)) + exclamation_count * 0.2)
            / 3.0,
            0.0,
            1.0,
        )

        social_reach_out = _bounded(0.55 * help_seeking_density + 0.45 * question_count / max(1.0, token_count / 6.0), 0.0, 1.0)
        gratitude_boost = _bounded((gratitude_hits / token_count) * 10.0, 0.0, 1.0)
        negativity_overdrive = _bounded(stress_density * 0.6 + hopelessness_density * 0.7 + hostility_density * 0.8, 0.0, 1.0)

        trend_signal, volatility_penalty, recency_drop = self._history_signals(session, sentiment_balance, stress_density)

        weighted_sum = (
            0.26 * sentiment_balance
            + 0.14 * affection_density
            + 0.12 * gratitude_boost
            + 0.11 * recovery_density
            + 0.08 * social_reach_out
            + 0.08 * trend_signal
            - 0.19 * stress_density
            - 0.12 * urgency_density
            - 0.11 * punctuation_intensity
            - 0.14 * negativity_overdrive
            - 0.08 * volatility_penalty
            - 0.07 * recency_drop
        )
        mood_percent = _bounded(58.0 + (weighted_sum * 100.0), 0.0, 100.0)

        risk_level = self._risk_level(mood_percent)
        should_pause_automation = mood_percent <= self.critical_threshold or hopelessness_density >= 0.65
        should_intervene = mood_percent <= self.low_threshold or hopelessness_density >= 0.5
        intervention = self._build_intervention(mood_percent, risk_level, should_pause_automation)

        variables = {
            "sentiment_balance": sentiment_balance,
            "affection_density": affection_density,
            "stress_density": stress_density,
            "hostility_density": hostility_density,
            "recovery_density": recovery_density,
            "help_seeking_density": help_seeking_density,
            "hopelessness_density": hopelessness_density,
            "punctuation_intensity": punctuation_intensity,
            "urgency_density": urgency_density,
            "social_reach_out": social_reach_out,
            "gratitude_boost": gratitude_boost,
            "negativity_overdrive": negativity_overdrive,
            "trend_signal": trend_signal,
            "volatility_penalty": volatility_penalty,
            "recency_drop": recency_drop,
            "uppercase_ratio": uppercase_ratio,
            "elongated_ratio": elongated_ratio,
        }
        detected_signals = {
            "positive_hits": float(positive_hits),
            "negative_hits": float(negative_hits),
            "affection_hits": float(affection_hits),
            "gratitude_hits": float(gratitude_hits),
            "stress_hits": float(stress_hits),
            "recovery_hits": float(recovery_hits),
            "help_hits": float(help_hits),
            "hopeless_hits": float(hopeless_hits),
            "hostility_hits": float(hostility_hits),
            "exclamation_count": float(exclamation_count),
            "question_count": float(question_count),
            "token_count": float(token_count),
        }
        return AffectionAssessment(
            mood_percent=mood_percent,
            risk_level=risk_level,
            should_intervene=should_intervene,
            should_pause_automation=should_pause_automation,
            variables=variables,
            detected_signals=detected_signals,
            intervention=intervention,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _history_signals(self, session, sentiment_balance: float, stress_density: float) -> tuple[float, float, float]:
        if not session or not getattr(session, "mood_history", None):
            return 0.0, 0.0, 0.0

        recent = session.mood_history[-8:]
        previous_scores = [float(item.get("mood_percent", 0.0)) for item in recent if "mood_percent" in item]
        if not previous_scores:
            return 0.0, 0.0, 0.0

        avg_previous = sum(previous_scores) / len(previous_scores)
        current_projection = _bounded(55.0 + 35.0 * sentiment_balance - 20.0 * stress_density, 0.0, 100.0)
        trend_signal = _bounded((current_projection - avg_previous) / 35.0, -1.0, 1.0)

        volatility_penalty = 0.0
        if len(previous_scores) >= 3:
            stdev = statistics.pstdev(previous_scores)
            volatility_penalty = _bounded(stdev / 18.0, 0.0, 1.0)

        recency_drop = 0.0
        last_score = previous_scores[-1]
        if last_score - current_projection > 12.0:
            recency_drop = _bounded((last_score - current_projection) / 30.0, 0.0, 1.0)

        return trend_signal, volatility_penalty, recency_drop

    def _risk_level(self, mood_percent: float) -> str:
        if mood_percent <= self.critical_threshold:
            return "critical"
        if mood_percent <= self.low_threshold:
            return "high"
        if mood_percent <= 58.0:
            return "medium"
        return "low"

    def _build_intervention(self, mood_percent: float, risk_level: str, should_pause_automation: bool) -> dict[str, Any]:
        rounded = round(mood_percent, 1)
        if risk_level == "critical":
            return {
                "message": f"Mood signal is {rounded}%. I paused automation and switched to support mode.",
                "suggestions": [
                    "take a 2 minute reset",
                    "ask for one small next step",
                    "create reminder drink water in 10 minutes",
                ],
                "recommended_actions": ["pause_automation", "reduce_task_load", "offer_grounding"],
                "priority": "critical",
                "paused": should_pause_automation,
            }
        if risk_level == "high":
            return {
                "message": f"Mood signal is {rounded}%. I detected stress and switched to gentle guidance.",
                "suggestions": [
                    "break this into one tiny action",
                    "create reminder take a short break",
                    "open website breathing exercise",
                ],
                "recommended_actions": ["offer_break", "simplify_plan", "slow_execution"],
                "priority": "high",
                "paused": should_pause_automation,
            }
        if risk_level == "medium":
            return {
                "message": f"Mood signal is {rounded}%. You are stable but showing mild strain.",
                "suggestions": [
                    "continue with shorter commands",
                    "take a quick posture check",
                ],
                "recommended_actions": ["monitor"],
                "priority": "medium",
                "paused": False,
            }
        return {
            "message": f"Mood signal is {rounded}%. Emotional state looks healthy.",
            "suggestions": [],
            "recommended_actions": ["none"],
            "priority": "low",
            "paused": False,
        }


def _match_terms(text: str, terms: set[str]) -> int:
    hits = 0
    for term in terms:
        if " " in term:
            if term in text:
                hits += 1
            continue
        if re.search(rf"\b{re.escape(term)}\b", text):
            hits += 1
    return hits


def _uppercase_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for char in letters if char.isupper())
    return _bounded(upper / len(letters), 0.0, 1.0)


def _elongated_word_ratio(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    elongated = 0
    for token in tokens:
        if re.search(r"(.)\1\1", token):
            elongated += 1
    return _bounded(elongated / len(tokens), 0.0, 1.0)


def _bounded(value: float, lower: float, upper: float) -> float:
    if math.isnan(value):
        return lower
    return max(lower, min(upper, value))
