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
from typing import List, Dict, Any, Optional, Tuple
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
    ok_count: int = 0           # consecutive OK frames (building towards latch)
    grace_count: int = 0        # frames since gauge last disappeared


@dataclass
class InspectionLog:
    """One completed inspection record."""
    log_id: int
    timestamp: str
    part_id: str
    result: str                 # "OK" or "NG"


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
        gauge_grace_frames: int = 15,
        part_absent_patience: int = 45,
    ):
        self.overlap_threshold = overlap_threshold
        self.near_distance_threshold = near_distance_threshold
        self.ok_hold_frames = ok_hold_frames
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

    # ─── Public API ──────────────────────────────────────────────────────

    def validate(self, detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point — called every inference frame.

        1. Update part-presence state machine.
        2. If INSPECTING, validate each unlocked checkpoint.
        3. Check for auto-completion or auto-reset.
        """
        # Separate gauge detections from part detections
        gauge_detections: Dict[str, List[Dict]] = {}
        part_detections: Dict[str, List[Dict]] = {}

        for det in detections:
            name = det["class_name"]
            if det["class_id"] <= 5:
                gauge_detections.setdefault(name, []).append(det)
            else:
                part_detections.setdefault(name, []).append(det)

        # ── Step 1: Part-presence state machine ──────────────────────────
        tml_present = "TML Part" in part_detections
        self._update_part_state(tml_present)

        # ── Step 2: Only run gauge checks while INSPECTING ───────────────
        if self.inspection_state == InspectionState.INSPECTING:
            self._run_gauge_checks(gauge_detections, part_detections)
            self._check_completion()

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
        """
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
            gauge_visible = gauge_class in gauge_detections

            if not part_visible:
                # The part area itself is not visible — neutral, wait
                self._handle_missing(result, GaugeStatus.NO_AREA)
                continue

            if not gauge_visible:
                # Part visible but gauge not — operator moved gauge away
                self._handle_missing(result, GaugeStatus.NO_GAUGE)
                continue

            # Both gauge and part are in frame — evaluate spatial check
            result.grace_count = 0   # reset grace since gauge is visible

            best_gauge = max(gauge_detections[gauge_class], key=lambda d: d["confidence"])
            best_part  = max(part_detections[part_class],  key=lambda d: d["confidence"])

            is_valid, overlap = self._evaluate_spatial(
                best_gauge["bbox"], best_part["bbox"], method
            )

            result.confidence = best_gauge["confidence"]
            result.overlap = overlap

            if is_valid:
                result.ok_count += 1
                if result.ok_count >= self.ok_hold_frames:
                    result.status = GaugeStatus.OK
                    logger.info(
                        f"Checkpoint {result.name} → LATCHED OK "
                        f"(conf={result.confidence:.2f}, overlap={overlap:.3f})"
                    )
                else:
                    result.status = GaugeStatus.UNCERTAIN
            else:
                # Gauge is in the WRONG position right now — show NG
                # But don't reset ok_count fully: decay slowly so a brief
                # mis-position doesn't undo hard-won ok_count
                result.ok_count = max(0, result.ok_count - 1)
                result.status = GaugeStatus.NG

    def _handle_missing(self, result: CheckpointResult, missing_status: GaugeStatus) -> None:
        """
        Called when gauge or part area is not detected in this frame.

        Grace period: preserve ok_count for GAUGE_GRACE_FRAMES so that
        the operator can briefly move the gauge between checks without
        losing accumulated progress.
        """
        result.grace_count += 1

        if result.grace_count <= self.gauge_grace_frames:
            # Within grace — keep the last non-OK status visible but
            # don't destroy ok_count yet
            if result.ok_count > 0:
                # Operator briefly moved gauge but had some OK frames —
                # show WAITING so operator knows to bring it back
                result.status = GaugeStatus.WAITING
            else:
                result.status = missing_status
        else:
            # Grace expired — operator moved on; clear progress
            result.ok_count = 0
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
            }

        return {
            "model": "DFP6",
            "overall_status": overall.value,
            "inspection_state": self.inspection_state.value,
            "completed": completed,
            "total": total,
            "gauges": gauges,
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
                }
                for log in self.recent_logs[-5:]
            ],
        }

    def _reset_checkpoints(self) -> None:
        """Clear all per-checkpoint runtime state."""
        for result in self.checkpoints.values():
            result.status = GaugeStatus.PENDING
            result.confidence = 0.0
            result.overlap = 0.0
            result.ok_count = 0
            result.grace_count = 0

    def _add_log(self, result: str) -> None:
        """Record a completed inspection and update production counters."""
        self._log_counter += 1
        self.total_count += 1
        if result == "OK":
            self.pass_count += 1
        else:
            self.fail_count += 1

        log = InspectionLog(
            log_id=self._log_counter,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            part_id=f"FWDPF6-{self.total_count:06d}",
            result=result,
        )
        self.recent_logs.append(log)
        if len(self.recent_logs) > 50:
            self.recent_logs = self.recent_logs[-50:]

        logger.info(f"Inspection logged: {log.part_id} → {result}")
