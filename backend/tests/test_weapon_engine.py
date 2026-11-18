import pytest
from app.core.weapon_engine import (
    CandidateDetection,
    TemporalWeaponTracker,
    associate_weapons_with_people,
    compute_iou,
)


def test_compute_iou():
    box1 = [0, 0, 100, 100]
    box2 = [0, 0, 100, 100]
    assert compute_iou(box1, box2) == 1.0

    box3 = [200, 200, 300, 300]
    assert compute_iou(box1, box3) == 0.0

    box4 = [50, 0, 150, 100]
    iou = compute_iou(box1, box4)
    assert 0.3 < iou < 0.4


def test_temporal_confirmation_requires_two_frames():
    tracker = TemporalWeaponTracker(confirmation_frames=2, iou_threshold=0.25)

    # Frame 0: First appearance -> should NOT be confirmed yet
    confirmed_f0 = tracker.update([([100, 100, 180, 180], 0.85, "gun")], frame_id=0, frame_width=640, frame_height=480)
    assert len(confirmed_f0) == 0

    # Frame 1: Same location (slight movement) -> should NOW be confirmed
    confirmed_f1 = tracker.update([([102, 101, 182, 183], 0.88, "gun")], frame_id=1, frame_width=640, frame_height=480)
    assert len(confirmed_f1) == 1
    assert confirmed_f1[0].confirmed is True
    assert confirmed_f1[0].class_name == "gun"


def test_oversized_box_rejected_as_face_or_torso():
    tracker = TemporalWeaponTracker(confirmation_frames=1)
    # A box occupying 60% of width and 60% of height (like a face/torso close to camera)
    oversized = [50, 50, 450, 350]
    res = tracker.update([(oversized, 0.90, "gun")], frame_id=0, frame_width=640, frame_height=480)
    assert len(res) == 0


def test_associate_weapons_with_people():
    weapon = CandidateDetection(bbox=[120, 150, 160, 180], class_name="knife", confidence=0.82)
    # Person box containing the weapon
    person_boxes = [(1, [100, 50, 250, 400])]
    associate_weapons_with_people([weapon], person_boxes)
    assert weapon.associated_person_id == 1

    # Far away weapon
    unattended_weapon = CandidateDetection(bbox=[500, 400, 550, 450], class_name="gun", confidence=0.91)
    associate_weapons_with_people([unattended_weapon], person_boxes)
    assert unattended_weapon.associated_person_id is None
