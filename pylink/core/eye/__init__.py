"""Eye tracking and blink detection for accessibility input."""

from core.eye.eye_control import (
    start_eye_loop,
    stop_eye_loop,
    is_eye_control_available,
    BlinkType,
)

__all__ = [
    "start_eye_loop",
    "stop_eye_loop",
    "is_eye_control_available",
    "BlinkType",
]
