"""
Eye tracking and blink detection using webcam.
Uses MediaPipe landmarks and EAR (Eye Aspect Ratio) for blinks.
Supports both legacy Face Mesh and modern FaceLandmarker task APIs.
Gaze is mapped to screen coordinates via simple linear mapping (no calibration in MVP).
"""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlretrieve

# Optional dependencies: opencv-python, mediapipe
# If missing, is_eye_control_available() returns False and start_eye_loop no-ops.
try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    import mediapipe as mp
except ImportError:
    mp = None  # type: ignore[assignment]


class BlinkType(str, Enum):
    NONE = "none"
    SINGLE = "single"
    DOUBLE = "double"


# MediaPipe Face Mesh indices for left/right eye (6 points per eye for EAR)
# Left eye: 33, 160, 158, 133, 153, 144
# Right eye: 362, 385, 387, 263, 373, 380
LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
LEFT_IRIS_INDICES = [468, 469, 470, 471, 472]
RIGHT_IRIS_INDICES = [473, 474, 475, 476, 477]

# EAR threshold below which we consider eye "closed"
EYE_AR_THRESHOLD = 0.25
# Consecutive frames below threshold to count as one blink
EYE_AR_CONSEC_FRAMES = 3
# Max ms between two blinks to count as double blink
DOUBLE_BLINK_MS = 400
# Gaze smoothing: exponential moving average factor (0 = no smooth, 1 = no change)
GAZE_SMOOTH = 0.35
# Iris-based gaze gain relative to face center.
GAZE_EYE_GAIN_X = 1.65
GAZE_EYE_GAIN_Y = 1.2
# Camera resolution (lower = faster)
CAM_WIDTH = 320
CAM_HEIGHT = 240
# Target FPS for eye loop (cap to save CPU)
TARGET_FPS = 20

FACE_LANDMARKER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
FACE_LANDMARKER_MODEL_PATH = Path.home() / ".pixelink" / "models" / "face_landmarker.task"
EYE_PREVIEW_WINDOW_NAME = "PixelLink Eye Control"

_stop_event: threading.Event | None = None
_eye_thread: threading.Thread | None = None
_last_start_error: str | None = None


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return default


def _should_show_preview(show_preview: bool | None) -> bool:
    if show_preview is not None:
        return show_preview
    return _as_bool(os.getenv("PIXELINK_EYE_PREVIEW"), default=True)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_ratio(value: float, start: float, end: float) -> float:
    span = end - start
    if abs(span) < 1e-6:
        return 0.5
    return _clamp((value - start) / span, 0.0, 1.0)


def _average_landmark(landmarks, indices: list[int]) -> tuple[float, float] | None:
    if not indices:
        return None
    max_index = len(landmarks) - 1
    if any(idx > max_index for idx in indices):
        return None
    xs = [landmarks[idx].x for idx in indices]
    ys = [landmarks[idx].y for idx in indices]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _estimate_gaze_target_from_landmarks(
    landmarks,
    screen_w: int,
    screen_h: int,
) -> tuple[int, int, dict[str, Any]]:
    """
    Estimate on-screen gaze target from face + iris landmarks.

    Returns:
        (screen_x, screen_y, telemetry)
    """
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    face_cx = _clamp((min(xs) + max(xs)) * 0.5, 0.0, 1.0)
    face_cy = _clamp((min(ys) + max(ys)) * 0.5, 0.0, 1.0)

    gaze_nx = face_cx
    gaze_ny = face_cy
    iris_tracking = False
    iris_ratio_x = 0.5
    iris_ratio_y = 0.5
    iris_offset_x = 0.0
    iris_offset_y = 0.0
    control_mode = "face"

    iris_gain_x = _as_float(os.getenv("PIXELINK_EYE_IRIS_GAIN_X"), default=3.2)
    iris_gain_y = _as_float(os.getenv("PIXELINK_EYE_IRIS_GAIN_Y"), default=2.8)
    head_weight = _as_float(os.getenv("PIXELINK_EYE_HEAD_WEIGHT"), default=0.0)

    left_iris = _average_landmark(landmarks, LEFT_IRIS_INDICES)
    right_iris = _average_landmark(landmarks, RIGHT_IRIS_INDICES)
    if left_iris and right_iris:
        iris_tracking = True
        left_hr = _safe_ratio(left_iris[0], landmarks[33].x, landmarks[133].x)
        right_hr = _safe_ratio(right_iris[0], landmarks[362].x, landmarks[263].x)
        left_vr = _safe_ratio(left_iris[1], landmarks[159].y, landmarks[145].y)
        right_vr = _safe_ratio(right_iris[1], landmarks[386].y, landmarks[374].y)

        iris_ratio_x = (left_hr + right_hr) * 0.5
        iris_ratio_y = (left_vr + right_vr) * 0.5

        iris_offset_x = (iris_ratio_x - 0.5) * GAZE_EYE_GAIN_X
        iris_offset_y = (iris_ratio_y - 0.5) * GAZE_EYE_GAIN_Y

        if _as_bool(os.getenv("PIXELINK_EYE_INVERT_X"), default=False):
            iris_offset_x = -iris_offset_x
        if _as_bool(os.getenv("PIXELINK_EYE_INVERT_Y"), default=False):
            iris_offset_y = -iris_offset_y

        # Iris-driven gaze (eye movement dominant). Optional tiny head blend for stability.
        eye_only_x = _clamp(0.5 + ((iris_ratio_x - 0.5) * iris_gain_x), 0.0, 1.0)
        eye_only_y = _clamp(0.5 + ((iris_ratio_y - 0.5) * iris_gain_y), 0.0, 1.0)
        gaze_nx = _clamp(eye_only_x + ((face_cx - 0.5) * head_weight), 0.0, 1.0)
        gaze_ny = _clamp(eye_only_y + ((face_cy - 0.5) * head_weight), 0.0, 1.0)
        control_mode = "iris"

    ix = int(round(gaze_nx * max(0, screen_w - 1)))
    iy = int(round(gaze_ny * max(0, screen_h - 1)))
    telemetry = {
        "gaze_norm": (gaze_nx, gaze_ny),
        "face_norm": (face_cx, face_cy),
        "iris_tracking": iris_tracking,
        "iris_ratio": (iris_ratio_x, iris_ratio_y),
        "iris_offset": (iris_offset_x, iris_offset_y),
        "control_mode": control_mode,
        "iris_gain": (iris_gain_x, iris_gain_y),
        "head_weight": head_weight,
    }
    return (ix, iy, telemetry)


def _is_mediapipe_face_mesh_available() -> bool:
    """Return True if mediapipe exposes legacy FaceMesh API."""
    if mp is None:
        return False
    solutions = getattr(mp, "solutions", None)
    if solutions is None:
        return False
    face_mesh = getattr(solutions, "face_mesh", None)
    if face_mesh is None:
        return False
    return hasattr(face_mesh, "FaceMesh")


def _is_mediapipe_task_landmarker_available() -> bool:
    """Return True if mediapipe exposes the modern tasks FaceLandmarker API."""
    if mp is None:
        return False
    tasks = getattr(mp, "tasks", None)
    if tasks is None:
        return False
    if not hasattr(tasks, "BaseOptions"):
        return False
    vision = getattr(tasks, "vision", None)
    if vision is None:
        return False
    return all(
        hasattr(vision, attr)
        for attr in ("FaceLandmarker", "FaceLandmarkerOptions", "RunningMode")
    )


def _ensure_face_landmarker_model() -> Path | None:
    """Ensure the FaceLandmarker task model exists locally."""
    try:
        FACE_LANDMARKER_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not FACE_LANDMARKER_MODEL_PATH.exists():
            urlretrieve(FACE_LANDMARKER_MODEL_URL, FACE_LANDMARKER_MODEL_PATH)
        return FACE_LANDMARKER_MODEL_PATH
    except (OSError, URLError):
        return None


def _create_landmark_backend():
    """
    Create a landmark backend.

    Returns:
        ("face_mesh", backend) or ("task_landmarker", backend), or None on failure.
    """
    if _is_mediapipe_face_mesh_available():
        try:
            return (
                "face_mesh",
                mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                ),
            )
        except Exception:
            pass

    if _is_mediapipe_task_landmarker_available():
        model_path = _ensure_face_landmarker_model()
        if model_path is None:
            return None
        try:
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            return ("task_landmarker", mp.tasks.vision.FaceLandmarker.create_from_options(options))
        except Exception:
            return None

    return None


def _extract_landmarks(backend_kind: str, backend, frame_rgb, timestamp_ms: int):
    """Run the active backend and return a landmark list (or None)."""
    if backend_kind == "face_mesh":
        result = backend.process(frame_rgb)
        if result.multi_face_landmarks:
            return result.multi_face_landmarks[0].landmark
        return None

    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
    result = backend.detect_for_video(image, timestamp_ms)
    if result.face_landmarks:
        return result.face_landmarks[0]
    return None


def _close_landmark_backend(backend) -> None:
    try:
        backend.close()
    except Exception:
        pass


def _draw_eye_preview(
    frame,
    landmarks,
    *,
    ear: float | None,
    gaze: tuple[int, int] | None,
    gaze_norm: tuple[float, float] | None,
    iris_tracking: bool,
    backend_kind: str,
    control_mode: str,
    last_blink: str | None,
    consec_low: int,
) -> None:
    """Draw eye-control diagnostics directly onto camera frame."""
    if cv2 is None:
        return

    overlay = frame.copy()
    h, w = overlay.shape[:2]

    if landmarks:
        for idx in LEFT_EYE_INDICES + RIGHT_EYE_INDICES:
            lm = landmarks[idx]
            px = int(lm.x * w)
            py = int(lm.y * h)
            cv2.circle(overlay, (px, py), 2, (0, 255, 0), -1)
        for idx in LEFT_IRIS_INDICES + RIGHT_IRIS_INDICES:
            if idx < len(landmarks):
                lm = landmarks[idx]
                px = int(lm.x * w)
                py = int(lm.y * h)
                cv2.circle(overlay, (px, py), 2, (255, 210, 0), -1)

        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]
        cx = int(((min(xs) + max(xs)) * 0.5) * w)
        cy = int(((min(ys) + max(ys)) * 0.5) * h)
        cv2.circle(overlay, (cx, cy), 4, (0, 200, 255), -1)

    lines = [
        f"EAR: {ear:.3f}" if ear is not None else "EAR: n/a",
        f"Blink state: {'closed' if consec_low > 0 else 'open'}",
        f"Last blink: {last_blink or '-'}",
        f"Gaze: {gaze[0]}, {gaze[1]}" if gaze else "Gaze: n/a",
        (
            f"Gaze norm: {gaze_norm[0]:.2f}, {gaze_norm[1]:.2f}"
            if gaze_norm
            else "Gaze norm: n/a"
        ),
        f"Mode: {control_mode}",
        f"Iris tracking: {'on' if iris_tracking else 'off'}",
        f"Backend: {backend_kind}",
        "Double blink = click",
    ]
    for i, line in enumerate(lines):
        cv2.putText(
            overlay,
            line,
            (10, 24 + (i * 22)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    cv2.imshow(EYE_PREVIEW_WINDOW_NAME, overlay)


def _euclidean(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _eye_aspect_ratio(landmarks, indices: list[int], width: int, height: int) -> float:
    """Compute EAR for one eye from MediaPipe landmarks."""
    points = []
    for i in indices:
        lm = landmarks[i]
        points.append((lm.x * width, lm.y * height))
    # EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    p1, p2, p3, p4, p5, p6 = points
    vertical1 = _euclidean(p2, p6)
    vertical2 = _euclidean(p3, p5)
    horizontal = _euclidean(p1, p4)
    if horizontal == 0:
        return 0.0
    return (vertical1 + vertical2) / (2.0 * horizontal)


def _run_eye_loop(
    on_gaze: Callable[[int, int], None],
    on_blink: Callable[[BlinkType], None],
    get_screen_size: Callable[[], tuple[int, int]],
    show_preview: bool,
    on_metrics: Callable[[dict[str, Any]], None] | None,
) -> None:
    """Run webcam loop in current thread. Exits when _stop_event is set."""
    global _stop_event, _last_start_error
    if cv2 is None:
        _last_start_error = "OpenCV dependency is unavailable."
        return
    backend_info = _create_landmark_backend()
    if backend_info is None:
        _last_start_error = "Failed to initialize MediaPipe eye landmark backend."
        return
    backend_kind, landmark_backend = backend_info
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        _last_start_error = "Unable to open camera device 0."
        cap.release()
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

    frame_interval = 1.0 / TARGET_FPS
    consec_low = 0
    last_blink_time: float = 0
    blink_count_for_double = 0
    last_blink_label: str | None = None
    last_gaze: tuple[int, int] | None = None
    last_gaze_norm: tuple[float, float] | None = None
    iris_tracking_active = False
    control_mode = "face"
    last_ear: float | None = None
    smooth_x: float | None = None
    smooth_y: float | None = None
    last_timestamp_ms = 0
    preview_enabled = show_preview

    if preview_enabled:
        try:
            cv2.namedWindow(EYE_PREVIEW_WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(EYE_PREVIEW_WINDOW_NAME, 460, 340)
            cv2.startWindowThread()
        except Exception as exc:
            print(f"[eye] Preview disabled: {exc}", file=sys.stderr)
            preview_enabled = False

    try:
        while _stop_event and not _stop_event.is_set():
            loop_start = time.perf_counter()
            ret, frame = cap.read()
            if not ret:
                continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            timestamp_ms = max(last_timestamp_ms + 1, int(time.perf_counter() * 1000))
            last_timestamp_ms = timestamp_ms
            landmarks = _extract_landmarks(
                backend_kind,
                landmark_backend,
                frame_rgb,
                timestamp_ms,
            )

            if landmarks:
                ear_left = _eye_aspect_ratio(landmarks, LEFT_EYE_INDICES, w, h)
                ear_right = _eye_aspect_ratio(landmarks, RIGHT_EYE_INDICES, w, h)
                ear = (ear_left + ear_right) / 2.0
                last_ear = ear

                # Blink detection
                if ear < EYE_AR_THRESHOLD:
                    consec_low += 1
                else:
                    if consec_low >= EYE_AR_CONSEC_FRAMES:
                        now = time.perf_counter() * 1000
                        if now - last_blink_time < DOUBLE_BLINK_MS:
                            blink_count_for_double += 1
                            if blink_count_for_double >= 2:
                                on_blink(BlinkType.DOUBLE)
                                last_blink_label = BlinkType.DOUBLE.value
                                blink_count_for_double = 0
                        else:
                            blink_count_for_double = 1
                            on_blink(BlinkType.SINGLE)
                            last_blink_label = BlinkType.SINGLE.value
                        last_blink_time = now
                    consec_low = 0

                # Gaze proxy: face center from the landmark bounding box.
                screen_w, screen_h = get_screen_size()
                raw_ix, raw_iy, gaze_telemetry = _estimate_gaze_target_from_landmarks(
                    landmarks, screen_w, screen_h
                )
                raw_gx = float(raw_ix)
                raw_gy = float(raw_iy)
                if smooth_x is not None and smooth_y is not None:
                    smooth_x = GAZE_SMOOTH * smooth_x + (1 - GAZE_SMOOTH) * raw_gx
                    smooth_y = GAZE_SMOOTH * smooth_y + (1 - GAZE_SMOOTH) * raw_gy
                else:
                    smooth_x, smooth_y = raw_gx, raw_gy
                ix, iy = int(round(smooth_x)), int(round(smooth_y))
                ix = max(0, min(screen_w - 1, ix))
                iy = max(0, min(screen_h - 1, iy))
                on_gaze(ix, iy)
                last_gaze = (ix, iy)
                last_gaze_norm = gaze_telemetry["gaze_norm"]
                iris_tracking_active = bool(gaze_telemetry["iris_tracking"])
                control_mode = str(gaze_telemetry.get("control_mode", "face"))
            else:
                smooth_x = None
                smooth_y = None
                last_ear = None
                last_gaze_norm = None
                iris_tracking_active = False
                control_mode = "face"

            if on_metrics:
                try:
                    on_metrics(
                        {
                            "ear": round(last_ear, 4) if last_ear is not None else None,
                            "blink_state": "closed" if consec_low > 0 else "open",
                            "blink_frames": consec_low,
                            "last_blink": last_blink_label,
                            "last_gaze": last_gaze,
                            "gaze_norm": last_gaze_norm,
                            "iris_tracking": iris_tracking_active,
                            "control_mode": control_mode,
                            "backend": backend_kind,
                            "preview_active": preview_enabled,
                        }
                    )
                except Exception:
                    pass

            if preview_enabled:
                try:
                    _draw_eye_preview(
                        frame,
                        landmarks,
                        ear=last_ear,
                        gaze=last_gaze,
                        gaze_norm=last_gaze_norm,
                        iris_tracking=iris_tracking_active,
                        backend_kind=backend_kind,
                        control_mode=control_mode,
                        last_blink=last_blink_label,
                        consec_low=consec_low,
                    )
                    key = cv2.waitKey(1) & 0xFF
                    if key in {27, ord("q"), ord("Q")} and _stop_event:
                        _stop_event.set()
                except Exception as exc:
                    print(f"[eye] Preview disabled during runtime: {exc}", file=sys.stderr)
                    preview_enabled = False

            elapsed = time.perf_counter() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception as exc:
        _last_start_error = f"Eye loop runtime error: {type(exc).__name__}: {exc}"
    finally:
        if preview_enabled and cv2 is not None:
            try:
                cv2.destroyWindow(EYE_PREVIEW_WINDOW_NAME)
            except Exception:
                pass
        _close_landmark_backend(landmark_backend)
        cap.release()


def get_eye_control_diagnostics(
    *,
    check_camera: bool = True,
    ensure_model: bool = True,
    require_frame: bool = False,
) -> dict[str, Any]:
    """Probe eye-control readiness with explicit diagnostics."""
    result: dict[str, Any] = {
        "available": False,
        "reason_code": "",
        "reason": "",
        "backend": None,
        "camera_checked": bool(check_camera),
        "camera_ok": None,
        "frame_ok": None,
        "model_ready": None,
    }

    if cv2 is None:
        result["reason_code"] = "missing_opencv"
        result["reason"] = "OpenCV dependency is missing."
        return result
    if mp is None:
        result["reason_code"] = "missing_mediapipe"
        result["reason"] = "MediaPipe dependency is missing."
        return result

    backend = None
    if _is_mediapipe_face_mesh_available():
        backend = "face_mesh"
        result["model_ready"] = True
    elif _is_mediapipe_task_landmarker_available():
        backend = "task_landmarker"
        model_ok = True
        if ensure_model:
            model_ok = _ensure_face_landmarker_model() is not None
        result["model_ready"] = bool(model_ok)
        if not model_ok:
            result["reason_code"] = "model_unavailable"
            result["reason"] = "FaceLandmarker model is missing or failed to download."
            result["backend"] = backend
            return result
    else:
        result["reason_code"] = "unsupported_mediapipe_runtime"
        result["reason"] = "No supported MediaPipe face landmark backend was found."
        return result

    result["backend"] = backend
    if not check_camera:
        result["available"] = True
        result["reason_code"] = "ok_soft"
        result["reason"] = "Dependencies are available; camera not verified."
        return result

    cap = cv2.VideoCapture(0)
    try:
        camera_ok = bool(cap.isOpened())
        result["camera_ok"] = camera_ok
        if not camera_ok:
            result["reason_code"] = "camera_unavailable"
            result["reason"] = "Camera device is unavailable or permission is denied."
            return result

        if require_frame:
            frame_ok, _frame = cap.read()
            result["frame_ok"] = bool(frame_ok)
            if not frame_ok:
                result["reason_code"] = "camera_frame_failed"
                result["reason"] = "Camera opened but no frames were received."
                return result
    finally:
        cap.release()

    result["available"] = True
    result["reason_code"] = "ok"
    result["reason"] = "Eye control is ready."
    return result


def is_eye_control_available(check_camera: bool = True, ensure_model: bool = True) -> bool:
    """
    Return True if eye control dependencies are available.

    Args:
        check_camera: When True, verify that a camera can be opened.
        ensure_model: When True, ensure the task-landmarker model is present.
            Set False for startup checks to avoid network/download side effects.
    """
    diagnostics = get_eye_control_diagnostics(
        check_camera=check_camera,
        ensure_model=ensure_model,
    )
    return bool(diagnostics.get("available", False))


def start_eye_loop(
    on_gaze: Callable[[int, int], None],
    on_blink: Callable[[BlinkType], None],
    get_screen_size: Callable[[], tuple[int, int]],
    show_preview: bool | None = None,
    on_metrics: Callable[[dict[str, Any]], None] | None = None,
) -> bool:
    """
    Start the eye tracking loop in a background thread.
    on_gaze(x, y) is called with screen coordinates; on_blink(BlinkType) for single/double blink.
    get_screen_size() should return (width, height) of the screen.
    show_preview controls the camera diagnostics window. If None, reads PIXELINK_EYE_PREVIEW
    (default: enabled).
    on_metrics receives frame-level telemetry for UI diagnostics.
    Returns True if started, False if dependencies missing or camera unavailable.
    """
    global _stop_event, _eye_thread, _last_start_error
    diagnostics = get_eye_control_diagnostics(
        check_camera=True,
        ensure_model=True,
        require_frame=True,
    )
    if not diagnostics.get("available"):
        _last_start_error = str(diagnostics.get("reason", "Eye control is unavailable."))
        return False
    if _stop_event is not None and _eye_thread is not None and _eye_thread.is_alive():
        return True  # already running
    _last_start_error = None
    _stop_event = threading.Event()
    _eye_thread = threading.Thread(
        target=_run_eye_loop,
        args=(
            on_gaze,
            on_blink,
            get_screen_size,
            _should_show_preview(show_preview),
            on_metrics,
        ),
        daemon=True,
    )
    _eye_thread.start()
    # If the loop exits immediately (e.g. backend init failure), report failure.
    time.sleep(0.05)
    if not _eye_thread.is_alive():
        _last_start_error = _last_start_error or "Eye control loop exited during startup."
        _stop_event = None
        _eye_thread = None
        return False
    return True


def stop_eye_loop() -> None:
    """Stop the eye tracking loop gracefully."""
    global _stop_event, _eye_thread
    if _stop_event:
        _stop_event.set()
    if _eye_thread and _eye_thread.is_alive():
        _eye_thread.join(timeout=2.0)
    _stop_event = None
    _eye_thread = None


def get_eye_control_last_error() -> str:
    """Last startup/runtime eye-control error message."""
    return _last_start_error or ""
