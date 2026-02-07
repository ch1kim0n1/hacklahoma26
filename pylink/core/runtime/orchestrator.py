from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.nlu.intents import Intent
from core.nlu.parser import parse_intent
from core.planner.action_planner import ActionPlanner
from core.safety.guard import KillSwitch, SafetyGuard


DEFAULT_PERMISSION_PROFILE = {
    "open_app": True,
    "focus_app": True,
    "close_app": True,
    "open_url": True,
    "open_file": True,
    "send_text_native": True,
    "type_text": True,
    "click": True,
    "right_click": True,
    "double_click": True,
    "scroll": True,
    "press_key": True,
    "hotkey": True,
    "send_email": True,
    "send_message": True,
    "wait": True,
}


class PixelLinkRuntime:
    def __init__(
        self,
        *,
        dry_run: bool = False,
        speed: float = 1.0,
        permission_profile: dict[str, bool] | None = None,
        enable_kill_switch: bool = True,
        verbose: bool = True,
    ) -> None:
        self.session = SessionContext()
        self.guard = SafetyGuard()
        self.kill_switch = KillSwitch()
        if enable_kill_switch:
            self.kill_switch.start()
        self.enable_kill_switch = enable_kill_switch
        self.planner = ActionPlanner()
        self.executor = ExecutionEngine(self.kill_switch, dry_run=dry_run, verbose=verbose)
        self.executor.set_speed(speed)
        self.guard.set_allowed_actions(permission_profile or DEFAULT_PERMISSION_PROFILE)

    def close(self) -> None:
        if self.enable_kill_switch:
            self.kill_switch.stop()

    def set_preferences(
        self,
        *,
        speed: float | None = None,
        permission_profile: dict[str, bool] | None = None,
    ) -> None:
        if speed is not None:
            self.executor.set_speed(speed)
        if permission_profile is not None:
            self.guard.set_allowed_actions(permission_profile)

    def handle_input(self, raw_text: str, source: str = "text") -> dict[str, Any]:
        cleaned_text = " ".join((raw_text or "").strip().split())
        if not cleaned_text:
            return self._response("idle", "No input provided.", source=source)

        if self.session.pending_clarification:
            return self._handle_clarification(cleaned_text, source)

        intent = parse_intent(cleaned_text, self.session)
        self.session.record_intent(intent.name, cleaned_text)

        if self.session.pending_steps:
            return self._handle_pending(intent.name, source)

        if intent.name == "unknown":
            return self._response(
                "unknown",
                "Sorry, I didn't understand that.",
                source=source,
                intent=intent,
                suggestions=[
                    "open Notes",
                    "type Hello world",
                    "reply email saying I'll send the file tomorrow",
                ],
            )

        if intent.name == "send_text":
            recipient = str(intent.entities.get("target", "")).strip()
            content = str(intent.entities.get("content", "")).strip()
            if not recipient:
                prompt = "Who should receive this text message?"
                self.session.set_pending_clarification(
                    {
                        "intent_name": "send_text",
                        "clarification_type": "send_text_target",
                        "target": "",
                        "content": content,
                        "app": intent.entities.get("app", "Messages"),
                        "prompt": prompt,
                        "original_text": cleaned_text,
                    }
                )
                return self._response(
                    "awaiting_clarification",
                    prompt,
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )
            if not content:
                prompt = f"What message should I send to {recipient}?"
                self.session.set_pending_clarification(
                    {
                        "intent_name": "send_text",
                        "clarification_type": "send_text_content",
                        "target": recipient,
                        "content": "",
                        "app": intent.entities.get("app", "Messages"),
                        "prompt": prompt,
                        "original_text": cleaned_text,
                    }
                )
                return self._response(
                    "awaiting_clarification",
                    prompt,
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )

        if intent.entities.get("requires_clarification"):
            prompt = intent.entities.get("clarification_prompt", "Please provide more details.")
            self.session.set_pending_clarification(
                {
                    "intent_name": intent.name,
                    "clarification_type": intent.entities.get("clarification_type", ""),
                    "target": intent.entities.get("target", ""),
                    "content": intent.entities.get("content", ""),
                    "app": intent.entities.get("app", "Messages"),
                    "prompt": prompt,
                    "original_text": cleaned_text,
                }
            )
            return self._response(
                "awaiting_clarification",
                prompt,
                source=source,
                intent=intent,
                pending_clarification=True,
            )

        return self._execute_intent(intent, source)

    def _execute_intent(self, intent: Intent, source: str) -> dict[str, Any]:
        steps = self.planner.plan(intent, self.session, self.guard)
        safety = self.guard.validate_plan(steps)
        if not safety.allowed:
            return self._response("blocked", safety.reason, source=source, intent=intent, steps=steps)

        result = self.executor.execute_steps(steps, self.guard)
        self._record_last_app(steps)

        if result.pending_steps:
            self.session.set_pending(result.pending_steps)
            return self._response(
                "awaiting_confirmation",
                "Awaiting confirmation to proceed.",
                source=source,
                intent=intent,
                steps=steps,
                pending_confirmation=True,
            )

        if result.completed:
            return self._response(
                "completed",
                "Task completed successfully.",
                source=source,
                intent=intent,
                steps=steps,
            )

        return self._response("error", "Task did not complete.", source=source, intent=intent, steps=steps)

    def _handle_clarification(self, user_reply: str, source: str) -> dict[str, Any]:
        if user_reply.lower() in {"cancel", "stop", "abort", "no", "nevermind", "never mind"}:
            self.session.clear_pending_clarification()
            return self._response("canceled", "Clarification canceled.", source=source)

        pending = self.session.pending_clarification or {}
        intent_name = pending.get("intent_name", "")
        clarification_type = pending.get("clarification_type", "")

        if intent_name == "send_text":
            target = (pending.get("target", "") or "").strip()
            content = (pending.get("content", "") or "").strip()
            app_name = (pending.get("app", "") or "Messages").strip()

            if clarification_type == "send_text_target":
                target = _clean_clarified_target(user_reply)
            elif clarification_type == "send_text_content":
                content = user_reply.strip()

            resolved_intent = Intent(
                name="send_text",
                entities={"target": target, "content": content, "app": app_name},
                confidence=0.9,
                raw_text=f"{pending.get('original_text', '')} | {user_reply}",
            )
            self.session.clear_pending_clarification()
            self.session.record_intent(resolved_intent.name, resolved_intent.raw_text)
            return self._execute_intent(resolved_intent, source)

        self.session.clear_pending_clarification()
        return self._response("error", "Unable to resolve clarification context.", source=source)

    def _handle_pending(self, intent_name: str, source: str) -> dict[str, Any]:
        if intent_name == "confirm":
            result = self.executor.execute_steps(self.session.pending_steps, self.guard)
            self.session.clear_pending()
            if result.completed:
                return self._response("completed", "Confirmed and completed.", source=source)
            return self._response("error", "Execution halted during confirmation.", source=source)
        if intent_name == "cancel":
            self.session.clear_pending()
            return self._response("canceled", "Pending actions canceled.", source=source)
        return self._response(
            "awaiting_confirmation",
            "Type confirm or cancel to continue.",
            source=source,
            pending_confirmation=True,
        )

    def _record_last_app(self, steps: list[Any]) -> None:
        for step in steps:
            if step.action in {"open_app", "focus_app"}:
                self.session.set_last_app(step.params.get("app", ""))
                break

    def _response(
        self,
        status: str,
        message: str,
        *,
        source: str,
        intent=None,
        steps=None,
        pending_confirmation: bool = False,
        pending_clarification: bool = False,
        suggestions: list[str] | None = None,
    ) -> dict[str, Any]:
        serialized_steps = []
        for step in steps or []:
            serialized_steps.append(
                {
                    "action": step.action,
                    "params": step.params,
                    "requires_confirmation": step.requires_confirmation,
                    "description": step.description,
                }
            )

        serialized_intent = None
        if intent is not None:
            serialized_intent = asdict(intent)

        return {
            "status": status,
            "message": message,
            "source": source,
            "intent": serialized_intent,
            "steps": serialized_steps,
            "pending_confirmation": pending_confirmation or bool(self.session.pending_steps),
            "pending_clarification": pending_clarification or bool(self.session.pending_clarification),
            "clarification_prompt": (self.session.pending_clarification or {}).get("prompt", ""),
            "last_app": self.session.last_app,
            "history_count": len(self.session.history),
            "suggestions": suggestions or [],
        }


def _clean_clarified_target(value: str) -> str:
    cleaned = re.sub(r"^\s*to\s+", "", value.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:in|on|via)\s+(?:i\s*message|imessage|imeesage|imesage|messages?)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = " ".join(cleaned.split())
    return cleaned.strip().strip('"').strip("'").strip("“”")
