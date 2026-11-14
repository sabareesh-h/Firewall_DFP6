"""
Unit tests for HMI 8mm and 11mm gauge tracking, confusion resolution, and validation.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic import GaugeValidator
from logic.gauge_validator import GaugeStatus, InspectionState


def make_hmi_validator():
    cfg = config.PROFILES["HMI"]
    return GaugeValidator(
        checkpoints=cfg["checkpoints"],
        gauge_class_ids=set(cfg["gauge_classes"].keys()),
        gauge_confusion=cfg.get("gauge_confusion"),
        u_gauge_cfg=cfg.get("u_gauge_identity"),
        overlap_threshold=config.OVERLAP_THRESHOLD,
        near_distance_threshold=config.NEAR_DISTANCE_THRESHOLD,
        ok_hold_frames=config.OK_HOLD_FRAMES,
        ok_hold_seconds=0.1,  # fast dwell for unit tests
        gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
        part_clear_time_complete=0.0,
        part_clear_time_inspecting=0.0,
    )


def box(x, y, w=40, h=40):
    return [x - w // 2, y - h // 2, x + w // 2, y + h // 2]


def det(cls_id, name, x, y, conf=0.90):
    return {
        "class_id": cls_id,
        "class_name": name,
        "confidence": conf,
        "bbox": box(x, y),
    }


# Standard positions on HMI table:
# Part is on left/center:
PART = det(6, "Part", 300, 300, conf=0.95)
INLET_HOLE = det(4, "Inlet Hole", 250, 280, conf=0.95)
OUTLET_HOLE = det(5, "Outlet Hole", 350, 320, conf=0.95)

# Resting pin gauges on the table (to the right of the part):
# 8mm is upper (y=470), 11mm is lower (y=520)
REST_8MM = (500, 470)
REST_11MM = (500, 520)


def test_both_gauges_on_table_detected_as_8mm_are_disambiguated():
    """
    When both resting gauges are detected by YOLO as '8mm',
    the validator must disambiguate them so one is 8mm and the other is 11mm.
    """
    v = make_hmi_validator()

    # Both reported as 8mm on the table
    d1 = det(1, "8mm", REST_8MM[0], REST_8MM[1], conf=0.85)
    d2 = det(1, "8mm", REST_11MM[0], REST_11MM[1], conf=0.80)

    for _ in range(5):
        dets = [dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d1), dict(d2)]
        v.validate(dets)

    # Detections should have one 8mm and one 11mm
    labels = [d["class_name"] for d in dets if d["class_name"] in ("8mm", "11mm")]
    assert labels.count("8mm") == 1, "There must be exactly one 8mm gauge"
    assert labels.count("11mm") == 1, "There must be exactly one 11mm gauge"


def test_checking_8mm_does_not_falsely_latch_11mm():
    """
    When the operator checks the part using the 8mm gauge:
    - 8mm Checkpoint latches OK (green).
    - 11mm Checkpoint remains PENDING/WAITING because 11mm stayed on the table.
    """
    v = make_hmi_validator()

    # 1. Establish rest spots on table for both gauges
    d_8mm_rest = det(1, "8mm", REST_8MM[0], REST_8MM[1], conf=0.88)
    d_11mm_rest = det(0, "11mm", REST_11MM[0], REST_11MM[1], conf=0.85)

    for _ in range(8):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_rest), dict(d_11mm_rest)])

    assert v.checkpoints[1].status in (GaugeStatus.PENDING, GaugeStatus.NO_GAUGE)
    assert v.checkpoints[2].status in (GaugeStatus.PENDING, GaugeStatus.NO_GAUGE)

    # 2. Operator picks up 8mm and moves it to INLET_HOLE
    d_8mm_hole = det(1, "8mm", 250, 280, conf=0.80)

    for _ in range(6):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_hole), dict(d_11mm_rest)])
        time.sleep(0.03)

    # 8mm must be latched OK!
    assert v.checkpoints[2].status == GaugeStatus.OK, "8mm Gauge must latch OK"
    # 11mm must NOT be latched (it is still on the table)!
    assert v.checkpoints[1].status != GaugeStatus.OK, (
        f"11mm Gauge must NOT latch OK while on table! Got {v.checkpoints[1].status}"
    )


def test_flickering_label_at_hole_cannot_latch_both_checkpoints():
    """
    If the 8mm gauge is held at the hole and YOLO flickers to '11mm',
    the physical track mutual exclusion must prevent it from latching 11mm.
    """
    v = make_hmi_validator()

    # Establish resting baseline
    d_8mm_rest = det(1, "8mm", REST_8MM[0], REST_8MM[1], conf=0.88)
    d_11mm_rest = det(0, "11mm", REST_11MM[0], REST_11MM[1], conf=0.85)

    for _ in range(8):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_rest), dict(d_11mm_rest)])

    # Operator checks 8mm at the hole -> latches OK
    d_8mm_hole = det(1, "8mm", 250, 280, conf=0.80)
    for _ in range(6):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_hole), dict(d_11mm_rest)])
        time.sleep(0.03)

    assert v.checkpoints[2].status == GaugeStatus.OK

    # Now simulate label flicker: the same physical gauge at the hole is reported as 11mm
    d_flicker_11mm = det(0, "11mm", 250, 280, conf=0.80)
    for _ in range(6):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_flicker_11mm), dict(d_11mm_rest)])
        time.sleep(0.03)

    # 11mm MUST STILL NOT BE LATCHED because that track was already used for 8mm!
    assert v.checkpoints[1].status != GaugeStatus.OK, (
        "Same gauge track must NOT latch 11mm when it was already used to check 8mm!"
    )


def test_both_gauges_checked_sequentially_both_latch_ok():
    """
    Operator checks 8mm at the hole, returns it, then checks 11mm at the hole.
    Both checkpoints must latch OK (green).
    """
    v = make_hmi_validator()

    d_8mm_rest = det(1, "8mm", REST_8MM[0], REST_8MM[1], conf=0.88)
    d_11mm_rest = det(0, "11mm", REST_11MM[0], REST_11MM[1], conf=0.85)

    for _ in range(8):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_rest), dict(d_11mm_rest)])

    # 1. Check 8mm at Inlet Hole
    d_8mm_hole = det(1, "8mm", 250, 280, conf=0.85)
    for _ in range(6):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_hole), dict(d_11mm_rest)])
        time.sleep(0.03)

    assert v.checkpoints[2].status == GaugeStatus.OK, "8mm must latch OK"

    # 2. Return 8mm to rest spot
    for _ in range(4):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_rest), dict(d_11mm_rest)])

    # 3. Check 11mm at Outlet Hole
    d_11mm_hole = det(0, "11mm", 350, 320, conf=0.85)
    for _ in range(6):
        v.validate([dict(PART), dict(INLET_HOLE), dict(OUTLET_HOLE), dict(d_8mm_rest), dict(d_11mm_hole)])
        time.sleep(0.03)

    assert v.checkpoints[1].status == GaugeStatus.OK, "11mm must latch OK"
    assert v.checkpoints[2].status == GaugeStatus.OK, "8mm must remain OK"


if __name__ == "__main__":
    test_both_gauges_on_table_detected_as_8mm_are_disambiguated()
    print("PASS: test_both_gauges_on_table_detected_as_8mm_are_disambiguated")
    test_checking_8mm_does_not_falsely_latch_11mm()
    print("PASS: test_checking_8mm_does_not_falsely_latch_11mm")
    test_flickering_label_at_hole_cannot_latch_both_checkpoints()
    print("PASS: test_flickering_label_at_hole_cannot_latch_both_checkpoints")
    test_both_gauges_checked_sequentially_both_latch_ok()
    print("PASS: test_both_gauges_checked_sequentially_both_latch_ok")
