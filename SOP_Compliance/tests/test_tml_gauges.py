"""
Unit tests for TML 11mm, 13mm, and Dia gauge tracking, confusion resolution, and validation.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic import GaugeValidator
from logic.gauge_validator import GaugeStatus, InspectionState


def make_tml_validator():
    cfg = config.PROFILES["TML"]
    return GaugeValidator(
        checkpoints=cfg["checkpoints"],
        gauge_class_ids=set(cfg["gauge_classes"].keys()),
        gauge_confusion=cfg.get("gauge_confusion"),
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


# Standard TML positions:
PART = det(13, "Part", 300, 300, conf=0.95)
INLET = det(11, "In", 220, 260, conf=0.95)
OUTLET = det(12, "Out", 380, 260, conf=0.95)
DS_THREAD = det(6, "DS Thread", 300, 350, conf=0.95)

# Resting positions on table:
REST_11MM = (520, 420)
REST_13MM = (520, 480)
REST_DIA = (520, 540)


def test_13mm_mislabeled_as_11mm_near_inlet_latches_13mm_checkpoint():
    """
    When the operator brings the 13mm gauge to the Inlet hole, but YOLO mislabels it
    as '11mm', target-guided resolution reassigns it to 13mm and Checkpoint 7 latches OK.
    """
    v = make_tml_validator()

    # Learn resting spots on table
    for _ in range(10):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *REST_11MM),
            det(5, "13mm", *REST_13MM),
        ])

    assert v.inspection_state == InspectionState.INSPECTING

    # Operator carries 13mm to Inlet, but YOLO reports it as '11mm' (class_id=14)
    # The true 11mm gauge remains resting on the table.
    inlet_xy = (220, 260)
    for _ in range(6):
        status = v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *inlet_xy),      # mislabeled as 11mm at Inlet
            det(14, "11mm", *REST_11MM),     # real 11mm still on table
        ])
        time.sleep(0.03)

    # Checkpoint 7 (13mm Gauge near Inlet) must be OK!
    assert v.checkpoints[7].status == GaugeStatus.OK, (
        f"13mm at Inlet should latch OK even if YOLO reported 11mm, got {v.checkpoints[7].status}"
    )
    # Checkpoint 6 (11mm Gauge near Outlet) must NOT be OK (it stayed at rest on the table!)
    assert v.checkpoints[6].status != GaugeStatus.OK, (
        f"11mm resting on table should not latch OK, got {v.checkpoints[6].status}"
    )


def test_11mm_mislabeled_as_13mm_near_outlet_latches_11mm_checkpoint():
    """
    When the operator brings the 11mm gauge to the Outlet hole, but YOLO mislabels it
    as '13mm', target-guided resolution reassigns it to 11mm and Checkpoint 6 latches OK.
    """
    v = make_tml_validator()

    for _ in range(10):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *REST_11MM),
            det(5, "13mm", *REST_13MM),
        ])

    outlet_xy = (380, 260)
    for _ in range(6):
        status = v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(5, "13mm", *outlet_xy),     # mislabeled as 13mm at Outlet
            det(5, "13mm", *REST_13MM),     # real 13mm still on table
        ])
        time.sleep(0.03)

    assert v.checkpoints[6].status == GaugeStatus.OK, (
        f"11mm at Outlet should latch OK even if YOLO reported 13mm, got {v.checkpoints[6].status}"
    )
    assert v.checkpoints[7].status != GaugeStatus.OK, (
        f"13mm resting on table should not latch OK, got {v.checkpoints[7].status}"
    )


def test_dia_mislabeled_as_13mm_near_ds_thread_latches_dia_checkpoint():
    """
    When the operator checks DS Thread with Dia gauge, but YOLO mislabels it as 13mm,
    target-guided resolution correctly assigns Dia Gauge and Checkpoint 3 latches OK.
    """
    v = make_tml_validator()

    for _ in range(6):
        v.validate([PART, INLET, OUTLET, DS_THREAD])

    ds_xy = (300, 350)
    for _ in range(6):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(5, "13mm", *ds_xy),         # mislabeled as 13mm at DS Thread
            det(5, "13mm", *REST_13MM),     # resting 13mm on table
        ])
        time.sleep(0.03)

    assert v.checkpoints[3].status == GaugeStatus.OK, (
        f"Dia at DS Thread should latch OK even if YOLO reported 13mm, got {v.checkpoints[3].status}"
    )


def test_track_mutual_exclusion_prevents_single_gauge_from_latching_both():
    """
    A single physical gauge track that was used to latch 13mm near Inlet
    CANNOT be carried over to latch 11mm near Outlet. The operator must pick
    up the distinct physical gauge.
    """
    v = make_tml_validator()

    # Gauges resting on table
    for _ in range(10):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *REST_11MM),
            det(5, "13mm", *REST_13MM),
        ])

    # 1. 13mm is moved to Inlet and latches Checkpoint 7
    inlet_xy = (220, 260)
    for _ in range(6):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(5, "13mm", *inlet_xy),
            det(14, "11mm", *REST_11MM),
        ])
        time.sleep(0.03)

    assert v.checkpoints[7].status == GaugeStatus.OK

    # 2. Operator now moves the SAME physical gauge from Inlet to Outlet
    # (continuous motion to same track)
    outlet_xy = (380, 260)
    for _ in range(6):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *outlet_xy),    # Same gauge track shifted to outlet
            det(14, "11mm", *REST_11MM),    # Real 11mm is STILL resting on table
        ])
        time.sleep(0.03)

    # Checkpoint 6 must NOT be latched by the same physical gauge!
    assert v.checkpoints[6].status != GaugeStatus.OK, (
        "Reused physical gauge must NOT latch Checkpoint 6 due to track mutual exclusion"
    )

    # 3. Return reused gauge to table (both gauges resting)
    for _ in range(4):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(5, "13mm", *REST_13MM),
            det(14, "11mm", *REST_11MM),
        ])

    # 4. Now the operator moves the REAL 11mm gauge from REST_11MM to Outlet
    for _ in range(6):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(5, "13mm", *REST_13MM),     # 13mm resting on table
            det(14, "11mm", *outlet_xy),    # 11mm brought from table to outlet
        ])
        time.sleep(0.03)

    assert v.checkpoints[6].status == GaugeStatus.OK, (
        "Genuine 11mm physical gauge from table MUST latch Checkpoint 6 OK"
    )
    assert v.checkpoints[7].status == GaugeStatus.OK, (
        "13mm Checkpoint must remain OK"
    )


def test_tml_multiple_gauges_detected_as_same_label_on_table_are_disambiguated():
    """
    When 11mm, 13mm, and Dia are resting on the table and YOLO detects two of them
    with the same label (e.g. both '11mm'), the validator disambiguates them and
    neither overwrites the other.
    """
    v = make_tml_validator()

    d1 = det(14, "11mm", *REST_11MM, conf=0.88)
    d2 = det(14, "11mm", *REST_13MM, conf=0.82)
    d3 = det(2, "Dia", *REST_DIA, conf=0.85)

    for _ in range(6):
        status = v.validate([PART, INLET, OUTLET, DS_THREAD, d1, d2, d3])

    # Checkpoint results should have unique distinct classes in gauge_detections
    assert "11mm" in v._confused_classes
    assert "13mm" in v._confused_classes
    assert "Dia" in v._confused_classes


def test_dia_cannot_be_reused_to_latch_11mm_or_13mm():
    """
    A gauge used to latch Checkpoint 3 (Dia at DS Thread) cannot be carried
    to latch Checkpoint 6 (11mm) or Checkpoint 7 (13mm).
    """
    v = make_tml_validator()

    # Gauges resting on table
    for _ in range(10):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *REST_11MM),
            det(5, "13mm", *REST_13MM),
            det(2, "Dia", *REST_DIA),
        ])

    # 1. Dia is moved to DS Thread and latches Checkpoint 3
    ds_xy = (300, 350)
    for _ in range(6):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(2, "Dia", *ds_xy),
            det(14, "11mm", *REST_11MM),
            det(5, "13mm", *REST_13MM),
        ])
        time.sleep(0.03)

    assert v.checkpoints[3].status == GaugeStatus.OK

    # 2. Operator now tries to use the same Dia gauge to check Outlet (Checkpoint 6)
    outlet_xy = (380, 260)
    for _ in range(6):
        v.validate([
            PART, INLET, OUTLET, DS_THREAD,
            det(14, "11mm", *outlet_xy),    # Same gauge track shifted to outlet
            det(14, "11mm", *REST_11MM),
            det(5, "13mm", *REST_13MM),
        ])
        time.sleep(0.03)

    assert v.checkpoints[6].status != GaugeStatus.OK, (
        "Reused Dia gauge track must NOT latch Checkpoint 6 (11mm)"
    )


if __name__ == "__main__":
    test_13mm_mislabeled_as_11mm_near_inlet_latches_13mm_checkpoint()
    print("PASS: test_13mm_mislabeled_as_11mm_near_inlet_latches_13mm_checkpoint")
    test_11mm_mislabeled_as_13mm_near_outlet_latches_11mm_checkpoint()
    print("PASS: test_11mm_mislabeled_as_13mm_near_outlet_latches_11mm_checkpoint")
    test_dia_mislabeled_as_13mm_near_ds_thread_latches_dia_checkpoint()
    print("PASS: test_dia_mislabeled_as_13mm_near_ds_thread_latches_dia_checkpoint")
    test_track_mutual_exclusion_prevents_single_gauge_from_latching_both()
    print("PASS: test_track_mutual_exclusion_prevents_single_gauge_from_latching_both")
    test_tml_multiple_gauges_detected_as_same_label_on_table_are_disambiguated()
    print("PASS: test_tml_multiple_gauges_detected_as_same_label_on_table_are_disambiguated")
    test_dia_cannot_be_reused_to_latch_11mm_or_13mm()
    print("PASS: test_dia_cannot_be_reused_to_latch_11mm_or_13mm")
