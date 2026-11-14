# Chapter 10 — Troubleshooting

**Firewall DFP6 SOP Monitoring System**
*Delphi-TVS Technologies Limited*

---

## Overview

> **📝 NOTE:** This chapter is intended for **IT engineers and maintenance staff**. Operators who encounter a problem should contact their supervisor or maintenance team rather than attempting to diagnose the issue themselves.

Use the table below to quickly find the section that matches the symptom you are experiencing.

| Symptom | Section |
|---------|---------|
| Application won't start / crashes on launch | [10.1](#101-application-wont-start) |
| Camera feed shows black screen or won't connect | [10.2](#102-camera-feed-is-black--not-connecting) |
| Barcode scanner not being detected / not switching profiles | [10.3](#103-barcode-scanner-not-being-detected) |
| Inspection results not appearing in the database | [10.4](#104-database-not-logging-results) |
| AI detection is wrong, missing, or unreliable | [10.5](#105-ai-detection-is-incorrect-or-missing-detections) |
| Browser shows blank page or "Connection Refused" | [10.6](#106-browser-shows-blank-page-or-connection-refused) |
| Supervisor bypass is stuck ON | [10.7](#107-supervisor-bypass-left-on-accidentally) |

---

## 10.1 Application Won't Start

### Problem: "Virtual environment not found!" error

| | Detail |
|-|--------|
| **Error Message** | `Virtual environment not found! Please run setup_environment.bat first.` |
| **Likely Cause** | `setup_environment.bat` was not run, or it ran but completed with errors |

**Solution:**
1. Close the command window showing the error.
2. In the `SOP_Compliance` folder, double-click **`setup_environment.bat`**.
3. Watch the output — it must finish without any `ERROR` lines.
4. Once complete, double-click **`Run_App.bat`** again.

> **📝 NOTE:** If `setup_environment.bat` itself fails, check whether Python is correctly installed (see the next problem below).

---

### Problem: Python not found / `'python' is not recognized`

| | Detail |
|-|--------|
| **Error Message** | `'python' is not recognized as an internal or external command` |
| **Likely Cause** | Python 3.11 is not installed, or it was installed without being added to the system PATH |

**Solution:**
1. Locate **`python-3.11.9-amd64.exe`** (on the USB drive or in the software folder).
2. Run the installer.
3. On the first screen of the installer, make sure **"Add Python 3.11 to PATH"** is checked. This is unchecked by default and must be enabled manually.
4. Complete the installation.
5. **Restart the IPC.**
6. Run **`Run_App.bat`** again.

> **⚠️ WARNING:** If Python was installed without the PATH option, the application will never start until Python is reinstalled correctly. Do not attempt to manually edit the PATH variable unless you are confident in doing so — reinstalling Python is safer.

---

### Problem: DLL Error on Startup (`vcruntime`, `msvcp`, or `[WinError 1114]` on `c10.dll`)

| | Detail |
|-|--------|
| **Error Message** | `The code execution cannot proceed because VCRUNTIME140.dll was not found`, or `[WinError 1114]` loading PyTorch `c10.dll` |
| **Likely Cause** | Microsoft Visual C++ Redistributable Runtime is not installed, or NVIDIA GeForce GPU driver is missing/outdated |

**Solution:**
1. Locate **`vc_redist.x64.exe`** (on the USB drive or in the software/root folder).
2. Run it and click **Install** / **Repair**.
3. If using the CUDA build on an NVIDIA GPU, verify the NVIDIA driver is installed by opening Command Prompt and running `nvidia-smi` (for RTX 4070 GPUs, confirm driver version `550+`). Install the official NVIDIA GeForce driver if `nvidia-smi` fails.
4. **Restart the IPC.**
5. Run **`Run_App.bat`** (or **`Run_Software.bat`**) again.

---

### Problem: "Model file not found" warning but app continues

| | Detail |
|-|--------|
| **Behaviour** | App starts but detection does not work. Command window shows a model-related warning. |
| **Likely Cause** | The `.pt` model files are missing from the `models\` folder |

**Solution:**
1. Navigate to `SOP_Compliance\models\` on the IPC.
2. Check whether the following files exist:
   - `best_v2.pt` (required for TML Part profile)
   - `best_hmi_v2.pt` (required for HMI Part profile)
3. If either file is missing, copy it from the developer PC or USB drive into this folder.
4. Restart the application with **`Run_App.bat`**.

---

### Problem: Port 8000 Already in Use

| | Detail |
|-|--------|
| **Error Message** | `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000): only one usage of each socket address` |
| **Likely Cause** | A previous instance of the app was not stopped cleanly, or another application is using port 8000 |

**Solution (Option A — Kill the existing process):**
1. Press **Ctrl + Shift + Esc** to open Task Manager.
2. Click the **Details** tab.
3. Find any process named **`python.exe`**.
4. Right-click it → **End Task**.
5. Run **`Run_App.bat`** again.

**Solution (Option B — Change the port):**
1. Open `SOP_Compliance\config.py` in Notepad.
2. Find the line `PORT = 8000` and change it to a free port, e.g., `PORT = 8001`.
3. Save the file.
4. Run **`Run_App.bat`**.
5. Update the browser URL to `http://localhost:8001`.

---

## 10.2 Camera Feed Is Black / Not Connecting

The dashboard shows a black or frozen video panel instead of a live camera image.

Work through the following checks in order:

### Check 1 — Source Mode

1. In the **top-left dropdown of the dashboard header**, ensure **`Live Camera`** is selected (not `Pre-recorded Video` or `Demo Mode`).
2. Also check `DEFAULT_SOURCE` in `SOP_Compliance\config.py`:
   ```python
   DEFAULT_SOURCE = "live"     # Valid values: "live", "video", or "demo" (NOT "camera")
   ```
   If you switched modes in the dashboard dropdown, the app connects to `LIVE_CAMERA_URL`.

---

### Check 2 — RTSP URL

The camera is accessed via an RTSP URL. Verify the URL in `config.py`:

```python
LIVE_CAMERA_URL = "rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101"
```

| Part of the URL | What to Check |
|-----------------|---------------|
| `admin` | Camera login username — confirm with camera administrator |
| `Wedit@2024` | Camera login password — confirm with camera administrator |
| `192.168.1.66` | Camera IP address — must match the actual camera's IP on the LAN |
| `554` | RTSP port — standard default; change only if the camera uses a custom port |

---

### Check 3 — Network Connectivity

Open a **Command Prompt** window and ping the camera's IP address:

```
ping 192.168.1.66
```

| Ping Result | Meaning | Action |
|-------------|---------|--------|
| Replies received (e.g., `Reply from 192.168.1.66`) | Camera is reachable on the network | Proceed to Check 4 |
| `Request timed out` or `Destination host unreachable` | Camera cannot be reached | Check camera power, network cable, switch, and confirm the IPC Ethernet adapter has a static IP in the same subnet (e.g., `192.168.1.100`, subnet mask `255.255.255.0` via `ncpa.cpl`) |

---

### Check 4 — Windows Firewall (RTSP)

RTSP uses TCP/UDP port **554**. Confirm that the Windows Firewall on the IPC is not blocking outgoing connections on this port.

1. Press **Win + R**, type `wf.msc`, press Enter (Windows Defender Firewall with Advanced Security).
2. Check **Outbound Rules** for any rule blocking port 554.
3. If a blocking rule exists, disable it or create an exception for the RTSP stream.

---

### Quick Test — Confirm App Logic Is Working

If you are unsure whether the problem is the camera or the application:

1. In the dashboard header dropdown, select **`Pre-recorded Video`** (or set `DEFAULT_SOURCE = "video"` in `config.py` and restart).
2. If the video plays correctly in the dashboard, the **application is working** — the issue is specific to the camera connection.
3. Switch back to **`Live Camera`** after testing.

### Issue: Pre-recorded Video Runs Slowly (0.8× Speed / Delayed)

- **Cause:** Windows default 15.6 ms timer resolution throttling sleep intervals in Balanced/Power Saver mode.
- **Solution:** Press `Win + R` → type `powercfg.cpl` → select **High Performance** (or **Ultimate Performance**). No restart required.

---

## 10.3 Barcode Scanner Not Being Detected

The barcode scanner is a keyboard-wedge USB device. Scanning a barcode should automatically switch the inspection profile on the dashboard.

### Check 1 — Scan Listener Enabled

Open `SOP_Compliance\config.py` and confirm:

```python
SCAN_LISTENER_ENABLED = True
```

If it reads `False`, change it to `True`, save the file, and restart the application.

---

### Check 2 — `pynput` Package Installed

The scan listener depends on the `pynput` Python library. To verify it is installed:

1. Open a Command Prompt.
2. Navigate to the `SOP_Compliance` folder.
3. Activate the virtual environment:
   ```
   venv\Scripts\activate
   ```
4. Run:
   ```
   pip show pynput
   ```
5. If `pynput` is **not found**, install it:
   ```
   pip install pynput
   ```
6. Restart the application.

---

### Check 3 — USB Connection

1. Confirm the barcode scanner is physically plugged into a USB port on the IPC.
2. Try unplugging and re-plugging the scanner.
3. Test the scanner in a text editor (e.g., Notepad) — scanning a barcode should type the barcode number into the text field. If nothing appears, the scanner itself may be faulty.

---

### Check 4 — Barcode Prefix

The system only responds to barcodes that start with a recognised prefix. All other barcodes are **silently ignored by design**.

| Part Profile | Required Barcode Prefix |
|-------------|------------------------|
| TML Part | `005724` |
| HMI Part | `33100-2A160` |

If your barcodes do not start with these prefixes, the scan listener will not switch the profile. Contact the development team if new prefixes need to be added to `config.py`.

---

## 10.4 Database Not Logging Results

Inspection results are saved to the `inspection_logs` table in the `firewall_sop` database. If records are not appearing:

### Check 1 — Database Logging Enabled

Open `SOP_Compliance\config.py` and confirm:

```python
DB_ENABLED = True
```

If `False`, change to `True`, save, and restart the application.

---

### Check 2 — Database Credentials

Verify that all database connection settings in `config.py` are correct:

| Setting | Description | Default / Example |
|---------|-------------|-------------------|
| `DB_HOST` | Server hostname or IP address | `localhost\\SQLEXPRESS` (MSSQL) or `localhost` (MySQL) |
| `DB_USER` | Database username | `""` (empty = Windows Authentication for MSSQL) or `sop_user` (MySQL) |
| `DB_PASSWORD` | Database password | `""` (empty = Windows Auth for MSSQL) or `Sop@1234` (MySQL) |
| `DB_NAME` | Database name | `firewall_sop` |
| `DB_DRIVER` | ODBC driver name (MSSQL only) | `ODBC Driver 17 for SQL Server` |

---

### Check 3 — Database Service Running

The database engine must be running as a Windows service.

**For Microsoft SQL Server Express:**
1. Press **Win + R**, type `services.msc`, press **Enter**.
2. Find **"SQL Server (SQLEXPRESS)"** in the list.
3. If its status is not "Running", right-click it and select **Start**.

**For MySQL:**
1. Press **Win + R**, type `services.msc`, press **Enter**.
2. Find **"MySQL80"** (or the version installed on your system).
3. If its status is not "Running", right-click it and select **Start**.

---

### Check 4 — ODBC Driver (MSSQL Only)

If using Microsoft SQL Server, the ODBC Driver 17 for SQL Server must be installed on the IPC.

1. Press **Win + R**, type `odbcad32`, press **Enter** (ODBC Data Source Administrator).
2. Click the **Drivers** tab.
3. Look for **"ODBC Driver 17 for SQL Server"** in the list.
4. If it is **not listed**, download and install it from Microsoft's official website, or run the installer from the USB drive if it was included.
5. Ensure that `DB_DRIVER` in `config.py` exactly matches the driver name as it appears in the ODBC administrator.

---

### Check 5 — Table Does Not Exist Yet

The application automatically creates the `inspection_logs` table the first time it connects to the database. If the table is missing:

1. Simply **restart the application** — it will re-create the table automatically on startup.
2. No manual SQL commands are required.

---

### Check 6 — Read the Error in the Command Window

The application prints all database errors to the command window. Look for lines containing `db_logger` — they will show the exact error message and the line of code where the failure occurred. This information is essential for diagnosing connection failures.

> **📝 NOTE:** Copy the error text and share it with the development team when requesting support.

---

## 10.5 AI Detection Is Incorrect or Missing Detections

### Issue: Gauge detections are missing or unreliable

Work through the following checks:

| Check | Setting / Action | Details |
|-------|-----------------|---------|
| Confidence threshold | `CONFIDENCE_THRESHOLD` in `config.py` | Try lowering from e.g. `0.10` to `0.05`. Note: lower values may increase false positives. |
| GPU in use | `DEVICE` in `config.py` | Should be `"0"` (first GPU). If set to `"cpu"`, detection is slower and may time out. |
| Correct model loaded | Check `models\` folder | Verify `best_v2.pt` (TML) and `best_hmi_v2.pt` (HMI) are present and not zero-byte files. |
| Lighting conditions | Physical inspection | Ensure the inspection area is **evenly and brightly lit**. Shadows, glare, and reflections are the most common cause of detection failures. |
| Camera alignment | Physical inspection | The camera should point **straight down** at the inspection surface. Any tilt or angle affects detection accuracy. |
| Part in frame | Physical inspection | The entire part must be visible within the camera's field of view, not cut off at the edges. |

---

### Issue: Detections appear in the wrong area of the frame

- If detections are appearing outside the inspection area (for example, on the operator's hands or clothing), **increase the blur zone** in **⚙️ Admin → Dynamic Settings → Privacy Blur Zone** (`X1 (%)`, `Y1 (%)`, `X2 (%)`, `Y2 (%)`), or in `config.py` using a 4-element normalised list `[x1, y1, x2, y2]`:
  ```python
  DEFAULT_BLUR_ZONE = [0.0, 0.0, 0.45, 1.0]   # Increase X2 (e.g. from 0.36 to 0.45) to extend rightwards
  ```
- Any detection whose centre falls inside an active blur zone is ignored. Note that if `SOP_Compliance\settings.json` exists, it overrides `config.py` defaults — use Admin **Reset** or edit through the Admin UI.

---

### Issue: Inspection always shows FAIL even when gauges are checked

1. Verify that the correct profile (`TML` or `HMI`) is active on the dashboard.
2. Confirm that the gauge check sequence (and U-gauge rack positions for HMI) matches the required procedure.
3. Check **`OK_HOLD_SECONDS`** (Dwell Time in Admin Dynamic Settings, default `1.0` s) and **`OK_HOLD_FRAMES`** (default `3` frames) in `config.py` / `settings.json` — if Dwell Time is set too high, operators may move the gauge away before it latches OK.
4. Consult the development team if the YOLO model itself may need retraining.

---

## 10.6 Browser Shows Blank Page or "Connection Refused"

| Possible Cause | Action |
|----------------|--------|
| Application is still starting up | Wait **5–10 seconds** after double-clicking `Run_App.bat`, then try again |
| Application crashed on startup | Check the command window for a Python error message and exit |
| Wrong URL | Make sure you are using `http://localhost:8000` — not `https://` |
| Wrong port | If `PORT` was changed in `config.py`, update the URL to match |
| Browser cache issue | Press **Ctrl + Shift + R** (hard refresh) or try a different browser |

> **📝 NOTE:** The application does not use HTTPS (SSL). Using `https://` in the browser URL will always fail — always use `http://`.

**Step-by-step diagnosis:**
1. Look at the command window where `Run_App.bat` was run. If the window is **closed** or shows a Python exception, the app has crashed — fix the error and relaunch.
2. If the command window shows `Uvicorn running on http://0.0.0.0:8000`, the app is running — the problem is with the browser.
3. Try opening a browser and navigating to `http://127.0.0.1:8000` (alternative way to reach localhost).
4. If still failing, try pressing **F5** to refresh, or open a new browser tab.

---

## 10.7 Supervisor Bypass Left On Accidentally

**Symptom:** All inspection checkpoints show OK (green) regardless of what is actually in front of the camera. The system approves every part as PASS.

> **⚠️ WARNING:** While the supervisor bypass is active, the AI inspection system is **not running**. Parts inspected under bypass are still logged to the database, but the AI has not verified gauge checks. Refer to the bypass safety policy in Chapter 12.3.

**To check and disable the bypass:**

1. Open a web browser and go to **http://localhost:8000**.
2. Click the **⚙️ Admin** button in the top-right header.
3. Enter the Supervisor PIN (default: `1234`) and click **Login**.
4. Under **Supervisor Bypass** at the top of the modal, click the grey **Disable** button (no PIN is needed to turn bypass off).
5. The red **`⚠ BYPASS ACTIVE`** banner disappears and the dashboard returns to normal AI-based inspection immediately — no restart is required.

> **📝 NOTE:** The supervisor bypass is **automatically reset to OFF** every time the application is restarted. If the bypass was left ON and the app is restarted, it will be cleared.

---

## Diagnostic Summary Table

Use this table as a quick reference when escalating an issue to the development team. Record the answers before making contact.

| Question | Where to Find the Answer |
|----------|--------------------------|
| What is the application version? | `config.py` → `APP_VERSION` |
| Is the error reproducible every time? | Try repeating the same action 3 times |
| What does the command window show? | Copy the last 20 lines of text from the command window |
| Is the camera reachable? | `ping <camera IP>` from Command Prompt |
| Is the database service running? | `services.msc` → check SQL Server / MySQL status |
| When did the problem first occur? | Check inspection logs for the last successful record timestamp |
| Were any changes made before the problem started? | Confirm with maintainer / IT team |

---

*End of Chapter 10*

| ← Previous Chapter | Next Chapter → |
|-------------------|----------------|
| Chapter 9 — Updating the Software | Chapter 11 — Maintenance Schedule |
