"""
Tests for the supervisor bypass.

Covers the validator behaviour (all gauges OK without detections, log marked
as bypassed) and the /bypass endpoint (password required to enable, disable
always allowed, never persisted).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic import GaugeValidator


def make_validator(profile="TML"):
    cfg = config.PROFILES[profile]
    return GaugeValidator(
        checkpoints=cfg["checkpoints"],
        gauge_class_ids=set(cfg["gauge_classes"].keys()),
        gauge_confusion=cfg.get("gauge_confusion"),
        u_gauge_cfg=cfg.get("u_gauge_identity"),
        overlap_threshold=config.OVERLAP_THRESHOLD,
        near_distance_threshold=config.NEAR_DISTANCE_THRESHOLD,
        ok_hold_frames=config.OK_HOLD_FRAMES,
        ok_hold_seconds=config.OK_HOLD_SECONDS,
        gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
        part_clear_time_complete=0.0,
        part_clear_time_inspecting=0.0,
    )


def part_frame():
    return [{"class_name": "Part", "class_id": 13, "confidence": 0.9,
             "bbox": [100, 100, 500, 500]}]


def test_bypass_marks_all_gauges_ok_without_detections():
    v = make_validator("TML")
    v.set_bypass(True)

    status = None
    for _ in range(6):                     # 5 frames to confirm part arrival
        status = v.validate(part_frame())

    assert status["inspection_state"] == "COMPLETE"
    assert status["overall_status"] == "OK"
    assert all(g["status"] == "OK" for g in status["gauges"].values())
    assert status["completed"] == status["total"]


def test_bypass_log_entry_is_marked():
    v = make_validator("TML")
    v.set_bypass(True)
    for _ in range(6):
        v.validate(part_frame())
    v.validate([])                          # part removed -> log written

    assert v.recent_logs, "expected a log entry after part removal"
    assert v.recent_logs[-1].result == "OK"
    assert v.recent_logs[-1].bypass is True


def test_bypass_off_does_not_mark_ok():
    v = make_validator("TML")
    v.set_bypass(False)
    status = None
    for _ in range(6):
        status = v.validate(part_frame())

    assert status["inspection_state"] == "INSPECTING"
    assert any(g["status"] != "OK" for g in status["gauges"].values())


def test_force_bypass_complete_from_idle():
    v = make_validator("TML")
    v.set_bypass(True)
    v.force_bypass_complete()

    assert v.inspection_state.value == "COMPLETE"
    assert all(cp.status.value == "OK" for cp in v.checkpoints.values())
    assert v.scanned_part_no is None


def test_bypass_endpoint_requires_password():
    import asyncio
    import app as app_module

    app_module.bypass_active = False

    res = asyncio.run(app_module.set_bypass(
        app_module.BypassRequest(enabled=True, password="wrong")))
    assert res.status_code == 401
    assert app_module.bypass_active is False

    res = asyncio.run(app_module.set_bypass(
        app_module.BypassRequest(enabled=True)))
    assert res.status_code == 401
    assert app_module.bypass_active is False


def test_bypass_endpoint_enable_and_disable():
    import asyncio
    import app as app_module

    res = asyncio.run(app_module.set_bypass(
        app_module.BypassRequest(enabled=True, password=config.ADMIN_PASSWORD)))
    assert res.status_code == 200
    assert app_module.bypass_active is True

    res = asyncio.run(app_module.set_bypass(
        app_module.BypassRequest(enabled=False)))
    assert res.status_code == 200
    assert app_module.bypass_active is False


def test_scan_under_bypass_closes_part_and_ignores_repeat():
    import app as app_module

    class FakeValidator:
        def __init__(self):
            self.inspection_state = "IDLE"
            self.forced = 0
            self.part_no = None

        def set_part_no(self, code, restore_memory=True):
            self.part_no = code

        def force_bypass_complete(self):
            self.forced += 1
            self.inspection_state = "INSPECTING"

        def set_bypass(self, active):
            pass

        def reset(self):
            pass

    fake = FakeValidator()
    saved = (app_module.validators, app_module.active_profile,
             app_module.bypass_active, app_module.pending_profile,
             app_module.scan_latch_active)

    try:
        app_module.validators = {"TML": fake}
        app_module.active_profile = "TML"
        app_module.bypass_active = True
        app_module.pending_profile = None
        app_module.scan_latch_active = False

        app_module._handle_scan_code("0057240710010501D645321026004242")
        assert fake.forced == 1
        assert fake.part_no == "0057240710010501D645321026004242"

        # Same part, second scan → first one wins.
        app_module._handle_scan_code("0057240710010501D645321026004501")
        assert fake.forced == 1
    finally:
        (app_module.validators, app_module.active_profile,
         app_module.bypass_active, app_module.pending_profile,
         app_module.scan_latch_active) = saved


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
