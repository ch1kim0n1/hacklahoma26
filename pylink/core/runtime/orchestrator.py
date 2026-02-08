from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import asdict
from typing import Any

from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.nlu.hybrid_parser import HybridIntentParser
from core.nlu.intents import Intent
from core.planner.action_planner import ActionPlanner, ActionStep
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
    "mcp_create_reminder": True,
    "mcp_create_note": True,
    "mcp_list_reminders": True,
    "mcp_list_notes": True,
    "mcp_get_events": True,
    "mcp_create_event": True,
    "autofill_login": True,
}


class _PersistentAsyncRunner:
    def __init__(self) -> None:
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        loop.run_forever()
        pending = asyncio.all_tasks(loop=loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        self._closed.set()

    def run(self, coro, *, timeout: float | None = None):
        if not self._loop:
            raise RuntimeError("Async runner loop not initialized")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._closed.wait(timeout=2.0)


class PixelLinkRuntime:
    def __init__(
        self,
        *,
        dry_run: bool = False,
        speed: float = 1.0,
        permission_profile: dict[str, bool] | None = None,
        enable_kill_switch: bool = True,
        verbose: bool = True,
        mcp_tools: dict[str, Any] | None = None,
    ) -> None:
        self.session = SessionContext()
        self.guard = SafetyGuard()
        self.kill_switch = KillSwitch()
        if enable_kill_switch:
            self.kill_switch.start()
        self.enable_kill_switch = enable_kill_switch
        self.mcp_tools = mcp_tools or {}
        self.nlu = HybridIntentParser()
        self.planner = ActionPlanner(mcp_tools=self.mcp_tools)
        self.executor = ExecutionEngine(self.kill_switch, dry_run=dry_run, verbose=verbose)
        self.executor.set_speed(speed)
        self.guard.set_allowed_actions(permission_profile or DEFAULT_PERMISSION_PROFILE)
        self._mcp_runner = _PersistentAsyncRunner() if self.mcp_tools else None

    def close(self) -> None:
        if self.enable_kill_switch:
            self.kill_switch.stop()
        if self._mcp_runner:
            self._mcp_runner.close()

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

    def handle_input(self, raw_text: str, source: str = "text", trace_id: str | None = None) -> dict[str, Any]:
        start_total = time.perf_counter()
        metrics = {
            "parse_ms": 0.0,
            "plan_ms": 0.0,
            "execute_ms": 0.0,
            "total_ms": 0.0,
            "nlu_mode": "rules",
        }
        intent_name = "none"

        cleaned_text = " ".join((raw_text or "").strip().split())
        if not cleaned_text:
            response = self._response("idle", "No input provided.", source=source)
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

        if self.session.pending_clarification:
            response = self._handle_clarification(cleaned_text, source, metrics)
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

        parse_start = time.perf_counter()
        nlu_result = self.nlu.parse(cleaned_text, self.session, source=source)
        metrics["parse_ms"] = round((time.perf_counter() - parse_start) * 1000.0, 3)
        metrics["nlu_mode"] = nlu_result.mode

        intent = nlu_result.intent
        intent_name = intent.name
        self.session.record_intent(intent.name, cleaned_text)

        if self.session.pending_steps:
            response = self._handle_pending(intent.name, source, metrics)
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

        if intent.name == "unknown":
            response = self._response(
                "unknown",
                "Sorry, I didn't understand that.",
                source=source,
                intent=intent,
                suggestions=[
                    "open Notes",
                    "type Hello world",
                    "reply email saying I'll send the file tomorrow",
                    "create reminder Buy milk",
                    "create note Meeting notes in Work",
                    "browse for machine learning tutorials",
                    "find file report.pdf",
                    "login to github",
                ],
            )
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

        if intent.name == "search_file":
            query = str(intent.entities.get("query", "")).strip()
            matches = self.session.filesystem.search_files(query, limit=10)
            if matches:
                message = f"Found {len(matches)} file(s) matching '{query}':\n"
                for i, file_info in enumerate(matches[:5], 1):
                    message += f"  {i}. {file_info.name} ({file_info.path})\n"
                if len(matches) > 5:
                    message += f"  ... and {len(matches) - 5} more"
                response = self._response("completed", message, source=source, intent=intent)
            else:
                response = self._response(
                    "completed",
                    f"No files found matching '{query}'.",
                    source=source,
                    intent=intent,
                )
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

        if intent.name == "login":
            response = self._handle_login(intent, source, metrics)
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

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
                response = self._response(
                    "awaiting_clarification",
                    prompt,
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )
                return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

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
                response = self._response(
                    "awaiting_clarification",
                    prompt,
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )
                return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

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
            response = self._response(
                "awaiting_clarification",
                prompt,
                source=source,
                intent=intent,
                pending_clarification=True,
            )
            return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

        response = self._execute_intent(intent, source, metrics)
        return self._finalize_response(response, metrics, trace_id, source, intent_name, start_total)

    def _handle_login(self, intent: Intent, source: str, metrics: dict[str, Any]) -> dict[str, Any]:
        from core.context.password_manager import get_password_manager

        service = str(intent.entities.get("service", "")).strip()
        pm = get_password_manager()
        cred = pm.get_credential(service)

        if not cred:
            return self._response(
                "error",
                f"No credentials found for '{service}' in password manager. Please add them to your Keychain first.",
                source=source,
                intent=intent,
            )

        steps = [
            ActionStep("type_text", {"content": cred.username}, False, "Enter username"),
            ActionStep("press_key", {"key": "tab"}, False, "Move to password field"),
            ActionStep("type_text", {"content": cred.password}, False, "Enter password"),
        ]

        execute_start = time.perf_counter()
        result = self.executor.execute_steps(steps, self.guard)
        metrics["execute_ms"] += round((time.perf_counter() - execute_start) * 1000.0, 3)

        if result.completed:
            return self._response(
                "completed",
                f"Autofilled credentials for {service} ({cred.username})",
                source=source,
                intent=intent,
                steps=steps,
            )

        return self._response("error", "Failed to autofill credentials", source=source, intent=intent)

    def _execute_intent(self, intent: Intent, source: str, metrics: dict[str, Any]) -> dict[str, Any]:
        plan_start = time.perf_counter()
        steps = self.planner.plan(intent, self.session, self.guard)
        metrics["plan_ms"] += round((time.perf_counter() - plan_start) * 1000.0, 3)

        safety = self.guard.validate_plan(steps)
        if not safety.allowed:
            return self._response("blocked", safety.reason, source=source, intent=intent, steps=steps)

        if intent.name in {"search_web", "search_youtube", "open_website"}:
            for step in steps:
                if step.action == "open_url":
                    url = step.params.get("url", "")
                    search_query = intent.entities.get("query", "")
                    self.session.add_browsing_entry(url, search_query=search_query)

        execute_start = time.perf_counter()
        if any(step.action.startswith("mcp_") for step in steps):
            result = self._run_mcp_steps(steps)
            metrics["execute_ms"] += round((time.perf_counter() - execute_start) * 1000.0, 3)
            if result.get("error"):
                return self._response("error", result["error"], source=source, intent=intent, steps=steps)
            return self._response(
                "completed",
                result.get("message", "Task completed successfully."),
                source=source,
                intent=intent,
                steps=steps,
            )

        result = self.executor.execute_steps(steps, self.guard)
        metrics["execute_ms"] += round((time.perf_counter() - execute_start) * 1000.0, 3)
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

    def _handle_clarification(self, user_reply: str, source: str, metrics: dict[str, Any]) -> dict[str, Any]:
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
            return self._execute_intent(resolved_intent, source, metrics)

        self.session.clear_pending_clarification()
        return self._response("error", "Unable to resolve clarification context.", source=source)

    def _handle_pending(self, intent_name: str, source: str, metrics: dict[str, Any]) -> dict[str, Any]:
        if intent_name == "confirm":
            execute_start = time.perf_counter()
            result = self.executor.execute_steps(self.session.pending_steps, self.guard)
            metrics["execute_ms"] += round((time.perf_counter() - execute_start) * 1000.0, 3)
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

    def _run_mcp_steps(self, steps: list[Any]) -> dict[str, Any]:
        try:
            if self._mcp_runner:
                return self._mcp_runner.run(self._execute_mcp_steps(steps), timeout=10.0)
            return asyncio.run(self._execute_mcp_steps(steps))
        except FutureTimeoutError:
            return {"error": "MCP execution timed out."}
        except Exception as exc:
            return {"error": f"MCP execution failed: {str(exc)}"}

    async def _execute_mcp_steps(self, steps: list[Any]) -> dict[str, Any]:
        try:
            for step in steps:
                if step.action == "mcp_create_reminder":
                    tool = self.mcp_tools.get("reminders_create_reminder")
                    if not tool:
                        return {"error": "Reminders tool not available"}
                    result = await tool(**step.params)
                    return {"message": f"Created reminder '{result['name']}' in list '{result['list']}'"}
                if step.action == "mcp_create_note":
                    tool = self.mcp_tools.get("notes_create_note")
                    if not tool:
                        return {"error": "Notes tool not available"}
                    result = await tool(**step.params)
                    return {"message": f"Created note '{result['title']}' in folder '{result['folder']}'"}
            return {"message": "Task completed"}
        except Exception as exc:
            return {"error": f"MCP execution failed: {str(exc)}"}

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

    def _finalize_response(
        self,
        response: dict[str, Any],
        metrics: dict[str, Any],
        trace_id: str | None,
        source: str,
        intent_name: str,
        started_at: float,
    ) -> dict[str, Any]:
        metrics["parse_ms"] = round(float(metrics.get("parse_ms", 0.0)), 3)
        metrics["plan_ms"] = round(float(metrics.get("plan_ms", 0.0)), 3)
        metrics["execute_ms"] = round(float(metrics.get("execute_ms", 0.0)), 3)
        metrics["total_ms"] = round((time.perf_counter() - started_at) * 1000.0, 3)
        response["metrics"] = metrics
        if trace_id:
            response["trace_id"] = trace_id

        log_payload = {
            "event": "runtime.handle_input",
            "trace_id": trace_id,
            "source": source,
            "intent": intent_name,
            "status": response.get("status"),
            "metrics": metrics,
        }
        logging.info(json.dumps(log_payload, sort_keys=True))
        return response


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
