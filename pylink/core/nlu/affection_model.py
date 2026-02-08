from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Plutchik's Wheel of Emotions - 8 primary emotions with intensity tiers
# ---------------------------------------------------------------------------
# Each primary emotion has 3 intensity levels: mild, moderate, intense
EMOTION_TAXONOMY = {
    "joy": {
        "intense": {"ecstasy", "elated", "euphoric", "blissful", "thrilled", "exhilarated", "overjoyed"},
        "moderate": {"happy", "joyful", "cheerful", "delighted", "pleased", "glad", "content", "satisfied", "enjoying"},
        "mild": {"serene", "okay", "fine", "alright", "peaceful", "comfortable", "pleasant", "calm", "relaxed"},
    },
    "trust": {
        "intense": {"admiration", "devoted", "worship", "adore", "idolize", "revere"},
        "moderate": {"trust", "confident", "secure", "reliable", "faith", "believe", "loyal", "committed"},
        "mild": {"acceptance", "tolerant", "open", "willing", "receptive", "agreeable"},
    },
    "fear": {
        "intense": {"terror", "terrified", "panic", "panicking", "panicked", "horror", "dread", "petrified", "paralyzed", "overwhelmed", "freaking out"},
        "moderate": {"afraid", "scared", "frightened", "anxious", "worried", "worrying", "nervous", "uneasy", "alarmed", "stressed", "stressing", "pressured", "swamped", "dreading", "fearing"},
        "mild": {"apprehensive", "uncertain", "hesitant", "wary", "cautious", "unsure", "tense", "concerned", "on edge", "uneasy", "restless"},
    },
    "surprise": {
        "intense": {"amazement", "astonished", "stunned", "shocked", "flabbergasted", "blown away"},
        "moderate": {"surprised", "unexpected", "startled", "caught off guard", "wow", "whoa"},
        "mild": {"curious", "intrigued", "interested", "wondering", "huh", "hmm"},
    },
    "sadness": {
        "intense": {"grief", "devastated", "heartbroken", "anguish", "despairing", "miserable", "wrecked", "shattered", "crushed", "destroyed"},
        "moderate": {"sad", "unhappy", "depressed", "down", "blue", "gloomy", "sorrowful", "mourning", "melancholy", "hopeless", "worthless", "drained", "exhausted"},
        "mild": {"disappointed", "let down", "bummed", "meh", "low", "blah", "flat", "empty", "tired", "weary", "spent", "numb"},
    },
    "disgust": {
        "intense": {"loathing", "revolted", "repulsed", "abhorrent", "vile", "disgusting"},
        "moderate": {"disgusted", "grossed", "sickened", "appalled", "offended", "repelled"},
        "mild": {"dislike", "aversion", "uncomfortable", "unpleasant", "distaste", "ugh"},
    },
    "anger": {
        "intense": {"rage", "fury", "livid", "seething", "enraged", "furious", "outraged", "irate"},
        "moderate": {"angry", "mad", "frustrated", "irritated", "annoyed", "pissed", "aggravated", "infuriated", "fed up", "sick of"},
        "mild": {"bothered", "displeased", "impatient", "grumpy", "cranky", "edgy", "agitated", "bugged", "irked"},
    },
    "anticipation": {
        "intense": {"vigilance", "obsessed", "fixated", "consumed", "driven", "determined"},
        "moderate": {"expectant", "eager", "excited", "looking forward", "motivated", "enthusiastic", "pumped"},
        "mild": {"interested", "attentive", "hopeful", "optimistic", "planning", "considering"},
    },
}

# Composite emotions (combinations of primary emotions from Plutchik)
COMPOSITE_EMOTIONS = {
    "love": {"components": ("joy", "trust"), "terms": {"love", "loving", "adore", "cherish", "care", "caring", "affection", "tender", "warmth", "devotion"}},
    "submission": {"components": ("trust", "fear"), "terms": {"submission", "compliant", "obedient", "submissive", "yielding", "docile"}},
    "awe": {"components": ("fear", "surprise"), "terms": {"awe", "awed", "wonder", "wonderstruck", "overwhelmed", "speechless"}},
    "disapproval": {"components": ("surprise", "sadness"), "terms": {"disapproval", "disapproving", "dismayed", "disappointed", "let down", "disillusioned"}},
    "remorse": {"components": ("sadness", "disgust"), "terms": {"remorse", "regret", "guilt", "guilty", "ashamed", "sorry", "apologetic"}},
    "contempt": {"components": ("disgust", "anger"), "terms": {"contempt", "scorn", "disdain", "condescending", "patronizing", "belittling"}},
    "aggressiveness": {"components": ("anger", "anticipation"), "terms": {"aggressive", "hostile", "combative", "confrontational", "belligerent", "provocative"}},
    "optimism": {"components": ("anticipation", "joy"), "terms": {"optimistic", "hopeful", "positive", "upbeat", "promising", "bright", "looking up"}},
}

# ---------------------------------------------------------------------------
# Linguistic pattern detectors (beyond keywords)
# ---------------------------------------------------------------------------
NEGATION_WORDS = {"not", "no", "never", "neither", "nor", "nobody", "nothing", "nowhere", "hardly", "barely", "scarcely", "don't", "doesn't", "didn't", "won't", "wouldn't", "can't", "cannot", "couldn't", "shouldn't", "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't"}

HEDGING_PHRASES = {
    "i guess", "i suppose", "kind of", "sort of", "maybe", "perhaps",
    "i think", "not sure", "not really", "i don't know", "whatever",
    "doesn't matter", "who cares", "it's fine", "it's whatever",
}

SARCASM_PATTERNS = [
    r"\b(great|wonderful|fantastic|amazing|perfect|brilliant|lovely)\b.*\b(not|sarcast|obviously|clearly|sure)\b",
    r"\b(oh)\s+(great|wonderful|fantastic|perfect|joy|lovely)\b",
    r"\b(yeah|yep|sure)\s+(right|whatever|okay)\b",
    r"\bthanks?\s+(?:a lot|so much)\b.*(?:not|nothing|useless|broken)",
    r"\bwow\b.*(?:useless|broken|terrible|awful|nothing)",
]

CATASTROPHIZING_PATTERNS = [
    r"\b(everything|nothing|always|never|everyone|nobody)\b",
    r"\b(worst|ruined|disaster|catastrophe|end of the world|can't take)\b",
    r"\ball\b.*\b(wrong|bad|terrible|ruined|lost|over)\b",
]

EMOTIONAL_SUPPRESSION_PATTERNS = [
    r"\bi['']?m\s+(?:fine|okay|alright|good)\b.*\bbut\b",
    r"\bit['']?s\s+(?:fine|okay|whatever|nothing)\b",
    r"\b(?:don't|doesn't)\s+matter\b",
    r"\bi\s+(?:don't|shouldn't)\s+(?:care|worry|complain)\b",
]

SELF_COMPASSION_PATTERNS = [
    r"\bi\s+(?:need|deserve)\s+(?:a\s+)?(?:break|rest|time|space)\b",
    r"\btaking\s+(?:care|time)\s+(?:of|for)\s+(?:myself|me)\b",
    r"\bit['']?s\s+okay\s+to\b",
    r"\bi['']?m\s+(?:allowed|permitted)\s+to\b",
]

COGNITIVE_LOAD_INDICATORS = {
    "high": {"overwhelmed", "too much", "can't handle", "drowning", "buried", "swamped", "slammed", "crushed", "overloaded", "so many things", "million things", "everything at once", "falling behind", "piling up"},
    "moderate": {"busy", "lot to do", "hectic", "packed", "full plate", "tight schedule", "back to back", "nonstop", "juggling"},
    "low": {"free", "light", "easy", "chill", "relaxed", "nothing much", "taking it easy", "slow day", "winding down"},
}

BURNOUT_SIGNALS = {
    "detachment": {"don't care", "whatever", "doesn't matter", "who cares", "pointless", "what's the point", "why bother", "numb", "empty", "going through the motions"},
    "exhaustion": {"exhausted", "drained", "burned out", "burnout", "running on empty", "can't anymore", "done", "wiped", "spent", "fried", "toast", "dead tired", "bone tired"},
    "cynicism": {"nothing works", "what's the point", "waste of time", "useless", "stupid", "broken", "impossible", "never going to", "give up", "hopeless"},
    "inefficacy": {"can't do this", "not good enough", "failing", "failure", "incompetent", "useless", "worthless", "imposter", "fraud", "not capable", "falling short"},
}

RECOVERY_INDICATORS = {
    "active_recovery": {"breathe", "breathing", "walk", "exercise", "stretch", "yoga", "meditate", "meditation", "workout", "run", "jog"},
    "passive_recovery": {"rest", "break", "nap", "sleep", "relax", "unwind", "decompress", "recharge", "recover", "chill"},
    "social_recovery": {"talk", "vent", "call", "friend", "family", "support", "help", "hug", "comfort", "connect"},
    "cognitive_recovery": {"step back", "perspective", "reset", "regroup", "prioritize", "simplify", "delegate", "let go", "pause", "reflect"},
}

GRATITUDE_TERMS = {"thanks", "thank", "appreciate", "grateful", "gratitude", "thankful", "blessed", "fortunate", "lucky"}
AFFECTION_TERMS = {"care", "caring", "support", "supported", "hug", "kind", "kindness", "warm", "safe", "connection", "connected", "close", "compassion", "gentle", "tender", "comforting"}

STRESS_TERMS = {"deadline", "urgent", "asap", "pressure", "panic", "stuck", "late", "behind", "failure", "failing", "broken", "blocked", "impossible", "crunch", "emergency", "crisis"}

HELP_SEEKING_TERMS = {"help", "assist", "support", "guide", "advise", "need", "please", "can you", "could you", "would you"}

HOPELESSNESS_TERMS = {"give up", "done", "can't do this", "nothing works", "no point", "worthless", "hopeless", "end it", "over", "finished"}

HOSTILITY_TERMS = {"idiot", "stupid", "useless", "shut up", "hate you", "dumb", "pathetic", "moron", "garbage", "trash"}

# Time-of-day energy patterns (circadian rhythm modeling)
CIRCADIAN_ENERGY = {
    (6, 9): 0.6,    # morning ramp-up
    (9, 12): 0.9,   # peak morning
    (12, 14): 0.65,  # post-lunch dip
    (14, 17): 0.8,   # afternoon recovery
    (17, 19): 0.7,   # evening wind-down
    (19, 22): 0.5,   # low energy evening
    (22, 6): 0.3,    # night (should be resting)
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class EmotionVector:
    """Multi-dimensional emotion representation using Plutchik's wheel."""
    joy: float = 0.0
    trust: float = 0.0
    fear: float = 0.0
    surprise: float = 0.0
    sadness: float = 0.0
    disgust: float = 0.0
    anger: float = 0.0
    anticipation: float = 0.0

    def dominant_emotion(self) -> tuple[str, float]:
        emotions = {
            "joy": self.joy, "trust": self.trust, "fear": self.fear,
            "surprise": self.surprise, "sadness": self.sadness,
            "disgust": self.disgust, "anger": self.anger,
            "anticipation": self.anticipation,
        }
        dominant = max(emotions, key=emotions.get)
        return dominant, emotions[dominant]

    def valence(self) -> float:
        """Overall positive/negative valence (-1 to 1)."""
        positive = self.joy + self.trust + self.anticipation + self.surprise * 0.3
        negative = self.sadness + self.anger + self.fear + self.disgust
        total = positive + negative
        if total == 0:
            return 0.0
        return _bounded((positive - negative) / total, -1.0, 1.0)

    def arousal(self) -> float:
        """Activation level (0 to 1). High = intense, low = calm."""
        high_arousal = self.anger + self.fear + self.surprise + self.anticipation
        low_arousal = self.sadness + self.trust
        total = high_arousal + low_arousal + self.joy + self.disgust
        if total == 0:
            return 0.0
        return _bounded(high_arousal / total, 0.0, 1.0)

    def to_dict(self) -> dict[str, float]:
        return {
            "joy": round(self.joy, 4), "trust": round(self.trust, 4),
            "fear": round(self.fear, 4), "surprise": round(self.surprise, 4),
            "sadness": round(self.sadness, 4), "disgust": round(self.disgust, 4),
            "anger": round(self.anger, 4), "anticipation": round(self.anticipation, 4),
            "valence": round(self.valence(), 4), "arousal": round(self.arousal(), 4),
        }


@dataclass
class CognitiveState:
    """Models the user's cognitive/mental load and energy."""
    cognitive_load: float = 0.0           # 0-1: how overloaded the user feels
    energy_level: float = 0.7            # 0-1: estimated energy
    burnout_risk: float = 0.0            # 0-1: burnout probability
    emotional_resilience: float = 0.7    # 0-1: capacity to handle stress
    focus_capacity: float = 0.7          # 0-1: ability to concentrate
    social_need: float = 0.0            # 0-1: need for social connection
    recovery_mode: bool = False          # whether user is in recovery

    def to_dict(self) -> dict[str, Any]:
        return {
            "cognitive_load": round(self.cognitive_load, 4),
            "energy_level": round(self.energy_level, 4),
            "burnout_risk": round(self.burnout_risk, 4),
            "emotional_resilience": round(self.emotional_resilience, 4),
            "focus_capacity": round(self.focus_capacity, 4),
            "social_need": round(self.social_need, 4),
            "recovery_mode": self.recovery_mode,
        }


@dataclass
class EmotionalTrajectory:
    """Tracks emotional momentum and direction over time."""
    trend_direction: float = 0.0       # -1 (declining) to 1 (improving)
    trend_velocity: float = 0.0        # speed of change (0 = stable)
    volatility: float = 0.0            # 0-1: how erratic mood swings are
    stability_score: float = 0.7       # 0-1: overall emotional stability
    consecutive_low_count: int = 0     # number of consecutive low readings
    sudden_drop_detected: bool = False # sharp negative shift detected
    recovery_in_progress: bool = False # user is bouncing back

    def to_dict(self) -> dict[str, Any]:
        return {
            "trend_direction": round(self.trend_direction, 4),
            "trend_velocity": round(self.trend_velocity, 4),
            "volatility": round(self.volatility, 4),
            "stability_score": round(self.stability_score, 4),
            "consecutive_low_count": self.consecutive_low_count,
            "sudden_drop_detected": self.sudden_drop_detected,
            "recovery_in_progress": self.recovery_in_progress,
        }


@dataclass
class LinguisticAnalysis:
    """Deep linguistic features beyond simple keyword matching."""
    negation_detected: bool = False
    sarcasm_probability: float = 0.0
    hedging_level: float = 0.0
    catastrophizing_level: float = 0.0
    emotional_suppression: float = 0.0
    self_compassion: float = 0.0
    sentence_complexity: float = 0.0
    urgency_markers: float = 0.0
    exclamation_intensity: float = 0.0
    caps_intensity: float = 0.0
    elongation_ratio: float = 0.0
    question_density: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in self.__dict__.items()}


@dataclass
class ScheduleAwareness:
    """Context about user's schedule that affects emotional recommendations."""
    schedule_density: float = 0.0      # 0-1: how packed the schedule is
    upcoming_high_stakes: bool = False  # important events soon
    free_slots_today: int = 0          # available time blocks
    overdue_tasks: int = 0             # tasks past their due date
    tasks_today: int = 0               # tasks due today
    next_event_minutes: float = -1     # minutes until next event (-1 if none)
    recommended_capacity: float = 0.7  # how much the user should take on

    def to_dict(self) -> dict[str, Any]:
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in self.__dict__.items()}


@dataclass
class AffectionAssessment:
    """Comprehensive emotional assessment with multi-dimensional analysis."""
    mood_percent: float
    risk_level: str
    should_intervene: bool
    should_pause_automation: bool
    variables: dict[str, float]
    detected_signals: dict[str, float]
    intervention: dict[str, Any]
    generated_at: str
    # Advanced fields
    emotion_vector: dict[str, float] = field(default_factory=dict)
    cognitive_state: dict[str, Any] = field(default_factory=dict)
    trajectory: dict[str, Any] = field(default_factory=dict)
    linguistic_analysis: dict[str, Any] = field(default_factory=dict)
    schedule_awareness: dict[str, Any] = field(default_factory=dict)
    composite_emotions: list[str] = field(default_factory=list)
    dominant_emotion: str = ""
    dominant_intensity: float = 0.0
    emotional_summary: str = ""
    proactive_suggestions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mood_percent": round(self.mood_percent, 2),
            "risk_level": self.risk_level,
            "should_intervene": self.should_intervene,
            "should_pause_automation": self.should_pause_automation,
            "variables": {k: round(v, 4) for k, v in self.variables.items()},
            "detected_signals": {k: round(v, 4) if isinstance(v, float) else v for k, v in self.detected_signals.items()},
            "intervention": self.intervention,
            "generated_at": self.generated_at,
            "emotion_vector": self.emotion_vector,
            "cognitive_state": self.cognitive_state,
            "trajectory": self.trajectory,
            "linguistic_analysis": self.linguistic_analysis,
            "schedule_awareness": self.schedule_awareness,
            "composite_emotions": self.composite_emotions,
            "dominant_emotion": self.dominant_emotion,
            "dominant_intensity": round(self.dominant_intensity, 4),
            "emotional_summary": self.emotional_summary,
            "proactive_suggestions": self.proactive_suggestions,
        }


# ---------------------------------------------------------------------------
# The advanced NLU model
# ---------------------------------------------------------------------------
class AffectionNLUModel:
    """
    Advanced multi-dimensional emotion analysis engine.

    Capabilities:
    - 8 primary emotions (Plutchik's wheel) with 3 intensity tiers each
    - 8 composite emotion detections
    - Negation-aware sentiment analysis
    - Sarcasm probability estimation
    - Emotional suppression detection
    - Cognitive load modeling
    - Burnout trajectory tracking
    - Circadian energy estimation
    - Emotional momentum and volatility analysis
    - Catastrophizing and hedging detection
    - Self-compassion recognition
    - Schedule-aware capacity estimation
    - Proactive intervention with calendar/todo context

    Score output is 0..100 where lower values represent lower emotional state.
    """

    def __init__(self, low_threshold: float = 42.0, critical_threshold: float = 25.0) -> None:
        self.low_threshold = low_threshold
        self.critical_threshold = critical_threshold
        self._emotion_history: list[EmotionVector] = []

    def analyze(self, text: str, session=None) -> AffectionAssessment:
        normalized_text = " ".join((text or "").split())
        lowered = normalized_text.lower()
        tokens = re.findall(r"[a-zA-Z']+", lowered)
        token_count = max(1, len(tokens))

        # --- Phase 1: Multi-dimensional emotion detection ---
        emotion_vec = self._detect_emotions(lowered, tokens, token_count)

        # --- Phase 2: Linguistic deep analysis ---
        linguistics = self._analyze_linguistics(normalized_text, lowered, tokens, token_count)

        # --- Phase 3: Apply negation/sarcasm corrections ---
        emotion_vec = self._apply_linguistic_corrections(emotion_vec, linguistics, lowered)

        # --- Phase 4: Detect composite emotions ---
        composites = self._detect_composite_emotions(lowered)

        # --- Phase 5: Cognitive state modeling ---
        cognitive = self._model_cognitive_state(lowered, tokens, token_count, session)

        # --- Phase 6: Emotional trajectory ---
        trajectory = self._compute_trajectory(emotion_vec, session)

        # --- Phase 7: Circadian energy adjustment ---
        circadian_energy = self._circadian_energy_factor()
        cognitive.energy_level = _bounded(cognitive.energy_level * circadian_energy, 0.0, 1.0)

        # --- Phase 8: Compute final mood score ---
        mood_percent = self._compute_mood_score(
            emotion_vec, linguistics, cognitive, trajectory
        )

        # --- Phase 9: Risk assessment ---
        risk_level = self._risk_level(mood_percent, cognitive, trajectory)
        should_pause = mood_percent <= self.critical_threshold or cognitive.burnout_risk >= 0.8
        should_intervene = mood_percent <= self.low_threshold or cognitive.burnout_risk >= 0.6 or trajectory.sudden_drop_detected

        # --- Phase 10: Build intervention with schedule awareness ---
        schedule = ScheduleAwareness()  # will be enriched by orchestrator with real data
        intervention = self._build_intervention(
            mood_percent, risk_level, should_pause, emotion_vec, cognitive, trajectory, schedule
        )

        # --- Phase 11: Generate proactive suggestions ---
        proactive = self._generate_proactive_suggestions(
            emotion_vec, cognitive, trajectory, schedule
        )

        # --- Phase 12: Generate emotional summary ---
        dominant_name, dominant_val = emotion_vec.dominant_emotion()
        summary = self._generate_emotional_summary(
            emotion_vec, cognitive, trajectory, linguistics, composites
        )

        # Store for trajectory tracking
        self._emotion_history.append(emotion_vec)
        if len(self._emotion_history) > 50:
            self._emotion_history = self._emotion_history[-50:]

        # Build legacy-compatible signal dict
        variables = self._build_variables_dict(emotion_vec, linguistics, cognitive, trajectory)
        detected_signals = self._build_signals_dict(lowered, tokens, token_count)

        return AffectionAssessment(
            mood_percent=mood_percent,
            risk_level=risk_level,
            should_intervene=should_intervene,
            should_pause_automation=should_pause,
            variables=variables,
            detected_signals=detected_signals,
            intervention=intervention,
            generated_at=datetime.now(timezone.utc).isoformat(),
            emotion_vector=emotion_vec.to_dict(),
            cognitive_state=cognitive.to_dict(),
            trajectory=trajectory.to_dict(),
            linguistic_analysis=linguistics.to_dict(),
            schedule_awareness=schedule.to_dict(),
            composite_emotions=composites,
            dominant_emotion=dominant_name,
            dominant_intensity=dominant_val,
            emotional_summary=summary,
            proactive_suggestions=proactive,
        )

    # ------------------------------------------------------------------
    # Phase 1: Multi-dimensional emotion detection
    # ------------------------------------------------------------------
    def _detect_emotions(self, lowered: str, tokens: list[str], token_count: int) -> EmotionVector:
        scores: dict[str, float] = {}
        intensity_weights = {"intense": 1.0, "moderate": 0.65, "mild": 0.15}

        for emotion_name, tiers in EMOTION_TAXONOMY.items():
            total = 0.0
            for tier_name, terms in tiers.items():
                hits = _match_terms(lowered, terms)
                total += hits * intensity_weights[tier_name]
            # Normalize differently: use sqrt scaling so single strong hits register
            scores[emotion_name] = _bounded(
                (total ** 0.8) / (token_count ** 0.5) * 0.8,
                0.0, 1.0,
            )

        return EmotionVector(
            joy=scores.get("joy", 0.0),
            trust=scores.get("trust", 0.0),
            fear=scores.get("fear", 0.0),
            surprise=scores.get("surprise", 0.0),
            sadness=scores.get("sadness", 0.0),
            disgust=scores.get("disgust", 0.0),
            anger=scores.get("anger", 0.0),
            anticipation=scores.get("anticipation", 0.0),
        )

    # ------------------------------------------------------------------
    # Phase 2: Linguistic deep analysis
    # ------------------------------------------------------------------
    def _analyze_linguistics(self, text: str, lowered: str, tokens: list[str], token_count: int) -> LinguisticAnalysis:
        la = LinguisticAnalysis()

        # Negation detection
        negation_hits = sum(1 for t in tokens if t in NEGATION_WORDS)
        la.negation_detected = negation_hits > 0

        # Sarcasm probability
        sarcasm_hits = sum(1 for p in SARCASM_PATTERNS if re.search(p, lowered))
        la.sarcasm_probability = _bounded(sarcasm_hits * 0.35, 0.0, 1.0)

        # Hedging level
        hedge_hits = sum(1 for phrase in HEDGING_PHRASES if phrase in lowered)
        la.hedging_level = _bounded(hedge_hits * 0.25, 0.0, 1.0)

        # Catastrophizing
        cat_hits = sum(1 for p in CATASTROPHIZING_PATTERNS if re.search(p, lowered))
        la.catastrophizing_level = _bounded(cat_hits * 0.3, 0.0, 1.0)

        # Emotional suppression
        suppress_hits = sum(1 for p in EMOTIONAL_SUPPRESSION_PATTERNS if re.search(p, lowered))
        la.emotional_suppression = _bounded(suppress_hits * 0.4, 0.0, 1.0)

        # Self-compassion
        comp_hits = sum(1 for p in SELF_COMPASSION_PATTERNS if re.search(p, lowered))
        la.self_compassion = _bounded(comp_hits * 0.35, 0.0, 1.0)

        # Sentence complexity (avg words per sentence)
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if sentences:
            avg_words = sum(len(s.split()) for s in sentences) / len(sentences)
            la.sentence_complexity = _bounded(avg_words / 20.0, 0.0, 1.0)

        # Urgency markers
        urgent_patterns = [r"\basap\b", r"\burgent\b", r"\bnow\b", r"\bimmediately\b", r"\bhurry\b", r"\bquick\b", r"\bfast\b"]
        urgent_hits = sum(1 for p in urgent_patterns if re.search(p, lowered))
        la.urgency_markers = _bounded(urgent_hits * 0.2, 0.0, 1.0)

        # Punctuation analysis
        la.exclamation_intensity = _bounded(text.count("!") * 0.15, 0.0, 1.0)
        la.caps_intensity = _uppercase_ratio(text)
        la.elongation_ratio = _elongated_word_ratio(tokens)
        la.question_density = _bounded(text.count("?") / max(1, len(sentences)) * 0.5, 0.0, 1.0)

        return la

    # ------------------------------------------------------------------
    # Phase 3: Negation and sarcasm corrections
    # ------------------------------------------------------------------
    def _apply_linguistic_corrections(self, ev: EmotionVector, la: LinguisticAnalysis, lowered: str) -> EmotionVector:
        # Negation flipping: "I'm not happy" -> reduce joy, increase sadness
        if la.negation_detected:
            # Check for negated positive patterns
            negated_positive = bool(re.search(
                r"\b(?:not|don't|doesn't|didn't|can't|won't|never)\s+(?:happy|good|great|fine|okay|excited|glad|pleased|love|like)\b",
                lowered,
            ))
            negated_negative = bool(re.search(
                r"\b(?:not|don't|doesn't|didn't|can't|won't|never)\s+(?:sad|angry|mad|upset|worried|afraid|scared|bad|terrible)\b",
                lowered,
            ))

            if negated_positive:
                ev.joy *= 0.2
                ev.trust *= 0.4
                ev.sadness = _bounded(ev.sadness + 0.3, 0.0, 1.0)

            if negated_negative:
                ev.sadness *= 0.3
                ev.anger *= 0.3
                ev.fear *= 0.3
                ev.joy = _bounded(ev.joy + 0.15, 0.0, 1.0)

        # Sarcasm inversion: if sarcasm detected, flip positive to negative
        if la.sarcasm_probability > 0.5:
            original_joy = ev.joy
            ev.joy *= 0.15
            ev.anger = _bounded(ev.anger + original_joy * 0.5, 0.0, 1.0)
            ev.disgust = _bounded(ev.disgust + original_joy * 0.3, 0.0, 1.0)

        # Emotional suppression: surface-level "fine" masks deeper issues
        if la.emotional_suppression > 0.3:
            ev.sadness = _bounded(ev.sadness + la.emotional_suppression * 0.35, 0.0, 1.0)
            ev.joy *= max(0.3, 1.0 - la.emotional_suppression)

        # Catastrophizing amplifies negative emotions
        if la.catastrophizing_level > 0.2:
            amplifier = 1.0 + la.catastrophizing_level * 0.5
            ev.fear = _bounded(ev.fear * amplifier, 0.0, 1.0)
            ev.sadness = _bounded(ev.sadness * amplifier, 0.0, 1.0)
            ev.anger = _bounded(ev.anger * amplifier, 0.0, 1.0)

        return ev

    # ------------------------------------------------------------------
    # Phase 4: Composite emotions
    # ------------------------------------------------------------------
    def _detect_composite_emotions(self, lowered: str) -> list[str]:
        detected = []
        for name, info in COMPOSITE_EMOTIONS.items():
            hits = _match_terms(lowered, info["terms"])
            if hits >= 1:
                detected.append(name)
        return detected

    # ------------------------------------------------------------------
    # Phase 5: Cognitive state modeling
    # ------------------------------------------------------------------
    def _model_cognitive_state(self, lowered: str, tokens: list[str], token_count: int, session=None) -> CognitiveState:
        cs = CognitiveState()

        # Cognitive load from explicit indicators
        high_load_hits = sum(1 for phrase in COGNITIVE_LOAD_INDICATORS["high"] if phrase in lowered)
        mod_load_hits = sum(1 for phrase in COGNITIVE_LOAD_INDICATORS["moderate"] if phrase in lowered)
        low_load_hits = sum(1 for phrase in COGNITIVE_LOAD_INDICATORS["low"] if phrase in lowered)
        cs.cognitive_load = _bounded(
            (high_load_hits * 0.4 + mod_load_hits * 0.2 - low_load_hits * 0.15),
            0.0, 1.0,
        )

        # Burnout risk from multi-axis signals
        burnout_axes = {}
        total_burnout_hits = 0
        for axis, phrases in BURNOUT_SIGNALS.items():
            hits = sum(1 for phrase in phrases if phrase in lowered)
            total_burnout_hits += hits
            burnout_axes[axis] = _bounded(hits * 0.35, 0.0, 1.0)
        axes_active = sum(1 for v in burnout_axes.values() if v > 0)
        cs.burnout_risk = _bounded(
            (sum(burnout_axes.values()) / max(1, len(burnout_axes)) * 1.8)
            + (0.15 if axes_active >= 3 else 0.0),  # bonus for multi-axis burnout
            0.0, 1.0,
        )

        # Energy level estimation (inverse of exhaustion + burnout)
        exhaustion_hits = sum(1 for phrase in BURNOUT_SIGNALS["exhaustion"] if phrase in lowered)
        cs.energy_level = _bounded(0.7 - exhaustion_hits * 0.2 - cs.burnout_risk * 0.3, 0.0, 1.0)

        # Recovery mode detection
        recovery_total = 0
        for category, terms in RECOVERY_INDICATORS.items():
            recovery_total += sum(1 for t in terms if t in lowered)
        cs.recovery_mode = recovery_total >= 2

        if cs.recovery_mode:
            cs.energy_level = _bounded(cs.energy_level + 0.1, 0.0, 1.0)  # recovery is positive

        # Emotional resilience (from history)
        if session and hasattr(session, "mood_history") and session.mood_history:
            recent_moods = [m.get("mood_percent", 50) for m in session.mood_history[-10:]]
            if recent_moods:
                avg = sum(recent_moods) / len(recent_moods)
                cs.emotional_resilience = _bounded(avg / 100.0, 0.0, 1.0)

        # Focus capacity (inverse of cognitive load and burnout)
        cs.focus_capacity = _bounded(1.0 - cs.cognitive_load * 0.6 - cs.burnout_risk * 0.4, 0.0, 1.0)

        # Social need
        help_hits = sum(1 for t in HELP_SEEKING_TERMS if t in lowered)
        social_recovery_hits = sum(1 for t in RECOVERY_INDICATORS["social_recovery"] if t in lowered)
        cs.social_need = _bounded((help_hits + social_recovery_hits) * 0.15, 0.0, 1.0)

        return cs

    # ------------------------------------------------------------------
    # Phase 6: Emotional trajectory
    # ------------------------------------------------------------------
    def _compute_trajectory(self, current: EmotionVector, session=None) -> EmotionalTrajectory:
        traj = EmotionalTrajectory()

        if not session or not getattr(session, "mood_history", None):
            return traj

        recent = session.mood_history[-12:]
        scores = [float(m.get("mood_percent", 50.0)) for m in recent if "mood_percent" in m]
        if not scores:
            return traj

        current_valence = current.valence()
        current_projection = _bounded(55.0 + 40.0 * current_valence, 0.0, 100.0)
        avg_previous = sum(scores) / len(scores)

        # Trend direction
        traj.trend_direction = _bounded((current_projection - avg_previous) / 40.0, -1.0, 1.0)

        # Trend velocity (rate of change)
        if len(scores) >= 2:
            deltas = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
            avg_delta = sum(deltas) / len(deltas)
            traj.trend_velocity = _bounded(abs(avg_delta) / 15.0, 0.0, 1.0)

        # Volatility
        if len(scores) >= 3:
            stdev = statistics.pstdev(scores)
            traj.volatility = _bounded(stdev / 20.0, 0.0, 1.0)

        # Stability (inverse of volatility + trend velocity)
        traj.stability_score = _bounded(1.0 - traj.volatility * 0.6 - traj.trend_velocity * 0.4, 0.0, 1.0)

        # Consecutive low count
        low_threshold = 45.0
        consecutive = 0
        for s in reversed(scores):
            if s <= low_threshold:
                consecutive += 1
            else:
                break
        traj.consecutive_low_count = consecutive

        # Sudden drop detection
        if scores:
            last = scores[-1]
            if last - current_projection > 15.0:
                traj.sudden_drop_detected = True

        # Recovery detection
        if len(scores) >= 3 and scores[-1] < 50 and current_projection > scores[-1] + 8:
            traj.recovery_in_progress = True

        return traj

    # ------------------------------------------------------------------
    # Phase 7: Circadian energy
    # ------------------------------------------------------------------
    def _circadian_energy_factor(self) -> float:
        hour = datetime.now().hour
        for (start, end), factor in CIRCADIAN_ENERGY.items():
            if start <= end:
                if start <= hour < end:
                    return factor
            else:  # wraps midnight
                if hour >= start or hour < end:
                    return factor
        return 0.5

    # ------------------------------------------------------------------
    # Phase 8: Mood score computation
    # ------------------------------------------------------------------
    def _compute_mood_score(
        self,
        ev: EmotionVector,
        la: LinguisticAnalysis,
        cs: CognitiveState,
        traj: EmotionalTrajectory,
    ) -> float:
        # Base score from emotion valence
        valence_component = ev.valence() * 30.0  # -30 to +30

        # Positive emotion contributions
        joy_boost = ev.joy * 12.0
        trust_boost = ev.trust * 8.0
        anticipation_boost = ev.anticipation * 6.0

        # Negative emotion penalties
        sadness_penalty = ev.sadness * -14.0
        anger_penalty = ev.anger * -10.0
        fear_penalty = ev.fear * -12.0
        disgust_penalty = ev.disgust * -8.0

        # Cognitive state adjustments
        load_penalty = cs.cognitive_load * -8.0
        burnout_penalty = cs.burnout_risk * -15.0
        energy_boost = (cs.energy_level - 0.5) * 8.0
        resilience_boost = (cs.emotional_resilience - 0.5) * 6.0

        # Linguistic adjustments
        sarcasm_penalty = la.sarcasm_probability * -6.0
        suppression_penalty = la.emotional_suppression * -5.0
        catastrophizing_penalty = la.catastrophizing_level * -8.0
        self_compassion_boost = la.self_compassion * 5.0
        urgency_penalty = la.urgency_markers * -6.0
        punctuation_penalty = (la.exclamation_intensity + la.caps_intensity) * -3.0

        # Trajectory adjustments
        trend_boost = traj.trend_direction * 6.0
        volatility_penalty = traj.volatility * -5.0
        consecutive_low_penalty = min(traj.consecutive_low_count, 5) * -2.0
        drop_penalty = -8.0 if traj.sudden_drop_detected else 0.0
        recovery_boost = 4.0 if traj.recovery_in_progress else 0.0

        # Recovery mode bonus
        recovery_mode_boost = 5.0 if cs.recovery_mode else 0.0

        raw = (
            55.0  # baseline
            + valence_component
            + joy_boost + trust_boost + anticipation_boost
            + sadness_penalty + anger_penalty + fear_penalty + disgust_penalty
            + load_penalty + burnout_penalty + energy_boost + resilience_boost
            + sarcasm_penalty + suppression_penalty + catastrophizing_penalty
            + self_compassion_boost + urgency_penalty + punctuation_penalty
            + trend_boost + volatility_penalty + consecutive_low_penalty
            + drop_penalty + recovery_boost + recovery_mode_boost
        )

        return _bounded(raw, 0.0, 100.0)

    # ------------------------------------------------------------------
    # Phase 9: Risk level
    # ------------------------------------------------------------------
    def _risk_level(self, mood: float, cs: CognitiveState, traj: EmotionalTrajectory) -> str:
        # Burnout overrides
        if cs.burnout_risk >= 0.8:
            return "critical"
        if cs.burnout_risk >= 0.6:
            return "high" if mood > self.critical_threshold else "critical"

        # Trajectory overrides
        if traj.sudden_drop_detected and mood <= 50.0:
            return "high" if mood > self.critical_threshold else "critical"
        if traj.consecutive_low_count >= 4:
            return "high" if mood > self.critical_threshold else "critical"

        # Standard thresholds
        if mood <= self.critical_threshold:
            return "critical"
        if mood <= self.low_threshold:
            return "high"
        if mood <= 58.0:
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # Phase 10: Intervention builder
    # ------------------------------------------------------------------
    def _build_intervention(
        self,
        mood: float,
        risk: str,
        paused: bool,
        ev: EmotionVector,
        cs: CognitiveState,
        traj: EmotionalTrajectory,
        schedule: ScheduleAwareness,
    ) -> dict[str, Any]:
        rounded = round(mood, 1)
        dominant, _ = ev.dominant_emotion()

        if risk == "critical":
            message = f"Mood signal is {rounded}%. "
            if cs.burnout_risk >= 0.8:
                message += "Burnout risk is critical. I've paused automation to protect you."
            elif traj.sudden_drop_detected:
                message += "I detected a sharp emotional drop. Stepping into support mode."
            else:
                message += "I paused automation and switched to support mode."

            suggestions = [
                "take a 2 minute reset",
                "ask for one small next step",
                "create reminder drink water in 10 minutes",
            ]
            if dominant == "anger":
                suggestions.insert(0, "open website breathing exercise")
            elif dominant == "sadness":
                suggestions.insert(0, "Would you like me to lighten your schedule?")
            elif dominant == "fear":
                suggestions.insert(0, "Let me help break this into tiny steps")

            return {
                "message": message,
                "suggestions": suggestions,
                "recommended_actions": ["pause_automation", "reduce_task_load", "offer_grounding", "suggest_reschedule"],
                "priority": "critical",
                "paused": paused,
                "emotion_context": dominant,
                "cognitive_load": round(cs.cognitive_load, 2),
                "burnout_risk": round(cs.burnout_risk, 2),
            }

        if risk == "high":
            message = f"Mood signal is {rounded}%. "
            if cs.cognitive_load > 0.6:
                message += "You seem overloaded. Let me help simplify things."
            elif traj.consecutive_low_count >= 3:
                message += f"Your mood has been low for {traj.consecutive_low_count} interactions. Let's take it easy."
            else:
                message += "I detected stress and switched to gentle guidance."

            suggestions = [
                "break this into one tiny action",
                "create reminder take a short break",
            ]
            if cs.energy_level < 0.4:
                suggestions.insert(0, "Maybe move heavy tasks to tomorrow?")
            if schedule.overdue_tasks > 0:
                suggestions.append(f"You have {schedule.overdue_tasks} overdue item(s). Want me to reschedule?")

            return {
                "message": message,
                "suggestions": suggestions,
                "recommended_actions": ["offer_break", "simplify_plan", "slow_execution", "suggest_reschedule"],
                "priority": "high",
                "paused": paused,
                "emotion_context": dominant,
                "cognitive_load": round(cs.cognitive_load, 2),
                "burnout_risk": round(cs.burnout_risk, 2),
            }

        if risk == "medium":
            message = f"Mood signal is {rounded}%. You're stable but I notice mild strain."
            suggestions = ["continue with shorter commands", "take a quick posture check"]
            if cs.cognitive_load > 0.5:
                suggestions.append("Consider spreading your tasks across the week")

            return {
                "message": message,
                "suggestions": suggestions,
                "recommended_actions": ["monitor", "gentle_suggestions"],
                "priority": "medium",
                "paused": False,
                "emotion_context": dominant,
                "cognitive_load": round(cs.cognitive_load, 2),
                "burnout_risk": round(cs.burnout_risk, 2),
            }

        message = f"Mood signal is {rounded}%. Emotional state looks healthy."
        suggestions = []
        if traj.recovery_in_progress:
            message += " Great to see you recovering!"
            suggestions.append("Keep the positive momentum going!")

        return {
            "message": message,
            "suggestions": suggestions,
            "recommended_actions": ["none"],
            "priority": "low",
            "paused": False,
            "emotion_context": dominant,
            "cognitive_load": round(cs.cognitive_load, 2),
            "burnout_risk": round(cs.burnout_risk, 2),
        }

    # ------------------------------------------------------------------
    # Phase 11: Proactive suggestions (calendar/todo-aware)
    # ------------------------------------------------------------------
    def _generate_proactive_suggestions(
        self,
        ev: EmotionVector,
        cs: CognitiveState,
        traj: EmotionalTrajectory,
        schedule: ScheduleAwareness,
    ) -> list[dict[str, Any]]:
        """Generate context-aware proactive suggestions."""
        suggestions = []

        # Energy-based task rescheduling
        if cs.energy_level < 0.4 and schedule.tasks_today > 2:
            suggestions.append({
                "type": "reschedule_tasks",
                "reason": "low_energy",
                "message": "Your energy is low. Want me to move non-urgent tasks to tomorrow?",
                "urgency": "high",
                "action": "lighten_today",
            })

        # Burnout prevention
        if cs.burnout_risk > 0.5:
            suggestions.append({
                "type": "burnout_prevention",
                "reason": "burnout_risk",
                "message": "I'm detecting burnout signals. Consider clearing your afternoon.",
                "urgency": "high",
                "action": "protect_recovery_time",
            })

        # Cognitive overload
        if cs.cognitive_load > 0.7 and schedule.schedule_density > 0.6:
            suggestions.append({
                "type": "reduce_load",
                "reason": "cognitive_overload",
                "message": "You're overloaded and your schedule is packed. Let me help prioritize.",
                "urgency": "high",
                "action": "prioritize_and_defer",
            })

        # Emotional drop + upcoming events
        if traj.sudden_drop_detected and schedule.next_event_minutes > 0 and schedule.next_event_minutes < 60:
            suggestions.append({
                "type": "prepare_for_event",
                "reason": "emotional_drop_before_event",
                "message": f"You have something in {int(schedule.next_event_minutes)} minutes. Want a quick breather first?",
                "urgency": "medium",
                "action": "schedule_micro_break",
            })

        # Recovery encouragement
        if cs.recovery_mode:
            suggestions.append({
                "type": "support_recovery",
                "reason": "recovery_detected",
                "message": "Good that you're taking time to recover. I'll keep tasks light.",
                "urgency": "low",
                "action": "maintain_light_load",
            })

        # Consecutive lows - major intervention
        if traj.consecutive_low_count >= 3:
            suggestions.append({
                "type": "sustained_low_intervention",
                "reason": "consecutive_low_mood",
                "message": f"Your mood has been low for {traj.consecutive_low_count} interactions. Want me to reschedule today's remaining tasks?",
                "urgency": "high",
                "action": "reschedule_remaining",
            })

        # Fear/anxiety + high schedule density
        if ev.fear > 0.4 and schedule.schedule_density > 0.5:
            suggestions.append({
                "type": "anxiety_relief",
                "reason": "anxiety_with_full_schedule",
                "message": "I sense anxiety and your schedule is heavy. Want me to find time blocks you can free up?",
                "urgency": "medium",
                "action": "find_free_slots",
            })

        # Anger management
        if ev.anger > 0.5:
            suggestions.append({
                "type": "anger_management",
                "reason": "high_anger",
                "message": "You seem frustrated. Want to take a step back before continuing?",
                "urgency": "medium",
                "action": "cool_down_pause",
            })

        return suggestions

    # ------------------------------------------------------------------
    # Phase 12: Emotional summary generation
    # ------------------------------------------------------------------
    def _generate_emotional_summary(
        self,
        ev: EmotionVector,
        cs: CognitiveState,
        traj: EmotionalTrajectory,
        la: LinguisticAnalysis,
        composites: list[str],
    ) -> str:
        dominant, intensity = ev.dominant_emotion()
        parts = []

        # Primary emotion
        intensity_word = "mildly" if intensity < 0.3 else "moderately" if intensity < 0.6 else "intensely"
        parts.append(f"Primarily {intensity_word} {dominant}")

        # Composite emotions
        if composites:
            parts.append(f"with undertones of {', '.join(composites)}")

        # Cognitive state
        if cs.burnout_risk > 0.5:
            parts.append("showing burnout signals")
        elif cs.cognitive_load > 0.6:
            parts.append("under high cognitive load")
        elif cs.energy_level < 0.4:
            parts.append("with low energy")

        # Linguistic features
        if la.sarcasm_probability > 0.5:
            parts.append("(sarcasm detected)")
        if la.emotional_suppression > 0.3:
            parts.append("(possibly suppressing true feelings)")

        # Trajectory
        if traj.sudden_drop_detected:
            parts.append("- sudden emotional shift detected")
        elif traj.recovery_in_progress:
            parts.append("- showing signs of recovery")
        elif traj.consecutive_low_count >= 3:
            parts.append(f"- sustained low mood ({traj.consecutive_low_count} readings)")

        return ". ".join(parts) + "."

    # ------------------------------------------------------------------
    # Legacy-compatible variable dicts
    # ------------------------------------------------------------------
    def _build_variables_dict(
        self,
        ev: EmotionVector,
        la: LinguisticAnalysis,
        cs: CognitiveState,
        traj: EmotionalTrajectory,
    ) -> dict[str, float]:
        return {
            "sentiment_balance": ev.valence(),
            "affection_density": _bounded((ev.joy + ev.trust) * 0.5, 0.0, 1.0),
            "stress_density": _bounded((ev.fear + ev.anger) * 0.5, 0.0, 1.0),
            "hostility_density": ev.disgust,
            "recovery_density": 1.0 if cs.recovery_mode else 0.0,
            "help_seeking_density": cs.social_need,
            "hopelessness_density": _bounded(cs.burnout_risk * 0.8 + ev.sadness * 0.2, 0.0, 1.0),
            "punctuation_intensity": _bounded(la.exclamation_intensity + la.caps_intensity, 0.0, 1.0),
            "urgency_density": la.urgency_markers,
            "social_reach_out": cs.social_need,
            "gratitude_boost": _bounded(ev.trust * 0.5, 0.0, 1.0),
            "negativity_overdrive": _bounded(ev.sadness + ev.anger + ev.disgust, 0.0, 1.0),
            "trend_signal": traj.trend_direction,
            "volatility_penalty": traj.volatility,
            "recency_drop": 1.0 if traj.sudden_drop_detected else 0.0,
            "uppercase_ratio": la.caps_intensity,
            "elongated_ratio": la.elongation_ratio,
            # New advanced variables
            "cognitive_load": cs.cognitive_load,
            "burnout_risk": cs.burnout_risk,
            "energy_level": cs.energy_level,
            "emotional_resilience": cs.emotional_resilience,
            "focus_capacity": cs.focus_capacity,
            "sarcasm_probability": la.sarcasm_probability,
            "catastrophizing_level": la.catastrophizing_level,
            "emotional_suppression": la.emotional_suppression,
            "self_compassion": la.self_compassion,
            "hedging_level": la.hedging_level,
            "stability_score": traj.stability_score,
        }

    def _build_signals_dict(self, lowered: str, tokens: list[str], token_count: int) -> dict[str, float]:
        return {
            "positive_hits": float(_match_terms(lowered, EMOTION_TAXONOMY["joy"]["moderate"] | EMOTION_TAXONOMY["joy"]["intense"])),
            "negative_hits": float(_match_terms(lowered, EMOTION_TAXONOMY["sadness"]["moderate"] | EMOTION_TAXONOMY["sadness"]["intense"])),
            "affection_hits": float(_match_terms(lowered, AFFECTION_TERMS)),
            "gratitude_hits": float(_match_terms(lowered, GRATITUDE_TERMS)),
            "stress_hits": float(_match_terms(lowered, STRESS_TERMS)),
            "recovery_hits": float(sum(1 for cat in RECOVERY_INDICATORS.values() for t in cat if t in lowered)),
            "help_hits": float(_match_terms(lowered, HELP_SEEKING_TERMS)),
            "hopeless_hits": float(_match_terms(lowered, HOPELESSNESS_TERMS)),
            "hostility_hits": float(_match_terms(lowered, HOSTILITY_TERMS)),
            "exclamation_count": float(lowered.count("!")),
            "question_count": float(lowered.count("?")),
            "token_count": float(token_count),
            # Advanced signals
            "burnout_detachment_hits": float(sum(1 for p in BURNOUT_SIGNALS["detachment"] if p in lowered)),
            "burnout_exhaustion_hits": float(sum(1 for p in BURNOUT_SIGNALS["exhaustion"] if p in lowered)),
            "burnout_cynicism_hits": float(sum(1 for p in BURNOUT_SIGNALS["cynicism"] if p in lowered)),
            "burnout_inefficacy_hits": float(sum(1 for p in BURNOUT_SIGNALS["inefficacy"] if p in lowered)),
            "cognitive_load_high_hits": float(sum(1 for p in COGNITIVE_LOAD_INDICATORS["high"] if p in lowered)),
            "sarcasm_pattern_hits": float(sum(1 for p in SARCASM_PATTERNS if re.search(p, lowered))),
            "negation_count": float(sum(1 for t in tokens if t in NEGATION_WORDS)),
            "hedging_hits": float(sum(1 for p in HEDGING_PHRASES if p in lowered)),
            "catastrophizing_hits": float(sum(1 for p in CATASTROPHIZING_PATTERNS if re.search(p, lowered))),
            "suppression_hits": float(sum(1 for p in EMOTIONAL_SUPPRESSION_PATTERNS if re.search(p, lowered))),
            "self_compassion_hits": float(sum(1 for p in SELF_COMPASSION_PATTERNS if re.search(p, lowered))),
        }

    # ------------------------------------------------------------------
    # Public: Enrich assessment with real schedule data
    # ------------------------------------------------------------------
    def enrich_with_schedule(
        self, assessment: AffectionAssessment, events: list[dict], reminders: list[dict]
    ) -> AffectionAssessment:
        """Call this from orchestrator after fetching real calendar/reminder data."""
        now = datetime.now(timezone.utc)
        today_end = now.replace(hour=23, minute=59, second=59)

        # Count events today
        events_today = 0
        next_event_minutes = -1.0
        for event in events:
            start_str = event.get("start", "")
            try:
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start.date() == now.date():
                    events_today += 1
                if start > now and next_event_minutes < 0:
                    next_event_minutes = (start - now).total_seconds() / 60.0
            except (ValueError, AttributeError):
                continue

        # Schedule density (events/8 work hours)
        schedule_density = _bounded(events_today / 8.0, 0.0, 1.0)

        # Estimate free slots (8 work hours minus events, assume 1hr each)
        free_slots = max(0, 8 - events_today)

        # Overdue reminders / tasks today
        overdue = 0
        tasks_today = len(reminders)

        schedule = ScheduleAwareness(
            schedule_density=schedule_density,
            upcoming_high_stakes=False,
            free_slots_today=free_slots,
            overdue_tasks=overdue,
            tasks_today=tasks_today,
            next_event_minutes=next_event_minutes,
            recommended_capacity=_bounded(
                assessment.cognitive_state.get("energy_level", 0.7) * (1.0 - schedule_density),
                0.1, 1.0,
            ),
        )

        # Regenerate proactive suggestions with real schedule data
        ev = EmotionVector(**{k: v for k, v in assessment.emotion_vector.items() if k not in ("valence", "arousal")})
        cs_dict = assessment.cognitive_state
        cs = CognitiveState(
            cognitive_load=cs_dict.get("cognitive_load", 0.0),
            energy_level=cs_dict.get("energy_level", 0.7),
            burnout_risk=cs_dict.get("burnout_risk", 0.0),
            emotional_resilience=cs_dict.get("emotional_resilience", 0.7),
            focus_capacity=cs_dict.get("focus_capacity", 0.7),
            social_need=cs_dict.get("social_need", 0.0),
            recovery_mode=cs_dict.get("recovery_mode", False),
        )
        traj_dict = assessment.trajectory
        traj = EmotionalTrajectory(
            trend_direction=traj_dict.get("trend_direction", 0.0),
            trend_velocity=traj_dict.get("trend_velocity", 0.0),
            volatility=traj_dict.get("volatility", 0.0),
            stability_score=traj_dict.get("stability_score", 0.7),
            consecutive_low_count=traj_dict.get("consecutive_low_count", 0),
            sudden_drop_detected=traj_dict.get("sudden_drop_detected", False),
            recovery_in_progress=traj_dict.get("recovery_in_progress", False),
        )

        proactive = self._generate_proactive_suggestions(ev, cs, traj, schedule)

        # Update assessment
        assessment.schedule_awareness = schedule.to_dict()
        assessment.proactive_suggestions = proactive

        # Update intervention with schedule context
        if assessment.intervention.get("priority") in ("critical", "high"):
            if tasks_today > 3 and cs.energy_level < 0.5:
                assessment.intervention["suggestions"].insert(
                    0, f"You have {tasks_today} tasks today but low energy. Want me to move some to tomorrow?"
                )
            if schedule_density > 0.7:
                assessment.intervention["suggestions"].append(
                    "Your calendar is packed. Consider declining or rescheduling a meeting."
                )

        return assessment


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def _match_terms(text: str, terms: set[str]) -> int:
    hits = 0
    for term in terms:
        if " " in term:
            if term in text:
                hits += 1
            continue
        # Match the term and common suffixes (ing, ed, s, ly, ness, ment, ful)
        if re.search(rf"\b{re.escape(term)}(?:ing|ed|s|ly|ness|ment|ful|er|est)?\b", text):
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
    elongated = sum(1 for token in tokens if re.search(r"(.)\1\1", token))
    return _bounded(elongated / len(tokens), 0.0, 1.0)


def _bounded(value: float, lower: float, upper: float) -> float:
    if math.isnan(value):
        return lower
    return max(lower, min(upper, value))
