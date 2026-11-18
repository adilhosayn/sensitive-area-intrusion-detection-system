"""Enterprise-grade Weapon Threat Detection & Spatial Association Engine.

Features:
1. Multi-Frame Temporal Confirmation (IoU matching across frames to eliminate transient single-frame false positives).
2. Spatial Person-Weapon Association (determines if a weapon is held by an armed suspect or unattended).
3. Scale & Aspect Ratio Validation (rejects oversized full-body/background false alarms).
4. Audio Siren Triggers with non-blocking Windows hardware audio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class CandidateDetection:
    bbox: list[int]          # [x1, y1, x2, y2]
    class_name: str
    confidence: float
    hits: int = 1
    last_frame: int = 0
    confirmed: bool = False
    associated_person_id: int | None = None


def compute_iou(boxA: list[int], boxB: list[int]) -> float:
    """Computes Intersection over Union between two [x1, y1, x2, y2] boxes."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    if inter_area == 0:
        return 0.0

    boxA_area = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxB_area = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])
    union_area = float(boxA_area + boxB_area - inter_area)

    return inter_area / union_area if union_area > 0 else 0.0


class TemporalWeaponTracker:
    """Eliminates single-frame false alarms by requiring spatial consistency (IoU >= 0.25)
    across multiple consecutive evaluation frames before confirming an armed threat."""

    def __init__(self, confirmation_frames: int = 2, max_age: int = 6, iou_threshold: float = 0.25):
        self.confirmation_frames = confirmation_frames
        self.max_age = max_age
        self.iou_threshold = iou_threshold
        self._next_id: int = 1
        self._candidates: dict[int, CandidateDetection] = {}

    def update(
        self,
        raw_detections: list[tuple[list[int], float, str]],
        frame_id: int,
        frame_width: int,
        frame_height: int,
    ) -> list[CandidateDetection]:
        """
        raw_detections: list of ([x1, y1, x2, y2], confidence, class_name)
        Returns: list of confirmed CandidateDetections for this frame.
        """
        # Filter 1: Scale sanity check (a handheld weapon cannot occupy > 40% of both dimensions)
        filtered: list[tuple[list[int], float, str]] = []
        for bbox, conf, cls_name in raw_detections:
            w_frac = (bbox[2] - bbox[0]) / frame_width
            h_frac = (bbox[3] - bbox[1]) / frame_height
            if w_frac > 0.40 and h_frac > 0.40:
                continue  # reject oversized person/face artifacts
            filtered.append((bbox, conf, cls_name))

        # Match new detections against active candidates using IoU
        matched_candidates = set()
        matched_new = set()

        for cand_id, cand in list(self._candidates.items()):
            best_iou = 0.0
            best_idx = -1
            for idx, (bbox, conf, cls_name) in enumerate(filtered):
                if idx in matched_new:
                    continue
                iou = compute_iou(cand.bbox, bbox)
                if iou > best_iou and iou >= self.iou_threshold:
                    best_iou = iou
                    best_idx = idx

            if best_idx != -1:
                bbox, conf, cls_name = filtered[best_idx]
                cand.bbox = bbox
                cand.confidence = conf
                cand.class_name = cls_name
                cand.hits += 1
                cand.last_frame = frame_id
                if cand.hits >= self.confirmation_frames:
                    cand.confirmed = True
                matched_candidates.add(cand_id)
                matched_new.add(best_idx)

        # Unmatched new detections become new tentative candidates
        for idx, (bbox, conf, cls_name) in enumerate(filtered):
            if idx not in matched_new:
                cand_id = self._next_id
                self._next_id += 1
                new_cand = CandidateDetection(
                    bbox=bbox,
                    class_name=cls_name,
                    confidence=conf,
                    hits=1,
                    last_frame=frame_id,
                    confirmed=(self.confirmation_frames <= 1),
                )
                self._candidates[cand_id] = new_cand

        # Prune candidates not seen in `max_age` frames
        stale_ids = [
            cid for cid, c in self._candidates.items()
            if frame_id - c.last_frame > self.max_age
        ]
        for cid in stale_ids:
            del self._candidates[cid]

        # Return only confirmed weapons active in the current frame
        return [
            c for c in self._candidates.values()
            if c.confirmed and c.last_frame == frame_id
        ]


def associate_weapons_with_people(
    weapons: list[CandidateDetection],
    person_boxes: list[tuple[int, list[int]]],  # (track_id, [x1, y1, x2, y2])
) -> None:
    """Associates each detected weapon with the nearest or enclosing person track.
    Mutates candidate.associated_person_id in place."""
    for weapon in weapons:
        wx_center = (weapon.bbox[0] + weapon.bbox[2]) / 2.0
        wy_center = (weapon.bbox[1] + weapon.bbox[3]) / 2.0

        best_person_id = None
        min_dist = float("inf")

        for pid, pbox in person_boxes:
            # Check if weapon center is inside or near the person's bounding box
            is_inside = (pbox[0] - 25 <= wx_center <= pbox[2] + 25) and (pbox[1] - 25 <= wy_center <= pbox[3] + 25)
            if is_inside:
                best_person_id = pid
                break

            # Distance to person center
            px_center = (pbox[0] + pbox[2]) / 2.0
            py_center = (pbox[1] + pbox[3]) / 2.0
            dist = (wx_center - px_center) ** 2 + (wy_center - py_center) ** 2
            if dist < min_dist and dist < 120 ** 2:
                min_dist = dist
                best_person_id = pid

        weapon.associated_person_id = best_person_id
