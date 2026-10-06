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

import config as _cfg

logger = logging.getLogger(__name__)

# Build a set of gauge class IDs from config for fast lookup
_GAUGE_CLASS_IDS: Set[int] = set(_cfg.GAUGE_CLASSES.keys())


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


# ─── Validator ───────────────────────────────────────────────────────────────

class GaugeValidator:
    """
    Validates gauge positions against SOP rules.

    Uses a part-presence state machine so that:
    - One physical part = one inspection session.
    - Gauges latch OK and remain OK when moved away.
    - Auto-resets when the part is removed from the table.
    """

    def __init__(
        self,
        checkpoints: List[Dict[str, Any]],
        overlap_threshold: float = 0.15,
        near_distance_threshold: float = 150,
        ok_hold_frames: int = 3,
        ok_hold_seconds: float = 2.0,
        gauge_grace_frames: int = 15,
        part_absent_patience: int = 45,
    ):
        self.overlap_threshold = overlap_threshold
        self.near_distance_threshold = near_distance_threshold
        self.ok_hold_frames = ok_hold_frames
        self.ok_hold_seconds = ok_hold_seconds
        self.gauge_grace_frames = gauge_grace_frames
        self.part_absent_patience = part_absent_patience

        self._checkpoint_configs = {cp["id"]: cp for cp in checkpoints}
        self.checkpoints: Dict[int, CheckpointResult] = {}
        for cp in checkpoints:
            self.checkpoints[cp["id"]] = CheckpointResult(
                checkpoint_id=cp["id"],
                name=cp["name"],
                description=cp["description"],
            )

        # Part-presence state machine
        self.inspection_state = InspectionState.IDLE
        self._part_absent_frames = 0   # how many consecutive frames TML Part missing
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

        # Part memory (for occlusion handling)
        self._last_known_parts: Dict[str, List[int]] = {}
        
        # Memory of completed gauges for returning parts
        self.part_memory: Dict[str, Set[int]] = {}

    def set_part_no(self, part_no: str):
        self.scanned_part_no = part_no
        # Restore memory if we are already inspecting
        if part_no in self.part_memory and self.inspection_state == InspectionState.INSPECTING:
            logger.info(f"Restoring memory for part {part_no}")
            for cp_id in self.part_memory[part_no]:
                if cp_id in self.checkpoints:
                    self.checkpoints[cp_id].status = GaugeStatus.OK
                    self.checkpoints[cp_id].dwell_progress = 1.0

    # ─── Public API ──────────────────────────────────────────────────────

    def validate(self, detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point — called every inference frame.

        1. Update part-presence state machine.
        2. If INSPECTING, validate each unlocked checkpoint.
        3. Check for auto-completion or auto-reset.
        """
        # Separate gauge detections from part detections using config class IDs
        # (not a hardcoded range — class 14 "11mm Gauge" would be missed otherwise)
        gauge_detections: Dict[str, List[Dict]] = {}
        part_detections: Dict[str, List[Dict]] = {}

        for det in detections:
            name = det["class_name"]
            if det["class_id"] in _GAUGE_CLASS_IDS:
                gauge_detections.setdefault(name, []).append(det)
            else:
                part_detections.setdefault(name, []).append(det)

        # ── Step 0: Fix 11mm / 13mm Confusion (The "One Gauge" Rule) ─────
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

        # ── Step 1: Part-presence state machine ──────────────────────────
        tml_present = "Part" in part_detections
        self._update_part_state(tml_present)

        # ── Step 2: Only run gauge checks while INSPECTING ───────────────
        if self.inspection_state == InspectionState.INSPECTING:
            self._run_gauge_checks(gauge_detections, part_detections)
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
        self._part_absent_frames = 0
        self._part_present_frames = 0
        logger.info("Inspection manually reset.")
        return self._build_status()

    def get_status(self) -> Dict[str, Any]:
        return self._build_status()

    # ─── Part-Presence State Machine ─────────────────────────────────────

    def _update_part_state(self, tml_present: bool) -> None:
        """
        Track TML Part presence to drive inspection sessions.

        Uses patience counters to avoid false triggers on YOLO misses.
        """
        if tml_present:
            self._part_present_frames += 1
            self._part_absent_frames = 0

            # Part just arrived → start new session
            if self.inspection_state == InspectionState.IDLE:
                if self._part_present_frames >= 5:   # 5 frames to confirm arrival
                    self.inspection_state = InspectionState.INSPECTING
                    self._reset_checkpoints()
                    self._session_start_time = time.time()
                    logger.info("TML Part detected — inspection session started.")

        else:
            # Part not in this frame
            self._part_present_frames = 0
            self._part_absent_frames += 1

            if self.inspection_state in (InspectionState.INSPECTING,
                                         InspectionState.COMPLETE):
                if self._part_absent_frames >= self.part_absent_patience:
                    # Part has been absent long enough → treat as removed
                    overall = self._compute_overall()
                    result_str = "OK" if self.inspection_state == InspectionState.COMPLETE else "NG"
                    self._add_log(result_str)
                    logger.info(
                        f"TML Part removed. Logging result: {result_str}. "
                        f"Resetting for next part."
                    )
                    self._reset_checkpoints()
                    self.inspection_state = InspectionState.IDLE
                    self._part_absent_frames = 0

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
            part_class = config["part_class"]

            # ── "exists" method: just needs part area detected ─────────
            if method == "exists":
                if part_class in part_detections:
                    best = max(part_detections[part_class], key=lambda d: d["confidence"])
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
            part_visible = part_class in part_detections
            part_remembered = part_class in self._last_known_parts
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
            
            if part_visible:
                best_part  = max(part_detections[part_class],  key=lambda d: d["confidence"])
                part_bbox = best_part["bbox"]
                # Update memory
                self._last_known_parts[part_class] = part_bbox
            else:
                # Use memory for occluded part
                part_bbox = self._last_known_parts[part_class]

            is_valid, overlap = self._evaluate_spatial(
                best_gauge["bbox"], part_bbox, method
            )

            result.confidence = best_gauge["confidence"]
            result.overlap = overlap

            if is_valid:
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
                # Gauge moved away — reset dwell timer and decay
                result.ok_first_seen = 0.0
                result.dwell_progress = 0.0
                result.ok_count = max(0, result.ok_count - 1)
                result.status = GaugeStatus.NG

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
    ) -> Tuple[bool, float]:
        if method == "inside":
            return self._check_inside(gauge_bbox, part_bbox)
        elif method == "fully_inside":
            return self._check_fully_inside(gauge_bbox, part_bbox)
        elif method == "overlap":
            return self._check_overlap(gauge_bbox, part_bbox)
        elif method == "near":
            return self._check_near(gauge_bbox, part_bbox)
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

    def _check_overlap(self, gauge_bbox, part_bbox):
        """Gauge and part bounding boxes must overlap by at least threshold."""
        iou = self.calculate_iou(gauge_bbox, part_bbox)
        return iou >= self.overlap_threshold, iou

    def _check_near(self, gauge_bbox, part_bbox):
        """Gauge center must be within distance threshold of part center."""
        gcx, gcy = self._center(gauge_bbox)
        pcx, pcy = self._center(part_bbox)
        dist = ((gcx - pcx) ** 2 + (gcy - pcy) ** 2) ** 0.5
        return dist <= self.near_distance_threshold, self.calculate_iou(gauge_bbox, part_bbox)

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
            else:
                result.status = GaugeStatus.PENDING
                result.confidence = 0.0
                result.overlap = 0.0
                result.dwell_progress = 0.0
                result.ok_count = 0
                result.grace_count = 0
            
        # Clear part memory for the new session
        self._last_known_parts.clear()

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
        )
        self.recent_logs.append(log)
        if len(self.recent_logs) > 50:
            self.recent_logs = self.recent_logs[-50:]

        self.scanned_part_no = None
        logger.info(f"Inspection logged: {log.part_id} → {result_str} (Cycle: {log.cycle_time})")
