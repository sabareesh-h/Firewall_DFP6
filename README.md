# Firewall_DFP6
This is the codebase for firewall_DFP6_SOP Monitoring system

## Barcode scanner (global scan listener)
The scanner stays configured exactly as today and keeps serving the Firewall
software. The SOP app ALSO receives every scan automatically — this is built
into the app itself (`SOP_Compliance/scan_listener.py`), no separate program.

Setup on the shop-floor PC (once):
    pip install pynput

Enable/disable: `SCAN_LISTENER_ENABLED` in `SOP_Compliance/config.py`.
Tunables (burst timing, min length, duplicate debounce) are at the top of
`SOP_Compliance/scan_listener.py`. Accepted barcode characters can be widened
via `ALLOWED_CHARS` there if your labels contain other symbols.

