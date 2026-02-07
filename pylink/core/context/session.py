from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class SessionContext:
    last_intent: str | None = None
    last_app: str | None = None
    last_action: str | None = None
    history: List[dict[str, Any]] = field(default_factory=list)
    pending_steps: list[Any] = field(default_factory=list)
    pending_clarification: dict[str, Any] | None = None

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
