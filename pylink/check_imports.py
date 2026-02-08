#!/usr/bin/env python3
"""Validate that all critical imports resolve. Run from repo root or from pylink/.

  python3 check_imports.py
  # or from repo root:
  PYTHONPATH=pylink python3 pylink/check_imports.py

Catches import/name mismatches (e.g. PixelLinkRuntime vs MaesRuntime) early.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure pylink is on path when run as script
_PYLINK = Path(__file__).resolve().parent
if str(_PYLINK) not in sys.path:
    sys.path.insert(0, str(_PYLINK))

# (module, [expected attributes])
_IMPORT_CHECKS = [
    ("core.runtime", ["MaesRuntime", "PixelLinkRuntime", "DEFAULT_PERMISSION_PROFILE"]),
    ("core.runtime.orchestrator", ["MaesRuntime", "PixelLinkRuntime", "DEFAULT_PERMISSION_PROFILE"]),
    ("core.nlu", ["AffectionAssessment", "AffectionNLUModel", "Intent", "parse_intent"]),
    ("core.voice", ["TextToSpeech", "SpeechToText", "VoiceController"]),
    ("core.browser", ["BrowserAgent", "get_browser_agent"]),
    ("core.context.session", ["SessionContext"]),
    ("core.executor.engine", ["ExecutionEngine"]),
    ("core.planner.action_planner", ["ActionPlanner"]),
    ("core.safety.guard", ["KillSwitch", "SafetyGuard"]),
    ("core.input.text_input", ["read_text_input"]),
]


def main() -> int:
    errors: list[str] = []
    for mod_name, attrs in _IMPORT_CHECKS:
        try:
            mod = __import__(mod_name, fromlist=attrs)
            for attr in attrs:
                if not hasattr(mod, attr):
                    errors.append(f"{mod_name}: missing attribute {attr!r}")
        except Exception as e:
            errors.append(f"{mod_name}: {e}")

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        return 1
    print("All critical imports OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
