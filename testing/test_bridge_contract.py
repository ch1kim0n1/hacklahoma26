from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "pylink" / "desktop_bridge.py"


def _start_bridge() -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "PIXELINK_DRY_RUN": "1",
            "PIXELINK_ENABLE_KILL_SWITCH": "0",
            "PIXELINK_VOICE_INPUT": "0",
            "PIXELINK_VOICE_OUTPUT": "0",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return subprocess.Popen(
        ["python3", str(BRIDGE)],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_line(proc: subprocess.Popen) -> dict:
    line = proc.stdout.readline()
    assert line, "Expected JSON line from bridge"
    return json.loads(line)


def test_bridge_contract_backward_compatible() -> None:
    proc = _start_bridge()
    try:
        ready = _read_line(proc)
        assert ready["status"] == "ready"

        payload = {
            "action": "process_input",
            "text": "open Notes",
            "source": "text",
            "request_id": "contract-1",
        }
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
        result = _read_line(proc)

        # Existing contract fields
        for key in [
            "status",
            "message",
            "source",
            "intent",
            "steps",
            "pending_confirmation",
            "pending_clarification",
            "clarification_prompt",
            "last_app",
            "history_count",
            "suggestions",
            "voice",
            "request_id",
        ]:
            assert key in result

        assert result["request_id"] == "contract-1"

        # Additive fields
        assert "metrics" in result
        assert "trace_id" in result
        for key in ["parse_ms", "plan_ms", "execute_ms", "total_ms", "nlu_mode"]:
            assert key in result["metrics"]

        proc.stdin.write(json.dumps({"action": "shutdown", "request_id": "contract-shutdown"}) + "\n")
        proc.stdin.flush()
        _ = _read_line(proc)
    finally:
        proc.kill()
