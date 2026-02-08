"""
Emotional Intelligence Engine - Calendar & Todo-Aware Decision System.

This module bridges the affection NLU model with real schedule data
(Google Calendar events, Apple Reminders) to make emotionally intelligent
decisions about task management.

Key capabilities:
- Fetches and analyzes calendar density and upcoming commitments
- Evaluates todo/reminder urgency and reschedulability
- Generates context-aware reschedule recommendations
- Determines optimal days to move deferred tasks
- Produces human-readable explanations for all suggestions
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from core.nlu.affection_model import AffectionAssessment, AffectionNLUModel

logger = logging.getLogger(__name__)


@dataclass
class TaskProfile:
    """Analyzed profile of a single task/reminder."""
    name: str
    source: str  # "reminder" or "calendar"
    original_id: str = ""
    estimated_effort: str = "medium"  # low, medium, high
    is_moveable: bool = True
    is_overdue: bool = False
    due_date: datetime | None = None
    priority_score: float = 0.5  # 0-1
    cognitive_weight: float = 0.5  # 0-1: how mentally taxing
    suggested_new_date: str = ""
    move_reason: str = ""


@dataclass
class RescheduleRecommendation:
    """A specific recommendation to move a task."""
    task_name: str
    task_source: str
    current_date: str
    suggested_date: str
    reason: str
    confidence: float
    action_command: str  # the PixelLink command to execute this


@dataclass
class EmotionalScheduleAnalysis:
    """Full analysis combining emotional state with schedule context."""
    emotional_capacity: float  # 0-1: how much the user can handle right now
    schedule_pressure: float  # 0-1: how demanding the schedule is
    recommended_max_tasks: int  # max tasks user should tackle today
    should_lighten_load: bool
    tasks_analyzed: list[TaskProfile] = field(default_factory=list)
    reschedule_recommendations: list[RescheduleRecommendation] = field(default_factory=list)
    summary_message: str = ""
    action_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "emotional_capacity": round(self.emotional_capacity, 3),
            "schedule_pressure": round(self.schedule_pressure, 3),
            "recommended_max_tasks": self.recommended_max_tasks,
            "should_lighten_load": self.should_lighten_load,
            "tasks_count": len(self.tasks_analyzed),
            "reschedule_count": len(self.reschedule_recommendations),
            "reschedule_recommendations": [
                {
                    "task": r.task_name,
                    "from": r.current_date,
                    "to": r.suggested_date,
                    "reason": r.reason,
                    "confidence": round(r.confidence, 2),
                    "command": r.action_command,
                }
                for r in self.reschedule_recommendations
            ],
            "summary_message": self.summary_message,
            "action_items": self.action_items,
        }


# Keywords that suggest a task is high-effort
HIGH_EFFORT_KEYWORDS = {
    "presentation", "report", "review", "meeting", "interview", "exam",
    "deadline", "project", "proposal", "analysis", "design", "plan",
    "migrate", "refactor", "debug", "deploy", "release", "launch",
}

# Keywords that suggest a task is low-effort
LOW_EFFORT_KEYWORDS = {
    "call", "email", "reply", "buy", "pick up", "water", "lunch",
    "coffee", "snack", "read", "check", "quick", "simple", "easy",
    "remind", "text", "message", "schedule", "book", "order",
}

# Tasks that should never be auto-rescheduled
IMMOVABLE_KEYWORDS = {
    "doctor", "appointment", "flight", "interview", "exam", "test",
    "court", "hearing", "surgery", "wedding", "funeral", "ceremony",
}


class EmotionalIntelligenceEngine:
    """
    Bridges emotion analysis with calendar/todo data to make
    intelligent decisions about task management.
    """

    def __init__(self, mcp_tools: dict[str, Any] | None = None) -> None:
        self.mcp_tools = mcp_tools or {}
        self._cached_events: list[dict] | None = None
        self._cached_reminders: list[dict] | None = None
        self._cache_time: datetime | None = None
        self._cache_ttl = timedelta(minutes=5)

    async def fetch_calendar_events(self, max_results: int = 20) -> list[dict]:
        """Fetch upcoming Google Calendar events."""
        tool_fn = self.mcp_tools.get("calendar_list_events")
        if not tool_fn:
            return []
        try:
            events = await tool_fn(max_results=max_results)
            return events if isinstance(events, list) else []
        except Exception as e:
            logger.warning("Failed to fetch calendar events: %s", e)
            return []

    async def fetch_reminders(self, list_name: str = "Reminders") -> list[dict]:
        """Fetch Apple Reminders from a list."""
        tool_fn = self.mcp_tools.get("reminders_list_reminders")
        if not tool_fn:
            return []
        try:
            reminders = await tool_fn(list_name=list_name)
            if isinstance(reminders, list):
                return [{"name": r} if isinstance(r, str) else r for r in reminders]
            return []
        except Exception as e:
            logger.warning("Failed to fetch reminders: %s", e)
            return []

    async def fetch_all_reminder_lists(self) -> list[str]:
        """Fetch all reminder list names."""
        tool_fn = self.mcp_tools.get("reminders_list_lists")
        if not tool_fn:
            return []
        try:
            lists = await tool_fn()
            return lists if isinstance(lists, list) else []
        except Exception as e:
            logger.warning("Failed to fetch reminder lists: %s", e)
            return []

    async def gather_schedule_data(self) -> tuple[list[dict], list[dict]]:
        """Fetch both calendar events and reminders, with caching."""
        now = datetime.now(timezone.utc)
        if (
            self._cached_events is not None
            and self._cache_time
            and (now - self._cache_time) < self._cache_ttl
        ):
            return self._cached_events, self._cached_reminders or []

        events, reminders = await asyncio.gather(
            self.fetch_calendar_events(),
            self.fetch_reminders(),
        )
        self._cached_events = events
        self._cached_reminders = reminders
        self._cache_time = now
        return events, reminders

    def invalidate_cache(self) -> None:
        self._cached_events = None
        self._cached_reminders = None
        self._cache_time = None

    def analyze_schedule_with_emotion(
        self,
        assessment: AffectionAssessment,
        events: list[dict],
        reminders: list[dict],
    ) -> EmotionalScheduleAnalysis:
        """
        Core analysis: combine emotional state with schedule data
        to produce actionable recommendations.
        """
        mood = assessment.mood_percent
        cognitive = assessment.cognitive_state
        energy = cognitive.get("energy_level", 0.7)
        burnout = cognitive.get("burnout_risk", 0.0)
        load = cognitive.get("cognitive_load", 0.0)

        # Calculate emotional capacity (0-1)
        emotional_capacity = _clamp(
            (mood / 100.0) * 0.4
            + energy * 0.3
            + (1.0 - burnout) * 0.2
            + (1.0 - load) * 0.1,
            0.0, 1.0,
        )

        # Analyze schedule pressure
        now = datetime.now(timezone.utc)
        events_today = self._count_events_today(events, now)
        schedule_pressure = _clamp(events_today / 6.0, 0.0, 1.0)

        # Determine max tasks
        if emotional_capacity < 0.25:
            max_tasks = 1
        elif emotional_capacity < 0.4:
            max_tasks = 2
        elif emotional_capacity < 0.6:
            max_tasks = 4
        elif emotional_capacity < 0.8:
            max_tasks = 6
        else:
            max_tasks = 10

        # Reduce max tasks if schedule is already packed
        if schedule_pressure > 0.5:
            max_tasks = max(1, int(max_tasks * 0.6))

        should_lighten = emotional_capacity < 0.5 or (emotional_capacity < 0.65 and schedule_pressure > 0.5)

        # Profile each task
        task_profiles = self._profile_tasks(reminders, events, now)

        # Generate reschedule recommendations
        recommendations = []
        if should_lighten:
            recommendations = self._generate_reschedule_plan(
                task_profiles, emotional_capacity, max_tasks, now
            )

        # Build summary
        summary = self._build_summary(
            emotional_capacity, schedule_pressure, max_tasks,
            should_lighten, len(events_today) if isinstance(events_today, list) else events_today,
            len(reminders), len(recommendations),
        )

        action_items = [r.action_command for r in recommendations]

        return EmotionalScheduleAnalysis(
            emotional_capacity=emotional_capacity,
            schedule_pressure=schedule_pressure,
            recommended_max_tasks=max_tasks,
            should_lighten_load=should_lighten,
            tasks_analyzed=task_profiles,
            reschedule_recommendations=recommendations,
            summary_message=summary,
            action_items=action_items,
        )

    def _count_events_today(self, events: list[dict], now: datetime) -> int:
        count = 0
        for event in events:
            start_str = event.get("start", "")
            try:
                start = datetime.fromisoformat(str(start_str).replace("Z", "+00:00"))
                if start.date() == now.date():
                    count += 1
            except (ValueError, AttributeError):
                continue
        return count

    def _profile_tasks(
        self, reminders: list[dict], events: list[dict], now: datetime
    ) -> list[TaskProfile]:
        profiles = []

        for rem in reminders:
            name = rem if isinstance(rem, str) else rem.get("name", str(rem))
            name_lower = name.lower()

            effort = "medium"
            cognitive_weight = 0.5
            if any(kw in name_lower for kw in HIGH_EFFORT_KEYWORDS):
                effort = "high"
                cognitive_weight = 0.8
            elif any(kw in name_lower for kw in LOW_EFFORT_KEYWORDS):
                effort = "low"
                cognitive_weight = 0.2

            is_moveable = not any(kw in name_lower for kw in IMMOVABLE_KEYWORDS)

            profiles.append(TaskProfile(
                name=name,
                source="reminder",
                estimated_effort=effort,
                is_moveable=is_moveable,
                cognitive_weight=cognitive_weight,
                priority_score=0.7 if effort == "high" else 0.4 if effort == "low" else 0.5,
            ))

        for event in events:
            summary = event.get("summary", "Unknown event")
            name_lower = summary.lower()
            start_str = event.get("start", "")

            try:
                start = datetime.fromisoformat(str(start_str).replace("Z", "+00:00"))
                is_today = start.date() == now.date()
            except (ValueError, AttributeError):
                is_today = False

            if not is_today:
                continue

            effort = "high" if any(kw in name_lower for kw in HIGH_EFFORT_KEYWORDS) else "medium"
            is_moveable = not any(kw in name_lower for kw in IMMOVABLE_KEYWORDS)

            profiles.append(TaskProfile(
                name=summary,
                source="calendar",
                original_id=event.get("id", ""),
                estimated_effort=effort,
                is_moveable=is_moveable,
                cognitive_weight=0.7 if effort == "high" else 0.4,
                priority_score=0.6,
            ))

        return profiles

    def _generate_reschedule_plan(
        self,
        profiles: list[TaskProfile],
        capacity: float,
        max_tasks: int,
        now: datetime,
    ) -> list[RescheduleRecommendation]:
        recommendations = []

        # Sort by priority (lowest priority first = first to be moved)
        moveable = [p for p in profiles if p.is_moveable]
        moveable.sort(key=lambda p: p.priority_score)

        # Calculate how many we need to move
        total = len(profiles)
        to_move = max(0, total - max_tasks)

        if to_move == 0 and capacity < 0.35:
            # Even if task count is within limits, if capacity is very low, move the heaviest one
            heavy = [p for p in moveable if p.estimated_effort == "high"]
            if heavy:
                to_move = 1
                moveable = heavy

        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        day_after = (now + timedelta(days=2)).strftime("%Y-%m-%d")

        for i, task in enumerate(moveable[:to_move]):
            # Pick target day based on capacity
            target_day = tomorrow if capacity > 0.2 else day_after

            reason = self._pick_reason(task, capacity)

            if task.source == "reminder":
                command = f"create reminder {task.name} due {target_day}"
            else:
                command = f"Reschedule '{task.name}' to {target_day}"

            recommendations.append(RescheduleRecommendation(
                task_name=task.name,
                task_source=task.source,
                current_date=now.strftime("%Y-%m-%d"),
                suggested_date=target_day,
                reason=reason,
                confidence=_clamp(0.6 + (1.0 - capacity) * 0.3, 0.0, 1.0),
                action_command=command,
            ))

        return recommendations

    def _pick_reason(self, task: TaskProfile, capacity: float) -> str:
        if capacity < 0.25:
            return f"Your emotional state is critically low. '{task.name}' can wait."
        if capacity < 0.4:
            return f"You're running low on energy. Moving '{task.name}' to reduce pressure."
        if task.estimated_effort == "high":
            return f"'{task.name}' requires high cognitive effort. Better tackled when rested."
        return f"Lightening your load by deferring '{task.name}'."

    def _build_summary(
        self,
        capacity: float,
        pressure: float,
        max_tasks: int,
        should_lighten: bool,
        events_today: int,
        reminders_count: int,
        reschedule_count: int,
    ) -> str:
        parts = []
        cap_pct = int(capacity * 100)
        parts.append(f"Emotional capacity: {cap_pct}%.")

        if events_today > 0:
            parts.append(f"You have {events_today} calendar event(s) today.")
        if reminders_count > 0:
            parts.append(f"{reminders_count} reminder(s) on your list.")

        if should_lighten:
            parts.append(f"I recommend keeping to at most {max_tasks} task(s) right now.")
            if reschedule_count > 0:
                parts.append(f"I suggest moving {reschedule_count} task(s) to a lighter day.")
        else:
            parts.append("Your capacity looks good for your current workload.")

        return " ".join(parts)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
