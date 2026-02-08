from __future__ import annotations

import re
import threading
from dataclasses import asdict
from typing import Any

from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.nlu.affection_model import AffectionNLUModel
from core.nlu.emotional_intelligence import EmotionalIntelligenceEngine
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
    "mcp_create_reminder": True,
    "mcp_create_note": True,
    "mcp_list_reminders": True,
    "mcp_list_notes": True,
    "mcp_get_events": True,
    "mcp_create_event": True,
    "autofill_login": True,
    "emotional_reschedule": True,
    "emotional_lighten": True,
    "emotional_check_in": True,
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
        mcp_tools: dict[str, Any] | None = None,
        mood_low_threshold: float = 42.0,
        mood_critical_threshold: float = 25.0,
    ) -> None:
        self.session = SessionContext()
        self.guard = SafetyGuard()
        self.kill_switch = KillSwitch()
        if enable_kill_switch:
            self.kill_switch.start()
        self.enable_kill_switch = enable_kill_switch
        self.mcp_tools = mcp_tools or {}
        self.planner = ActionPlanner(mcp_tools=self.mcp_tools)
        self.executor = ExecutionEngine(self.kill_switch, dry_run=dry_run, verbose=verbose)
        self.affection_nlu = AffectionNLUModel(
            low_threshold=mood_low_threshold,
            critical_threshold=mood_critical_threshold,
        )
        self.emotional_intelligence = EmotionalIntelligenceEngine(mcp_tools=self.mcp_tools)
        self._current_affection: dict[str, Any] | None = None
        self.executor.set_speed(speed)
        self.guard.set_allowed_actions(permission_profile or DEFAULT_PERMISSION_PROFILE)
        self._cursor_lock = threading.Lock()

        # Initialize file system context in background
        threading.Thread(target=self.session.filesystem.index_files, daemon=True).start()

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

    def move_cursor(self, x: int, y: int) -> None:
        """Move the system mouse cursor to (x, y). Thread-safe for use from eye control."""
        with self._cursor_lock:
            # Eye tracking updates at video frame rate; instant moves avoid cumulative lag.
            self.executor.mouse.move_to(x, y, duration=0.0)

    def handle_input(self, raw_text: str, source: str = "text") -> dict[str, Any]:
        cleaned_text = " ".join((raw_text or "").strip().split())
        if not cleaned_text:
            return self._response("idle", "No input provided.", source=source)

        affection_assessment = self.affection_nlu.analyze(cleaned_text, self.session)

        # Enrich with real calendar/reminder data when available
        try:
            import asyncio
            events, reminders = asyncio.run(
                self.emotional_intelligence.gather_schedule_data()
            )
            affection_assessment = self.affection_nlu.enrich_with_schedule(
                affection_assessment, events, reminders
            )
        except Exception:
            events, reminders = [], []

        self._current_affection = affection_assessment.to_dict()
        self.session.record_affection(self._current_affection, cleaned_text)

        if self.session.pending_clarification:
            return self._handle_clarification(cleaned_text, source)

        intent = parse_intent(cleaned_text, self.session)
        self.session.record_intent(intent.name, cleaned_text)

        if self.session.pending_steps:
            return self._handle_pending(intent.name, source)

        if intent.name == "check_mood":
            mood_percent = self._current_affection.get("mood_percent", 0.0)
            risk_level = self._current_affection.get("risk_level", "low")
            dominant = self._current_affection.get("dominant_emotion", "")
            summary = self._current_affection.get("emotional_summary", "")
            emotion_vec = self._current_affection.get("emotion_vector", {})
            cognitive = self._current_affection.get("cognitive_state", {})

            message = f"Current mood signal: {mood_percent:.1f}% ({risk_level})\n"
            if dominant:
                message += f"Dominant emotion: {dominant}\n"
            if summary:
                message += f"Analysis: {summary}\n"
            if cognitive:
                energy = cognitive.get("energy_level", 0)
                burnout = cognitive.get("burnout_risk", 0)
                load = cognitive.get("cognitive_load", 0)
                message += f"Energy: {energy:.0%} | Cognitive load: {load:.0%} | Burnout risk: {burnout:.0%}\n"

            intervention_msg = self._current_affection.get("intervention", {}).get("message", "")
            if intervention_msg:
                message += f"\n{intervention_msg}"

            # Include proactive suggestions if any
            proactive = self._current_affection.get("proactive_suggestions", [])
            suggestions = list(self._current_affection.get("intervention", {}).get("suggestions", []))
            for p in proactive:
                if p.get("message"):
                    suggestions.insert(0, p["message"])

            return self._response(
                "completed",
                message.strip(),
                source=source,
                intent=intent,
                suggestions=suggestions,
            )

        # Emotional check-in (full report with schedule context)
        if intent.name == "emotional_check_in":
            return self._handle_emotional_check_in(source, intent)

        # Reschedule tasks based on emotional state
        if intent.name == "reschedule_tasks":
            return self._handle_reschedule_tasks(intent, source)

        # Lighten load (auto-analyze and suggest)
        if intent.name == "lighten_load":
            return self._handle_lighten_load(intent, source)

        # Check schedule
        if intent.name == "check_schedule":
            return self._handle_check_schedule(intent, source)

        if self._should_pause_for_low_mood(intent.name):
            return self._response(
                "support_required",
                self._current_affection.get("intervention", {}).get(
                    "message",
                    "Mood is critically low. Automation paused for safety.",
                ),
                source=source,
                intent=intent,
                suggestions=self._current_affection.get("intervention", {}).get("suggestions", []),
            )

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
                    "create reminder Buy milk",
                    "create note Meeting notes in Work",
                    "browse for machine learning tutorials",
                    "find file report.pdf",
                    "login to github",
                    "check my mood",
                ],
            )
        
        # Handle file search
        if intent.name == "search_file":
            query = intent.entities.get("query", "")
            matches = self.session.filesystem.search_files(query, limit=10)
            if matches:
                message = f"Found {len(matches)} file(s) matching '{query}':\n"
                for i, file_info in enumerate(matches[:5], 1):
                    message += f"  {i}. {file_info.name} ({file_info.path})\n"
                if len(matches) > 5:
                    message += f"  ... and {len(matches) - 5} more"
                return self._response("completed", message, source=source, intent=intent)
            else:
                return self._response(
                    "completed",
                    f"No files found matching '{query}'.",
                    source=source,
                    intent=intent,
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

    def _handle_emotional_check_in(self, source: str, intent: Intent) -> dict[str, Any]:
        """Full emotional check-in with calendar context."""
        try:
            import asyncio
            events, reminders = asyncio.run(
                self.emotional_intelligence.gather_schedule_data()
            )
            affection = self._current_affection or {}
            # Use AffectionAssessment to reconstruct for analysis
            from core.nlu.affection_model import AffectionAssessment
            assessment_obj = AffectionAssessment(
                mood_percent=affection.get("mood_percent", 55),
                risk_level=affection.get("risk_level", "low"),
                should_intervene=affection.get("should_intervene", False),
                should_pause_automation=affection.get("should_pause_automation", False),
                variables=affection.get("variables", {}),
                detected_signals=affection.get("detected_signals", {}),
                intervention=affection.get("intervention", {}),
                generated_at=affection.get("generated_at", ""),
                emotion_vector=affection.get("emotion_vector", {}),
                cognitive_state=affection.get("cognitive_state", {}),
                trajectory=affection.get("trajectory", {}),
                linguistic_analysis=affection.get("linguistic_analysis", {}),
                schedule_awareness=affection.get("schedule_awareness", {}),
                composite_emotions=affection.get("composite_emotions", []),
                dominant_emotion=affection.get("dominant_emotion", ""),
                dominant_intensity=affection.get("dominant_intensity", 0.0),
                emotional_summary=affection.get("emotional_summary", ""),
                proactive_suggestions=affection.get("proactive_suggestions", []),
            )

            analysis = self.emotional_intelligence.analyze_schedule_with_emotion(
                assessment_obj, events, reminders
            )

            message = "--- Emotional Intelligence Report ---\n"
            message += f"Mood: {affection.get('mood_percent', 0):.1f}% ({affection.get('risk_level', 'unknown')})\n"
            message += f"Dominant emotion: {affection.get('dominant_emotion', 'unknown')}\n"
            if affection.get("emotional_summary"):
                message += f"Summary: {affection['emotional_summary']}\n"
            message += f"\nEmotional capacity: {analysis.emotional_capacity:.0%}\n"
            message += f"Schedule pressure: {analysis.schedule_pressure:.0%}\n"
            message += f"Recommended max tasks: {analysis.recommended_max_tasks}\n"

            if analysis.reschedule_recommendations:
                message += f"\nI recommend rescheduling {len(analysis.reschedule_recommendations)} task(s):\n"
                for rec in analysis.reschedule_recommendations:
                    message += f"  - {rec.task_name}: {rec.reason}\n"
                    message += f"    Suggested: move to {rec.suggested_date}\n"

            message += f"\n{analysis.summary_message}"

            suggestions = []
            for rec in analysis.reschedule_recommendations:
                suggestions.append(rec.action_command)
            proactive = affection.get("proactive_suggestions", [])
            for p in proactive:
                if p.get("message"):
                    suggestions.append(p["message"])

            return self._response(
                "completed", message.strip(), source=source, intent=intent, suggestions=suggestions
            )
        except Exception as e:
            return self._response(
                "completed",
                f"Emotional check-in (limited): {self._current_affection.get('emotional_summary', 'Unable to generate full report.')}",
                source=source, intent=intent,
            )

    def _handle_reschedule_tasks(self, intent: Intent, source: str) -> dict[str, Any]:
        """Handle task rescheduling based on emotional state."""
        try:
            import asyncio
            events, reminders = asyncio.run(
                self.emotional_intelligence.gather_schedule_data()
            )
            affection = self._current_affection or {}
            from core.nlu.affection_model import AffectionAssessment
            assessment_obj = AffectionAssessment(
                mood_percent=affection.get("mood_percent", 55),
                risk_level=affection.get("risk_level", "low"),
                should_intervene=affection.get("should_intervene", False),
                should_pause_automation=affection.get("should_pause_automation", False),
                variables=affection.get("variables", {}),
                detected_signals=affection.get("detected_signals", {}),
                intervention=affection.get("intervention", {}),
                generated_at=affection.get("generated_at", ""),
                emotion_vector=affection.get("emotion_vector", {}),
                cognitive_state=affection.get("cognitive_state", {}),
                trajectory=affection.get("trajectory", {}),
                linguistic_analysis=affection.get("linguistic_analysis", {}),
                schedule_awareness=affection.get("schedule_awareness", {}),
                composite_emotions=affection.get("composite_emotions", []),
                dominant_emotion=affection.get("dominant_emotion", ""),
                dominant_intensity=affection.get("dominant_intensity", 0.0),
                emotional_summary=affection.get("emotional_summary", ""),
                proactive_suggestions=affection.get("proactive_suggestions", []),
            )

            analysis = self.emotional_intelligence.analyze_schedule_with_emotion(
                assessment_obj, events, reminders
            )

            if not analysis.reschedule_recommendations:
                return self._response(
                    "completed",
                    f"Your workload looks manageable (capacity: {analysis.emotional_capacity:.0%}). No tasks need rescheduling right now.",
                    source=source, intent=intent,
                )

            message = f"Based on your emotional state ({affection.get('mood_percent', 0):.0f}% mood, {analysis.emotional_capacity:.0%} capacity):\n\n"
            for i, rec in enumerate(analysis.reschedule_recommendations, 1):
                message += f"{i}. {rec.task_name}\n"
                message += f"   Reason: {rec.reason}\n"
                message += f"   Move to: {rec.suggested_date}\n\n"

            message += "Say 'confirm' to reschedule these tasks, or 'cancel' to keep them as is."

            # Store recommendations as pending
            self.session.set_pending_clarification({
                "intent_name": "reschedule_tasks",
                "clarification_type": "confirm_reschedule",
                "recommendations": [
                    {
                        "task_name": r.task_name,
                        "task_source": r.task_source,
                        "suggested_date": r.suggested_date,
                        "action_command": r.action_command,
                    }
                    for r in analysis.reschedule_recommendations
                ],
                "prompt": "Confirm or cancel the reschedule?",
            })

            return self._response(
                "awaiting_clarification",
                message.strip(),
                source=source,
                intent=intent,
                pending_clarification=True,
            )
        except Exception as e:
            return self._response(
                "error",
                f"Could not analyze schedule for rescheduling: {e}",
                source=source, intent=intent,
            )

    def _handle_lighten_load(self, intent: Intent, source: str) -> dict[str, Any]:
        """Auto-analyze and suggest load reduction."""
        try:
            import asyncio
            events, reminders = asyncio.run(
                self.emotional_intelligence.gather_schedule_data()
            )
            affection = self._current_affection or {}
            from core.nlu.affection_model import AffectionAssessment
            assessment_obj = AffectionAssessment(
                mood_percent=affection.get("mood_percent", 55),
                risk_level=affection.get("risk_level", "low"),
                should_intervene=affection.get("should_intervene", False),
                should_pause_automation=affection.get("should_pause_automation", False),
                variables=affection.get("variables", {}),
                detected_signals=affection.get("detected_signals", {}),
                intervention=affection.get("intervention", {}),
                generated_at=affection.get("generated_at", ""),
                emotion_vector=affection.get("emotion_vector", {}),
                cognitive_state=affection.get("cognitive_state", {}),
                trajectory=affection.get("trajectory", {}),
                linguistic_analysis=affection.get("linguistic_analysis", {}),
                schedule_awareness=affection.get("schedule_awareness", {}),
                composite_emotions=affection.get("composite_emotions", []),
                dominant_emotion=affection.get("dominant_emotion", ""),
                dominant_intensity=affection.get("dominant_intensity", 0.0),
                emotional_summary=affection.get("emotional_summary", ""),
                proactive_suggestions=affection.get("proactive_suggestions", []),
            )

            analysis = self.emotional_intelligence.analyze_schedule_with_emotion(
                assessment_obj, events, reminders
            )

            message = analysis.summary_message
            if analysis.reschedule_recommendations:
                message += "\n\nSuggested changes:\n"
                for rec in analysis.reschedule_recommendations:
                    message += f"  - Move '{rec.task_name}' to {rec.suggested_date} ({rec.reason})\n"
                message += "\nSay 'confirm' to apply these changes."

                self.session.set_pending_clarification({
                    "intent_name": "reschedule_tasks",
                    "clarification_type": "confirm_reschedule",
                    "recommendations": [
                        {
                            "task_name": r.task_name,
                            "task_source": r.task_source,
                            "suggested_date": r.suggested_date,
                            "action_command": r.action_command,
                        }
                        for r in analysis.reschedule_recommendations
                    ],
                    "prompt": "Confirm or cancel?",
                })

                return self._response(
                    "awaiting_clarification",
                    message.strip(),
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )

            return self._response(
                "completed", message, source=source, intent=intent,
            )
        except Exception as e:
            return self._response("error", f"Could not analyze workload: {e}", source=source, intent=intent)

    def _handle_check_schedule(self, intent: Intent, source: str) -> dict[str, Any]:
        """Show schedule with emotional context."""
        try:
            import asyncio
            events, reminders = asyncio.run(
                self.emotional_intelligence.gather_schedule_data()
            )

            message = "--- Your Schedule ---\n"
            if events:
                message += "\nCalendar events:\n"
                for e in events[:10]:
                    summary = e.get("summary", "Unknown")
                    start = e.get("start", "")
                    message += f"  - {summary} ({start})\n"
            else:
                message += "\nNo upcoming calendar events found.\n"

            if reminders:
                message += f"\nReminders ({len(reminders)}):\n"
                for r in reminders[:10]:
                    name = r if isinstance(r, str) else r.get("name", str(r))
                    message += f"  - {name}\n"
            else:
                message += "\nNo reminders found.\n"

            # Add emotional context
            affection = self._current_affection or {}
            capacity_info = affection.get("schedule_awareness", {})
            if capacity_info:
                message += f"\nSchedule density: {capacity_info.get('schedule_density', 0):.0%}"
                message += f" | Tasks today: {capacity_info.get('tasks_today', 0)}"
                message += f" | Free slots: {capacity_info.get('free_slots_today', 0)}"

            return self._response("completed", message.strip(), source=source, intent=intent)
        except Exception as e:
            return self._response("error", f"Could not fetch schedule: {e}", source=source, intent=intent)

    def _execute_intent(self, intent: Intent, source: str) -> dict[str, Any]:
        steps = self.planner.plan(intent, self.session, self.guard)
        safety = self.guard.validate_plan(steps)
        if not safety.allowed:
            return self._response("blocked", safety.reason, source=source, intent=intent, steps=steps)

        # Track browsing history for search intents
        if intent.name in {"search_web", "search_youtube", "open_website"}:
            for step in steps:
                if step.action == "open_url":
                    url = step.params.get("url", "")
                    search_query = intent.entities.get("query", "")
                    self.session.add_browsing_entry(url, search_query=search_query)

        # Handle MCP async actions
        if any(step.action.startswith("mcp_") for step in steps):
            import asyncio
            result = asyncio.run(self._execute_mcp_steps(steps))
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
        self._record_last_app(steps)

        if result.pending_steps:
            self.session.set_pending(result.pending_steps)
            first_pending = result.pending_steps[0]
            message = "Awaiting confirmation to proceed."
            if first_pending.action == "autofill_login":
                service = str(first_pending.params.get("service", "")).strip()
                service_label = service or "the requested service"
                message = (
                    f"Ready to autofill credentials for {service_label}. "
                    "Say 'confirm' to proceed or 'cancel' to abort. "
                    "Credentials stay local and are never shown in the UI."
                )
            return self._response(
                "awaiting_confirmation",
                message,
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

        return self._response(
            "error",
            result.error or "Task did not complete.",
            source=source,
            intent=intent,
            steps=steps,
        )

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

        if intent_name == "reschedule_tasks" and clarification_type == "confirm_reschedule":
            normalized_reply = user_reply.lower().strip()
            if normalized_reply in {"yes", "y", "confirm", "ok", "okay", "sure", "proceed", "go ahead", "do it"}:
                self.session.clear_pending_clarification()
                recommendations = pending.get("recommendations", [])
                return self._execute_reschedule(recommendations, source)
            if normalized_reply in {"no", "n", "cancel", "stop", "abort", "nope", "never mind", "nevermind"}:
                self.session.clear_pending_clarification()
                return self._response("canceled", "Reschedule canceled. Your tasks remain as is.", source=source)
            return self._response(
                "awaiting_clarification",
                "Please say 'confirm' to apply the reschedule or 'cancel' to keep the current schedule.",
                source=source,
                pending_clarification=True,
            )

        self.session.clear_pending_clarification()
        return self._response("error", "Unable to resolve clarification context.", source=source)

    def _handle_pending(self, intent_name: str, source: str) -> dict[str, Any]:
        if intent_name == "confirm":
            result = self.executor.execute_steps(self.session.pending_steps, self.guard)
            self.session.clear_pending()
            if result.completed:
                return self._response("completed", "Confirmed and completed.", source=source)
            return self._response(
                "error",
                result.error or "Execution halted during confirmation.",
                source=source,
            )
        if intent_name == "cancel":
            self.session.clear_pending()
            return self._response("canceled", "Pending actions canceled.", source=source)
        return self._response(
            "awaiting_confirmation",
            "Type confirm or cancel to continue.",
            source=source,
            pending_confirmation=True,
        )

    async def _execute_mcp_steps(self, steps: list[Any]) -> dict[str, Any]:
        """Execute MCP tool calls asynchronously."""
        try:
            for step in steps:
                if step.action == "mcp_create_reminder":
                    tool = self.mcp_tools.get("reminders_create_reminder")
                    if not tool:
                        return {"error": "Reminders tool not available"}
                    result = await tool(**step.params)
                    return {"message": f"Created reminder '{result['name']}' in list '{result['list']}'"}
                elif step.action == "mcp_create_note":
                    tool = self.mcp_tools.get("notes_create_note")
                    if not tool:
                        return {"error": "Notes tool not available"}
                    result = await tool(**step.params)
                    return {"message": f"Created note '{result['title']}' in folder '{result['folder']}'"}
            return {"message": "Task completed"}
        except Exception as e:
            return {"error": f"MCP execution failed: {str(e)}"}

    def _execute_reschedule(self, recommendations: list[dict], source: str) -> dict[str, Any]:
        """Execute the rescheduling of tasks based on recommendations."""
        results = []
        for rec in recommendations:
            task_name = rec.get("task_name", "")
            task_source = rec.get("task_source", "reminder")
            suggested_date = rec.get("suggested_date", "")

            if task_source == "reminder" and suggested_date:
                # Create a new reminder with the due date
                tool = self.mcp_tools.get("reminders_create_reminder")
                if tool:
                    try:
                        import asyncio
                        asyncio.run(tool(
                            list_name="Reminders",
                            name=f"{task_name} (rescheduled)",
                            body=f"Moved from today due to emotional wellbeing. Original: {task_name}",
                            due_date_iso=f"{suggested_date}T09:00:00",
                        ))
                        results.append(f"Moved '{task_name}' to {suggested_date}")
                    except Exception as e:
                        results.append(f"Failed to move '{task_name}': {e}")
                else:
                    results.append(f"Would move '{task_name}' to {suggested_date} (reminder tool unavailable)")
            elif task_source == "calendar":
                results.append(f"Calendar event '{task_name}' flagged for rescheduling to {suggested_date} (manual action needed)")
            else:
                results.append(f"'{task_name}' noted for rescheduling to {suggested_date}")

        self.emotional_intelligence.invalidate_cache()

        message = "Rescheduling complete:\n" + "\n".join(f"  - {r}" for r in results)
        message += "\n\nTake care of yourself. I've lightened your load."

        return self._response("completed", message, source=source)

    def _record_last_app(self, steps: list[Any]) -> None:
        for step in steps:
            if step.action in {"open_app", "focus_app"}:
                self.session.set_last_app(step.params.get("app", ""))
                break

    def _should_pause_for_low_mood(self, intent_name: str) -> bool:
        affection = self._current_affection or {}
        if not affection.get("should_pause_automation"):
            return False
        safety_allowlist = {
            "check_mood",
            "confirm",
            "cancel",
            "emotional_check_in",
            "reschedule_tasks",
            "lighten_load",
            "check_schedule",
        }
        return intent_name not in safety_allowlist

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

        active_affection = self._current_affection or self.session.last_affection or {}
        intervention = active_affection.get("intervention", {})
        intervention_suggestions = intervention.get("suggestions", []) if active_affection.get("should_intervene") else []
        final_suggestions = _merge_unique_suggestions(suggestions or [], intervention_suggestions)
        affection_notice = ""
        if active_affection.get("should_intervene") and status not in {"blocked", "error", "support_required"}:
            affection_notice = intervention.get("message", "")

        return {
            "status": status,
            "message": message,
            "source": source,
            "intent": serialized_intent,
            "steps": serialized_steps,
            "pending_confirmation": pending_confirmation or bool(self.session.pending_steps),
            "pending_clarification": pending_clarification or bool(self.session.pending_clarification),
            "pending_action": _serialize_pending_action(self.session.pending_steps),
            "clarification_prompt": (self.session.pending_clarification or {}).get("prompt", ""),
            "last_app": self.session.last_app,
            "history_count": len(self.session.history),
            "suggestions": final_suggestions,
            "affection": active_affection,
            "affection_notice": affection_notice,
            "emotion_vector": active_affection.get("emotion_vector", {}),
            "dominant_emotion": active_affection.get("dominant_emotion", ""),
            "emotional_summary": active_affection.get("emotional_summary", ""),
            "cognitive_state": active_affection.get("cognitive_state", {}),
            "proactive_suggestions": active_affection.get("proactive_suggestions", []),
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


def _merge_unique_suggestions(primary: list[str], secondary: list[str], limit: int = 8) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in primary + secondary:
        normalized = value.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(normalized)
        if len(merged) >= limit:
            break
    return merged


def _serialize_pending_action(steps: list[Any]) -> dict[str, Any] | None:
    if not steps:
        return None
    first = steps[0]
    params = dict(first.params)
    # Keep credential autofill metadata explicit but non-sensitive.
    if first.action == "autofill_login":
        params = {"service": str(first.params.get("service", "")).strip()}
    return {
        "action": first.action,
        "description": first.description,
        "params": params,
    }
