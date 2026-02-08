from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

from pynput import keyboard


@dataclass
class SafetyResult:
    allowed: bool
    reason: str = ""


class KillSwitch:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._listener = keyboard.Listener(on_press=self._on_press)

    def _on_press(self, key) -> None:
        if key == keyboard.Key.esc:
            self._event.set()

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()
        # Wait for listener thread to finish to avoid race conditions
        if hasattr(self._listener, '_thread') and self._listener._thread:
            self._listener._thread.join(timeout=1.0)

    def is_triggered(self) -> bool:
        return self._event.is_set()

    def reset(self) -> None:
        self._event.clear()


class SafetyGuard:
    def __init__(self) -> None:
        self.blocked_actions = {"delete_file", "shutdown_system", "format_drive"}
        self.confirm_actions = {"send_email", "reply_email", "autofill_login"}
        self.allowed_actions = {
            "open_app",
            "focus_app",
            "close_app",
            "open_url",
            "open_file",
            "send_text_native",
            "type_text",
            "click",
            "right_click",
            "double_click",
            "scroll",
            "press_key",
            "hotkey",
            "send_email",
            "send_message",
            "wait",
            "autofill_login",
        }

    def set_allowed_actions(self, allowed_actions: dict[str, bool] | None) -> None:
        if not allowed_actions:
            return
        enabled = {name for name, is_enabled in allowed_actions.items() if is_enabled}
        if enabled:
            self.allowed_actions = enabled

    def validate_plan(self, steps: Iterable) -> SafetyResult:
        for step in steps:
            if step.action in self.blocked_actions:
                return SafetyResult(False, f"Blocked unsafe action: {step.action}")
            if step.action not in self.allowed_actions:
                return SafetyResult(False, f"Action not permitted by current safety profile: {step.action}")
        return SafetyResult(True, "")

    def requires_confirmation(self, action: str) -> bool:
        return action in self.confirm_actions
