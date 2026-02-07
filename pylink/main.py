from __future__ import annotations

import logging
import os
import platform
from datetime import datetime

from core.input.text_input import read_text_input
from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime


def _setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", f"pixelink-{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def main() -> None:
    _setup_logging()

    # OS Detection and Warning
    system = platform.system()
    print(f"PixelLink MVP - Running on {system}")
    if system == "Darwin":
        print("✓ macOS detected (recommended)")
        print("⚠ Note: Ensure accessibility permissions are enabled for Terminal/Python")
        print("  (System Preferences → Security & Privacy → Accessibility)")
    elif system == "Windows":
        print("⚠ Windows support is experimental and not fully tested")
    elif system == "Linux":
        print("⚠ Linux support is experimental and not fully tested")
    else:
        print(f"⚠ WARNING: Unsupported OS '{system}'. Functionality may be limited.")

    runtime = PixelLinkRuntime(
        dry_run=False,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=True,
    )

    print("\nPixelLink started. Type 'exit' to quit. Press ESC for kill switch.")

    try:
        while True:
            input_data = read_text_input()
            raw_text = input_data["raw_text"]
            if not raw_text:
                continue
            if raw_text.lower() in {"exit", "quit"}:
                break

            result = runtime.handle_input(raw_text, source=input_data.get("source", "text"))
            if result.get("steps"):
                print("Planned steps:")
                for index, step in enumerate(result["steps"], start=1):
                    print(f"  {index}. {step['action']} - {step['description']}")
            print(result.get("message", ""))
            suggestions = result.get("suggestions", [])
            if suggestions:
                print("Try:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")
            logging.info("Runtime result: %s", result)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
