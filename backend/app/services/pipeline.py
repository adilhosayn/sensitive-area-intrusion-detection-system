"""Single shared frame-processing pipeline: detect -> track -> apply rules.

Both the batch video-upload path (`api/video.py`) and the live WebSocket path
(`api/stream.py`) call `process_frame` for every frame. 
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2

from app.core.audio import trigger_weapon_siren
from app.core.config import settings
from app.core.detector import YOLODetector
from app.core.rules import RuleConfig, RuleEngine
from app.core.tracker import ObjectTracker
from app.schemas.detection import Alert, Detection

_BOX_COLOR_DEFAULT = (0, 255, 0)
_BOX_COLOR_WEAPON = (0, 0, 255)


def process_frame(
    frame,
    detector: YOLODetector,
    tracker: ObjectTracker,
    rule_engine: RuleEngine,
    frame_id: int,
    confidence_threshold: float = 0.4,
    draw: bool = True,
) -> tuple[object, list[Detection], list[Alert]]:
    """Run one frame through the full pipeline. Mutates `frame` in place when
    `draw=True` and also returns it, so callers can chain calls easily."""
    height, width = frame.shape[:2]
    results = detector.detect(frame, confidence_threshold)

    yolo_dets = []
    for box in results.boxes:
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls_id = int(box.cls[0])
        cls_name = results.names[cls_id]

        bw_frac = (x2 - x1) / width
        bh_frac = (y2 - y1) / height
        # Handheld weapons are never half the screen: reject oversized full-body false alarms
        if rule_engine.config.weapon_only_mode and (bw_frac > 0.45 and bh_frac > 0.45):
            continue

        yolo_dets.append(([x1, y1, x2 - x1, y2 - y1], conf, cls_name))

    tracks = tracker.update(yolo_dets, frame)

    detections: list[Detection] = []
    has_weapon = False
    weapon_class_name = ""

    for track in tracks:
        cls_name = track.get_det_class() or "unknown"
        conf = track.get_det_conf() or 0.0
        is_weapon = cls_name.lower() in rule_engine.config.weapon_class_names

        # Accept confirmed tracks, or instant high-confidence weapon detections
        if not track.is_confirmed() and not (is_weapon and conf >= 0.4):
            continue

        if rule_engine.config.weapon_only_mode and not is_weapon:
            continue

        bx1, by1, bx2, by2 = map(int, track.to_ltrb())
        if is_weapon:
            has_weapon = True
            weapon_class_name = cls_name

        detections.append(Detection(
            track_id=int(track.track_id),
            class_name=cls_name,
            confidence=round(float(conf), 3),
            bbox=[bx1, by1, bx2, by2],
        ))

        if draw:
            box_color = _BOX_COLOR_WEAPON if is_weapon else _BOX_COLOR_DEFAULT
            thickness = 3 if is_weapon else 2
            cv2.rectangle(frame, (bx1, by1), (bx2, by2), box_color, thickness)

            label = (
                f"WARNING: WEAPON ({cls_name.upper()}) #{track.track_id} {conf:.2f}"
                if is_weapon
                else f"{cls_name} #{track.track_id}"
            )
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame, (bx1, max(by1 - lh - 8, 0)), (bx1 + lw + 6, max(by1, lh + 8)), box_color, -1)
            cv2.putText(
                frame, label, (bx1 + 3, max(by1 - 4, lh + 4)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255) if is_weapon else (0, 0, 0), 2,
            )

    alerts = rule_engine.process_frame(frame_id, detections, width, height)

    # Top visual HUD banner
    if draw:
        if has_weapon or any(a.type == "weapon_detected" and a.event == "started" for a in alerts):
            cv2.rectangle(frame, (0, 0), (width, 42), (0, 0, 220), -1)
            banner = f"CRITICAL ALERT: WEAPON IN SIGHT ({weapon_class_name.upper() or 'THREAT'})"
            (bw, bh), _ = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.putText(
                frame, banner, (max((width - bw) // 2, 10), 29),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
            )
        elif rule_engine.config.weapon_only_mode:
            cv2.rectangle(frame, (0, 0), (width, 28), (30, 30, 30), -1)
            status_text = "WEAPON SURVEILLANCE ACTIVE - SCANNING FOR FIREARMS & KNIVES"
            cv2.putText(
                frame, status_text, (12, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 120), 1, cv2.LINE_AA,
            )

    if any(a.type == "weapon_detected" and a.event == "started" for a in alerts):
        trigger_weapon_siren()

    return frame, detections, alerts


def run_video_job(job, input_path: Path, output_path: Path, confidence_threshold: float) -> None:
    """Process an entire video file for a background job, updating `job` in
    place as frames complete so `GET /infer/video/{id}` can report progress."""
    from app.core import registry  # deferred: avoids a circular import at module load

    detector = registry.yolo_detector
    if detector is None:
        raise RuntimeError("Detector not initialized — model failed to load at startup")

    tracker = ObjectTracker()

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Real fps from the source video, so alert cooldowns are wall-clock
    # accurate (e.g. "at most one zone_intrusion alert per 2 seconds")
    # rather than an arbitrary frame count.
    rule_engine = RuleEngine(RuleConfig(weapon_only_mode=settings.weapon_only_mode), fps=fps)
    job.total_frames = total_frames

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # OpenCV's own encoder writes here first; see _transcode_to_browser_compatible_mp4
    # for why this can't be the file we actually serve.
    raw_path = output_path.with_suffix(".raw.mp4")
    writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(
            f"Could not open a video writer for '{raw_path}' — the OpenCV build "
            "on this machine may be missing codec support."
        )

    frame_id = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            annotated, _detections, alerts = process_frame(
                frame, detector, tracker, rule_engine, frame_id, confidence_threshold,
            )
            writer.write(annotated)
            job.alerts.extend(alerts)

            frame_id += 1
            job.processed_frames = frame_id
            if total_frames:
                job.progress = min(frame_id / total_frames, 0.99)
    finally:
        cap.release()
        writer.release()

    if frame_id > 0:
        # Close out any incidents still open at end-of-video (e.g. the
        # intrusion was still ongoing in the last frame) so every "started"
        # alert has a matching "ended" one in the timeline.
        job.alerts.extend(rule_engine.finalize(frame_id - 1))

    _transcode_to_browser_compatible_mp4(raw_path, output_path)
    raw_path.unlink(missing_ok=True)
    job.output_path = output_path


def _transcode_to_browser_compatible_mp4(raw_path: Path, output_path: Path) -> None:
    """Re-encode to real H.264.

    `cv2.VideoWriter_fourcc(*"mp4v")` writes MPEG-4 Part 2 (fourcc 'mp4v') —
    a valid, playable video file, but not one Chrome/Firefox/Safari's native
    <video> element will decode; browsers only play H.264/AVC, VP8/9, or AV1
    inside an mp4/webm container. Without this step the job completes and the
    file downloads fine, but the frontend's <video> tag silently shows
    nothing — the bug this function fixes.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required to produce a browser-playable video but was not "
            "found on PATH. Install it (the backend Docker image already does; "
            "for local dev install ffmpeg and ensure it's on PATH)."
        )

    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_path),
            "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"ffmpeg transcode to H.264 failed: {result.stderr.strip()[:500]}")
