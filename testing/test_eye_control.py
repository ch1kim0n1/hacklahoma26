"""
Test eye control module: availability and graceful fallback when deps are missing.
Run from repo root: python -m pytest hacklahoma26/testing/test_eye_control.py -v
Or: cd hacklahoma26 && PYTHONPATH=. python testing/test_eye_control.py
"""

import sys
from pathlib import Path

# Add pylink dir so "from core.eye" works (core is under pylink/)
HACK_ROOT = Path(__file__).resolve().parents[1]
PYLINK_DIR = HACK_ROOT / "pylink"
sys.path.insert(0, str(PYLINK_DIR))


def test_eye_control_import_and_availability():
    """Import eye module and check is_eye_control_available() does not raise."""
    from core.eye.eye_control import is_eye_control_available, start_eye_loop, stop_eye_loop, BlinkType

    available = is_eye_control_available()
    # When opencv/mediapipe or camera are missing, available is False; no exception
    assert isinstance(available, bool)
    assert BlinkType.SINGLE.value == "single"
    assert BlinkType.DOUBLE.value == "double"


def test_eye_control_start_stop_no_crash_when_unavailable():
    """When eye control is unavailable, start_eye_loop returns False and stop_eye_loop is safe."""
    from core.eye.eye_control import is_eye_control_available, start_eye_loop, stop_eye_loop

    def noop_gaze(x: int, y: int) -> None:
        pass

    def noop_blink(bt) -> None:
        pass

    def get_size():
        return (1920, 1080)

    # Stop first in case a previous test left it running
    stop_eye_loop()

    started = start_eye_loop(noop_gaze, noop_blink, get_size, show_preview=False)
    # If deps/camera missing, started is False; if available, started is True
    if not is_eye_control_available():
        assert started is False
    else:
        assert started is True
        stop_eye_loop()

    # Stop again is safe (idempotent)
    stop_eye_loop()


def test_is_eye_control_unavailable_when_mediapipe_face_mesh_missing(monkeypatch):
    """If mediapipe lacks FaceMesh API, availability should be False without touching camera."""
    from core.eye import eye_control

    class FakeCV2:
        def __init__(self) -> None:
            self.calls = 0

        def VideoCapture(self, *_):
            self.calls += 1
            raise AssertionError("VideoCapture should not be called when mediapipe is unusable")

    fake_cv2 = FakeCV2()
    monkeypatch.setattr(eye_control, "cv2", fake_cv2)
    monkeypatch.setattr(eye_control, "mp", object())

    assert eye_control.is_eye_control_available() is False
    assert fake_cv2.calls == 0


def test_start_eye_loop_returns_false_when_mediapipe_face_mesh_missing(monkeypatch):
    """start_eye_loop should fail fast and avoid starting a thread for unusable mediapipe."""
    from core.eye import eye_control

    eye_control.stop_eye_loop()
    monkeypatch.setattr(eye_control, "cv2", object())
    monkeypatch.setattr(eye_control, "mp", object())

    started = eye_control.start_eye_loop(
        lambda _x, _y: None,
        lambda _blink: None,
        lambda: (1920, 1080),
        show_preview=False,
    )
    assert started is False
    assert eye_control._eye_thread is None


def test_eye_control_diagnostics_provide_reason_codes(monkeypatch):
    """Diagnostics should explain dependency failures without probing camera."""
    from core.eye import eye_control

    class FakeCV2:
        def __init__(self) -> None:
            self.calls = 0

        def VideoCapture(self, *_):
            self.calls += 1
            raise AssertionError("VideoCapture should not be touched for dependency failures")

    fake_cv2 = FakeCV2()
    monkeypatch.setattr(eye_control, "cv2", fake_cv2)
    monkeypatch.setattr(eye_control, "mp", None)

    diagnostics = eye_control.get_eye_control_diagnostics(
        check_camera=False,
        ensure_model=False,
    )
    assert diagnostics["available"] is False
    assert diagnostics["reason_code"] == "missing_mediapipe"
    assert fake_cv2.calls == 0


def test_resolve_blink_action_mapping():
    """Blink action mapping: double blink clicks, single blink confirms pending actions."""
    from desktop_bridge import _resolve_blink_action

    assert _resolve_blink_action("single", pending=True) == "confirm"
    assert _resolve_blink_action("double", pending=True) == "cancel"
    assert _resolve_blink_action("double", pending=False) == "left_click"
    assert _resolve_blink_action("single", pending=False) is None
    assert _resolve_blink_action("none", pending=False) is None


def test_estimate_gaze_target_uses_iris_offset():
    """Iris positions should shift gaze target away from plain face-center mapping."""
    from core.eye.eye_control import _estimate_gaze_target_from_landmarks

    class LM:
        def __init__(self, x: float = 0.5, y: float = 0.5) -> None:
            self.x = x
            self.y = y

    landmarks = [LM() for _ in range(478)]
    # Face bounds around center.
    landmarks[10] = LM(0.40, 0.30)
    landmarks[152] = LM(0.60, 0.70)

    # Eye corners + lids.
    landmarks[33] = LM(0.44, 0.50)
    landmarks[133] = LM(0.49, 0.50)
    landmarks[159] = LM(0.465, 0.48)
    landmarks[145] = LM(0.465, 0.52)

    landmarks[362] = LM(0.51, 0.50)
    landmarks[263] = LM(0.56, 0.50)
    landmarks[386] = LM(0.535, 0.48)
    landmarks[374] = LM(0.535, 0.52)

    # Iris points pushed to the right/down in both eyes.
    for idx in [468, 469, 470, 471, 472]:
        landmarks[idx] = LM(0.485, 0.515)
    for idx in [473, 474, 475, 476, 477]:
        landmarks[idx] = LM(0.555, 0.515)

    x, y, telemetry = _estimate_gaze_target_from_landmarks(landmarks, 1920, 1080)
    assert telemetry["iris_tracking"] is True
    assert telemetry["control_mode"] == "iris"
    assert x > 960  # shifted right vs center
    assert y > 540  # shifted down vs center


if __name__ == "__main__":
    test_eye_control_import_and_availability()
    test_eye_control_start_stop_no_crash_when_unavailable()
    print("Eye control tests passed (graceful fallback when deps/camera missing).")
