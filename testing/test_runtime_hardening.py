from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYLINK_DIR = ROOT / "pylink"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PYLINK_DIR))

from core.executor.os_control import OSController
from core.nlu.affection_model import AffectionNLUModel
from core.nlu.parser import parse_intent
from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime
from core.safety.guard import SafetyGuard
from core.planner.action_planner import ActionPlanner
from core.context.session import SessionContext


def test_open_app_non_macos_running_does_not_recurse(monkeypatch) -> None:
    ctrl = OSController()
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(ctrl, "is_app_running", lambda _name: True)
    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("subprocess.run should not execute")

    monkeypatch.setattr("subprocess.run", _fail_if_called)
    ctrl.open_app("firefox")


def test_login_action_requires_confirmation() -> None:
    planner = ActionPlanner()
    guard = SafetyGuard()
    session = SessionContext()
    intent = parse_intent("login to github", session)
    steps = planner.plan(intent, session, guard)
    assert steps
    assert steps[0].action == "autofill_login"
    assert steps[0].requires_confirmation is True


def test_runtime_login_flow_exposes_sanitized_pending_action() -> None:
    runtime = PixelLinkRuntime(
        dry_run=True,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=False,
        verbose=False,
    )
    try:
        result = runtime.handle_input("login to github", source="test")
    finally:
        runtime.close()

    assert result["status"] == "awaiting_confirmation"
    assert result.get("pending_action", {}).get("action") == "autofill_login"
    assert result.get("pending_action", {}).get("params", {}).get("service") == "github"
    assert "never shown in the UI" in result.get("message", "")


def test_pause_mode_still_allows_supportive_schedule_intent(monkeypatch) -> None:
    runtime = PixelLinkRuntime(
        dry_run=True,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=False,
        verbose=False,
    )
    try:
        assessment = AffectionNLUModel().analyze(
            "I am hopeless, overwhelmed, and I want to give up.",
            runtime.session,
        )
        assert assessment.should_pause_automation is True
        monkeypatch.setattr(runtime.affection_nlu, "analyze", lambda _text, _session: assessment)
        result = runtime.handle_input("show my schedule today", source="test")
    finally:
        runtime.close()

    assert result["status"] != "support_required"


def test_ambiguous_reschedule_reply_keeps_clarification_pending() -> None:
    runtime = PixelLinkRuntime(
        dry_run=True,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=False,
        verbose=False,
    )
    try:
        runtime.session.set_pending_clarification(
            {
                "intent_name": "reschedule_tasks",
                "clarification_type": "confirm_reschedule",
                "recommendations": [],
                "prompt": "Confirm or cancel?",
            }
        )
        result = runtime.handle_input("maybe", source="test")
    finally:
        runtime.close()

    assert result["status"] == "awaiting_clarification"
    assert result["pending_clarification"] is True
