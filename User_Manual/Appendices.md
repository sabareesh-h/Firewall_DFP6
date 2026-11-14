# Appendices (A–E)

**Firewall DFP6 SOP Compliance System — User Manual**  
*Delphi-TVS Technologies Limited*

---

## Table of Contents

- [Appendix A — Glossary](#appendix-a--glossary)
- [Appendix B — File & Folder Reference](#appendix-b--file--folder-reference)
- [Appendix C — API Endpoint Reference](#appendix-c--api-endpoint-reference)
- [Appendix D — Operator Quick-Reference Card](#appendix-d--operator-quick-reference-card)
- [Appendix E — Contact & Escalation List](#appendix-e--contact--escalation-list)

---

## Appendix A — Glossary

| Term | Definition |
|---|---|
| **Barcode Scanner** | USB keyboard-wedge device used to scan part barcodes. Listened to globally at the OS level via `pynput` without stealing focus from the Firewall factory software; automatically switches between TML and HMI profiles. |
| **Blur Zone** | A configurable normalised rectangle (`[x1, y1, x2, y2]`, default `[0.0, 0.0, 0.36, 1.0]`) on the camera frame that is Gaussian-blurred on screen to protect operator privacy and excluded from YOLO detection processing. |
| **Bounding Box** | The semi-transparent coloured rectangle overlay drawn over detected gauges (grey = unchecked, glowing green = dwelling/in progress, green = checked) and parts (faint yellow dashed) in the live dashboard view. |
| **Bypass (Supervisor Bypass)** | An emergency Admin-only override (`POST /bypass`) that forces all checkpoints to report OK automatically so production can continue if the camera/AI fails. Never persisted across restarts. |
| **Checkpoint** | A single required gauge verification step inside an inspection profile (7 checkpoints for TML; 7 checkpoints for HMI). |
| **Compound Status** | Database integer field (`compound_status` in `inspection_logs`): `1` = all gauges checked and inspection PASSED (`OK`); `0` = one or more gauges missing / failed (`NG` / incomplete). |
| **CUDA** | NVIDIA's parallel computing platform required for fast GPU-accelerated YOLO inference (`DEVICE = "0"`). |
| **Cycle Time** | Elapsed time in seconds from part detection until inspection completion, logged to the database as `cycle_time`. |
| **Dynamic Pacing** | Feature (`enable_pacing`) that throttles the inference frame rate during `IDLE` and `COMPLETE` states while running at full speed during `INSPECTING` to reduce unnecessary GPU load. |
| **Focus Mode** | Dashboard camera header toggle that hides unchecked gauges and the part bounding box so only active/checked gauges are highlighted on screen. |
| **Gauge** | A physical inspection tool (e.g., Distance Gauge, Pin Gauge, Dia Gauge, M6, M8, 11mm, 13mm, 8mm, Outer Seal, or U-Gauge) applied by the operator to a part area. |
| **Glove Warning** | A pulsing red banner (`⚠️ SAFETY: Use gloves when handling the part!`) triggered automatically when bare hands (`Hand` class) are detected in the inspection view. |
| **IPC** | Industrial PC — the Windows computer on the shop floor running the SOP Compliance System. |
| **MSSQL** | Microsoft SQL Server (specifically SQL Server 2022 Express, `localhost\SQLEXPRESS`) — the primary database engine used to log inspection records. |
| **NG** | "Not Good" — indicates an incomplete or failed inspection. |
| **ODBC** | Open Database Connectivity — Windows database driver interface (`ODBC Driver 17 for SQL Server` or `SQL Server`) used by `pyodbc` to connect Python to MSSQL. |
| **OK** | Latched pass state for an individual gauge checkpoint after remaining in the required spatial relationship for `OK_HOLD_FRAMES` and `OK_HOLD_SECONDS`. |
| **Part** | The manufactured component placed on the inspection table (`TML Part` or `HMI Part`). |
| **Profile** | A self-contained inspection configuration in `config.py` (`TML` or `HMI`) specifying the YOLO model weights, gauge/part classes, reference images, and checkpoints. |
| **RTSP** | Real-Time Streaming Protocol — network video protocol (over TCP port `554`) used to stream live video from the Hikvision IP camera. |
| **SOP** | Standard Operating Procedure — the mandatory inspection sequence verified by this software. |
| **synced_to_it** | Database flag column (`0` = pending, `1` = synced) reserved for external IT / MES / ERP scripts to track which `inspection_logs` records have been uploaded. |
| **TensorRT** | NVIDIA's model optimisation engine (`.engine` files built via `export_tensorrt.py`) that accelerates YOLO inference on a matching GPU. |
| **U-Gauge** | Four look-alike gauges used on the **HMI** profile (`Inlet Go`, `Inlet NoGo`, `LP Go`, `LP NoGo`). Detected as a single YOLO class `"U Gauge"` and distinguished by their top-to-bottom resting rack slots. |
| **Venv** | Python virtual environment (`venv/` folder) containing isolated Python dependencies so they do not conflict with other system software. |
| **YOLO** | "You Only Look Once" (Ultralytics YOLO) — the deep-learning object detection model that identifies parts, inspection areas, hands, and gauges in each video frame. |

---

## Appendix B — File & Folder Reference

### Root & Utility Files

| File / Folder | Location | Purpose |
|---|---|---|
| `Run_App.bat` | Root folder | Main launcher for source/venv installations: installs VC++ Runtime if missing, validates `venv/` and `best_v2.pt`, opens `http://localhost:8000`, and starts `SOP_Compliance/app.py`. |
| `setup_environment.bat` | Root folder | First-time online setup: creates `venv/`, lets you pick CUDA 12.8 or CPU PyTorch, and installs `requirements.txt`. |
| `Setup_Offline.bat` | Root folder | First-time offline setup: creates `venv/` and installs packages from local `wheels/` folder with no internet. |
| `Setup_MySQL.bat` | Root folder & `Software/` | One-time MySQL setup: creates database `firewall_sop` and user `sop_user` (password `Sop@1234`). |
| `Export_To_USB.bat` | Root folder | Exports full install (`Option 1`, downloads wheels) or code-only update (`Option 2`) to `USB:\Firewall_SOP_Offline`. |
| `Export_Software_To_USB.bat` | Root folder | Copies the standalone `Software/` package to `USB:\Firewall_SOP_Software`. |
| `Update_From_USB.bat` | Root folder | Applies updates from `USB:\Firewall_SOP_Offline` onto an offline IPC. |
| `Update_App.bat` | Root folder | Pulls latest source code via `git pull origin main` (requires internet & Git) and updates pip requirements. |
| `View_MSSQL_Database.bat` | Root folder & `Software/` | Launches `view_database.py` to display the latest 25 inspection logs from SQL Server Express. |
| `View_Database.bat` | Root folder & `Software/` | Displays the latest 20 inspection logs from MySQL (`firewall_sop.inspection_logs`). |
| `view_database.py` | Root folder & `Software/` | Python helper script queried by `View_MSSQL_Database.bat`. |
| `requirements.txt` | Root folder & `Software/` | Required Python packages (`fastapi`, `uvicorn`, `ultralytics`, `opencv-python`, `pynput`, `pyodbc`, `pymssql`, `pymysql`, etc.). |
| `python-3.11.9-amd64.exe` | Root folder & `Software/` | Official Python 3.11.9 (64-bit) Windows installer. |
| `vc_redist.x64.exe` | Root folder & `Software/` | Microsoft Visual C++ Redistributable (x64) installer required by PyTorch and OpenCV. |
| `SQL2022-SSEI-Expr.exe` | Root folder & `Software/` | Microsoft SQL Server 2022 Express installer. |
| `mysql-installer.msi` | Root folder & `Software/` | MySQL Community installer (alternative database). |

### Core Application (`SOP_Compliance/`)

| File / Folder | Location | Purpose |
|---|---|---|
| `app.py` | `SOP_Compliance/` | Main application: FastAPI web server, startup pre-loading of TML/HMI models, RTSP/video inference loop, WebSockets, barcode auto-switching, and all API routes. |
| `config.py` | `SOP_Compliance/` | **Central configuration file** — camera URL, AI thresholds, validation thresholds, barcode prefixes, database settings, server host/port, admin password, and `PROFILES` definitions. |
| `settings.json` | `SOP_Compliance/` | Runtime settings saved when clicking **Save Changes** in Admin Dynamic Settings or toggling the Blur Zone. Overrides `config.py` defaults on startup. |
| `db_logger.py` | `SOP_Compliance/` | Non-blocking background database logger supporting both MSSQL (`pyodbc`/`pymssql`) and MySQL (`pymysql`), with auto-table creation and retry queue. |
| `scan_listener.py` | `SOP_Compliance/` | Passive global OS keyboard hook (`pynput`) using burst detection to capture barcode scans even while factory Firewall software is in focus. |
| `Hikvision.py` | `SOP_Compliance/` | Standalone Hikvision RTSP test script with OpenCV preview (for camera testing outside the web app). |
| `export_tensorrt.py` | `SOP_Compliance/` | Compiles a `.pt` YOLO model into a GPU-specific TensorRT `.engine` file for faster inference. |
| `camera/camera.py` | `SOP_Compliance/camera/` | Thread-safe capture handler supporting `"live"` (RTSP-over-TCP or webcam), `"video"` (looping MP4), and `"demo"` modes. |
| `detection/yolo_detector.py` | `SOP_Compliance/detection/` | Ultralytics YOLO wrapper (prefers `.engine` if present, falls back to `.pt`) with class-name overrides and deadzone filtering. |
| `logic/gauge_validator.py` | `SOP_Compliance/logic/` | Core SOP state machine (`IDLE` → `INSPECTING` → `COMPLETE`), spatial geometry checks, U-gauge rack identity tracker, glove warning, and DB logging trigger. |
| `logic/scan_classifier.py` | `SOP_Compliance/logic/` | Matches scanned barcodes against `config.SCAN_PART_PREFIXES` (`005724` → `TML`, `33100-2A160` → `HMI`). |
| `frontend/index.html` | `SOP_Compliance/frontend/` | Web dashboard HTML layout, Admin modal, and smart-box CSS styling. |
| `frontend/app.js` | `SOP_Compliance/frontend/` | Dashboard client JavaScript: WebSocket status & video rendering, Admin PIN check, Dynamic Settings UI, and keyboard-wedge fallback listener. |
| `frontend/style.css` | `SOP_Compliance/frontend/` | Dashboard layout and theme stylesheet. |
| `models/` | `SOP_Compliance/models/` | Stores YOLO weights (`best_v2.pt` for TML, `best_hmi_v2.pt` for HMI, and optional `.engine` files). |
| `Reference_gauge_images/` | `SOP_Compliance/` | PNG images for gauges and `Logo.png` served at `/reference_images/`. |
| `tests/` | `SOP_Compliance/tests/` | Automated unit tests (`test_bypass.py`, `test_dia_gauge.py`, `test_scan_classifier.py`, `test_u_gauge_tracking.py`). |
| `video.mp4` | `SOP_Compliance/` | Local fallback test video used when `DEFAULT_SOURCE = "video"`. |

### Standalone Portable Package (`Software/`)

| File / Folder | Location | Purpose |
|---|---|---|
| `Run_Software.bat` | `Software/` | 1-click portable launcher using embedded `Software/python/python.exe` and compiled `.pyc` files. |
| `Firewall_SOP.exe` | `Software/` | Executable launcher inside the portable package. |
| `python/` | `Software/` | Pre-packaged portable Python 3.11 environment with CUDA PyTorch and VC++ DLLs. |
| `SOP_Compliance/` | `Software/` | Compiled application (`.pyc` bytecode), models, frontend, and reference images. |
| `wheels/` | `Software/` | Pre-downloaded `.whl` files for offline package installation. |
| `README.md` | `Software/` | Quick-start guide for the standalone portable package. |

---

## Appendix C — API Endpoint Reference

Base URL: `http://<IPC-IP-address>:8000` (default local: `http://localhost:8000`).  
All routes below are verified directly in `SOP_Compliance/app.py`.

### HTTP REST Endpoints

| Method | Endpoint | Description | Request Body / Notes | Auth / PIN |
|---|---|---|---|---|
| `GET` | `/` | Serves the main web dashboard (`frontend/index.html`) | — | None |
| `GET` | `/video` | MJPEG live video stream (`multipart/x-mixed-replace`) | Fallback stream when WebSocket video is not used | None |
| `GET` | `/status` | Returns full JSON status (checkpoints, overall result, active profile, camera/detector connection, blur zone, bypass state, scan listener stats) | Also acts as fallback when `/ws` disconnects | None |
| `GET` | `/profiles` | Lists all configured profiles (`TML`, `HMI`) and the currently active one | Returns `display_name` and `num_checkpoints` | None |
| `GET` | `/settings` | Returns active runtime settings (`confidence_threshold`, `overlap_threshold`, `near_distance_threshold`, `ok_hold_seconds`, `gauge_configs`, `visual_deadzone`, `blur_enabled`, `blur_zone`) | — | None |
| `POST` | `/reset` | Resets current inspection cycle to `IDLE` and clears scan latch | Empty body | None |
| `POST` | `/reset_counter` | Resets session `total_count`, `pass_count`, `fail_count`, and recent UI logs | Empty body | None |
| `POST` | `/switch_profile` | Immediately switches active inspection profile (`TML` ↔ `HMI`) | `{"profile": "TML"}` or `{"profile": "HMI"}` | None (UI button) |
| `POST` | `/bypass` | Enables or disables Supervisor Bypass | `{"enabled": true, "password": "<ADMIN_PASSWORD>"}` or `{"enabled": false}` | **Backend checks `config.ADMIN_PASSWORD` when enabling**; disabling requires no PIN |
| `POST` | `/source` | Switches video capture source at runtime | `{"mode": "live" / "video" / "demo", "source": "<optional path/URL>"}` | None |
| `POST` | `/set_part_no` | Manually sets the part number on the active validator | `{"part_no": "005724..."}` | None |
| `POST` | `/settings/confidence` | Toggles confidence score display on video overlays | `{"show": true / false}` | None |
| `POST` | `/settings/pacing` | Toggles Dynamic Pacing (FPS throttling when idle/complete) | `{"enable": true / false}` | None |
| `POST` | `/settings/blur` | Updates blur zone toggle and/or normalised rectangle `[x1, y1, x2, y2]` and persists to `settings.json` | `{"enabled": true, "zone": [0.0, 0.0, 0.36, 1.0]}` | None |
| `POST` | `/settings` | Updates global thresholds, per-gauge settings, deadzone, and blur zone; saves to `settings.json` | JSON matching `SettingsUpdate` schema | UI protected by Admin PIN modal |
| `POST` | `/settings/reset` | Deletes `settings.json` and restores all settings to `config.py` defaults | Empty body | UI protected by Admin PIN modal |

### WebSocket & Static Mounts

| Protocol / Mount | Path | Purpose |
|---|---|---|
| `WS` | `/ws` | Real-time JSON status broadcast every `0.1s` (supports `"ping"` / `"pong"` keep-alive) |
| `WS` | `/ws/video` | Real-time binary JPEG video frame stream (up to 20 FPS) rendered onto `#video-canvas` |
| Static | `/static/*` | Serves files from `SOP_Compliance/frontend/` (`style.css`, `app.js`) |
| Static | `/reference_images/*` | Serves gauge reference images and `Logo.png` from `SOP_Compliance/Reference_gauge_images/` |

---

## Appendix D — Operator Quick-Reference Card

> **Print and laminate this page and keep it next to the shop-floor inspection monitor.**

---

### SOP COMPLIANCE SYSTEM — OPERATOR QUICK REFERENCE (`Fire Wall DFP6`)

**1. Start of Check / New Part**
- Confirm browser is open at **`http://localhost:8000`** and **`System Online`** dot is green.
- Confirm the **Camera** is in **`Live Camera`** mode (top-left dropdown) and **Bypass banner is NOT visible**.
- **Scan the part barcode**:
  - Starts with **`005724`** → **TML Part**
  - Starts with **`33100-2A160`** → **HMI Part**
- Place the part flat inside the camera view (right side of screen — the left blur zone is normal).
- **Safety:** Always wear gloves. If the red **`⚠️ SAFETY: Use gloves when handling the part!`** banner flashes, put on gloves immediately.

**2. Required Gauges (Wait for each to turn Green / Checked)**

| TML Part (7 Checkpoints) | HMI Part (7 Checkpoints) |
|---|---|
| 1. **Distance Gauge** — inside TML Part body | 1. **11mm Gauge** — near Inlet or Outlet Hole |
| 2. **Pin Gauge** — overlapping DS Thread | 2. **8mm Gauge** — near Inlet or Outlet Hole |
| 3. **Dia Gauge** — near DS Thread | 3. **Outer Seal** — inside HMI Part body |
| 4. **M6 Thread** — near Top Hole | 4. **Inlet Go** *(U-Gauge #1 Top)* — near Inlet Hole |
| 5. **M8 Thread** — near Top Hole | 5. **Inlet NoGo** *(U-Gauge #2)* — near Inlet Hole |
| 6. **11mm Gauge** — near Outlet | 6. **LP Go** *(U-Gauge #3)* — near Outlet Hole |
| 7. **13mm Gauge** — near Inlet | 7. **LP NoGo** *(U-Gauge #4 Bottom)* — near Outlet Hole |

> **U-Gauge Rule (HMI):** Always pick up and return each U-Gauge to its exact **top-to-bottom slot** in the rack!

**3. Reading the Final Result**
- **Green `PASS`** (`7 / 7 Completed`) → Remove part and send to next station. Wait for screen to return to `Waiting for Part`.
- **Red `FAIL`** → Re-check any missing gauge. If still `FAIL`, **do not pass the part** — call your Supervisor.

**4. Quick Troubleshooting (When to Call Help)**
- **Red `BYPASS ACTIVE` banner visible** → Call Supervisor immediately to turn bypass OFF.
- **Wrong Part Type showing** → Re-scan barcode, or click **TML / HMI** under *Current Application → Part Type*.
- **Black / frozen camera or blank page** → Do **not** close the black terminal window; call Maintenance / IT.

**Emergency Shop-Floor Contacts:**  
Supervisor: `____________________` | Maintenance / IT: `____________________`

---

## Appendix E — Contact & Escalation List

Fill in this table before deploying the system to production and keep a copy inside the station binder and IT handover folder.

| Role | Name | Phone / Extension | Email | When to Contact |
|---|---|---|---|---|
| **Software Maintainer / IT Engineer** | | | | Startup errors, IPC hardware, `config.py` edits, USB updates, network/firewall issues |
| **Production Supervisor** | | | | Repeated NG parts, emergency Supervisor Bypass activation/deactivation, line stops |
| **Quality Engineer** | | | | Inspection log audits, missed/false detections, QMS retention compliance |
| **Camera / Hardware Technician** | | | | Hikvision camera alignment, PoE/power loss, lens damage, barcode scanner replacement |
| **Database Administrator (DBA)** | | | | SQL Server / MySQL failures, database backups/restores, `synced_to_it` MES/ERP sync |
| **Software Developer / AI Team** | | | | YOLO model retraining, TensorRT `.engine` rebuilds, adding new part profiles, software bugs |

---

*End of Appendices — Firewall DFP6 SOP Compliance System User Manual*
