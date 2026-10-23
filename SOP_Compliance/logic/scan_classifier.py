"""
Scan → profile classifier.

WHY THIS EXISTS
---------------
The operator scans several different codes per part, and the scanner is a
keyboard wedge shared with the Firewall software.  Only ONE of those codes
identifies the application (TML / HMI).  This module decides, from the raw
scanned string alone, which inspection profile that scan belongs to.

RULES (all in config.SCAN_PART_PREFIXES)
----------------------------------------
* Match is by PREFIX — the digits that follow may vary freely per part.
* Matching is done on a normalised copy: surrounding and internal whitespace
  is removed and the text is uppercased, so a scanner that drops the space in
  an HMI code (or sends lowercase) still matches.
* No length checks and no position checks: a prefix that is not configured
  can never match, which is exactly how the operator's other two codes are
  rejected.

The module is pure — no state, no side effects — so it is trivial to test.
"""

from typing import Optional

import config


def _normalise(value: str) -> str:
    """Uppercase and drop every whitespace character (safe for prefix match)."""
    return "".join(str(value or "").split()).upper()


def classify_scan(raw: str) -> Optional[str]:
    """
    Return the profile name ("TML", "HMI", …) the scan belongs to, or None.

    None means "not an application code" — the caller must then change
    nothing at all.
    """
    code = _normalise(raw)
    if not code:
        return None

    for profile, prefixes in config.SCAN_PART_PREFIXES.items():
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        for prefix in prefixes:
            normalised_prefix = _normalise(prefix)
            if normalised_prefix and code.startswith(normalised_prefix):
                return profile.upper()

    return None


def profiles_for_prefixes() -> dict:
    """Diagnostic helper: the active prefix table (for logs / debug screens)."""
    return {p: list(v) if not isinstance(v, str) else [v]
            for p, v in config.SCAN_PART_PREFIXES.items()}
