"""
Unit tests for TML Checkpoint 1 (Distance Gauge) and Checkpoint 3 (Dia Gauge).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic import GaugeValidator
from logic.gauge_validator import GaugeStatus


def make_tml_validator():
    cfg = config.PROFILES["TML"]
    return GaugeValidator(
        checkpoints=cfg["checkpoints"],
        gauge_class_ids=set(cfg["gauge_classes"].keys()),
        gauge_confusion=cfg.get("gauge_confusion"),
        overlap_threshold=config.OVERLAP_THRESHOLD,
        near_distance_threshold=config.NEAR_DISTANCE_THRESHOLD,
        ok_hold_frames=config.OK_HOLD_FRAMES,
        ok_hold_seconds=0.1,
        gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
        part_clear_time_complete=0.0,
        part_clear_time_inspecting=0.0,
    )


def test_dia_gauge_latches_ok_near_ds_thread():
    v = make_tml_validator()

    # Part arrives and transitions to INSPECTING
    part_det = {"class_name": "Part", "class_id": 13, "confidence": 0.95, "bbox": [100, 100, 500, 500]}
    ds_thread = {"class_name": "DS Thread", "class_id": 6, "confidence": 0.90, "bbox": [200, 400, 250, 450]}

    for _ in range(6):
        v.validate([part_det, ds_thread])

    assert v.inspection_state.value == "INSPECTING"
    assert v.checkpoints[3].status in (GaugeStatus.PENDING, GaugeStatus.NO_GAUGE)

    # Dia gauge is held near DS Thread (center distance ~70px, edge distance ~10px)
    dia_held = {"class_name": "Dia", "class_id": 2, "confidence": 0.85, "bbox": [210, 460, 260, 560]}

    for _ in range(5):
        v.validate([part_det, ds_thread, dia_held])
        time.sleep(0.03)

    assert v.checkpoints[3].status == GaugeStatus.OK, (
        f"Dia Gauge should latch OK near DS Thread, got {v.checkpoints[3].status}"
    )


def test_pin_and_dia_both_inside_part_only_pin_accepted_dia_suppressed():
    """
    When BOTH Pin gauge and Dia gauge are inside the part simultaneously:
    ONLY Pin gauge is accepted as checked. Dia gauge is NOT accepted.
    Dia has to be inside part WITHOUT Pin gauge to be accepted.
    """
    v = make_tml_validator()

    part_det = {"class_name": "Part", "class_id": 13, "confidence": 0.95, "bbox": [100, 100, 500, 500]}
    ds_thread = {"class_name": "DS Thread", "class_id": 6, "confidence": 0.90, "bbox": [200, 400, 250, 450]}

    for _ in range(6):
        v.validate([part_det, ds_thread])

    pin_det = {"class_name": "Pin", "class_id": 1, "confidence": 0.90, "bbox": [205, 405, 245, 445]}
    dia_det = {"class_name": "Dia", "class_id": 2, "confidence": 0.85, "bbox": [210, 410, 250, 450]}

    # Both Pin and Dia are inside the part simultaneously
    for _ in range(5):
        v.validate([part_det, ds_thread, pin_det, dia_det])
        time.sleep(0.03)

    # ONLY Pin gauge must be accepted as OK!
    assert v.checkpoints[2].status == GaugeStatus.OK, "Pin Gauge must be accepted as OK"
    # Dia gauge MUST NOT be accepted as OK while Pin gauge is also inside the part!
    assert v.checkpoints[3].status != GaugeStatus.OK, "Dia Gauge must NOT be accepted while Pin is inside"

    # Now Pin gauge is removed from part (only Dia remains near DS Thread)
    for _ in range(5):
        v.validate([part_det, ds_thread, dia_det])
        time.sleep(0.03)

    # Now Dia gauge without Pin gauge is accepted!
    assert v.checkpoints[3].status == GaugeStatus.OK, (
        "Dia Gauge must latch OK once Pin gauge is removed from the part"
    )


def test_distance_gauge_touches_part_not_ok_fully_inside_is_ok():
    """
    Distance gauge has to be fully inside the part to be checked.
    Merely touching or partially intersecting the part MUST NOT be accepted.
    """
    v = make_tml_validator()

    part_det = {"class_name": "Part", "class_id": 13, "confidence": 0.95, "bbox": [100, 100, 500, 500]}

    for _ in range(6):
        v.validate([part_det])

    assert v.checkpoints[1].status in (GaugeStatus.PENDING, GaugeStatus.NO_GAUGE)

    # Distance gauge touches / overlaps edge of part but is NOT fully inside:
    # Part is [100, 100, 500, 500], Distance gauge is [450, 200, 600, 350] (extends outside to 600)
    dist_touching = {"class_name": "Distance", "class_id": 0, "confidence": 0.90, "bbox": [450, 200, 600, 350]}

    for _ in range(5):
        v.validate([part_det, dist_touching])
        time.sleep(0.03)

    assert v.checkpoints[1].status != GaugeStatus.OK, (
        "Distance gauge touching or partially overlapping part must NOT be accepted as OK"
    )

    # Distance gauge is now FULLY inside the part ([200, 200, 350, 350])
    dist_inside = {"class_name": "Distance", "class_id": 0, "confidence": 0.90, "bbox": [200, 200, 350, 350]}

    for _ in range(5):
        v.validate([part_det, dist_inside])
        time.sleep(0.03)

    assert v.checkpoints[1].status == GaugeStatus.OK, (
        "Distance gauge must latch OK when fully inside the part"
    )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
