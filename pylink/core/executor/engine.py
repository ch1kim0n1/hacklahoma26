from __future__ import annotations

import time
from dataclasses import dataclass
import logging
from typing import List

from core.executor.keyboard import KeyboardController
from core.executor.mouse import MouseController
from core.executor.os_control import OSController
from core.safety.guard import KillSwitch, SafetyGuard


@dataclass
class ExecutionResult:
    completed: bool
    pending_steps: list


class ExecutionEngine:
    def __init__(self, kill_switch: KillSwitch, dry_run: bool = False, verbose: bool = True) -> None:
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.os = OSController()
        self.kill_switch = kill_switch
        self.dry_run = dry_run
        self.verbose = verbose
        self.speed = 1.0
        self.base_action_delay = 0.12
        self.base_typing_interval = 0.02

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.25, min(speed, 3.0))

    def _scaled_delay(self) -> float:
        return self.base_action_delay / self.speed

    def _scaled_typing_interval(self) -> float:
        return self.base_typing_interval / self.speed

    def execute_steps(self, steps: List, guard: SafetyGuard) -> ExecutionResult:
        for index, step in enumerate(steps):
            if self.kill_switch.is_triggered():
                logging.warning("Kill switch triggered. Execution halted.")
                if self.verbose:
                    print("⚠ Kill switch activated. Stopping execution.")
                return ExecutionResult(False, [])

            if step.requires_confirmation:
                logging.info("Awaiting confirmation for action: %s", step.action)
                step.requires_confirmation = False
                return ExecutionResult(False, steps[index:])

            logging.info("Executing step %s/%s: %s", index + 1, len(steps), step.action)
            if self.verbose:
                print(f"Action {index + 1}/{len(steps)}: {step.description or step.action}")

            try:
                self._execute_step(step)
                if self.verbose:
                    print(f"  ✓ {step.description or step.action} completed")
                if index < len(steps) - 1:
                    time.sleep(self._scaled_delay())
            except Exception as e:
                error_msg = f"Failed to execute {step.action}: {str(e)}"
                logging.error(error_msg)
                if self.verbose:
                    print(f"  ✗ {error_msg}")
                return ExecutionResult(False, [])

        return ExecutionResult(True, [])

    def _execute_step(self, step) -> None:
        action = step.action
        params = step.params

        if action in {"open_app", "focus_app"}:
            app_name = params.get("app", "")
            if not app_name:
                raise ValueError("App name is required for open_app/focus_app action")
            if self.dry_run:
                return
            if action == "focus_app":
                self.os.focus_app(app_name)
            else:
                self.os.open_app(app_name)
        elif action == "close_app":
            app_name = params.get("app", "")
            if not app_name:
                raise ValueError("App name is required for close_app action")
            if self.dry_run:
                return
            self.os.close_app(app_name)
        elif action == "open_url":
            url = params.get("url", "")
            if not url:
                raise ValueError("URL is required for open_url action")
            if self.dry_run:
                return
            self.os.open_url(url)
        elif action == "open_file":
            file_path = params.get("path", "")
            if not file_path:
                raise ValueError("File path is required for open_file action")
            if self.dry_run:
                return
            self.os.open_file(file_path)
        elif action == "send_text_native":
            target = params.get("target", "")
            content = params.get("content", "")
            app_name = params.get("app", "Messages")
            if not target:
                raise ValueError("Recipient is required for send_text_native action")
            if not content:
                raise ValueError("Content is required for send_text_native action")
            if self.dry_run:
                return
            self.os.send_text_native(app_name=app_name, target=target, content=content)
        elif action == "type_text":
            content = params.get("content", "")
            if not content:
                raise ValueError("Content is required for type_text action")
            if self.dry_run:
                return
            self.keyboard.type_text(content, interval=self._scaled_typing_interval())
        elif action == "click":
            if self.dry_run:
                return
            self.mouse.click()
        elif action == "right_click":
            if self.dry_run:
                return
            self.mouse.click(button="right")
        elif action == "double_click":
            if self.dry_run:
                return
            self.mouse.double_click()
        elif action == "scroll":
            amount = int(params.get("amount", 450))
            direction = params.get("direction", "down")
            signed_amount = amount if direction == "up" else -amount
            if self.dry_run:
                return
            self.mouse.scroll(signed_amount)
        elif action == "press_key":
            key = params.get("key", "")
            if not key:
                raise ValueError("Key is required for press_key action")
            if self.dry_run:
                return
            self.keyboard.press(_normalize_key(key))
        elif action == "hotkey":
            keys = params.get("keys", [])
            if not keys:
                raise ValueError("Keys are required for hotkey action")
            if self.dry_run:
                return
            self.keyboard.hotkey(keys)
        elif action == "send_email":
            keys = params.get("keys", [])
            if not keys:
                raise ValueError("Keys are required for send_email action")
            if self.dry_run:
                return
            self.keyboard.hotkey(keys)
        elif action == "send_message":
            key = params.get("key", "enter")
            if self.dry_run:
                return
            self.keyboard.press(_normalize_key(key))
        elif action == "wait":
            if self.dry_run:
                return
            seconds = max(0.0, float(params.get("seconds", 0.5)))
            time.sleep(seconds / self.speed)
        else:
            raise ValueError(f"Unknown action: {action}")


def _normalize_key(key: str) -> str:
    normalized = key.strip().lower()
    aliases = {
        "return": "enter",
        "spacebar": "space",
        "escape": "esc",
        "pgup": "pageup",
        "pgdn": "pagedown",
        "del": "delete",
    }
    return aliases.get(normalized, normalized)
