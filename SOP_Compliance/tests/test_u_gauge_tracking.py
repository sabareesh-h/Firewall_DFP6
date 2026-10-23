"""
Regression tests for the U-gauge identity tracker.

These cover the two failures seen on the live line:

1. A gauge is checked, then laid down on the table instead of being returned
   to its rack slot.  The old "which slot is empty" logic then kept calling
   that old gauge "held" and never identified the next one, so Inlet NoGo was
   never checked even when it sat in the inlet hole.

2. The model occasionally reports a U-gauge as 8mm / 11mm.  The rescue step
   may relabel it only when it is provably the same physical gauge (or it
   rests on an empty rack slot) — never just because it is near the rack.
   The real 8mm / 11mm pins sit right next to the U-gauge rack and must keep
   their own labels.

3. A hand can hide one or more U-gauges for a few seconds.  The rack does not
   move on its own and only one gauge is carried to the part, so a hidden
   gauge keeps its identity (and its checkpoint progress) instead of being
   forgotten or swapping names.  The rack may shift in the frame, but the
   four gauges always stay in top-to-bottom order.

Run from SOP_Compliance/:
    python -m pytest tests/test_u_gauge_tracking.py -v
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic import GaugeValidator


# HMI class ids
C_11MM = 0
C_8MM = 1
C_UGAUGE = 3
C_INLET = 4
C_OUTLET = 5
C_PART = 6

RACK = [(200, 250), (200, 310), (200, 370), (200, 430)]
INLET_HOLE = (430, 330)
OUTLET_HOLE = (430, 450)

HOLD = 0.05      # seconds needed at the hole before latching


def make_validator():
    cfg = config.PROFILES["HMI"]
    return GaugeValidator(
        checkpoints=cfg["checkpoints"],
        gauge_class_ids=set(cfg["gauge_classes"].keys()),
        gauge_confusion=cfg.get("gauge_confusion"),
        u_gauge_cfg=cfg.get("u_gauge_identity"),
        overlap_threshold=config.OVERLAP_THRESHOLD,
        near_distance_threshold=config.NEAR_DISTANCE_THRESHOLD,
        ok_hold_frames=config.OK_HOLD_FRAMES,
        ok_hold_seconds=HOLD,
        gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
        part_clear_time_complete=0.0,
        part_clear_time_inspecting=0.0,
    )


def box(cx, cy, size=40):
    return [cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2]


def det(class_id, name, cx, cy, conf=0.9, size=40):
    return {
        "class_id": class_id,
        "class_name": name,
        "confidence": conf,
        "bbox": box(cx, cy, size),
    }


def frame(gauges):
    """A frame with the part and both holes, plus the given U-gauges."""
    dets = [
        det(C_PART, "Part", 430, 390, size=240),
        det(C_INLET, "Inlet Hole", 430, 330, size=60),
        det(C_OUTLET, "Outlet Hole", 430, 450, size=60),
    ]
    for cx, cy in gauges:
        dets.append(det(C_UGAUGE, "U Gauge", cx, cy))
    return dets


def run(v, positions, frames=1):
    for _ in range(frames):
        v.validate(frame(positions), frame_width=1496)
        time.sleep(HOLD * 1.5)


def learn(v, frames=14):
    """All four gauges resting in the rack, long enough to learn the layout."""
    run(v, RACK, frames)
    assert v._u_gauge_tracker.slots_established


# ─────────────────────────────────────────────────────────────────────────────

def test_inlet_nogo_is_checked_after_inlet_go_is_left_on_table():
    """The exact live-line failure."""
    v = make_validator()
    learn(v)

    # Inlet Go (rank 0) is checked at the inlet ...
    run(v, RACK[1:] + [(300, 290)])
    run(v, RACK[1:] + [(360, 310)])
    run(v, RACK[1:] + [INLET_HOLE], frames=4)
    assert v.checkpoints[4].status.value == "OK", "Inlet Go should latch"

    # ... and then laid down on the table, NOT returned to the rack.
    run(v, RACK[1:] + [(350, 220)], frames=6)

    # Now Inlet NoGo (rank 1) is picked up and put in the same inlet hole.
    run(v, RACK[2:] + [(350, 220), (290, 300)])
    run(v, RACK[2:] + [(350, 220), (360, 315)])
    run(v, RACK[2:] + [(350, 220), INLET_HOLE], frames=4)

    assert v.checkpoints[5].status.value == "OK", (
        "Inlet NoGo must be identified and checked even though Inlet Go "
        "was left lying on the table"
    )


def test_identity_is_kept_across_part_sessions():
    """Gauges lying off the rack are still named when the next part starts."""
    v = make_validator()
    learn(v)

    # End of a part: Inlet Go is put down on the table, Inlet NoGo is held
    # at the inlet (moved there over a few frames, like a real operator).
    run(v, RACK[1:] + [(260, 240)])
    run(v, RACK[1:] + [(350, 220)], frames=3)
    run(v, RACK[2:] + [(350, 220), (270, 310)])
    run(v, RACK[2:] + [(350, 220), (350, 320)], frames=2)
    run(v, RACK[2:] + [(350, 220), INLET_HOLE], frames=4)
    assert v.checkpoints[5].status.value == "OK"

    # New part -> per-session reset (names must survive).
    v._reset_checkpoints()
    run(v, RACK[2:] + [(350, 220), INLET_HOLE], frames=4)

    assert v.checkpoints[5].status.value == "OK", (
        "Inlet NoGo identity must survive the start of a new part"
    )


def test_resting_gauge_does_not_latch_its_checkpoint():
    """A gauge that never left the rack can not mark its checkpoint OK."""
    v = make_validator()
    learn(v)
    run(v, RACK, frames=10)

    for cp_id in (4, 5, 6, 7):
        assert v.checkpoints[cp_id].status.value != "OK"


def test_u_gauge_mislabelled_as_8mm_is_rescued():
    """A U-gauge resting on its slot but reported as 8mm keeps its identity."""
    v = make_validator()
    learn(v)
    run(v, RACK)

    gauge_detections = {
        "8mm": [
            # one U-gauge sitting on its rest slot (lower confidence)
            det(C_8MM, "8mm", 200, 250, conf=0.55),
            # the real 8mm gauge, away from the U-gauge rack
            det(C_8MM, "8mm", 650, 200, conf=0.80),
        ],
        "U Gauge": [
            det(C_UGAUGE, "U Gauge", 200, 310),
            det(C_UGAUGE, "U Gauge", 200, 370),
            det(C_UGAUGE, "U Gauge", 200, 430),
        ],
    }

    v._rescue_u_gauges(gauge_detections)

    assert len(gauge_detections["8mm"]) == 1
    assert gauge_detections["8mm"][0]["bbox"] == box(650, 200)
    assert len(gauge_detections["U Gauge"]) == 4


def _carry_to_inlet(v, frames=4):
    """
    Carry rank 0 (Inlet Go) to the inlet hole while the model calls it 8mm.

    The real 8mm and 11mm pins stay on the table, as in the live failure.
    """
    for p in [(260, 300), (330, 315), (390, 322)] + [INLET_HOLE] * frames:
        dets = frame(RACK[1:])
        dets.append(det(C_8MM, "8mm", p[0], p[1], conf=0.55))
        dets.append(det(C_8MM, "8mm", 650, 200, conf=0.92))
        dets.append(det(C_11MM, "11mm", 760, 200, conf=0.93))
        v.validate(dets, frame_width=1496)
        time.sleep(HOLD * 1.5)


def test_u_gauge_mislabelled_as_8mm_at_the_part_is_rescued():
    """The live failure: Inlet Go taken to the inlet, reported as 8mm."""
    v = make_validator()
    learn(v)

    _carry_to_inlet(v)

    assert v.checkpoints[4].status.value == "OK", (
        "the gauge at the inlet must be recognised as rank 0 even though the "
        "model called it 8mm"
    )
    # The real 8mm pin never moved, so its checkpoint must not latch.
    assert v.checkpoints[2].status.value != "OK"


def test_extra_8mm_at_part_is_not_rescued_when_all_u_gauges_are_in_rack():
    """
    With all four U-gauges on the rack, an extra 8mm near the part is the
    other pin (8mm/11mm confusion), never a U-gauge.
    """
    v = make_validator()
    learn(v)
    run(v, RACK)

    dets = frame(RACK)
    dets.append(det(C_8MM, "8mm", 650, 200, conf=0.92))
    dets.append(det(C_8MM, "8mm", INLET_HOLE[0], INLET_HOLE[1], conf=0.55))
    dets.append(det(C_11MM, "11mm", 760, 200, conf=0.93))
    v.validate(dets, frame_width=1496)

    labels = [d["class_name"] for d in dets]
    assert labels.count("U Gauge") == 4
    assert any(
        d["class_name"] == "8mm" and d["bbox"] == box(650, 200) for d in dets
    )


def test_pins_are_not_rescued_when_a_u_gauge_is_missed():
    """
    The live-line regression: one U-gauge hidden by a hand must not turn the
    nearest 8mm / 11mm pin into a U-gauge.  The pins rest right next to the
    U-gauge rack on this fixture.
    """
    v = make_validator()
    learn(v)
    run(v, RACK)

    # Rank-0 gauge is hidden this frame; only three U boxes are detected.
    dets = frame(RACK[1:])
    dets.append(det(C_8MM, "8mm", 250, 470, conf=0.90))
    dets.append(det(C_11MM, "11mm", 300, 500, conf=0.90))
    v.validate(dets, frame_width=1496)

    labels = [d["class_name"] for d in dets]
    assert labels.count("8mm") == 1, "the real 8mm pin must stay 8mm"
    assert labels.count("11mm") == 1, "the real 11mm pin must stay 11mm"
    assert labels.count("U Gauge") == 3, "no pin may become a U-gauge"


def test_pins_resting_next_to_the_rack_keep_their_labels():
    """Pins a few centimetres from the rack are not U-gauges."""
    v = make_validator()
    learn(v)

    dets = frame(RACK)
    dets.append(det(C_8MM, "8mm", 230, 455, conf=0.90))   # ~39 px from rank 3
    dets.append(det(C_11MM, "11mm", 320, 480, conf=0.90))
    for _ in range(6):
        v.validate(dets, frame_width=1496)

    labels = [d["class_name"] for d in dets]
    assert labels.count("8mm") == 1
    assert labels.count("11mm") == 1
    assert labels.count("U Gauge") == 4


def test_duplicate_8mm_boxes_are_dropped():
    """Two boxes on the same physical gauge are not two gauges."""
    v = make_validator()
    learn(v)

    gauge_detections = {
        "8mm": [
            det(C_8MM, "8mm", 650, 200, conf=0.80),
            det(C_8MM, "8mm", 655, 205, conf=0.30),
        ],
    }

    v._rescue_u_gauges(gauge_detections)

    assert len(gauge_detections["8mm"]) == 1
    assert "U Gauge" not in gauge_detections


def test_nearest_away_gauge_wins_when_two_slots_are_empty():
    """
    If two slots are empty but one gauge was seen moving, that moving gauge
    is the one at the part (the other slot is only hidden by the hand).
    """
    v = make_validator()
    learn(v)
    run(v, RACK)

    tracker = v._u_gauge_tracker
    for track in tracker._tracks:
        if track.get("rank") == 2:
            track["pos"] = (380.0, 320.0)   # rank 2 was carried towards the part
    tracker._update_activity()
    assert tracker._active_rank == 2

    gauge_detections = {
        # Ranks 1 and 3 are still on the rack; ranks 0 and 2 are empty.
        "U Gauge": [
            det(C_UGAUGE, "U Gauge", 200, 310),
            det(C_UGAUGE, "U Gauge", 200, 430),
        ],
        "8mm": [
            det(C_8MM, "8mm", 400, 325, conf=0.55),
            det(C_8MM, "8mm", 650, 200, conf=0.92),
        ],
    }

    v._rescue_u_gauges(gauge_detections, [box(430, 330)])

    assert len(gauge_detections.get("U Gauge", [])) == 3
    assert len(gauge_detections["8mm"]) == 1
    assert tracker.track_for_rank(2)["pos"] == (400.0, 325.0)


def test_multiple_empty_slots_without_a_moved_gauge_are_not_guessed():
    """Empty slots caused by a hand must not swap identities."""
    v = make_validator()
    learn(v)
    run(v, RACK)

    gauge_detections = {
        # Ranks 1 and 3 visible; 0 and 2 are hidden by the hand.
        "U Gauge": [
            det(C_UGAUGE, "U Gauge", 200, 310),
            det(C_UGAUGE, "U Gauge", 200, 430),
        ],
        "8mm": [
            det(C_8MM, "8mm", INLET_HOLE[0], INLET_HOLE[1], conf=0.55),
            det(C_8MM, "8mm", 650, 200, conf=0.92),
        ],
    }

    v._rescue_u_gauges(gauge_detections, [box(430, 330)])

    assert len(gauge_detections.get("U Gauge", [])) == 2
    assert len(gauge_detections["8mm"]) == 2


def test_u_gauge_at_part_is_recovered_after_its_track_timed_out():
    """
    A gauge mislabelled from the moment it was picked up can be away long
    enough for its track to time out.  The empty slot still identifies it.
    """
    v = make_validator()
    learn(v)
    run(v, RACK)

    tracker = v._u_gauge_tracker
    tracker.occlusion_hold_seconds = 0.0   # force the old frame timeout
    rack_without_rank0 = [
        d for d in frame(RACK[1:]) if d["class_name"] == "U Gauge"
    ]
    for _ in range(tracker.TRACK_MAX_MISSES + 2):
        tracker.update(rack_without_rank0)
    assert tracker.track_for_rank(0) is None
    tracker.occlusion_hold_seconds = 3.0

    gauge_detections = {
        "U Gauge": list(rack_without_rank0),
        "8mm": [
            det(C_8MM, "8mm", INLET_HOLE[0], INLET_HOLE[1], conf=0.55),
            det(C_8MM, "8mm", 650, 200, conf=0.92),
        ],
    }
    v._rescue_u_gauges(gauge_detections, [box(430, 330)])

    assert len(gauge_detections.get("U Gauge", [])) == 4
    assert len(gauge_detections["8mm"]) == 1
    assert gauge_detections["8mm"][0]["bbox"] == box(650, 200)
    assert tracker.track_for_rank(0) is not None


def test_hidden_rack_gauge_keeps_its_identity_for_a_few_seconds():
    """A hand over one rack gauge must not release its name."""
    v = make_validator()
    learn(v)
    run(v, RACK)

    tracker = v._u_gauge_tracker
    # Rank 1 is covered for a moment; the other three are still visible.
    run(v, RACK[:1] + RACK[2:], frames=4)

    assert tracker.track_for_rank(1) is None
    assert tracker.is_occluded(1)

    # It reappears in its own slot and still has its own name.
    run(v, RACK, frames=2)
    track = tracker.track_for_rank(1)
    assert track is not None
    assert track["rank"] == 1


def test_hidden_rack_gauge_cannot_jump_to_the_part():
    """A stale rack track may only come back at its own slot."""
    v = make_validator()
    learn(v)
    run(v, RACK)

    tracker = v._u_gauge_tracker
    ti = next(
        i for i, t in enumerate(tracker._tracks) if t.get("rank") == 2
    )
    tracker._tracks[ti]["misses"] = 5
    part = (430.0, 330.0)

    assert tracker._relink_allowed(ti, part) is False
    tracker.mark_active(2)
    assert tracker._relink_allowed(ti, part) is True


def test_checkpoint_progress_survives_the_hand_covering_the_gauge():
    """The hand hides the gauge at the hole: keep the dwell progress."""
    v = make_validator()
    v.ok_hold_seconds = 1.0          # long enough to observe partial progress
    learn(v)
    run(v, RACK)

    # Carry rank 0 to the inlet (still reported as a U-gauge).
    run(v, RACK[1:] + [INLET_HOLE], frames=2)
    assert v.checkpoints[4].ok_first_seen > 0.0
    assert v.checkpoints[4].status.value == "UNCERTAIN"

    # The hand covers it: no box for rank 0, but the gauge has not moved.
    for _ in range(3):
        v.validate(frame(RACK[1:]), frame_width=1496)
        time.sleep(0.08)

    assert v.checkpoints[4].status.value == "WAITING"
    assert v.checkpoints[4].ok_first_seen > 0.0, "progress was thrown away"

    # It is visible again and finishes the dwell.
    for _ in range(3):
        v.validate(frame(RACK[1:] + [INLET_HOLE]), frame_width=1496)
        time.sleep(0.35)

    assert v.checkpoints[4].status.value == "OK"


def test_rack_memory_follows_a_shifted_rack_in_top_to_bottom_order():
    """The rack may move, but rank 0 stays top and rank 3 stays bottom."""
    v = make_validator()
    learn(v)
    run(v, RACK)

    shift = (60, 40)
    moved = [(x + shift[0], y + shift[1]) for x, y in RACK]
    run(v, moved, frames=12)

    tracker = v._u_gauge_tracker
    slots = [tuple(tracker._slots[r]["pos"]) for r in range(4)]
    for rank, (sx, sy) in enumerate(slots):
        assert abs(sx - moved[rank][0]) <= 12
        assert abs(sy - moved[rank][1]) <= 12
    assert [p[1] for p in slots] == sorted(p[1] for p in slots)
    for rank in range(4):
        assert tracker.track_for_rank(rank)["rank"] == rank


def test_inlet_nogo_latches_when_gauge_is_returned_to_rack():
    """Sanity: the normal sequence (gauge returned to rack) still works."""
    v = make_validator()
    learn(v)

    run(v, RACK[1:] + [(300, 290)])
    run(v, RACK[1:] + [(360, 310)])
    run(v, RACK[1:] + [INLET_HOLE], frames=4)
    run(v, RACK, frames=4)

    run(v, [RACK[0]] + RACK[2:] + [(290, 310)])
    run(v, [RACK[0]] + RACK[2:] + [(360, 325)])
    run(v, [RACK[0]] + RACK[2:] + [INLET_HOLE], frames=4)

    assert v.checkpoints[4].status.value == "OK"
    assert v.checkpoints[5].status.value == "OK"


def test_fast_pickup_does_not_steal_a_neighbours_slot():
    """A gauge picked up in one frame must not land on a neighbour's slot."""
    v = make_validator()
    learn(v)

    # Rank 0 leaves its (now empty) slot and is already at the inlet.  The
    # other three boxes are still on their slots.  Rank 0 must follow the
    # gauge to the inlet instead of matching a neighbour's box.
    run(v, [RACK[1], RACK[2], RACK[3], INLET_HOLE], frames=3)

    tracker = v._u_gauge_tracker
    rank0 = tracker.track_for_rank(0)
    assert rank0 is not None
    assert tracker._dist(rank0["pos"], INLET_HOLE) < 25 * tracker.scale
    for rank in (1, 2, 3):
        track = tracker.track_for_rank(rank)
        assert track is not None
        assert tracker._dist(track["pos"], RACK[rank]) < 30 * tracker.scale


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
