"""
Unit tests for the scan → profile classifier and the auto-switch config.

Run from SOP_Compliance/:
    python -m pytest tests/ -v
    (or) python tests/test_scan_classifier.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic.scan_classifier import classify_scan


TML_SAMPLES = [
    "0057240710010501D645321026004242",
    "0057240710010501D645321026004501",
]

HMI_SAMPLES = [
    "33100-2A160 0004570KVV42031020",
    "33100-2A160 0003786KVV42031020",
]

# The operator scans other codes too — these must never trigger a switch.
UNRELATED_SAMPLES = [
    "98231-4471",
    "KVV42031020",
    "0004570KVV42031020",
    "12A34567890",
    "",
    "   ",
    "operator note: check seal",
    "33100-2A161 0004570KVV42031020",   # one digit off the HMI prefix
    "0057250710010501D645321026004242",  # one digit off the TML prefix
]


def test_tml_samples():
    for sample in TML_SAMPLES:
        assert classify_scan(sample) == "TML", sample


def test_hmi_samples():
    for sample in HMI_SAMPLES:
        assert classify_scan(sample) == "HMI", sample


def test_unrelated_scans_ignored():
    for sample in UNRELATED_SAMPLES:
        assert classify_scan(sample) is None, sample


def test_tolerance():
    # Leading/trailing whitespace, lowercase, dropped space (scanner quirk).
    assert classify_scan("  0057240710010501D645321026004242  ") == "TML"
    assert classify_scan("33100-2a160 0004570kvv42031020") == "HMI"
    assert classify_scan("33100-2A1600004570KVV42031020") == "HMI"


def test_prefix_table_covers_profiles():
    for profile, prefixes in config.SCAN_PART_PREFIXES.items():
        assert profile in config.PROFILES
        assert prefixes, f"{profile} has no prefix configured"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
