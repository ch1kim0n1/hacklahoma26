from dataclasses import dataclass, field
from typing import Any, List

from core.context.browsing_history import BrowsingHistory
from core.context.filesystem_context import FileSystemContext


@dataclass
class SessionContext:
    last_intent: str | None = None
    last_app: str | None = None
    last_action: str | None = None
    history: List[dict[str, Any]] = field(default_factory=list)
    pending_steps: list[Any] = field(default_factory=list)
    pending_clarification: dict[str, Any] | None = None
    browsing_history: BrowsingHistory = field(default_factory=BrowsingHistory)
    filesystem: FileSystemContext = field(default_factory=FileSystemContext)
    mood_history: List[dict[str, Any]] = field(default_factory=list)
    last_affection: dict[str, Any] | None = None
    last_response_message: str = ""
    last_status_message: str = ""

    def record_intent(self, intent_name: str, raw_text: str) -> None:
        self.last_intent = intent_name
        self.history.append({"intent": intent_name, "raw_text": raw_text})

    def record_action(self, action_name: str, params: dict[str, Any]) -> None:
        self.last_action = action_name
        self.history.append({"action": action_name, "params": params})

    def set_last_app(self, app_name: str) -> None:
        self.last_app = app_name

    def set_pending(self, steps: list[Any]) -> None:
        self.pending_steps = steps

    def clear_pending(self) -> None:
        self.pending_steps = []

    def set_pending_clarification(self, payload: dict[str, Any]) -> None:
        self.pending_clarification = payload

    def clear_pending_clarification(self) -> None:
        self.pending_clarification = None

    def record_affection(self, assessment: dict[str, Any], raw_text: str) -> None:
        payload = {
            "mood_percent": assessment.get("mood_percent", 0.0),
            "risk_level": assessment.get("risk_level", "low"),
            "generated_at": assessment.get("generated_at"),
            "raw_text": raw_text,
        }
        self.last_affection = assessment
        self.mood_history.append(payload)
        if len(self.mood_history) > 40:
            self.mood_history = self.mood_history[-40:]

    def set_last_response(self, message: str) -> None:
        self.last_response_message = message.strip()

    def set_last_status(self, message: str) -> None:
        self.last_status_message = message.strip()
    
    def add_browsing_entry(self, url: str, title: str = "", search_query: str = "") -> None:
        """Add a URL to browsing history."""
        self.browsing_history.add_url(url, title, search_query)
    
    def get_context_summary(self) -> str:
        """Get a comprehensive context summary for better intent understanding."""
        parts = []
        
        if self.last_app:
            parts.append(f"Current app: {self.last_app}")

        if self.last_affection:
            mood = self.last_affection.get("mood_percent", 0.0)
            risk = self.last_affection.get("risk_level", "low")
            parts.append(f"Recent mood: {mood:.1f}% ({risk})")
        
        browsing_summary = self.browsing_history.get_context_summary()
        if browsing_summary and "No browsing" not in browsing_summary:
            parts.append(f"\nBrowsing context:\n{browsing_summary}")
        
        if self.filesystem.indexed_files:
            fs_summary = self.filesystem.get_context_summary()
            parts.append(f"\nFile system context:\n{fs_summary}")
        
        return "\n".join(parts) if parts else "No context available."
