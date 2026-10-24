"""
Gauge Validator — SOP business logic.

KEY DESIGN PRINCIPLE:
    One TML Part on the table = one inspection session.

    State machine:
        IDLE       → TML Part appears          → INSPECTING
        INSPECTING → all gauges latched OK     → COMPLETE (auto-log PASS)
        INSPECTING → explicit NG detected      → shows NG (operator must fix)
        INSPECTING → TML Part removed (45f)   → auto-log + reset → IDLE
        COMPLETE   → TML Part removed          → auto-log + reset → IDLE

    Gauge latch logic (the critical fix):
        - When gauge+area spatial check passes for OK_HOLD_FRAMES consecutive
          frames → status latches to OK and STAYS OK forever (until reset).
        - When gauge disappears from frame (operator moves it to next check),
          we preserve the ok_count for GAUGE_GRACE_FRAMES before clearing.
        - This means the operator does NOT need to hold the gauge perfectly
          still for N frames; they just need a brief correct position.
        - Once latched, no further detection of that gauge is needed.
"""

import logging
import time
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Status Enums ────────────────────────────────────────────────────────────

class GaugeStatus(str, Enum):
    """Per-checkpoint status."""
    PENDING    = "PENDING"     # Not yet checked in this session
    WAITING    = "WAITING"     # Area/gauge not in frame right now
    UNCERTAIN  = "UNCERTAIN"   # Gauge seen at correct spot, accumulating frames
    OK         = "OK"          # Latched — confirmed correct (stays until reset)
    NG         = "NG"          # Gauge seen at WRONG position
    NO_GAUGE   = "NO_GAUGE"    # Area visible but gauge not present
    NO_AREA    = "NO_AREA"     # Part area not detected in frame


class InspectionState(str, Enum):
    """Overall session state (driven by TML Part presence)."""
    IDLE        = "IDLE"        # No part on table
    INSPECTING  = "INSPECTING"  # Part present, checks in progress
    COMPLETE    = "COMPLETE"    # All gauges OK — pass confirmed


class OverallStatus(str, Enum):
    """Reported overall status (for UI)."""
    OK          = "OK"
    NG          = "NG"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING     = "WAITING"


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class CheckpointResult:
    """Runtime state for a single gauge checkpoint."""
    checkpoint_id: int
    name: str
    description: str
    status: GaugeStatus = GaugeStatus.PENDING
    confidence: float = 0.0
    overlap: float = 0.0
    ok_count: int = 0           # consecutive OK frames (fallback)
    grace_count: int = 0        # frames since gauge last disappeared
    spatial_miss_count: int = 0 # consecutive visible-but-wrong frames
    ok_first_seen: float = 0.0  # time.time() when gauge first became valid (0 = not started)
    dwell_progress: float = 0.0 # 0.0 to 1.0 — how far towards 1s dwell we are


@dataclass
class InspectionLog:
    """One completed inspection record."""
    log_id: int
    timestamp: str
    part_id: str
    result: str                 # "OK" or "Not checked ..."
    cycle_time: str
    bypass: bool = False        # result produced while supervisor bypass was ON


# --- U-Gauge Identity Tracker ---

class UGaugeIdentityTracker:
    """
    Follows the four physically-identical U-gauges across frames.

    Identity is bound to the *physical gauge* (a track), not to "which rack
    slot is empty".  Rest slots are used only once, to name the gauges; after
    that a gauge keeps its name (Inlet Go / Inlet NoGo / LP Go / LP NoGo)
    while it is carried, checked and after it is put down anywhere on the
    table.

    Why this matters
    ----------------
    The old implementation decided identity by elimination: "rank 1 must be
    the gauge in hand because rack slot 1 is empty".  That only works when
    every gauge is returned to its exact slot after use.  In production a
    gauge is normally laid down next to the part, so its slot stays empty,
    the tracker keeps calling that old gauge "held", and the next gauge is
    never identified.  Checkpoints then silently stay unchecked.

    How identity is kept now
    ------------------------
    * Every frame, detections are matched one-to-one to the previous frame's
      tracks by nearest position (greedy, smallest distance first).
    * A gauge that jumps further than the normal radius is re-linked to its
      track, but only when the pairing is unambiguous (mutual nearest).
    * A box the model reports as 8mm / 11mm is handed back to a U-gauge track
      that has no box this frame (label flicker), or re-labelled by the
      highest-confidence rule.
    * A named track that is briefly occluded stays alive for
      `occlusion_hold_seconds` (3 s), so its name survives a hand or an arm
      passing over the rack.  This applies to every named gauge, not only the
      one that is currently being used.
    * A track is named once, while it rests on a learned rack slot (or, if
      only one rank is left, by elimination).  The name is sticky: it is
      never taken away because the gauge was put down.
    * Ranks are never shared by two visible gauges.  A lost track releases
      its rank so the gauge that is actually present can take it back.
    """

    MIN_STABLE_FRAMES = 8
    STABLE_PX = 20.0            # max wobble to call a gauge "still"
    MATCH_DIST_PX = 40.0        # rack slot <-> gauge bind radius
    RACK_BIND_PX = 60.0         # rescue radius for a mislabelled gauge
    LEARNING_MAX_SPREAD_PX = 250.0
    CHECK_AREA_MARGIN_PX = 60.0
    TRACK_MATCH_PX = 200.0      # max movement between two frames
    TRACK_MISS_STEP_PX = 45.0   # extra radius per missed frame
    TRACK_MAX_MISSES = 45       # ~1.5 s at 30 fps, longer at low fps
    RELINK_PX = 420.0           # recovery radius for an unambiguous jump
    RELINK_MAX_MISSES = 12      # only re-link a recently seen track
    TRACK_HISTORY = 6
    DEDUPE_PX = 15.0            # two boxes closer than this = one gauge
    REFERENCE_WIDTH = 1280.0    # pixel thresholds are tuned for this width
    OCCLUSION_HOLD_SECONDS = 3.0  # remember a hidden gauge for a few seconds
    SLOT_REFRESH_PX = 250.0     # all four at rest -> follow a shifted rack

    def __init__(
        self,
        checkpoint_ids: List[int],
        gauge_class: str = "U Gauge",
        match_distance: Optional[float] = None,
        min_stable_frames: Optional[int] = None,
        stable_px: Optional[float] = None,
        learning_max_spread: Optional[float] = None,
        occlusion_hold_seconds: Optional[float] = None,
        dedupe_px: Optional[float] = None,
    ):
        assert len(checkpoint_ids) == 4, "UGaugeIdentityTracker needs exactly 4 IDs"
        self.checkpoint_ids = list(checkpoint_ids)
        self.gauge_class = gauge_class

        self.match_distance = float(
            match_distance if match_distance is not None else self.MATCH_DIST_PX
        )
        self.min_stable_frames = int(
            min_stable_frames if min_stable_frames is not None
            else self.MIN_STABLE_FRAMES
        )
        self.stable_px = float(
            stable_px if stable_px is not None else self.STABLE_PX
        )
        self.learning_max_spread = float(
            learning_max_spread if learning_max_spread is not None
            else self.LEARNING_MAX_SPREAD_PX
        )
        self.occlusion_hold_seconds = float(
            occlusion_hold_seconds if occlusion_hold_seconds is not None
            else self.OCCLUSION_HOLD_SECONDS
        )
        self.dedupe_px = float(
            dedupe_px if dedupe_px is not None else self.DEDUPE_PX
        )

        # Pixel thresholds are expressed for a 1280 px wide frame.  Live and
        # recorded sources can have different widths (live is pre-scaled to
        # LIVE_IMGSZ), so every distance is multiplied by this factor.
        self.scale: float = 1.0

        self._slots: List[Optional[Dict[str, Any]]] = [None, None, None, None]
        self._slots_established: bool = False
        self._slot_last_seen: Dict[int, float] = {}
        self._learn_history: List[List[Tuple[float, float]]] = []
        self._waiting_logged: bool = False

        self._tracks: List[Dict[str, Any]] = []
        self._next_track_id: int = 1
        self._frame: int = 0
        self._last_u_positions: List[Tuple[float, float]] = []
        self._check_areas: List[List[int]] = []

        # The one gauge that is currently away from the rack (in the hand).
        # All other gauges are locked to their slots, even if the hand hides
        # them for a moment.
        self._active_rank: Optional[int] = None
        self._active_since: float = 0.0
        self._occupied_slots: Set[int] = set()

        # Per-frame map: id(detection dict) -> resting rank (0-3).
        # Used to label each "U Gauge" box with its real name.
        self._det_rank: Dict[int, Optional[int]] = {}

        # Detections of the frame being processed (used by the fallback).
        self._current_dets: List[Dict[str, Any]] = []

    # -- Public API ----------------------------------------------------------

    def reset(self) -> None:
        """Full reset: forget tracks, names and the learned rest layout."""
        self._slots = [None, None, None, None]
        self._slots_established = False
        self._slot_last_seen = {}
        self._learn_history = []
        self._tracks = []
        self._next_track_id = 1
        self._frame = 0
        self._last_u_positions = []
        self._check_areas = []
        self._det_rank = {}
        self._current_dets = []
        self._waiting_logged = False
        self._active_rank = None
        self._active_since = 0.0
        self._occupied_slots = set()
        logger.debug("[UGaugeTracker] full reset.")

    def reset_tracking(self) -> None:
        """
        Start a new part session.

        Track names are deliberately kept: the physical gauges are still on
        the table with the identity they were given, even if they are lying
        next to the part instead of being back in the rack.
        """
        self._det_rank = {}
        logger.debug("[UGaugeTracker] tracking reset (names kept).")

    def set_frame_width(self, width: Optional[int]) -> None:
        if not width or width <= 0:
            return
        self.scale = max(0.5, min(2.0, float(width) / self.REFERENCE_WIDTH))

    def rank_map(self) -> Dict[int, int]:
        """Return this frame's mapping of id(detection) -> resting rank."""
        return {
            det_id: rank
            for det_id, rank in self._det_rank.items()
            if rank is not None
        }

    def checkpoint_id_for_rank(self, rank: Optional[int]) -> Optional[int]:
        if rank is not None and 0 <= rank < len(self.checkpoint_ids):
            return self.checkpoint_ids[rank]
        return None

    def track_for_rank(self, rank: int) -> Optional[Dict[str, Any]]:
        """Live track (visible this frame) carrying this rank, if any."""
        for track in self._tracks:
            if track.get("rank") == rank and track.get("misses", 0) == 0:
                return dict(track)
        return None

    def rest_position_for_rank(self, rank: int) -> Optional[Tuple[float, float]]:
        """Where this rank's gauge normally rests (slot, or where it was named)."""
        for track in self._tracks:
            if track.get("rank") == rank and track.get("rest_pos") is not None:
                return tuple(track["rest_pos"])
        if 0 <= rank < len(self._slots) and self._slots[rank] is not None:
            return tuple(self._slots[rank]["pos"])
        return None

    def current_detections(self) -> List[Dict[str, Any]]:
        return list(self._current_dets)

    def held_rank(self) -> Optional[int]:
        """Rank of the gauge currently sitting on an Inlet/Outlet area."""
        for track in self._tracks:
            if track.get("misses", 0) != 0:
                continue
            if self._point_near_check_area(track["pos"], self._check_areas):
                return track.get("rank")
        return None

    def held_bbox(self) -> Optional[List[int]]:
        for track in self._tracks:
            if track.get("misses", 0) != 0:
                continue
            if self._point_near_check_area(track["pos"], self._check_areas):
                return track.get("bbox")
        return None

    @property
    def slots_established(self) -> bool:
        return self._slots_established

    def rest_slot_positions(self) -> List[Tuple[float, float]]:
        return [
            tuple(slot["pos"]) for slot in self._slots if slot is not None
        ]

    def free_rest_slots(
        self,
        occupied_positions: List[Tuple[float, float]],
        radius: Optional[float] = None,
    ) -> List[Tuple[float, float]]:
        """Rest slots that have no gauge detection sitting on them."""
        radius = self.RACK_BIND_PX * self.scale if radius is None else radius
        free: List[Tuple[float, float]] = []
        for slot in self._slots:
            if slot is None:
                continue
            pos = tuple(slot["pos"])
            if any(self._dist(pos, other) <= radius for other in occupied_positions):
                continue
            free.append(pos)
        return free

    def last_gauge_positions(self) -> List[Tuple[float, float]]:
        """Where a U-gauge was seen in the previous processed frame."""
        return list(self._last_u_positions)

    def is_slot_occluded(self, rank: int, now: Optional[float] = None) -> bool:
        """
        True when this rack slot has no visible gauge, but was occupied within
        the occlusion hold cooldown (3.0s). The gauge position is held in memory
        so hand occlusion does not trigger false pickup detection.
        """
        if not self._slots_established or rank not in range(len(self._slots)):
            return False
        if rank in self._occupied_slots:
            return False
        if now is None:
            now = time.monotonic()
        last_seen = self._slot_last_seen.get(rank, 0.0)
        return (now - last_seen) <= self.occlusion_hold_seconds

    def is_slot_missing(self, rank: int, now: Optional[float] = None) -> bool:
        """
        True when this slot has been continuously absent for longer than the
        occlusion hold cooldown (3.0s), confirming the gauge was truly removed.
        """
        if not self._slots_established or rank not in range(len(self._slots)):
            return False
        if rank in self._occupied_slots:
            return False
        if now is None:
            now = time.monotonic()
        last_seen = self._slot_last_seen.get(rank, 0.0)
        return (now - last_seen) > self.occlusion_hold_seconds

    def _is_track_at_slot(self, track: Dict[str, Any], rank: int) -> bool:
        """True when a track's last known position is at its rack slot."""
        if 0 <= rank < len(self._slots) and self._slots[rank] is not None:
            return self._dist(track["pos"], tuple(self._slots[rank]["pos"])) <= self.RACK_BIND_PX * self.scale
        return False

    def away_ranks(
        self,
        occupied_positions: List[Tuple[float, float]],
        radius: float,
    ) -> List[int]:
        """
        Ranks whose gauge is actually away from the rack.

        Only the gauge that was seen moving (or is at a hole) can be away.
        A slot that is merely empty because a hand covers it is not "away".
        When several slots are empty and no active gauge is known, the answer
        is deliberately empty: guessing would swap identities.
        """
        if not self._slots_established:
            return []

        if self._active_rank is not None:
            track = self._track_with_rank(self._active_rank)
            if track is None:
                self._active_rank = None
            else:
                slot = self._slots[self._active_rank]
                # A gauge that is back on its slot is no longer "away"; a
                # stale active flag must not recreate a duplicate identity.
                if (
                    track.get("misses", 0) == 0
                    and slot is not None
                    and self._dist(track["pos"], tuple(slot["pos"]))
                    <= self.RACK_BIND_PX * self.scale
                    and self._track_is_still(track)
                ):
                    self._active_rank = None
                else:
                    return [self._active_rank]

        missing: List[int] = []
        now_mono = time.monotonic()
        for rank, slot in enumerate(self._slots):
            if slot is None:
                continue
            slot_pos = tuple(slot["pos"])
            if any(
                self._dist(slot_pos, pos) <= radius
                for pos in occupied_positions
            ):
                continue
            missing.append(rank)

        # Exactly one empty slot: the operator took that gauge.
        if len(missing) == 1:
            return missing

        # Multiple empty slots: the hand is covering adjacent gauges.
        # Hold on to slots that are resting under occlusion memory for 3.0s.
        truly_missing = [
            r for r in missing
            if not self.is_slot_occluded(r, now_mono)
        ]
        return truly_missing if len(truly_missing) == 1 else []

    def adopt_away_gauge(
        self,
        bbox: List[int],
        occupied_positions: List[Tuple[float, float]],
        away_ranks: List[int],
        prefer_rank: Optional[int] = None,
    ) -> Optional[int]:
        """
        Bind a box reported as another class to the U-gauge that is away from
        the rack.

        Only tracks with no current U-Gauge box are eligible.  If one gauge is
        away (the normal workflow) there is nothing to choose.  If more than
        one is away, `prefer_rank` wins when given; otherwise the gauge whose
        last known position is nearest the box is used, and that rank is
        returned.  On success the track is moved onto the box, so the next
        update matches it normally.
        """
        if not away_ranks:
            return None

        candidates = [
            track
            for track in self._unrepresented_tracks(occupied_positions)
            if track.get("rank") in away_ranks
        ]
        if not candidates:
            # The gauge was away long enough for its track to time out.  With
            # exactly one empty slot there is still no ambiguity: recreate
            # that rank's track on the box so the checkpoint can latch.
            if len(away_ranks) != 1:
                return None
            rank = away_ranks[0]
            pos = self._center(bbox)
            slot = self._slots[rank] if rank < len(self._slots) else None
            # Never leave two tracks holding the same rank.
            for other in self._tracks:
                if other.get("rank") == rank:
                    other["rank"] = None
                    other["rest_pos"] = None
            self._tracks.append({
                "id": self._next_track_id,
                "pos": pos,
                "bbox": bbox,
                "rank": rank,
                "rest_pos": tuple(slot["pos"]) if slot is not None else None,
                "history": [pos],
                "misses": 0,
                "last_seen": self._frame,
                "last_seen_time": time.monotonic(),
            })
            self._next_track_id += 1
            logger.info(
                "[UGaugeTracker] Recreated track for away rank-%d.", rank
            )
            return rank

        if prefer_rank is not None:
            preferred = [
                track for track in candidates
                if track.get("rank") == prefer_rank
            ]
            if preferred:
                candidates = preferred

        pos = self._center(bbox)
        best = min(candidates, key=lambda track: self._dist(pos, track["pos"]))
        best["pos"] = pos
        best["bbox"] = bbox
        return best.get("rank")

    def _unrepresented_tracks(
        self, occupied_positions: List[Tuple[float, float]]
    ) -> List[Dict[str, Any]]:
        """
        Tracks that no current U-Gauge box explains.

        Boxes are assigned to tracks greedily (nearest first), one box per
        track, so a box that clearly belongs to a neighbouring gauge does not
        keep another track "occupied".
        """
        pairs: List[Tuple[float, int, int]] = []
        for ti, track in enumerate(self._tracks):
            for pi, pos in enumerate(occupied_positions):
                pairs.append((self._dist(track["pos"], pos), ti, pi))
        pairs.sort(key=lambda p: p[0])

        used_tracks: Set[int] = set()
        used_positions: Set[int] = set()
        for _dist, ti, pi in pairs:
            if ti in used_tracks or pi in used_positions:
                continue
            used_tracks.add(ti)
            used_positions.add(pi)

        return [
            track for ti, track in enumerate(self._tracks)
            if ti not in used_tracks
        ]

    # -- Frame update --------------------------------------------------------

    def update(
        self,
        u_gauge_detections: List[Dict[str, Any]],
        check_areas: Optional[List[List[int]]] = None,
        frame_width: Optional[int] = None,
    ) -> None:
        """
        Called every frame with all raw U-Gauge bounding boxes.

        check_areas: current/remembered Inlet & Outlet boxes.  A gauge at one
        of these boxes is being used, and is never learned as a rest slot.
        """
        self.set_frame_width(frame_width)
        self._check_areas = list(check_areas or [])
        self._frame += 1
        self._det_rank = {}

        dets = self._dedupe(list(u_gauge_detections))
        dets.sort(key=lambda d: self._center(d["bbox"])[1])
        self._current_dets = dets

        if not dets:
            self._age_tracks(set())
            self._remember_positions([])
            return

        positions = [self._center(d["bbox"]) for d in dets]

        # Which rack slots have a box on them this frame?  A gauge may only
        # leave the rack from an empty slot, which is what tells the gauge at
        # the part apart from its neighbours.
        self._occupied_slots = set()
        now_mono = time.monotonic()
        own = self._own_slot_radius()
        for pos in positions:
            best: Optional[Tuple[float, int]] = None
            for rank, slot in enumerate(self._slots):
                if slot is None:
                    continue
                dist = self._dist(pos, tuple(slot["pos"]))
                if (
                    dist <= own
                    and (best is None or dist < best[0])
                ):
                    best = (dist, rank)
            if best is not None:
                self._occupied_slots.add(best[1])
                self._slot_last_seen[best[1]] = now_mono

        # 1) Match detections to previous tracks: nearest pair first, one
        #    detection per track.
        #
        #    Two passes: tracks seen in the previous frame first, then tracks
        #    that were briefly occluded.  A stale track must never steal a
        #    detection that a live track can claim — that is what made a gauge
        #    left at the hole "re-identify" itself as the old gauge.
        det_track: Dict[int, int] = {}
        used_tracks: Set[int] = set()
        self._match_pass(
            positions,
            [i for i, t in enumerate(self._tracks) if t["misses"] == 0],
            det_track,
            used_tracks,
        )

        # 1b) Recovery pass: one gauge jumped further than the normal radius
        #     (picked up or put down quickly).  Re-link only when the pairing
        #     is unambiguous — mutual nearest and nothing else nearby.
        self._relink_pass(positions, det_track, used_tracks)

        # 2) Update the matched tracks.
        for di, ti in det_track.items():
            det = dets[di]
            track = self._tracks[ti]
            pos = positions[di]
            track["pos"] = pos
            track["bbox"] = det["bbox"]
            track["misses"] = 0
            track["last_seen"] = self._frame
            track["last_seen_time"] = time.monotonic()
            history = track["history"]
            history.append(pos)
            if len(history) > self.TRACK_HISTORY:
                history.pop(0)

        # 3) Create a track for every unexplained detection.
        for di, det in enumerate(dets):
            if di in det_track:
                continue
            self._tracks.append({
                "id": self._next_track_id,
                "pos": positions[di],
                "bbox": det["bbox"],
                "rank": None,
                "rest_pos": None,
                "history": [positions[di]],
                "misses": 0,
                "last_seen": self._frame,
                "last_seen_time": time.monotonic(),
            })
            self._next_track_id += 1

        # 4) Age tracks that were not matched this frame.  This removes
        #    timed-out tracks and therefore shifts list indices, so keep the
        #    detection -> track mapping by track id from here on.
        matched_ids = {
            di: self._tracks[ti]["id"] for di, ti in det_track.items()
        }
        self._age_tracks(used_tracks)

        # 5) Learn the rack layout once (only used to name the gauges).
        if not self._slots_established:
            self._learn_slots(dets, positions)

        # 6) Name unnamed tracks.
        self._bind_ranks()

        # 6a) A gauge resting on a known slot always has that slot's rank.
        #     Position is the most reliable identity at the rack and repairs
        #     any neighbour swap from the nearest-box matching.
        self._snap_ranks_to_slots()
        self._enforce_unique_ranks()

        # 6b) Remember which single gauge is away from the rack, and follow
        #     the rack if it has moved while all four gauges are at rest.
        self._update_activity()
        self._refresh_slots()

        # 7) Expose identities for the overlay (name may just have been given).
        index_by_id = {track["id"]: ti for ti, track in enumerate(self._tracks)}
        for di, track_id in matched_ids.items():
            ti = index_by_id.get(track_id)
            if ti is None:
                continue
            rank = self._tracks[ti].get("rank")
            if rank is not None:
                self._det_rank[id(dets[di])] = rank

        # 8) A stale track must not sit on top of a live one: it would fight
        #    for the same boxes on later frames.
        self._merge_duplicate_tracks()

        self._remember_positions([t["pos"] for t in self._tracks if t["misses"] == 0])

    # -- Matching helpers ----------------------------------------------------

    def _match_pass(
        self,
        positions: List[Tuple[float, float]],
        track_indices: List[int],
        det_track: Dict[int, int],
        used_tracks: Set[int],
    ) -> None:
        """Greedy nearest matching for one group of tracks."""
        pairs: List[Tuple[float, int, int]] = []
        for di, pos in enumerate(positions):
            if di in det_track:
                continue
            for ti in track_indices:
                if ti in used_tracks:
                    continue
                track = self._tracks[ti]
                if not self._match_allowed(ti, pos):
                    continue
                dist = self._dist(pos, track["pos"])
                if dist <= self._match_limit(track):
                    pairs.append((dist, di, ti))
        pairs.sort(key=lambda p: p[0])

        for _dist, di, ti in pairs:
            if di in det_track or ti in used_tracks:
                continue
            det_track[di] = ti
            used_tracks.add(ti)

    def _match_limit(self, track: Dict[str, Any]) -> float:
        limit = self.TRACK_MATCH_PX * self.scale
        misses = int(track.get("misses", 0))
        if misses:
            limit += min(misses, 20) * self.TRACK_MISS_STEP_PX * self.scale
        return limit

    def _own_slot_radius(self) -> float:
        """
        How close a box must be to a slot to count as that slot's gauge.

        Kept below half the closest slot spacing so a neighbour's box can
        never be mistaken for this slot's box.
        """
        gaps: List[float] = []
        for i in range(len(self._slots)):
            for j in range(i + 1, len(self._slots)):
                if self._slots[i] is None or self._slots[j] is None:
                    continue
                gaps.append(
                    self._dist(
                        tuple(self._slots[i]["pos"]),
                        tuple(self._slots[j]["pos"]),
                    )
                )
        if not gaps:
            return self.match_distance * self.scale
        return min(
            self.match_distance * self.scale,
            0.6 * min(gaps),
        )

    def _near_other_slot(
        self, pos: Tuple[float, float], rank: int
    ) -> bool:
        """True when a box is sitting on a rack slot other than `rank`."""
        for other_rank, slot in enumerate(self._slots):
            if slot is None or other_rank == rank:
                continue
            if self._dist(pos, tuple(slot["pos"])) <= self.stable_px * self.scale:
                return True
        return False

    def _match_allowed(
        self, ti: int, pos: Tuple[float, float]
    ) -> bool:
        """
        A gauge resting on its rack slot may only claim a box on that slot.

        It may also leave its slot (when that slot is empty) for a place that
        is not another slot.  This is what stops a hidden gauge's empty slot
        from dragging a neighbour onto the wrong box, while still letting the
        operator pick a gauge up.
        """
        track = self._tracks[ti]
        rank = track.get("rank")
        if rank is None:
            return True
        if rank == self._active_rank:
            return True
        slot = self._slots[rank] if 0 <= rank < len(self._slots) else None
        if slot is None:
            return True
        slot_pos = tuple(slot["pos"])
        if self._dist(track["pos"], slot_pos) <= self.stable_px * self.scale:
            own = self._own_slot_radius()
            if self._dist(pos, slot_pos) <= own:
                return True
            # Another gauge is already in use: the rack stays put.
            if self._active_rank is not None:
                return False
            # A gauge resting on its rack slot cannot jump directly into a check area in one frame.
            # Fast pickups that appear at a hole must be identified by rack slot vacancy memory.
            if self._point_near_check_area(pos, self._check_areas):
                return False
            return (
                rank not in self._occupied_slots
                and not self._near_other_slot(pos, rank)
            )
        return True

    def _relink_allowed(
        self, ti: int, pos: Tuple[float, float]
    ) -> bool:
        """
        A hidden rack gauge may only come back on its own slot.

        Without this, a stale track left at the rack could jump to the gauge
        at the part (the two are only ~150 px apart on the HMI fixture) and
        steal its identity.  The gauge actually in use is always allowed to
        move.
        """
        track = self._tracks[ti]
        rank = track.get("rank")
        if rank is None:
            return True
        if rank == self._active_rank:
            return True
        slot = self._slots[rank] if 0 <= rank < len(self._slots) else None
        if slot is None:
            return True
        slot_pos = tuple(slot["pos"])
        # A gauge still resting on its slot may leave it, but only from an
        # empty slot and never onto a neighbour's slot.
        if (
            track.get("misses", 0) == 0
            and self._dist(track["pos"], slot_pos)
            <= self.stable_px * self.scale
        ):
            own = self._own_slot_radius()
            if self._dist(pos, slot_pos) <= own:
                return True
            if self._active_rank is not None:
                return False
            # A gauge resting at its slot cannot jump directly into an inspection hole in a single frame.
            # Fast pickups that appear at a hole must be identified by rack slot vacancy memory.
            if self._point_near_check_area(pos, self._check_areas):
                return False
            return (
                rank not in self._occupied_slots
                and not self._near_other_slot(pos, rank)
            )
        # A hidden gauge may only reappear on its own slot.  The radius is
        # kept below half the slot spacing so it cannot land on a neighbour.
        if track.get("misses", 0) > 0:
            return (
                self._dist(pos, slot_pos)
                <= self._own_slot_radius()
            )
        return True

    def _relink_pass(
        self,
        positions: List[Tuple[float, float]],
        det_track: Dict[int, int],
        used_tracks: Set[int],
    ) -> None:
        """
        Re-link a gauge that jumped further than the normal radius.

        A gauge taken out of a hole and laid on the table can move ~250 px in
        one processed frame, which is more than the normal match radius.  If
        it is not re-linked, the old track stays parked at the hole and a new,
        unnamed track is created for the same physical gauge — it would lose
        its identity.

        Safety: only mutual-nearest pairs are linked, and only within a large
        but finite radius.  When two gauges are near each other the pairing is
        ambiguous and nothing is done.
        """
        limit = self.RELINK_PX * self.scale
        free_dets = [di for di in range(len(positions)) if di not in det_track]
        free_tracks = [
            ti for ti in range(len(self._tracks))
            if ti not in used_tracks
            and self._tracks[ti].get("misses", 0) <= self.RELINK_MAX_MISSES
        ]
        if not free_dets or not free_tracks:
            return

        best_for_det: Dict[int, Tuple[float, int]] = {}
        for di in free_dets:
            candidates = [
                (self._dist(positions[di], self._tracks[ti]["pos"]), ti)
                for ti in free_tracks
                if self._dist(positions[di], self._tracks[ti]["pos"]) <= limit
                and self._relink_allowed(ti, positions[di])
            ]
            if candidates:
                best_for_det[di] = min(candidates)

        best_for_track: Dict[int, Tuple[float, int]] = {}
        for di, (dist, ti) in best_for_det.items():
            previous = best_for_track.get(ti)
            if previous is None or dist < previous[0]:
                best_for_track[ti] = (dist, di)

        for ti, (jump, di) in best_for_track.items():
            if ti in used_tracks or di in det_track:
                continue
            if best_for_det.get(di, (0.0, -1))[1] != ti:
                continue        # not the detection's nearest track
            det_track[di] = ti
            used_tracks.add(ti)
            logger.debug(
                "[UGaugeTracker] Re-linked track#%s after a %.0f px jump.",
                self._tracks[ti]["id"],
                jump,
            )

    @staticmethod
    def _bbox_iou(box_a: List[int], box_b: List[int]) -> float:
        xa1, ya1, xa2, ya2 = box_a
        xb1, yb1, xb2, yb2 = box_b
        inter_x1 = max(xa1, xb1)
        inter_y1 = max(ya1, yb1)
        inter_x2 = min(xa2, xb2)
        inter_y2 = min(ya2, yb2)
        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h
        if inter_area <= 0:
            return 0.0
        area_a = max(0, xa2 - xa1) * max(0, ya2 - ya1)
        area_b = max(0, xb2 - xb1) * max(0, yb2 - yb1)
        union = area_a + area_b - inter_area
        return inter_area / union if union > 0 else 0.0

    def _dedupe(self, dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Drop duplicate boxes drawn on the same physical gauge."""
        radius = self.dedupe_px * self.scale
        ordered = sorted(
            dets, key=lambda d: d.get("confidence", 0.0), reverse=True
        )
        kept: List[Dict[str, Any]] = []
        for det in ordered:
            pos = self._center(det["bbox"])
            if any(
                self._dist(pos, self._center(k["bbox"])) <= radius
                or self._bbox_iou(det["bbox"], k["bbox"]) >= 0.45
                for k in kept
            ):
                continue
            kept.append(det)
        return kept

    def _age_tracks(self, matched: Set[int]) -> None:
        alive: List[Dict[str, Any]] = []
        now = time.monotonic()
        for idx, track in enumerate(self._tracks):
            if idx in matched:
                alive.append(track)
                continue
            track["misses"] = int(track.get("misses", 0)) + 1
            # A named gauge may be hidden by a hand for a few seconds.  It is
            # still on the rack, so keep its identity reserved.  The hold is
            # time-based: after exactly `occlusion_hold_seconds` the gauge is
            # treated as genuinely away and its rank is released.  An unnamed
            # track keeps the normal frame timeout.
            if track.get("rank") is not None:
                last = float(track.get("last_seen_time", 0.0))
                if now - last <= self.occlusion_hold_seconds:
                    alive.append(track)
                    continue
                logger.info(
                    "[UGaugeTracker] Rank-%d released after %.1fs occlusion hold."
                    % (track["rank"], now - last)
                )
                continue
            if track["misses"] > self.TRACK_MAX_MISSES:
                continue
            alive.append(track)
        self._tracks = alive

    def _remember_positions(self, positions: List[Tuple[float, float]]) -> None:
        self._last_u_positions = list(positions)

    def _merge_duplicate_tracks(self) -> None:
        """
        Drop a track that sits on top of another one.

        This can happen when a fast movement first creates a new track before
        the re-link pass can attach it to the old one.  The ranked track is
        kept, so the identity is not lost, and it takes over the fresh
        position of the duplicate.
        """
        radius = self.DEDUPE_PX * self.scale
        kept: List[Dict[str, Any]] = []
        for track in sorted(
            self._tracks,
            key=lambda t: (
                t.get("rank") is None,     # ranked tracks first
                t.get("misses", 0),        # then the freshest
                t.get("id", 0),
            ),
        ):
            duplicate = next(
                (
                    other
                    for other in kept
                    # Only a *stale* track may be absorbed.  Two live tracks
                    # that pass close to each other are two real gauges.
                    if (track.get("misses", 0) > 0 or other.get("misses", 0) > 0)
                    # And never merge two different identities: a lost rank-2
                    # gauge is not the same object as a live rank-1 gauge.
                    and (
                        track.get("rank") is None
                        or other.get("rank") is None
                        or track.get("rank") == other.get("rank")
                    )
                    and self._dist(track["pos"], other["pos"]) <= radius
                ),
                None,
            )
            if duplicate is None:
                kept.append(track)
                continue

            # Keep the ranked identity, but follow the live box.
            if (
                duplicate.get("rank") is not None
                and track.get("misses", 0) == 0
                and duplicate.get("misses", 0) > 0
            ):
                duplicate["pos"] = track["pos"]
                duplicate["bbox"] = track["bbox"]
                duplicate["history"] = list(track["history"])
                duplicate["misses"] = 0
            logger.debug(
                "[UGaugeTracker] Merged duplicate track#%s into track#%s.",
                track.get("id"), duplicate.get("id"),
            )
        self._tracks = kept

    # -- Learning the rack layout -------------------------------------------

    def _learn_slots(
        self,
        dets: List[Dict[str, Any]],
        positions: List[Tuple[float, float]],
    ) -> None:
        """
        Learn the four rest slots only from a clean, stable rest layout.

        This is the only place that looks at "the rack"; it runs while the
        gauges are still lying on the table and is not needed afterwards.

        A gauge is rejected only when it is *on* a hole (overlapping it), not
        merely near it: on some fixtures the rack sits right next to the part,
        and a wider exclusion made the layout impossible to learn.
        """
        on_area = [
            self._is_on_check_area(d["bbox"], self._check_areas) for d in dets
        ]
        if len(dets) != 4 or any(on_area):
            if not self._waiting_logged:
                logger.info(
                    "[UGaugeTracker] Waiting for all four U-gauges to rest "
                    "away from Inlet/Outlet before learning rest positions."
                )
                self._waiting_logged = True
            self._learn_history = []
            return

        spread_limit = self.learning_max_spread * self.scale
        max_spread = 0.0
        for i in range(4):
            for j in range(i + 1, 4):
                max_spread = max(max_spread, self._dist(positions[i], positions[j]))
        if max_spread > spread_limit:
            self._learn_history = []
            return

        if self._learn_history:
            prev = self._learn_history[-1]
            max_move = max(
                self._dist(positions[i], prev[i]) for i in range(4)
            )
            if max_move > self.stable_px * self.scale:
                self._learn_history = []

        self._learn_history.append(positions)
        if len(self._learn_history) > self.min_stable_frames:
            self._learn_history.pop(0)

        if len(self._learn_history) < self.min_stable_frames:
            return

        averaged: List[Tuple[float, float]] = []
        for rank in range(4):
            xs = [frame[rank][0] for frame in self._learn_history]
            ys = [frame[rank][1] for frame in self._learn_history]
            averaged.append((sum(xs) / len(xs), sum(ys) / len(ys)))

        # Never learn a "rest slot" that is physically on a hole.
        if any(
            ax1 <= px <= ax2 and ay1 <= py <= ay2
            for px, py in averaged
            for ax1, ay1, ax2, ay2 in self._check_areas
        ):
            logger.warning(
                "[UGaugeTracker] Rejecting rest layout learned on a hole."
            )
            self._learn_history = []
            return

        self._slots = [{"pos": pos} for pos in averaged]
        self._slots_established = True
        self._slot_last_seen = {r: time.monotonic() for r in range(4)}
        self._learn_history = []
        self._waiting_logged = False
        logger.info(
            "[UGaugeTracker] Slots established top->bottom: "
            + ", ".join(
                f"rank{r}=({p[0]:.0f},{p[1]:.0f})"
                for r, p in enumerate(averaged)
            )
        )

    # -- Naming --------------------------------------------------------------

    def _bind_ranks(self) -> None:
        """Give unnamed tracks their rank.  A name is never taken away."""
        live = [t for t in self._tracks if t["misses"] == 0]
        now_mono = time.monotonic()
        # A rank stays reserved while its gauge is hidden by a hand, so a
        # second box can never be given the same name.  After the occlusion
        # hold expires, the rank is released.
        reserved = {
            t["rank"]
            for t in self._tracks
            if t.get("rank") is not None and self._within_occlusion_hold(t)
        }
        for r in range(4):
            if self.is_slot_occluded(r, now_mono):
                reserved.add(r)

        # 1) A still gauge lying on a free rack slot gets that slot's rank.
        for track in live:
            if track.get("rank") is not None:
                continue
            if not self._track_is_still(track):
                continue

            candidates = []
            for rank, slot in enumerate(self._slots):
                if slot is None or rank in reserved:
                    continue
                dist = self._dist(track["pos"], slot["pos"])
                candidates.append((dist, rank))
            if not candidates:
                continue

            dist, rank = min(candidates)
            if dist <= self.match_distance * self.scale:
                self._name_track(track, rank, rest_pos=self._slots[rank]["pos"])
                reserved.add(rank)

        # 1b) Identify an unnamed U-gauge box near a check hole (Inlet or Outlet):
        #     - If exactly one rack slot is unoccupied and all other 3 are visibly
        #       occupied, that unoccupied slot is unambiguously the gauge at the hole.
        #     - When the operator occludes other gauges, we hold memory of each
        #       slot position for occlusion_hold_seconds (3.0s). Only a slot that
        #       is confirmed missing (absent beyond cooldown) or the single missing
        #       slot once hand clears can be bound.
        #     - An occluded slot's identity is NEVER stolen.
        at_part = [
            t for t in live
            if t.get("rank") is None
            and self._point_near_check_area(t["pos"], self._check_areas)
        ]
        if len(at_part) == 1:
            candidate_rank: Optional[int] = None
            allow_takeover = False
            unoccupied = [
                r for r in range(4)
                if r not in self._occupied_slots
                and not any(t.get("rank") == r and t.get("misses", 0) == 0 for t in live)
            ]
            if len(unoccupied) == 1:
                # All other 3 rack slots are visibly occupied: no ambiguity!
                candidate_rank = unoccupied[0]
                allow_takeover = True
            else:
                missing_slots = [
                    r for r in unoccupied
                    if not self.is_slot_occluded(r, now_mono)
                ]
                if len(missing_slots) == 1:
                    candidate_rank = missing_slots[0]
                    allow_takeover = True

            if candidate_rank is not None:
                rest_pos = None
                if 0 <= candidate_rank < len(self._slots) and self._slots[candidate_rank] is not None:
                    rest_pos = tuple(self._slots[candidate_rank]["pos"])
                self._name_track(
                    at_part[0],
                    candidate_rank,
                    rest_pos=rest_pos,
                    allow_occluded_takeover=allow_takeover,
                )
                reserved.add(candidate_rank)
                self.mark_active(candidate_rank)

        # 2) Exactly one free rank and exactly one unnamed gauge: it must be
        #    that gauge.  Covers a gauge picked up before the rack was seen,
        #    and a gauge whose old track was lost.  Once the layout is known
        #    the gauge must be standing still, so a gauge being carried is
        #    not named by guesswork.
        free = [r for r in range(4) if r not in reserved]
        unnamed = [t for t in live if t.get("rank") is None]
        if len(free) == 1 and len(unnamed) == 1:
            if self._slots_established and not self._track_is_still(unnamed[0]):
                return
            rest_pos = None
            if self._slots_established and self._slots[free[0]] is not None:
                rest_pos = tuple(self._slots[free[0]]["pos"])
            self._name_track(unnamed[0], free[0], rest_pos=rest_pos)

    def _name_track(
        self,
        track: Dict[str, Any],
        rank: int,
        rest_pos: Optional[Tuple[float, float]] = None,
        allow_occluded_takeover: bool = False,
    ) -> None:
        if track.get("rank") == rank:
            return
        # Never give a rank to two *visible* gauges.  A rank whose track has
        # been lost, however, moves to the gauge that is actually present.
        for other in self._tracks:
            if other is track:
                continue
            if other.get("rank") != rank:
                continue
            if other.get("misses", 0) == 0:
                return
            # A rank hidden by a hand is still that gauge.  Only the explicit
            # "one slot empty + one gauge at the hole" case may take it over.
            if self._within_occlusion_hold(other) and not allow_occluded_takeover:
                return
            other["rank"] = None
            other["rest_pos"] = None
            logger.info(
                "[UGaugeTracker] Rank-%d moved from lost track#%s to track#%s.",
                rank, other.get("id"), track.get("id"),
            )

        track["rank"] = rank
        track["rest_pos"] = rest_pos
        logger.info(
            "[UGaugeTracker] Rank-%d (cp_id=%s) identified -> %s"
            % (rank, self.checkpoint_ids[rank], self._track_label(track))
        )

    @staticmethod
    def _track_label(track: Dict[str, Any]) -> str:
        return "track#%s" % track.get("id")

    def _track_is_still(self, track: Dict[str, Any]) -> bool:
        history = track.get("history", [])
        if len(history) < 3:
            return False
        max_dist = 0.0
        for i, p1 in enumerate(history):
            for p2 in history[i + 1:]:
                max_dist = max(max_dist, self._dist(p1, p2))
        return max_dist <= self.stable_px * self.scale

    def _within_occlusion_hold(self, track: Dict[str, Any]) -> bool:
        """True while a hidden gauge is still assumed to be on the rack."""
        if track.get("misses", 0) == 0:
            return True
        last = float(track.get("last_seen_time", 0.0))
        return (time.monotonic() - last) <= self.occlusion_hold_seconds

    def _track_with_rank(self, rank: int) -> Optional[Dict[str, Any]]:
        for track in self._tracks:
            if track.get("rank") == rank:
                return track
        return None

    def is_occluded(self, rank: int) -> bool:
        """True when this rank's gauge is hidden by a hand but remembered."""
        track = self._track_with_rank(rank)
        return (
            track is not None
            and track.get("misses", 0) > 0
            and self._within_occlusion_hold(track)
        )

    def mark_active(self, rank: Optional[int]) -> None:
        """Remember the single gauge that is away from the rack."""
        if rank is None:
            return
        if self._active_rank != rank:
            logger.info(
                "[UGaugeTracker] Rank-%d is the gauge in use.", rank
            )
        self._active_rank = rank
        self._active_since = time.monotonic()

    def _enforce_unique_ranks(self) -> None:
        """
        Never let two tracks carry the same rank.

        A rank can briefly exist on two tracks while a lost identity is handed
        over.  Keep the best candidate: a visible track first, then the one
        closest to that rank's slot.  This is a safety net; the normal naming
        paths already avoid duplicates.
        """
        by_rank: Dict[int, List[Dict[str, Any]]] = {}
        for track in self._tracks:
            rank = track.get("rank")
            if rank is None:
                continue
            by_rank.setdefault(int(rank), []).append(track)

        for rank, tracks in by_rank.items():
            if len(tracks) <= 1:
                continue

            slot = (
                self._slots[rank]
                if 0 <= rank < len(self._slots)
                else None
            )

            def score(track: Dict[str, Any]) -> Tuple[int, float, int]:
                live = 0 if track.get("misses", 0) == 0 else 1
                if slot is not None:
                    dist = self._dist(track["pos"], tuple(slot["pos"]))
                else:
                    dist = 0.0
                return (live, dist, int(track.get("id", 0)))

            tracks.sort(key=score)
            for other in tracks[1:]:
                other["rank"] = None
                other["rest_pos"] = None
                logger.info(
                    "[UGaugeTracker] Dropped duplicate rank-%d from track#%s.",
                    rank, other.get("id"),
                )

    def _snap_ranks_to_slots(self) -> None:
        """
        A gauge resting on a known slot has that slot's rank.

        The four gauges always return to their own slot, so position at the
        rack is the ground truth. When a gauge is at slot r, it takes rank r
        immediately, and any other track claiming rank r has it cleared.
        """
        if not self._slots_established:
            return

        live = [t for t in self._tracks if t.get("misses", 0) == 0]
        radius = self._own_slot_radius()
        assigned: Dict[int, Dict[str, Any]] = {}
        for track in live:
            best: Optional[Tuple[float, int]] = None
            for rank, slot in enumerate(self._slots):
                if slot is None or rank in assigned:
                    continue
                dist = self._dist(track["pos"], tuple(slot["pos"]))
                if dist <= radius:
                    if best is None or dist < best[0]:
                        best = (dist, rank)
            if best is not None:
                assigned[best[1]] = track

        for rank, track in assigned.items():
            if track.get("rank") == rank:
                continue
            for other in self._tracks:
                if other is track or other.get("rank") != rank:
                    continue
                other["rank"] = None
                other["rest_pos"] = None
            track["rank"] = rank
            track["rest_pos"] = tuple(self._slots[rank]["pos"])

    def _update_activity(self) -> None:
        """
        Keep track of the one gauge that is away from the rack.

        A gauge that was seen moving (or is at an Inlet/Outlet hole) is the
        only one allowed to be away.  Every other gauge is locked to its slot,
        even when a hand hides it for a few seconds.
        """
        if not self._slots_established:
            return

        if self._active_rank is not None:
            track = self._track_with_rank(self._active_rank)
            if track is None:
                self._active_rank = None
            elif track.get("misses", 0) == 0:
                slot = self._slots[self._active_rank]
                if (
                    slot is not None
                    and self._dist(track["pos"], tuple(slot["pos"]))
                    <= self.RACK_BIND_PX * self.scale
                    and self._track_is_still(track)
                ):
                    self._active_rank = None
                elif not self._point_near_check_area(
                    track["pos"], self._check_areas
                ):
                    # The gauge was at a hole and has now been laid on the
                    # table.  It is no longer the gauge in use, even though
                    # it is still away from its rack slot.
                    self._active_rank = None
            elif not self._within_occlusion_hold(track):
                self._active_rank = None

        if self._active_rank is not None:
            return

        candidates: List[Tuple[float, int]] = []
        for track in self._tracks:
            rank = track.get("rank")
            if rank is None or track.get("misses", 0) != 0:
                continue
            slot = self._slots[rank] if 0 <= rank < len(self._slots) else None
            if slot is None:
                continue
            dist = self._dist(track["pos"], tuple(slot["pos"]))
            if dist <= self.match_distance * self.scale:
                continue
            # A gauge is only "in use" when it is at an Inlet/Outlet hole.
            # All four moving together is the rack shifting, not a gauge
            # being carried, so it must not set an active rank.
            if not self._point_near_check_area(
                track["pos"], self._check_areas
            ):
                continue
            candidates.append((-dist, rank))

        if candidates:
            candidates.sort()
            self.mark_active(candidates[0][1])

    def _refresh_slots(self) -> None:
        """
        Re-anchor the rack memory when all four gauges are back and still.

        The rack may shift in the frame, but the four gauges are always in
        top-to-bottom order.  Using that order also repairs a rank shuffle
        caused by a fast shift (the nearest-box matching can swap two
        neighbours when the whole rack moves at once).
        """
        if not self._slots_established:
            return

        live = [t for t in self._tracks if t.get("misses", 0) == 0]
        if len(live) != 4:
            return
        if any(not self._track_is_still(t) for t in live):
            return
        # A gauge at a hole is in use, not resting on the rack.
        if any(
            self._point_near_check_area(t["pos"], self._check_areas)
            for t in live
        ):
            return

        ordered = sorted(live, key=lambda t: t["pos"][1])
        ys = [t["pos"][1] for t in ordered]
        if any(ys[i + 1] - ys[i] <= 1.0 for i in range(3)):
            return

        # The four boxes must still look like the same rack: the gaps between
        # neighbours should match the learned rack's gaps.  A gauge held at
        # the part (usually below the rack) makes one gap much larger, so it
        # can never be mistaken for the fourth slot.
        slot_ys = [float(self._slots[r]["pos"][1]) for r in range(4)]
        for i in range(3):
            gap = ys[i + 1] - ys[i]
            slot_gap = slot_ys[i + 1] - slot_ys[i]
            if slot_gap <= 1.0:
                return
            if not (0.5 * slot_gap <= gap <= 1.6 * slot_gap):
                return

        # The four visible, still gauges are the four slots, top to bottom.
        # Every gauge is back on the rack, so nothing is in use any more.
        self._active_rank = None
        for track in self._tracks:
            track["rank"] = None
            track["rest_pos"] = None
        for rank, track in enumerate(ordered):
            track["rank"] = rank
            slot = self._slots[rank]
            if slot is None:
                self._slots[rank] = {"pos": tuple(track["pos"])}
                track["rest_pos"] = tuple(track["pos"])
                continue
            sx, sy = slot["pos"]
            nx, ny = track["pos"]
            slot["pos"] = (
                sx + (nx - sx) * 0.3,
                sy + (ny - sy) * 0.3,
            )
            track["rest_pos"] = tuple(slot["pos"])

    # -- Helpers -------------------------------------------------------------

    def _is_near_check_area(
        self, bbox: List[int], check_areas: List[List[int]]
    ) -> bool:
        if not check_areas:
            return False
        return self._point_near_check_area(self._center(bbox), check_areas)

    @staticmethod
    def _is_on_check_area(
        bbox: List[int], check_areas: List[List[int]]
    ) -> bool:
        """True when the box is physically on a hole (not just next to it)."""
        if not check_areas:
            return False
        gx1, gy1, gx2, gy2 = bbox
        cx, cy = (gx1 + gx2) / 2, (gy1 + gy2) / 2
        for ax1, ay1, ax2, ay2 in check_areas:
            if ax1 <= cx <= ax2 and ay1 <= cy <= ay2:
                return True
            if min(gx2, ax2) > max(gx1, ax1) and min(gy2, ay2) > max(gy1, ay1):
                return True
        return False

    def _point_near_check_area(
        self, pos: Tuple[float, float], check_areas: List[List[int]]
    ) -> bool:
        cx, cy = pos
        margin = self.CHECK_AREA_MARGIN_PX * self.scale
        for ax1, ay1, ax2, ay2 in check_areas:
            if (
                ax1 - margin <= cx <= ax2 + margin
                and ay1 - margin <= cy <= ay2 + margin
            ):
                return True
        return False

    @staticmethod
    def _center(bbox: List[int]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return (x1 + x2) / 2, (y1 + y2) / 2

    @staticmethod
    def _dist(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


# ─── Validator ───────────────────────────────────────────────────────────────

class GaugeValidator:
    """
    Validates gauge positions against SOP rules.

    Uses a part-presence state machine so that:
    - One physical part = one inspection session.
    - Gauges latch OK and remain OK when moved away.
    - Auto-resets when the part is removed from the table.
    """

    # ── Physical-gauge tracking (used by profiles with movement checks) ──
    _TRACK_MATCH_DISTANCE = 150.0   # px — max movement between two frames
    _TRACK_MAX_MISSES = 30          # frames a track is kept without a match
    _REST_STABILITY_PX = 20.0       # max wobble to call a gauge "stationary"
    _REST_HISTORY_FRAMES = 5        # frames used to confirm rest position
    _SPATIAL_GRACE_FRAMES = 3       # tolerate brief bbox jitter without losing dwell

    def __init__(
        self,
        checkpoints: List[Dict[str, Any]],
        gauge_class_ids: Optional[Set[int]] = None,
        gauge_confusion: Optional[Dict[str, Any]] = None,
        u_gauge_cfg: Optional[Dict[str, Any]] = None,
        overlap_threshold: float = 0.15,
        near_distance_threshold: float = 150,
        ok_hold_frames: int = 3,
        ok_hold_seconds: float = 2.0,
        gauge_grace_frames: int = 15,
        part_clear_time_complete: float = 2.0,
        part_clear_time_inspecting: float = 60.0,
    ):
        self.overlap_threshold = overlap_threshold
        self.near_distance_threshold = near_distance_threshold
        self.ok_hold_frames = ok_hold_frames
        self.ok_hold_seconds = ok_hold_seconds
        self.gauge_grace_frames = gauge_grace_frames
        self.part_clear_time_complete = part_clear_time_complete
        self.part_clear_time_inspecting = part_clear_time_inspecting

        self._checkpoint_configs = {cp["id"]: cp for cp in checkpoints}
        self.checkpoints: Dict[int, CheckpointResult] = {}
        for cp in checkpoints:
            self.checkpoints[cp["id"]] = CheckpointResult(
                checkpoint_id=cp["id"],
                name=cp["name"],
                description=cp["description"],
            )

        # Per-profile gauge class ID set (used to split detections in validate())
        # Falls back to reading from config for backward-compatibility.
        if gauge_class_ids is not None:
            self._gauge_class_ids: Set[int] = gauge_class_ids
        else:
            import config as _cfg
            self._gauge_class_ids = set(_cfg.GAUGE_CLASSES.keys())

        # Part-presence state machine
        self.inspection_state = InspectionState.IDLE
        self._part_absent_start_time = 0.0   # 0.0 means part is currently present or not tracked
        self._part_present_frames = 0  # how many consecutive frames TML Part visible

        # Production tracking
        self.total_count = 0
        self.pass_count = 0
        self.fail_count = 0
        self.recent_logs: List[InspectionLog] = []
        self._log_counter = 0
        
        self.scanned_part_no: Optional[str] = None
        self._session_start_time: float = 0.0

        # Safety logic
        self._hand_interaction_frames = 0
        self.glove_warning = False

        # Supervisor bypass — when True every checkpoint is latched OK without
        # any detection.  Never persisted; always starts False.
        self.bypass_active = False

        # Part memory (for occlusion handling)
        self._last_known_parts: Dict[str, List[int]] = {}
        # Last-known part/hole boxes kept across sessions.  Used to stop rest
        # positions being learned where the part normally sits, even on frames
        # where the part itself is not detected.
        self._part_area_memory: Dict[str, List[int]] = {}
        # Inlet/Outlet memory used only to guard U-Gauge rest-slot learning.
        # Kept across part sessions because the fixture does not move.
        self._u_gauge_area_memory: Dict[str, List[int]] = {}
        self._resting_positions: Dict[str, Tuple[float, float]] = {}
        self._gauge_history: Dict[str, List[Tuple[float, float]]] = {}

        # Config-driven gauge confusion (HMI: 8mm / 11mm).  When absent, the
        # legacy TML 13mm/11mm block in validate() is used unchanged.
        self.gauge_confusion: Dict[str, Any] = gauge_confusion or {}
        self._min_rest_distance = float(
            self.gauge_confusion.get("min_rest_distance", 30)
        )

        # Physical-gauge tracks.  Keyed by position, not by class label, so
        # the 8mm/11mm label swaps cannot mix up two different gauges.
        self._track_movement = bool(self.gauge_confusion) or any(
            cp.get("require_movement", False) for cp in checkpoints
        )
        self._movement_tracks: List[Dict[str, Any]] = []
        self._det_track: Dict[int, Dict[str, Any]] = {}
        self._frame_index = 0

        # Resting spots learned during the session (HMI movement rule).
        # Stored as (raw_class_name, x, y).
        self._rest_spots: List[Tuple[str, float, float]] = []

        # ── U-Gauge identity tracker ──────────────────────────────────────
        # Activated when the profile provides a u_gauge_identity config block.
        self._u_gauge_cfg: Dict[str, Any] = u_gauge_cfg or {}
        self._u_gauge_tracker: Optional[UGaugeIdentityTracker] = None
        # Map: u_gauge_rank → checkpoint_id (built from checkpoint configs)
        self._u_gauge_cp_ids: List[int] = []

        if self._u_gauge_cfg.get("enabled"):
            cp_ids = self._u_gauge_cfg.get("checkpoint_ids", [])
            if len(cp_ids) == 4:
                self._u_gauge_cp_ids = list(cp_ids)
                self._u_gauge_tracker = UGaugeIdentityTracker(
                    checkpoint_ids=cp_ids,
                    gauge_class=self._u_gauge_cfg.get("gauge_class", "U Gauge"),
                    match_distance=self._u_gauge_cfg.get("min_rest_distance", 40),
                    min_stable_frames=self._u_gauge_cfg.get("min_stable_frames", 8),
                    learning_max_spread=self._u_gauge_cfg.get("learning_max_spread", 250),
                    occlusion_hold_seconds=self._u_gauge_cfg.get(
                        "occlusion_hold_seconds", 3.0
                    ),
                    dedupe_px=self._u_gauge_cfg.get("dedupe_px", 15.0),
                )
                logger.info(
                    "[UGaugeTracker] Initialized with checkpoint IDs: "
                    f"{cp_ids}"
                )

        # Memory of completed gauges for returning parts
        self.part_memory: Dict[str, Set[int]] = {}

    def set_part_no(self, part_no: str, restore_memory: bool = True):
        """
        Store the scanned part number.

        restore_memory=True  — legacy/manual behaviour: if the same part is
            already being inspected, re-latch the checkpoints remembered from
            a previous pass of that part (rework / returning part).
        restore_memory=False — used by the automatic scanner path.  A late
            end-of-check scan must never silently re-latch gauges, so the
            part number is stored and nothing else is touched.
        """
        self.scanned_part_no = part_no
        if not restore_memory:
            return
        # Restore memory if we are already inspecting
        if part_no in self.part_memory and self.inspection_state == InspectionState.INSPECTING:
            logger.info(f"Restoring memory for part {part_no}")
            for cp_id in self.part_memory[part_no]:
                if cp_id in self.checkpoints:
                    self.checkpoints[cp_id].status = GaugeStatus.OK
                    self.checkpoints[cp_id].dwell_progress = 1.0

    # ─── Supervisor Bypass ───────────────────────────────────────────────
    def set_bypass(self, active: bool) -> None:
        """Turn the supervisor bypass on/off (called from the app layer)."""
        self.bypass_active = bool(active)

    def _apply_bypass_ok(self) -> None:
        """Latch every checkpoint OK without any detection."""
        for result in self.checkpoints.values():
            if result.status != GaugeStatus.OK:
                result.status = GaugeStatus.OK
                result.confidence = 0.0
                result.overlap = 0.0
                result.dwell_progress = 1.0

    def force_bypass_complete(self) -> None:
        """
        Bypass trigger from a scan: mark every gauge OK and close the session
        as COMPLETE immediately.

        Works even when no part is detected (broken model/camera), so the
        operator can keep production moving.  The normal state machine still
        writes the log entry when the (possibly absent) part clears.
        """
        if self.inspection_state == InspectionState.IDLE:
            self._reset_checkpoints()
            self._session_start_time = time.time()
        self._apply_bypass_ok()
        self.inspection_state = InspectionState.COMPLETE

    # ─── Public API ──────────────────────────────────────────────────────

    def validate(
        self,
        detections: List[Dict[str, Any]],
        frame_width: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point — called every inference frame.

        1. Update part-presence state machine.
        2. If INSPECTING, validate each unlocked checkpoint.
        3. Check for auto-completion or auto-reset.

        frame_width: width of the frame the detections came from.  The U-gauge
        pixel thresholds are scaled with it, so a live camera that is
        pre-scaled to a different width behaves like the recorded feed.
        """
        # Separate gauge detections from part detections using config class IDs
        # (not a hardcoded range — class 14 "11mm Gauge" would be missed otherwise)
        gauge_detections: Dict[str, List[Dict]] = {}
        part_detections: Dict[str, List[Dict]] = {}

        for det in detections:
            name = det["class_name"]
            if det["class_id"] in self._gauge_class_ids:
                gauge_detections.setdefault(name, []).append(det)
            else:
                part_detections.setdefault(name, []).append(det)

        # ── Step 1: Part-presence state machine ──────────────────────────
        for name, dets in part_detections.items():
            if dets:
                self._part_area_memory[name] = max(
                    dets, key=lambda d: d["confidence"]
                )["bbox"]
        tml_present = "Part" in part_detections
        self._update_part_state(tml_present)

        # ── Step 1b: rescue U-gauges reported as 8mm / 11mm ──────────────
        # A U-gauge taken to the part is sometimes called 8mm / 11mm.  One
        # gauge is away from the rack at a time, so the empty rack slot tells
        # us which gauge the box belongs to.  Must run before the tracker so
        # it sees all four.
        check_areas: List[List[int]] = []
        if self._u_gauge_tracker is not None:
            check_areas = self._u_gauge_check_areas(part_detections)
            self._u_gauge_tracker.set_frame_width(frame_width)
            self._rescue_u_gauges(gauge_detections, check_areas)

        # ── Step 1c: U-Gauge identity tracker (every frame) ──────────────
        # Runs in IDLE as well so the rest layout can be learned before the
        # operator picks up a gauge.  Held positions near Inlet/Outlet are
        # explicitly excluded from learning.
        if self._u_gauge_tracker is not None:
            u_class = self._u_gauge_cfg.get("gauge_class", "U Gauge")
            self._u_gauge_tracker.update(
                list(gauge_detections.get(u_class, [])),
                check_areas=check_areas,
                frame_width=frame_width,
            )
            self._apply_u_gauge_labels(gauge_detections.get(u_class, []))

        # ── Step 2: Track physical gauges (position-based, label-agnostic) ─
        if self._track_movement:
            self._update_movement_tracks(gauge_detections)
            self._update_rest_spots(gauge_detections, part_detections)

        # ── Step 3: Gauge-confusion correction ───────────────────────────
        if self.gauge_confusion:
            self._resolve_gauge_confusion(gauge_detections)
        else:
            # Legacy TML 13mm / 11mm handling — unchanged.
            # If YOLO detects multiple 13mm gauges, the high-confidence one on the table is the real 13mm.
            # The lower-confidence one being held/tilted is actually the 11mm gauge.
            if "13mm" in gauge_detections and len(gauge_detections["13mm"]) > 1:
                sorted_13 = sorted(gauge_detections["13mm"], key=lambda x: x["confidence"], reverse=True)
                gauge_detections["13mm"] = [sorted_13[0]]
                for det in sorted_13[1:]:
                    det["class_name"] = "11mm"
                    # Add to 11mm list (creating it if it doesn't exist)
                    gauge_detections.setdefault("11mm", []).append(det)

            # Conversely, if YOLO detects multiple 11mm gauges, the lower-confidence one is actually 13mm.
            if "11mm" in gauge_detections and len(gauge_detections["11mm"]) > 1:
                sorted_11 = sorted(gauge_detections["11mm"], key=lambda x: x["confidence"], reverse=True)
                gauge_detections["11mm"] = [sorted_11[0]]
                for det in sorted_11[1:]:
                    det["class_name"] = "13mm"
                    gauge_detections.setdefault("13mm", []).append(det)

            # If there is only ONE 13mm detection but its confidence is low, it's likely the 11mm gauge faking it
            # (The true 13mm gauge on the table usually has high confidence > 0.60)
            if "13mm" in gauge_detections and len(gauge_detections["13mm"]) == 1:
                if gauge_detections["13mm"][0]["confidence"] < 0.55:
                    det = gauge_detections["13mm"].pop(0)
                    det["class_name"] = "11mm"
                    gauge_detections.setdefault("11mm", []).append(det)
                    if not gauge_detections["13mm"]:
                        del gauge_detections["13mm"]

        # ── Step 4: Only run gauge checks while INSPECTING ───────────────
        if self.inspection_state == InspectionState.INSPECTING:
            self._run_gauge_checks(gauge_detections, part_detections)

            # Supervisor bypass: after the real checks, latch anything still
            # open so the part closes as a PASS and the line keeps moving.
            if self.bypass_active:
                self._apply_bypass_ok()

            self._check_completion()
            
            # Check for hand interaction — warn if a bare hand is detected anywhere during inspection
            hand_present = "Hand" in part_detections
            if hand_present:
                logger.warning(f"[SAFETY] Hand detected during inspection! Detections: {list(part_detections.keys())}")
            self.glove_warning = hand_present

        return self._build_status()

    def reset(self) -> Dict[str, Any]:
        """Manual reset — log current result if meaningful, then clear all."""
        overall = self._compute_overall()
        if self.inspection_state in (InspectionState.INSPECTING, InspectionState.COMPLETE):
            if overall in (OverallStatus.OK, OverallStatus.NG, OverallStatus.IN_PROGRESS):
                self._add_log(
                    "OK" if overall == OverallStatus.OK else "NG"
                )

        self._reset_checkpoints()
        self.inspection_state = InspectionState.IDLE
        self._part_absent_start_time = 0.0
        self._part_present_frames = 0
        logger.info("Inspection manually reset.")
        return self._build_status()

    def get_status(self) -> Dict[str, Any]:
        return self._build_status()

    # ─── Gauge Confusion & Physical Tracking ─────────────────────────────

    def _update_movement_tracks(self, gauge_detections: Dict[str, List[Dict]]) -> None:
        """
        Follow each physical gauge by position, independent of its class label.

        The model can label the same physical gauge differently from one frame
        to the next (8mm <-> 11mm).  Tracking by nearest previous position lets
        us keep a stable history and initial position even while the label
        changes.
        """
        self._frame_index += 1
        self._det_track = {}

        # Drop tracks that have been out of frame for a long time.
        self._movement_tracks = [
            t for t in self._movement_tracks
            if self._frame_index - t["last_seen"] <= self._TRACK_MAX_MISSES
        ]

        dets = [det for dets in gauge_detections.values() for det in dets]
        dets.sort(key=lambda d: d.get("confidence", 0.0), reverse=True)

        used_tracks: Set[int] = set()
        for det in dets:
            cx, cy = self._center(det["bbox"])
            cls_name = det["class_name"]

            # 1) Prefer the nearest unmatched track (normal, small movement).
            best_idx: Optional[int] = None
            best_dist: Optional[float] = None
            for idx, track in enumerate(self._movement_tracks):
                if idx in used_tracks:
                    continue
                tx, ty = track["pos"]
                dist = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
                if dist <= self._TRACK_MATCH_DISTANCE and (
                    best_dist is None or dist < best_dist
                ):
                    best_idx, best_dist = idx, dist

            # 2) Fall back to the most recent unmatched track with the same
            #    label.  Operators can lift a gauge much further than one
            #    frame's match distance; without this the gauge would get a
            #    brand-new track whose "rest" is the check position itself.
            if best_idx is None:
                same_cls = [
                    i for i, t in enumerate(self._movement_tracks)
                    if i not in used_tracks and t.get("last_class") == cls_name
                ]
                if same_cls:
                    best_idx = max(
                        same_cls,
                        key=lambda i: self._movement_tracks[i]["last_seen"],
                    )

            # 3) For an 8mm/11mm confusion frame, the extra box belongs to the
            #    other gauge in the pair.  Match it to that physical track
            #    (nearest one) so its original resting spot is preserved.
            if best_idx is None and self.gauge_confusion:
                pair = set(self.gauge_confusion.get("pair", []))
                candidates = [
                    i for i, t in enumerate(self._movement_tracks)
                    if i not in used_tracks and t.get("last_class") in pair
                ]
                if candidates:
                    def _dist(i):
                        tx, ty = self._movement_tracks[i]["pos"]
                        return ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
                    best_idx = min(candidates, key=_dist)

            if best_idx is None:
                # New physical gauge — remember only where it was seen; the
                # resting spot itself is learned from stable frames below.
                track = {
                    "pos": (cx, cy),
                    "first_pos": (cx, cy),
                    "history": [(cx, cy)],
                    "last_class": cls_name,
                    "last_seen": self._frame_index,
                }
                self._movement_tracks.append(track)
                best_idx = len(self._movement_tracks) - 1
            else:
                track = self._movement_tracks[best_idx]
                track["pos"] = (cx, cy)
                track["history"].append((cx, cy))
                if len(track["history"]) > self._REST_HISTORY_FRAMES:
                    track["history"].pop(0)
                track["last_class"] = cls_name
                track["last_seen"] = self._frame_index

            used_tracks.add(best_idx)
            self._det_track[id(det)] = self._movement_tracks[best_idx]

    def _track_is_stable(self, track: Dict[str, Any]) -> bool:
        """True when the gauge has barely moved over the last few frames."""
        history = track.get("history", [])
        if len(history) < self._REST_HISTORY_FRAMES:
            return False

        max_dist = 0.0
        for i, (x1, y1) in enumerate(history):
            for x2, y2 in history[i + 1:]:
                dist = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
                if dist > max_dist:
                    max_dist = dist
        return max_dist < self._REST_STABILITY_PX

    def _nearest_rest_spot(
        self,
        pos: Tuple[float, float],
        classes: Optional[Set[str]] = None,
    ) -> Optional[Tuple[str, float, float, float]]:
        """Return (class_name, x, y, distance) for the closest rest spot."""
        spots = [
            s for s in self._rest_spots
            if classes is None or s[0] in classes
        ]
        if not spots:
            return None

        cx, cy = pos
        cls, rx, ry = min(
            spots,
            key=lambda s: ((cx - s[1]) ** 2 + (cy - s[2]) ** 2),
        )
        dist = ((cx - rx) ** 2 + (cy - ry) ** 2) ** 0.5
        return cls, rx, ry, dist

    def _distance_to_nearest_rest(
        self,
        pos: Tuple[float, float],
        classes: Optional[Set[str]] = None,
    ) -> Optional[float]:
        """Distance to the closest known resting spot, or None if unknown."""
        spot = self._nearest_rest_spot(pos, classes)
        return None if spot is None else spot[3]

    def _detection_is_on_target(
        self,
        det: Dict[str, Any],
        part_detections: Dict[str, List[Dict]],
    ) -> bool:
        """
        True when this detection already satisfies one of its checkpoint's
        spatial rules.  Used to avoid learning a check position as "rest".
        """
        gauge_class = det["class_name"]

        for config in self._checkpoint_configs.values():
            if config.get("gauge_class") != gauge_class:
                continue

            part_classes = config.get("part_classes") or (
                [config["part_class"]] if config.get("part_class") else []
            )
            for pc in part_classes:
                if pc in part_detections:
                    part_bbox = max(
                        part_detections[pc], key=lambda d: d["confidence"]
                    )["bbox"]
                elif pc in self._last_known_parts:
                    part_bbox = self._last_known_parts[pc]
                else:
                    continue

                valid, _ = self._evaluate_spatial(
                    det["bbox"],
                    part_bbox,
                    config["method"],
                    config.get("overlap_threshold", self.overlap_threshold),
                    config.get(
                        "near_distance_threshold", self.near_distance_threshold
                    ),
                )
                if valid:
                    return True
        return False

    def _detection_is_at_check_area(
        self,
        det: Dict[str, Any],
        part_detections: Dict[str, List[Dict]],
    ) -> bool:
        """
        True when a detection is physically at (or touching) the target area,
        even if the exact spatial rule narrowly fails because of bbox jitter.

        Rest spots must only be learned well away from the part/holes.  Without
        this guard a gauge that is held at the check position but whose box is
        a few pixels outside would be learned as "resting" there, and the
        movement check would then reject it forever.
        """
        gauge_class = det["class_name"]
        gx1, gy1, gx2, gy2 = det["bbox"]
        cx, cy = self._center(det["bbox"])

        for config in self._checkpoint_configs.values():
            if config.get("gauge_class") != gauge_class:
                continue

            part_classes = config.get("part_classes") or (
                [config["part_class"]] if config.get("part_class") else []
            )
            for pc in part_classes:
                if pc in part_detections:
                    part_bbox = max(
                        part_detections[pc], key=lambda d: d["confidence"]
                    )["bbox"]
                elif pc in self._last_known_parts:
                    part_bbox = self._last_known_parts[pc]
                elif pc in self._part_area_memory:
                    part_bbox = self._part_area_memory[pc]
                else:
                    continue

                px1, py1, px2, py2 = part_bbox

                # Any bbox overlap means the gauge is on the target object.
                if min(gx2, px2) > max(gx1, px1) and min(gy2, py2) > max(gy1, py1):
                    return True

                # Also treat a detection whose centre is right next to the
                # target box as "at the check area" (small bbox jitter).
                if (
                    px1 - 20.0 <= cx <= px2 + 20.0
                    and py1 - 20.0 <= cy <= py2 + 20.0
                ):
                    return True

        return False

    def _update_rest_spots(
        self,
        gauge_detections: Dict[str, List[Dict]],
        part_detections: Dict[str, List[Dict]],
    ) -> None:
        """
        Learn where gauges rest: stationary AND not satisfying a check rule.
        Every detection is used (not just the highest-confidence one), because
        the lower duplicate in an 8mm/11mm confusion frame is a real gauge too.
        """
        for dets in gauge_detections.values():
            for det in dets:
                track = self._det_track.get(id(det))
                if track is None or not self._track_is_stable(track):
                    continue
                if self._detection_is_on_target(det, part_detections):
                    continue
                if self._detection_is_at_check_area(det, part_detections):
                    continue

                history = track["history"][-self._REST_HISTORY_FRAMES:]
                spot = (
                    sum(p[0] for p in history) / len(history),
                    sum(p[1] for p in history) / len(history),
                )

                near = self._distance_to_nearest_rest(
                    spot, {det["class_name"]}
                )
                if near is None or near >= self._min_rest_distance:
                    self._rest_spots.append((det["class_name"], spot[0], spot[1]))
                    if len(self._rest_spots) > 80:
                        self._rest_spots.pop(0)

    def _movement_distance(
        self,
        pos: Tuple[float, float],
        classes: Set[str],
        track: Optional[Dict[str, Any]],
        own_class: Optional[str] = None,
    ) -> Optional[float]:
        """
        How far a gauge is from "rest".

        A rest spot belonging to the detection's own class is always trusted.
        Spots belonging to the other member of a confused pair (8mm/11mm) are
        only trusted when this physical track was actually seen resting there;
        otherwise a gauge that has never moved could "borrow" the other
        gauge's rest spot and be accepted.

        The first-seen fallback covers gauges whose resting spot was never
        observed (for example because they rested outside the detection zone).
        """
        # Own-class rest spots are authoritative.
        if own_class is not None:
            own = self._nearest_rest_spot(pos, {own_class})
            if own is not None:
                return own[3]

        # Other-class (pair) rest spots only count if this track visited one.
        if track is not None:
            history = track.get("history", [])
            visited_dists: List[float] = []
            for cls, rx, ry in self._rest_spots:
                if cls not in classes:
                    continue
                if any(
                    ((hx - rx) ** 2 + (hy - ry) ** 2) ** 0.5
                    <= self._min_rest_distance
                    for hx, hy in history
                ):
                    visited_dists.append(
                        ((pos[0] - rx) ** 2 + (pos[1] - ry) ** 2) ** 0.5
                    )
            if visited_dists:
                return min(visited_dists)

        # Last resort: distance from where this physical gauge was first seen.
        if track is not None and track.get("first_pos") is not None:
            fx, fy = track["first_pos"]
            return ((pos[0] - fx) ** 2 + (pos[1] - fy) ** 2) ** 0.5

        return None

    def _detection_is_away_from_rest(self, det: Dict[str, Any]) -> bool:
        """True when this detection has moved far enough from all resting spots."""
        track = self._det_track.get(id(det))
        pair = set(self.gauge_confusion.get("pair", []))
        dist = self._movement_distance(
            self._center(det["bbox"]), pair, track,
            own_class=det["class_name"],
        )
        if dist is None:
            return True
        return dist >= self._min_rest_distance

    def _resolve_gauge_confusion(
        self, gauge_detections: Dict[str, List[Dict]]
    ) -> None:
        """
        HMI rule: when the same frame has two boxes with the same label, keep
        the higher-confidence box as that gauge.  The lower-confidence box is
        the other gauge (8mm <-> 11mm) ONLY if it has moved away from rest;
        otherwise it is treated as a duplicate / false detection and dropped.

        At most one detection per class survives this step.
        """
        pair = list(self.gauge_confusion.get("pair", []))
        if len(pair) != 2:
            logger.warning(f"Invalid gauge_confusion pair: {pair}")
            return

        a, b = pair

        # Work from a snapshot so a box relabelled in one pass is not
        # immediately processed again by the other pass.
        snapshot = {name: list(dets) for name, dets in gauge_detections.items()}
        lists: Dict[str, List[Dict]] = {
            a: list(snapshot.get(a, [])),
            b: list(snapshot.get(b, [])),
        }

        for cls, other in ((a, b), (b, a)):
            dets = lists[cls]
            if len(dets) <= 1:
                lists[cls] = dets[:1]
                continue

            dets.sort(key=lambda d: d.get("confidence", 0.0), reverse=True)
            kept = [dets[0]]
            other_present = bool(lists[other])

            for det in dets[1:]:
                # Two boxes on the same physical object are a duplicate, never
                # a second gauge.  A real second gauge sits in a different area.
                kx, ky = self._center(kept[0]["bbox"])
                dx, dy = self._center(det["bbox"])
                same_object = ((dx - kx) ** 2 + (dy - ky) ** 2) ** 0.5 < self._min_rest_distance

                if (
                    not same_object
                    and not other_present
                    and self._detection_is_away_from_rest(det)
                ):
                    det["class_name"] = other
                    lists[other] = [det]
                    other_present = True
                else:
                    logger.debug(
                        f"[Gauge confusion] Dropped extra '{cls}' "
                        f"(conf={det.get('confidence', 0.0):.2f})"
                    )

            lists[cls] = kept

        for name in (a, b):
            if lists.get(name):
                gauge_detections[name] = lists[name]
            else:
                gauge_detections.pop(name, None)

    # ─── Part-Presence State Machine ─────────────────────────────────────

    def _update_part_state(self, tml_present: bool) -> None:
        """
        Track TML Part presence to drive inspection sessions.

        Uses time-based patience to avoid false triggers and handle variable FPS.
        """
        now = time.time()
        if tml_present:
            self._part_present_frames += 1
            self._part_absent_start_time = 0.0

            # Part just arrived → start new session
            if self.inspection_state == InspectionState.IDLE:
                if self._part_present_frames >= 5:   # 5 frames to confirm arrival
                    self.inspection_state = InspectionState.INSPECTING
                    self._reset_checkpoints()
                    self._session_start_time = now
                    logger.info("TML Part detected — inspection session started.")

        else:
            # Part not in this frame
            self._part_present_frames = 0
            
            if self._part_absent_start_time == 0.0:
                self._part_absent_start_time = now

            absent_duration = now - self._part_absent_start_time

            if self.inspection_state == InspectionState.INSPECTING:
                if absent_duration >= self.part_clear_time_inspecting:
                    # Part has been absent long enough during inspection → treat as removed early
                    overall = self._compute_overall()
                    self._add_log("NG")
                    logger.info(
                        f"TML Part removed before completion. Logging NG. "
                        f"Resetting for next part."
                    )
                    self._reset_checkpoints()
                    self.inspection_state = InspectionState.IDLE
                    self._part_absent_start_time = 0.0

            elif self.inspection_state == InspectionState.COMPLETE:
                if absent_duration >= self.part_clear_time_complete:
                    # Part has been absent long enough after completion → treat as removed properly
                    overall = self._compute_overall()
                    self._add_log("OK")
                    logger.info(
                        f"TML Part removed. Logging OK. "
                        f"Resetting for next part."
                    )
                    self._reset_checkpoints()
                    self.inspection_state = InspectionState.IDLE
                    self._part_absent_start_time = 0.0

    # ─── Gauge Validation ────────────────────────────────────────────────

    def _run_gauge_checks(
        self,
        gauge_detections: Dict[str, List[Dict]],
        part_detections: Dict[str, List[Dict]],
    ) -> None:
        """
        Evaluate each checkpoint against current detections.

        Critical behaviour:
        - Already-latched (OK) checkpoints are skipped completely.
        - When a gauge disappears from frame, grace_count ticks up.
          During grace period, ok_count is preserved (not reset).
          Only after grace_count > GAUGE_GRACE_FRAMES does ok_count reset.

        Pin / Dia mutual-exclusion:
        - The Dia gauge is often physically inside the part area while the
          operator uses it to help seat the Pin gauge.  To prevent a false
          OK latch on Dia during that moment, we detect when BOTH Pin AND Dia
          are simultaneously overlapping the part and suppress Dia's dwell
          accumulation for that frame (treating Dia as if it were absent).
        """
        # ── Pin / Dia mutual-exclusion pre-check ──────────────────────────
        # Detect whether Pin is on top of the DS Thread and Dia is inside the Part
        # so the Dia checkpoint can be suppressed in the same frame.
        pin_on_ds_thread = False
        if "Pin" in gauge_detections and "DS Thread" in part_detections:
            best_pin  = max(gauge_detections["Pin"],  key=lambda d: d["confidence"])
            best_ds_thread = max(part_detections["DS Thread"],   key=lambda d: d["confidence"])
            _pin_valid, _ = self._evaluate_spatial(
                best_pin["bbox"], best_ds_thread["bbox"], "intersects"
            )
            pin_on_ds_thread = _pin_valid

        dia_inside_part = False
        if "Dia" in gauge_detections and "Part" in part_detections:
            best_dia  = max(gauge_detections["Dia"],  key=lambda d: d["confidence"])
            best_part = max(part_detections["Part"],   key=lambda d: d["confidence"])
            _dia_valid, _ = self._evaluate_spatial(
                best_dia["bbox"], best_part["bbox"], "intersects"
            )
            dia_inside_part = _dia_valid
            
        suppress_dia = pin_on_ds_thread and dia_inside_part

        for cp_id, config in self._checkpoint_configs.items():
            result = self.checkpoints[cp_id]

            # Skip latched checkpoints — they stay OK permanently
            if result.status == GaugeStatus.OK:
                result.grace_count = 0
                continue

            method = config["method"]
            gauge_class = config.get("gauge_class")
            part_classes = config.get("part_classes") or (
                [config["part_class"]] if config.get("part_class") else []
            )

            # ── U-Gauge identity branch ─────────────────────────────────────
            # Delegate to the identity tracker for all U Gauge checkpoints.
            if (
                self._u_gauge_tracker is not None
                and gauge_class == self._u_gauge_cfg.get("gauge_class", "U Gauge")
                and "u_gauge_rank" in config
            ):
                self._evaluate_u_gauge_checkpoint(
                    cp_id, config, result, part_detections
                )
                continue
            # ───────────────────────────────────────────────────────────────

            # ── "exists" method: just needs a part area detected ─────────
            if method == "exists":
                visible_areas = [pc for pc in part_classes if pc in part_detections]
                if visible_areas:
                    best = max(
                        (d for pc in visible_areas for d in part_detections[pc]),
                        key=lambda d: d["confidence"],
                    )
                    result.confidence = best["confidence"]
                    result.grace_count = 0
                    result.ok_count += 1
                    if result.ok_count >= self.ok_hold_frames:
                        result.status = GaugeStatus.OK
                        logger.info(f"Checkpoint {result.name} → LATCHED OK")
                    else:
                        result.status = GaugeStatus.UNCERTAIN
                else:
                    self._handle_missing(result, GaugeStatus.NO_AREA)
                continue

            # ── All other methods: need both gauge and part ─────────────
            part_visible = any(pc in part_detections for pc in part_classes)
            part_remembered = any(
                pc in self._last_known_parts for pc in part_classes
            )
            gauge_visible = gauge_class in gauge_detections

            if not part_visible and not part_remembered:
                # The part area itself is not visible AND we have no memory of it — neutral, wait
                self._handle_missing(result, GaugeStatus.NO_AREA)
                continue

            if not gauge_visible:
                # Part visible (or remembered) but gauge not — operator moved gauge away
                self._handle_missing(result, GaugeStatus.NO_GAUGE)
                continue

            # ── Pin / Dia mutual-exclusion ────────────────────────────────
            # If Pin is on DS Thread AND Dia is inside Part,
            # treat Dia as absent for this frame so it cannot falsely latch
            # while the operator is using it to assist with pin insertion.
            if gauge_class == "Dia" and suppress_dia:
                logger.debug(
                    "[Dia suppressed] Pin is on DS Thread and Dia is inside Part — "
                    "Dia dwell blocked this frame."
                )
                self._handle_missing(result, GaugeStatus.NO_GAUGE)
                continue

            # Both gauge and part are in frame (or part is remembered) — evaluate spatial check
            result.grace_count = 0   # reset grace since gauge is visible

            best_gauge = max(gauge_detections[gauge_class], key=lambda d: d["confidence"])

            # Remember every visible target area (used if it gets occluded).
            # A checkpoint may list multiple areas (e.g. Inlet OR Outlet).
            for pc in part_classes:
                if pc in part_detections:
                    self._last_known_parts[pc] = max(
                        part_detections[pc], key=lambda d: d["confidence"]
                    )["bbox"]

            target_bboxes = []
            for pc in part_classes:
                if pc in part_detections:
                    target_bboxes.append(self._last_known_parts[pc])
                elif pc in self._last_known_parts:
                    target_bboxes.append(self._last_known_parts[pc])

            overlap_thresh = config.get("overlap_threshold", self.overlap_threshold)
            near_thresh = config.get("near_distance_threshold", self.near_distance_threshold)

            # A checkpoint passes spatial validation if ANY of its target areas
            # passes (Inlet OR Outlet for the HMI 8mm / 11mm gauges).
            is_valid = False
            overlap = 0.0
            for part_bbox in target_bboxes:
                valid_for_area, overlap_for_area = self._evaluate_spatial(
                    best_gauge["bbox"], part_bbox, method,
                    overlap_thresh, near_thresh,
                )
                is_valid = is_valid or valid_for_area
                overlap = max(overlap, overlap_for_area)

            # ── Movement / resting-position check ─────────────────────────
            if self._track_movement:
                if config.get("require_movement"):
                    curr_pos = self._center(best_gauge["bbox"])

                    # 8mm and 11mm share rest information because the model
                    # may swap their labels.  Other gauges use their own rest.
                    pair = set(self.gauge_confusion.get("pair", []))
                    rest_classes = (
                        {gauge_class} | pair
                        if gauge_class in pair
                        else {gauge_class}
                    )
                    track = self._det_track.get(id(best_gauge))
                    dist_to_rest = self._movement_distance(
                        curr_pos, rest_classes, track,
                        own_class=gauge_class,
                    )

                    # A component that can be pre-installed (Outer Seal) has
                    # no movement reference on the very first cycle after an
                    # app restart.  In that case the spatial check is the only
                    # available evidence; once a rest spot has been observed,
                    # the normal movement rule applies.
                    own_rest = self._nearest_rest_spot(curr_pos, {gauge_class})
                    no_reference = own_rest is None and config.get("persist_rest")
                    if (
                        not no_reference
                        and dist_to_rest is not None
                        and dist_to_rest < self._min_rest_distance
                    ):
                        is_valid = False   # still at rest — not used yet
            elif gauge_class in ["11mm", "13mm"]:
                # Legacy TML movement check — unchanged.
                curr_pos = self._center(best_gauge["bbox"])

                if gauge_class not in self._gauge_history:
                    self._gauge_history[gauge_class] = []

                history = self._gauge_history[gauge_class]
                history.append(curr_pos)
                if len(history) > 5:
                    history.pop(0)

                # ONLY update resting spot if it is NOT currently interacting with the part
                if not is_valid and len(history) == 5:
                    max_dist = max(((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)**0.5 for p1 in history for p2 in history)
                    if max_dist < 20: # Stable/stationary
                        avg_x = sum(p[0] for p in history) / 5
                        avg_y = sum(p[1] for p in history) / 5
                        self._resting_positions[gauge_class] = (avg_x, avg_y)

                # Ensure it has moved away from its last known resting spot
                if gauge_class in self._resting_positions:
                    rest_x, rest_y = self._resting_positions[gauge_class]
                    dist_moved = ((curr_pos[0] - rest_x)**2 + (curr_pos[1] - rest_y)**2)**0.5

                    if dist_moved < 30:  # Hasn't moved from resting spot
                        is_valid = False # Overrule the spatial check!

            result.confidence = best_gauge["confidence"]
            result.overlap = overlap

            if is_valid:
                result.spatial_miss_count = 0
                now = time.time()
                if result.ok_first_seen == 0.0:
                    result.ok_first_seen = now  # start the dwell timer
                elapsed = now - result.ok_first_seen
                result.dwell_progress = min(elapsed / self.ok_hold_seconds, 1.0)
                if elapsed >= self.ok_hold_seconds:
                    result.status = GaugeStatus.OK
                    logger.info(
                        f"Checkpoint {result.name} → LATCHED OK after {elapsed:.1f}s "
                        f"(conf={result.confidence:.2f}, overlap={overlap:.3f})"
                    )
                else:
                    result.status = GaugeStatus.UNCERTAIN
            else:
                # A single noisy bbox must not wipe a nearly-complete dwell.
                # Keep the timer for a few consecutive bad frames, then reset.
                result.spatial_miss_count += 1
                if (
                    result.ok_first_seen > 0.0
                    and result.spatial_miss_count <= self._SPATIAL_GRACE_FRAMES
                ):
                    result.status = GaugeStatus.WAITING
                    continue

                result.ok_first_seen = 0.0
                result.dwell_progress = 0.0
                result.ok_count = max(0, result.ok_count - 1)
                result.status = GaugeStatus.NG

    def _rescue_u_gauges(
        self,
        gauge_detections: Dict[str, List[Dict]],
        check_areas: Optional[List[List[int]]] = None,
    ) -> None:
        """
        Recover a U-gauge that the model reported as 8mm / 11mm.

        The operator uses one gauge at a time, so when a U-gauge is taken to
        the part exactly one rack slot is empty.  The rule is:

          * the highest-confidence box of a pin class that is not at the part
            is the real pin and keeps its label;
          * an extra box of that class at the Inlet/Outlet hole belongs to the
            U-gauge whose rack slot is empty;
          * a box resting exactly on an empty rack slot belongs to that rank.

        If all four U-gauges are in the rack nothing is relabelled, so the real
        8mm / 11mm pins can never be stolen.  If more than one gauge is away
        (not the normal workflow) the one nearest the box is used.
        """
        tracker = self._u_gauge_tracker
        cfg = self._u_gauge_cfg
        if tracker is None or not cfg.get("enabled"):
            return
        # Identity only exists once the four resting slots are known.
        if not tracker.slots_established:
            return

        u_name = cfg.get("gauge_class", "U Gauge")
        confusable = list(cfg.get("confusable_classes", ["8mm", "11mm"]))
        if not confusable:
            return

        scale = tracker.scale
        slot_px = 25.0 * scale       # must be *on* the slot, not merely near it
        dup_px = 30.0 * scale
        areas = list(check_areas or [])

        def _close(
            p: Tuple[float, float], q: Tuple[float, float], limit: float
        ) -> bool:
            return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 <= limit

        def _at_part(pos: Tuple[float, float]) -> bool:
            return any(
                tracker._point_near_check_area(pos, [area]) for area in areas
            )

        occupied = [
            self._center(d["bbox"]) for d in gauge_detections.get(u_name, [])
        ]
        away = tracker.away_ranks(occupied, radius=slot_px)

        for cls in confusable:
            dets = sorted(
                gauge_detections.get(cls, []),
                key=lambda d: d.get("confidence", 0.0),
                reverse=True,
            )
            if not dets:
                continue

            # The real pin is the highest-confidence box that is not at the
            # part.  If every box is at the part, the strongest one is kept:
            # a pin being checked must never be turned into a U-gauge.  This
            # also keeps the rescue safe while a rack gauge is only hidden by
            # the operator's hand.
            real = next(
                (d for d in dets if not _at_part(self._center(d["bbox"]))),
                dets[0],
            )
            real_pos = self._center(real["bbox"])

            keep: List[Dict] = []
            rescued: List[Dict] = []

            for det in dets:
                pos = self._center(det["bbox"])

                if det is real:
                    keep.append(det)
                    continue

                # A second box on the real pin is one gauge, not two.
                if _close(pos, real_pos, dup_px):
                    logger.debug("[UGauge rescue] dropped duplicate '%s' box", cls)
                    continue

                # No U-gauge is away: nothing to attach this box to.
                if not away:
                    keep.append(det)
                    continue

                # Is it resting on an empty U-gauge slot?  Then that rank is
                # the gauge.  Otherwise it only counts when it is at the part.
                prefer = next(
                    (
                        rank for rank in away
                        if tracker.rest_position_for_rank(rank) is not None
                        and _close(
                            pos,
                            tracker.rest_position_for_rank(rank),
                            slot_px,
                        )
                    ),
                    None,
                )
                if prefer is None and not _at_part(pos):
                    keep.append(det)
                    continue

                rank = tracker.adopt_away_gauge(
                    det["bbox"], occupied, away, prefer_rank=prefer
                )
                if rank is None:
                    keep.append(det)
                    continue

                rescued.append(det)
                occupied.append(pos)
                if rank in away:
                    away.remove(rank)
                if prefer is None:
                    # It is at the part, not on its rack slot: this is the
                    # one gauge that is in use.
                    tracker.mark_active(rank)

            # Write the filtered list back so duplicates of the real gauge are
            # dropped.  The remaining boxes keep their label: the 8mm/11mm
            # rule owns that decision, not the U-gauge rescue.
            gauge_detections[cls] = keep
            if not keep:
                gauge_detections.pop(cls, None)
            if not rescued:
                continue

            u_list = gauge_detections.setdefault(u_name, [])
            for det in rescued:
                if det in u_list:
                    continue
                det["class_name"] = u_name
                u_list.append(det)
                logger.info(
                    "[UGauge rescue] '%s' relabelled as '%s' (conf=%.2f)"
                    % (cls, u_name, det.get("confidence", 0.0))
                )

    def _apply_u_gauge_labels(self, u_dets: List[Dict]) -> None:
        """
        Give every U-Gauge detection its real checkpoint name.

        The four U-gauges share one YOLO class ("U Gauge"), but in the UI and
        everywhere in the system they must always be labeled by their 4 distinct
        checkpoint names: Inlet Go, Inlet NoGo, LP Go, LP NoGo.
        Under NO circumstance does any box ever display generic "U Gauge".
        """
        if not u_dets or not self._u_gauge_cp_ids:
            return

        tracker = self._u_gauge_tracker
        names = [
            self.checkpoints[cid].name if cid in self.checkpoints else f"U Gauge {r+1}"
            for r, cid in enumerate(self._u_gauge_cp_ids)
        ]
        rank_map = tracker.rank_map() if tracker else {}

        assigned_ranks = set()
        # 1. Apply rank from tracker if identified
        for det in u_dets:
            rank = rank_map.get(id(det))
            if rank is not None and 0 <= rank < len(names):
                det["display_name"] = names[rank]
                assigned_ranks.add(rank)

        # 2. For any remaining detections (unranked / newly appeared / occluded hold):
        unassigned = [d for d in u_dets if not d.get("display_name")]
        if not unassigned:
            return

        available = [r for r in range(len(names)) if r not in assigned_ranks]

        # Sort unassigned top-to-bottom
        unassigned.sort(key=lambda d: (d["bbox"][1] + d["bbox"][3]) / 2)

        if tracker and tracker.slots_established:
            slots = tracker._slots
            for det in unassigned:
                c = [(det["bbox"][0] + det["bbox"][2]) / 2, (det["bbox"][1] + det["bbox"][3]) / 2]
                best_rank = None
                best_dist = float("inf")
                # First check available ranks with established slots
                for r in available:
                    if r < len(slots) and slots[r] is not None:
                        dist = tracker._dist(c, tuple(slots[r]["pos"]))
                        if dist < best_dist:
                            best_dist = dist
                            best_rank = r
                if best_rank is None and available:
                    best_rank = available[0]
                elif best_rank is None:
                    # All ranks used by duplicates, pick closest slot overall
                    best_rank = min(
                        range(len(names)),
                        key=lambda r: tracker._dist(c, tuple(slots[r]["pos"])) if slots[r] else 9999
                    )

                det["display_name"] = names[best_rank]
                if best_rank in available:
                    available.remove(best_rank)
        else:
            # Before slots established: order top-to-bottom
            for i, det in enumerate(unassigned):
                r = available[i] if i < len(available) else (i % len(names))
                det["display_name"] = names[r]

    def _u_gauge_check_areas(
        self, part_detections: Dict[str, List[Dict]]
    ) -> List[List[int]]:
        """
        Return the Inlet/Outlet boxes that the U-Gauge identity tracker should
        treat as "check areas".

        A U-Gauge whose centre falls inside one of these boxes (plus a margin)
        is being used, and is never learned as a rest position.  Remembered
        boxes are included so a briefly occluded hole still blocks bad
        learning.
        """
        if self._u_gauge_tracker is None:
            return []

        gauge_class = self._u_gauge_cfg.get("gauge_class", "U Gauge")
        area_names: Set[str] = set()
        for cp_id in self._u_gauge_cp_ids:
            cfg = self._checkpoint_configs.get(cp_id)
            if not cfg or cfg.get("gauge_class") != gauge_class:
                continue
            if cfg.get("part_class"):
                area_names.add(cfg["part_class"])
            area_names.update(cfg.get("part_classes") or [])

        areas: List[List[int]] = []
        for name in sorted(area_names):
            if name in part_detections:
                bbox = max(
                    part_detections[name], key=lambda d: d["confidence"]
                )["bbox"]
                self._last_known_parts[name] = bbox
                self._u_gauge_area_memory[name] = bbox
                areas.append(bbox)
            elif name in self._last_known_parts:
                areas.append(self._last_known_parts[name])
            elif name in self._u_gauge_area_memory:
                # Use last session's hole position as a learning guard only.
                areas.append(self._u_gauge_area_memory[name])
        return areas

    def _any_u_gauge_at_check_area(
        self, part_detections: Dict[str, List[Dict]]
    ) -> bool:
        """
        True when any U-gauge currently sits at an Inlet/Outlet hole.

        Used only to avoid calling a checkpoint "pending" while the operator
        is actually using a gauge at a hole but the tracker has not resolved
        its rank yet.  Both holes are considered; the rank→hole mapping is a
        preference, not a hard rule.
        """
        tracker = self._u_gauge_tracker
        if tracker is None:
            return False

        areas = self._u_gauge_check_areas(part_detections)
        if not areas:
            return False

        gauge_class = self._u_gauge_cfg.get("gauge_class", "U Gauge")
        for det in tracker.current_detections():
            if det.get("class_name") != gauge_class:
                continue
            pos = self._center(det["bbox"])
            if tracker._point_near_check_area(pos, areas):
                return True
        return False

    def _u_gauge_fallback_track(
        self, cp_id: int, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Last-resort identity: a U-gauge is physically in this checkpoint's
        hole and its partner gauge (the other Go / NoGo of the same hole) is
        already checked, so this gauge must be the outstanding one.

        Only used when the tracker could not name any gauge for this rank.
        """
        tracker = self._u_gauge_tracker
        if tracker is None:
            return None

        my_rank = int(config["u_gauge_rank"])
        # Only use this fallback when exactly this rank is the one that is
        # away from the rack.  Without this guard a gauge left at the hole
        # after an earlier check could be mistaken for the next gauge.
        occupied = [
            self._center(det["bbox"]) for det in tracker.current_detections()
        ]
        away = tracker.away_ranks(occupied, radius=25.0 * tracker.scale)
        if away != [my_rank]:
            return None

        gauge_class = config.get("gauge_class")
        part_classes = set(
            config.get("part_classes")
            or ([config["part_class"]] if config.get("part_class") else [])
        )

        method = config.get("method", "near")
        near_thresh = config.get(
            "near_distance_threshold", self.near_distance_threshold
        )
        overlap_thresh = config.get(
            "overlap_threshold", self.overlap_threshold
        )
        target_bboxes = [
            self._last_known_parts[pc]
            for pc in part_classes
            if pc in self._last_known_parts
        ]

        for det in tracker.current_detections():
            if det.get("class_name") != gauge_class:
                continue
            for part_bbox in target_bboxes:
                valid, _ = self._evaluate_spatial(
                    det["bbox"], part_bbox, method, overlap_thresh, near_thresh
                )
                if valid:
                    return {
                        "bbox": det["bbox"],
                        "pos": self._center(det["bbox"]),
                        "rank": my_rank,
                        "rest_pos": None,
                        "misses": 0,
                    }
        return None

    def _evaluate_u_gauge_checkpoint(
        self,
        cp_id: int,
        config: Dict[str, Any],
        result: CheckpointResult,
        part_detections: Dict[str, List[Dict]],
    ) -> None:
        """
        Identity-aware check for a single U-Gauge checkpoint.

        The identity tracker now names each physical gauge and follows it, so
        this method simply asks: "where is the gauge with my rank right now,
        and is it at a check hole?"  There is no shared "held gauge" state any
        more — the four gauges are evaluated independently, which is what lets
        Inlet NoGo be checked while Inlet Go is lying on the table.
        """
        tracker = self._u_gauge_tracker
        my_rank: int = config["u_gauge_rank"]

        # ── Remember part areas we can see ───────────────────────────────
        part_class = config.get("part_class") or (
            (config.get("part_classes") or [None])[0]
        )
        part_classes = config.get("part_classes") or (
            [part_class] if part_class else []
        )
        for pc in part_classes:
            if pc in part_detections:
                self._last_known_parts[pc] = max(
                    part_detections[pc], key=lambda d: d["confidence"]
                )["bbox"]

        # ── Part area visibility ──────────────────────────────────────────
        part_visible = any(pc in part_detections for pc in part_classes)
        part_remembered = any(pc in self._last_known_parts for pc in part_classes)

        if not part_visible and not part_remembered:
            self._handle_missing(result, GaugeStatus.NO_AREA)
            return

        # ── Where is this rank's gauge? ──────────────────────────────────
        track = tracker.track_for_rank(my_rank)
        if track is None and tracker.is_occluded(my_rank):
            # A hand/arm is covering the gauge.  The gauge itself has not
            # moved, so keep its identity, position and checkpoint progress.
            # An occlusion is never evidence that the gauge is missing.
            result.grace_count = 0
            if result.status != GaugeStatus.OK:
                result.status = GaugeStatus.WAITING
            return
        if track is None:
            track = self._u_gauge_fallback_track(cp_id, config)
            if track is None:
                # The gauge is no longer at its remembered rack position.
                # If a U-gauge is at an Inlet/Outlet hole it may be the one
                # being used; wait for the tracker to name it instead of
                # guessing.  Otherwise it has simply been laid on the table:
                # keep the checkpoint PENDING (it will be seen again).
                if self._any_u_gauge_at_check_area(part_detections):
                    result.grace_count = 0
                    result.status = GaugeStatus.WAITING
                else:
                    self._handle_missing(result, GaugeStatus.PENDING)
                return
            result.confidence = 0.5     # position-only identification
        else:
            result.confidence = 0.9

        # ── Movement: a gauge still at rest is simply not in use ─────────
        if config.get("require_movement", True):
            rest_pos = track.get("rest_pos")
            if rest_pos is None:
                rest_pos = tracker.rest_position_for_rank(my_rank)
            if rest_pos is not None:
                moved = (
                    (track["pos"][0] - rest_pos[0]) ** 2
                    + (track["pos"][1] - rest_pos[1]) ** 2
                ) ** 0.5
                min_move = (
                    float(self._u_gauge_cfg.get("min_rest_distance", 40))
                    * tracker.scale
                )
                if moved < min_move:
                    self._handle_missing(result, GaugeStatus.PENDING)
                    return

        # ── Spatial check against a check hole ───────────────────────────
        result.grace_count = 0

        method = config.get("method", "near")
        near_thresh = config.get(
            "near_distance_threshold", self.near_distance_threshold
        )
        overlap_thresh = config.get(
            "overlap_threshold", self.overlap_threshold
        )

        target_bboxes = [
            self._last_known_parts[pc]
            for pc in part_classes
            if pc in self._last_known_parts
        ]
        # The rank→hole mapping is a preference.  When cross-hole checking is
        # enabled, a gauge carried to the other Inlet/Outlet hole is still a
        # gauge being used, so it may latch instead of being rejected.
        if self._u_gauge_cfg.get("allow_cross_hole_check", True):
            for area in self._u_gauge_check_areas(part_detections):
                if area not in target_bboxes:
                    target_bboxes.append(area)

        is_valid = False
        overlap = 0.0
        for part_bbox in target_bboxes:
            valid_for_area, overlap_for_area = self._evaluate_spatial(
                track["bbox"], part_bbox, method, overlap_thresh, near_thresh,
            )
            if not valid_for_area and tracker._point_near_check_area(track["pos"], [part_bbox]):
                valid_for_area = True
            is_valid = is_valid or valid_for_area
            overlap = max(overlap, overlap_for_area)

        result.overlap = overlap

        if is_valid:
            result.spatial_miss_count = 0
            now = time.time()
            if result.ok_first_seen == 0.0:
                result.ok_first_seen = now
            elapsed = now - result.ok_first_seen
            result.dwell_progress = min(elapsed / self.ok_hold_seconds, 1.0)
            if elapsed >= self.ok_hold_seconds:
                result.status = GaugeStatus.OK
                logger.info(
                    f"[UGauge] Checkpoint '{result.name}' (rank={my_rank}) "
                    f"→ LATCHED OK after {elapsed:.1f}s"
                )
            else:
                result.status = GaugeStatus.UNCERTAIN
        else:
            # A U-gauge is only "checked" when it reaches a check hole.  A
            # missing or occluded gauge must never raise NG; keep it waiting
            # or pending until the operator actually uses it.
            result.spatial_miss_count += 1
            if (
                result.ok_first_seen > 0.0
                and result.spatial_miss_count <= self._SPATIAL_GRACE_FRAMES
            ):
                result.status = GaugeStatus.WAITING
                return

            result.ok_first_seen = 0.0
            result.dwell_progress = 0.0
            result.ok_count = max(0, result.ok_count - 1)
            if self._any_u_gauge_at_check_area(part_detections):
                result.status = GaugeStatus.WAITING
            else:
                result.status = GaugeStatus.PENDING

    def _handle_missing(self, result: CheckpointResult, missing_status: GaugeStatus) -> None:
        """
        Called when gauge or part area is not detected in this frame.

        Grace period: preserve ok_first_seen for GAUGE_GRACE_FRAMES so that
        the operator can briefly move the gauge between checks without
        losing accumulated dwell progress.
        """
        result.grace_count += 1

        if result.grace_count <= self.gauge_grace_frames:
            # Within grace — keep the last non-OK status visible but
            # don't destroy dwell timer yet
            if result.ok_first_seen > 0.0:
                result.status = GaugeStatus.WAITING
            else:
                result.status = missing_status
        else:
            # Grace expired — operator moved on; clear progress
            result.ok_count = 0
            result.ok_first_seen = 0.0
            result.dwell_progress = 0.0
            result.status = missing_status

    def _check_completion(self) -> None:
        """Auto-advance to COMPLETE when all checkpoints are latched OK."""
        if all(r.status == GaugeStatus.OK for r in self.checkpoints.values()):
            if self.inspection_state == InspectionState.INSPECTING:
                self.inspection_state = InspectionState.COMPLETE
                logger.info("All gauges OK — inspection COMPLETE (PASS).")

    # ─── Spatial Validation Methods ──────────────────────────────────────

    def _evaluate_spatial(
        self,
        gauge_bbox: List[int],
        part_bbox: List[int],
        method: str,
        overlap_threshold: float = None,
        near_distance_threshold: float = None,
    ) -> Tuple[bool, float]:
        overlap_threshold = overlap_threshold if overlap_threshold is not None else self.overlap_threshold
        near_distance_threshold = near_distance_threshold if near_distance_threshold is not None else self.near_distance_threshold

        if method == "inside":
            return self._check_inside(gauge_bbox, part_bbox)
        elif method == "fully_inside":
            return self._check_fully_inside(gauge_bbox, part_bbox)
        elif method == "overlap":
            return self._check_overlap(gauge_bbox, part_bbox, overlap_threshold)
        elif method == "near":
            return self._check_near(gauge_bbox, part_bbox, near_distance_threshold)
        elif method == "intersects":
            return self._check_intersects(gauge_bbox, part_bbox)
        else:
            logger.warning(f"Unknown method: {method}")
            return False, 0.0

    def _check_inside(self, gauge_bbox, part_bbox):
        """Gauge center must be inside the part bounding box."""
        cx, cy = self._center(gauge_bbox)
        px1, py1, px2, py2 = part_bbox
        inside = px1 <= cx <= px2 and py1 <= cy <= py2
        return inside, self.calculate_iou(gauge_bbox, part_bbox)

    def _check_fully_inside(self, gauge_bbox, part_bbox):
        """Every corner of the gauge bbox must be inside the part bounding box."""
        gx1, gy1, gx2, gy2 = gauge_bbox
        px1, py1, px2, py2 = part_bbox
        fully = (px1 <= gx1 and py1 <= gy1 and gx2 <= px2 and gy2 <= py2)
        return fully, self.calculate_iou(gauge_bbox, part_bbox)

    def _check_overlap(self, gauge_bbox, part_bbox, overlap_threshold):
        """Gauge and part bounding boxes must overlap by at least threshold."""
        iou = self.calculate_iou(gauge_bbox, part_bbox)
        return iou >= overlap_threshold, iou

    def _check_near(self, gauge_bbox, part_bbox, near_distance_threshold):
        """Gauge center must be within distance threshold of part center."""
        gcx, gcy = self._center(gauge_bbox)
        pcx, pcy = self._center(part_bbox)
        dist = ((gcx - pcx) ** 2 + (gcy - pcy) ** 2) ** 0.5
        return dist <= near_distance_threshold, self.calculate_iou(gauge_bbox, part_bbox)

    def _check_intersects(self, gauge_bbox, part_bbox):
        """Any overlap between gauge and part bbox counts."""
        iou = self.calculate_iou(gauge_bbox, part_bbox)
        return iou > 0.0, iou

    # ─── Geometry Utilities ──────────────────────────────────────────────

    @staticmethod
    def _center(bbox: List[int]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return (x1 + x2) / 2, (y1 + y2) / 2

    @staticmethod
    def calculate_iou(box_a: List[int], box_b: List[int]) -> float:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return round(inter / union, 4) if union > 0 else 0.0

    # ─── Status Building ─────────────────────────────────────────────────

    def _compute_overall(self) -> OverallStatus:
        """
        Compute overall result status from checkpoint states.

        Logic:
            COMPLETE session           → OK
            All PENDING                → WAITING (no part yet)
            Any explicit NG            → NG
            Otherwise                  → IN_PROGRESS
        """
        if self.inspection_state == InspectionState.COMPLETE:
            return OverallStatus.OK
        if self.inspection_state == InspectionState.IDLE:
            return OverallStatus.WAITING

        statuses = [cp.status for cp in self.checkpoints.values()]
        if all(s == GaugeStatus.PENDING for s in statuses):
            return OverallStatus.WAITING
        if any(s == GaugeStatus.NG for s in statuses):
            return OverallStatus.NG
        return OverallStatus.IN_PROGRESS

    def _build_status(self) -> Dict[str, Any]:
        overall = self._compute_overall()
        completed = sum(1 for cp in self.checkpoints.values() if cp.status == GaugeStatus.OK)
        total = len(self.checkpoints)

        gauges = {}
        for cp_id, result in self.checkpoints.items():
            gauges[f"G{cp_id}"] = {
                "id": cp_id,
                "name": result.name,
                "description": result.description,
                "status": result.status.value,
                "confidence": round(result.confidence, 3),
                "overlap": round(result.overlap, 4),
                "dwell_progress": round(result.dwell_progress, 3),
            }

        return {
            "model": "DFP6",
            "overall_status": overall.value,
            "inspection_state": self.inspection_state.value,
            "scanned_part_no": self.scanned_part_no,
            "completed": completed,
            "total": total,
            "gauges": gauges,
            "glove_warning": self.glove_warning,
            "production": {
                "total_count": self.total_count,
                "pass_count": self.pass_count,
                "fail_count": self.fail_count,
            },
            "recent_logs": [
                {
                    "id": log.log_id,
                    "time": log.timestamp,
                    "part_id": log.part_id,
                    "result": log.result,
                    "cycle_time": log.cycle_time,
                    "bypass": log.bypass,
                }
                for log in self.recent_logs[-5:]
            ],
        }

    def _reset_checkpoints(self) -> None:
        """Clear all per-checkpoint runtime state."""
        remembered_cps = set()
        if self.scanned_part_no and self.scanned_part_no in self.part_memory:
            remembered_cps = self.part_memory[self.scanned_part_no]

        for cp_id, result in self.checkpoints.items():
            if cp_id in remembered_cps:
                result.status = GaugeStatus.OK
                result.confidence = 0.0
                result.overlap = 0.0
                result.dwell_progress = 1.0
                result.ok_count = 0
                result.grace_count = 0
                result.spatial_miss_count = 0
            else:
                result.status = GaugeStatus.PENDING
                result.confidence = 0.0
                result.overlap = 0.0
                result.dwell_progress = 0.0
                result.ok_count = 0
                result.grace_count = 0
                result.spatial_miss_count = 0
            
        # Clear part memory for the new session
        self._last_known_parts.clear()
        self._resting_positions.clear()
        self._gauge_history.clear()

        # Clear physical-gauge tracks so each part starts with fresh tracks.
        self._movement_tracks.clear()
        self._det_track.clear()
        self._frame_index = 0

        # Keep the learned rest spots for components that may already be
        # installed when a new part appears (Outer Seal).  Hand-held gauges
        # (8mm/11mm) start each part with a fresh rest baseline, so a gauge
        # left at a hole from the previous cycle cannot pass without moving.
        persist_rest_classes = {
            cfg.get("gauge_class")
            for cfg in self._checkpoint_configs.values()
            if cfg.get("persist_rest")
        }
        if persist_rest_classes:
            self._rest_spots = [
                s for s in self._rest_spots if s[0] in persist_rest_classes
            ]
        else:
            self._rest_spots.clear()

        # Reset per-session U-Gauge state, but keep learned rest slots: the
        # physical resting rack does not move when a new part is loaded.
        if self._u_gauge_tracker is not None:
            self._u_gauge_tracker.reset_tracking()

    def _add_log(self, result: str) -> None:
        """Record a completed inspection and update production counters."""
        self._log_counter += 1
        self.total_count += 1
        if result == "OK":
            self.pass_count += 1
        else:
            self.fail_count += 1

        cycle_time = 0.0
        if self._session_start_time > 0.0:
            cycle_time = time.time() - self._session_start_time

        part_id = self.scanned_part_no if self.scanned_part_no else f"FWDPF6-{self.total_count:06d}"

        if result == "NG":
            missing = [cp.name for cp in self.checkpoints.values() if cp.status != GaugeStatus.OK]
            if missing:
                result_str = f"Not checked: {', '.join(missing)}"
            else:
                result_str = "NG"
                
            if self.scanned_part_no:
                completed_cps = {cp.checkpoint_id for cp in self.checkpoints.values() if cp.status == GaugeStatus.OK}
                self.part_memory[self.scanned_part_no] = completed_cps
        else:
            result_str = "OK"
            if self.scanned_part_no:
                self.part_memory.pop(self.scanned_part_no, None)

        log = InspectionLog(
            log_id=self._log_counter,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            part_id=part_id,
            result=result_str,
            cycle_time=f"{cycle_time:.1f}s",
            bypass=bool(self.bypass_active),
        )
        self.recent_logs.append(log)
        if len(self.recent_logs) > 50:
            self.recent_logs = self.recent_logs[-50:]

        self.scanned_part_no = None
        logger.info(f"Inspection logged: {log.part_id} → {result_str} (Cycle: {log.cycle_time})")
