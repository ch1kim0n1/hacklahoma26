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
    def __init__(self, kill_switch: KillSwitch) -> None:
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.os = OSController()
        self.kill_switch = kill_switch

    def execute_steps(self, steps: List, guard: SafetyGuard) -> ExecutionResult:
        for index, step in enumerate(steps):
            if self.kill_switch.is_triggered():
                logging.warning("Kill switch triggered. Execution halted.")
                print("⚠ Kill switch activated. Stopping execution.")
                return ExecutionResult(False, [])

            if step.requires_confirmation:
                logging.info("Awaiting confirmation for action: %s", step.action)
                return ExecutionResult(False, steps[index:])

            logging.info("Executing step %s/%s: %s", index + 1, len(steps), step.action)
            print(f"Action {index + 1}/{len(steps)}: {step.description or step.action}")

            try:
                self._execute_step(step)
                print(f"  ✓ {step.description or step.action} completed")
            except Exception as e:
                error_msg = f"Failed to execute {step.action}: {str(e)}"
                logging.error(error_msg)
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
            self.os.open_app(app_name)
        elif action == "type_text":
            content = params.get("content", "")
            if not content:
                raise ValueError("Content is required for type_text action")
            self.keyboard.type_text(content)
        elif action == "click":
            self.mouse.click()
        elif action == "hotkey":
            keys = params.get("keys", [])
            if not keys:
                raise ValueError("Keys are required for hotkey action")
            self.keyboard.hotkey(keys)
        elif action == "send_email":
            keys = params.get("keys", [])
            if not keys:
                raise ValueError("Keys are required for send_email action")
            self.keyboard.hotkey(keys)
        elif action == "wait":
            time.sleep(float(params.get("seconds", 0.5)))
        else:
            raise ValueError(f"Unknown action: {action}")
