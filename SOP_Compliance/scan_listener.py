"""
Barcode Scan Listener — global, passive keyboard watcher.

WHY THIS EXISTS
---------------
The scanner behaves as a keyboard and always types into whichever window has
focus — in production that is the Firewall software, not this dashboard.  The
old frontend-only scanner pickup (app.js) therefore never saw the scan.

This module listens at the OS level (global hook), so it receives every scan
regardless of which window is focused.

DESIGN PRINCIPLES
-----------------
PASSIVE:  The listener never swallows or blocks a single keystroke.  The
          Firewall software receives its scan exactly as before.

BURST-DETECTION:  Scanners type very fast (< ~80 ms between keys) and finish
          with Enter.  Human typing is slower, so bursts reset and never
          reach the minimum length.  This separates scans from a person
          accidentally typing a part number.

SELF-CONTAINED:  Runs as a daemon thread inside this same application —
          no extra service, no extra install.  Only requires `pip install
          pynput`; if it is missing the app simply logs a warning and keeps
          running (the frontend pickup / manual entry still works).
"""

import logging
import threading
import time
from typing import Callable, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scan_listener")

# ─── Tunables ────────────────────────────────────────────────────────────────
INTER_KEY_DELAY = 0.08      # s — max gap between keys to stay in one scan burst
MIN_SCAN_LENGTH = 6         # n — fewer characters can never be a scan
MAX_SCAN_LENGTH = 40        # n — sanity cap (keyboard noise protection)
DUPLICATE_DEBOUNCE = 2.0    # s — same BARCODE re-delivered within this window is ignored
ALLOWED_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_/., "       # space stays — labels often use it as separator
)


class ScanKeyListener:
    """
    Global barcode scan listener.

    Parameters
    ----------
    on_scan : Callable[[str], None]
        Called from the listener's hook thread with the scanned barcode.
        The callback must be fast and non-blocking (set_part_no is).
    enabled : bool
        Runtime on/off inherited from config.
    """

    def __init__(self, on_scan: Callable[[str], None], enabled: bool = True):
        self.on_scan = on_scan
        self.enabled = enabled

        self._listener = None          # pynput listener instance
        self._running = False
        self._lock = threading.Lock()

        # Burst detection state
        self._buffer = ""
        self._last_key_time = 0.0

        # Duplicate suppression
        self._last_barcode: Optional[str] = None
        self._last_barcode_time = 0.0

        # Enter key constants (resolved when pynput loads in start())
        self._enter_keys = set()

        # Diagnostics for the UI / logs
        self.total_scans = 0
        self.last_scan: Optional[str] = None
        self.last_scan_time: float = 0.0

    # ─── Public API ─────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the global listener.  Returns True when listening."""
        if not self.enabled:
            logger.info("Barcode scan listener is disabled by config.")
            return False

        try:
            from pynput import keyboard as pynput_kb

            # Not every platform/version exposes every special-key constant
            # (e.g. Windows pynput has no Key.numpad_enter).  Use whatever
            # exists, and fall back to the virtual-key check in _is_enter.
            self._enter_keys = {
                k for k in (
                    getattr(pynput_kb.Key, "enter", None),
                    getattr(pynput_kb.Key, "numpad_enter", None),
                )
                if k is not None
            }

            self._listener = pynput_kb.Listener(on_press=self._on_key_press)
            self._listener.daemon = True
            self._listener.start()
            self._running = True
            logger.info(
                "Global barcode scan listener ACTIVE — scans are captured "
                "even when another program (Firewall software) has focus."
            )
            return True
        except Exception as e:
            # NEVER block the application on scanner problems — the app must
            # start fine even when no scanner is connected at all.
            self._listener = None
            self._running = False
            logger.warning(
                "Global scan listener not started (app continues normally): %s", e,
            )
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._running = False
        with self._lock:
            self._buffer = ""
        logger.info("Barcode scan listener stopped.")

    def status(self) -> dict:
        """Expose listener health for the dashboard / debug."""
        return {
            "scan_listener_running": self._running,
            "scans_captured": self.total_scans,
            "last_scan": self.last_scan,
        }

    # ─── Internals ──────────────────────────────────────────────────────────

    def _on_key_press(self, key) -> None:
        """
        pynput hook callback.  Runs on the listener's own thread.

        Rules:
        - Never blocks or suppresses the key (passive) — the focused window,
          i.e. the Firewall software, always receives the scan as normal.
        - Builds a burst buffer; Enter commits it as a candidate barcode.
        - A gap longer than INTER_KEY_DELAY discards the burst (human typing).
        """
        if not self._running:
            return

        now = time.time()

        # Keep the hook thread safe: all state mutations under one lock.
        with self._lock:
            # Non-printable / modifier keys — ignore but reset the gap clock
            char = self._char_of(key)
            if char is None:
                if self._is_enter(key):
                    self._commit_burst(now)
                return

            gap = now - self._last_key_time
            self._last_key_time = now

            if gap > INTER_KEY_DELAY:
                # Too slow — this is typing, not a scan burst.
                self._buffer = ""

            if char not in ALLOWED_CHARS:
                # Scanner labels never contain unusual chars; treat as noise.
                self._buffer = ""
                return

            self._buffer += char

            if len(self._buffer) > MAX_SCAN_LENGTH:
                self._buffer = ""

    # -- Burst commit ────────────────────────────────────────────────────────

    def _commit_burst(self, now: float) -> None:
        """Called with the lock held when Enter ends a burst."""
        code = self._buffer.strip()
        self._buffer = ""

        if len(code) < MIN_SCAN_LENGTH:
            return  # too short to trust — likely keyboard noise

        # Duplicate debounce: scanners often double-fire; the operator may
        # also re-scan the same part within the same second.  Only ignore
        # the accidental instant repeats — a genuine re-scan after the
        # debounce window is a legit "returning part" event.
        if (
            code == self._last_barcode
            and now - self._last_barcode_time < DUPLICATE_DEBOUNCE
        ):
            logger.debug("Duplicate scan ignored: %s", code)
            return

        self._last_barcode = code
        self._last_barcode_time = now
        self.total_scans += 1
        self.last_scan = code
        self.last_scan_time = now

        logger.info("SCAN captured: %s", code)

        # NEVER let one bad callback kill the listener thread.
        try:
            self.on_scan(code)
        except Exception as e:
            logger.error("Scan callback failed for '%s': %s", code, e)

    # -- Key helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _char_of(key) -> Optional[str]:
        """Printable character of a key, or None for control/unknown keys."""
        try:
            return key.char if key.char is not None else None
        except AttributeError:
            return None  # modifier keys (Shift, Ctrl, …) have no .char

    def _is_enter(self, key) -> bool:
        """
        True for any Enter / keypad-Enter.

        Primary: the pynput Key constants gathered in start().  Fallback: the
        Windows virtual-key code for Enter (VK_RETURN = 13), which covers the
        numeric-keypad Enter that the constants may be missing.
        """
        if key in self._enter_keys:
            return True
        try:
            return getattr(key, "vk", None) == 13
        except Exception:
            return False
