#!/usr/bin/env python3
"""Bridge latency benchmark for PixelLink classes A/B and voice/text sources."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "pylink" / "desktop_bridge.py"


def _pct(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = int((p / 100) * (len(items) - 1))
    return items[idx]


def _read_json_line(proc: subprocess.Popen, timeout_sec: float = 15.0) -> dict:
    deadline = time.perf_counter() + timeout_sec
    while time.perf_counter() < deadline:
        line = proc.stdout.readline()
        if line:
            return json.loads(line)
    raise TimeoutError("Timed out waiting for bridge response")


def _run_case(proc: subprocess.Popen, action: str, text: str, source: str, i: int) -> float:
    request = {
        "action": action,
        "text": text,
        "source": source,
        "request_id": f"bench-{source}-{i}",
    }
    t0 = time.perf_counter()
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    _ = _read_json_line(proc)
    return (time.perf_counter() - t0) * 1000.0


def main() -> int:
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

    proc = subprocess.Popen(
        ["python3", str(BRIDGE)],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        ready = _read_json_line(proc)
        if ready.get("status") != "ready":
            print(f"Bridge failed to become ready: {ready}")
            return 1

        cases = {
            "class_a_text": ("process_input", "open Notes", "text"),
            "class_a_voice_source": ("process_input", "open Notes", "voice"),
            "class_b_text": ("process_input", "create reminder Buy milk", "text"),
        }

        runs = 80
        for label, (action, text, source) in cases.items():
            latencies = [_run_case(proc, action, text, source, i) for i in range(runs)]
            print(
                f"{label}: mean={statistics.mean(latencies):.2f}ms "
                f"p50={_pct(latencies,50):.2f}ms p95={_pct(latencies,95):.2f}ms p99={_pct(latencies,99):.2f}ms"
            )

        proc.stdin.write(json.dumps({"action": "shutdown", "request_id": "bench-shutdown"}) + "\n")
        proc.stdin.flush()
        _ = _read_json_line(proc)
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
