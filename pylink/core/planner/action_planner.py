from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, List

from core.nlu.intents import Intent
from core.safety.guard import SafetyGuard


@dataclass
class ActionStep:
    action: str
    params: dict[str, Any]
    requires_confirmation: bool = False
    description: str = ""


class ActionPlanner:
    def plan(self, intent: Intent, context, guard: SafetyGuard) -> List[ActionStep]:
        steps: List[ActionStep] = []

        if intent.name == "open_app":
            app_name = intent.entities.get("app", "")
            if app_name in {"last", "previous"} and context and context.last_app:
                app_name = context.last_app
            steps.append(ActionStep("open_app", {"app": app_name}, False, "Open app"))

        elif intent.name == "focus_app":
            app_name = intent.entities.get("app", "")
            if app_name in {"last", "previous"} and context and context.last_app:
                app_name = context.last_app
            steps.append(ActionStep("focus_app", {"app": app_name}, False, "Focus app"))

        elif intent.name == "type_text":
            steps.append(ActionStep("type_text", {"content": intent.entities.get("content", "")}, False, "Type text"))

        elif intent.name == "click":
            steps.append(ActionStep("click", {"target": intent.entities.get("target", "")}, False, "Click"))

        elif intent.name == "reply_email":
            app_name = intent.entities.get("app", "Mail")
            content = intent.entities.get("content", "")
            steps.append(ActionStep("focus_app", {"app": app_name}, False, "Focus email app"))
            steps.append(ActionStep("wait", {"seconds": 1.0}, False, "Wait for app"))
            steps.append(ActionStep("hotkey", {"keys": _reply_hotkey()}, False, "Open reply"))
            steps.append(ActionStep("type_text", {"content": content}, False, "Type reply"))
            steps.append(ActionStep(
                "send_email",
                {"keys": _send_hotkey()},
                guard.requires_confirmation("send_email"),
                "Send email",
            ))

        return steps


def _reply_hotkey() -> list[str]:
    if platform.system().lower() == "darwin":
        return ["command", "r"]
    return ["ctrl", "r"]


def _send_hotkey() -> list[str]:
    if platform.system().lower() == "darwin":
        return ["command", "shift", "d"]
    return ["ctrl", "enter"]
