# Chapter 7 — Configuration Reference (`config.py`)

**Firewall DFP6 SOP Monitoring System**
*Delphi-TVS Technologies Limited*

---

> **👥 Intended Audience:** This chapter is written for **IT Maintainers and Engineers** responsible for installing, tuning, and maintaining the system. Shop-floor operators do not need to edit configuration files.

---

## Table of Contents

- [7.1 File Location and How to Edit](#71-file-location-and-how-to-edit)
- [7.2 Camera Settings](#72-camera-settings)
- [7.3 YOLO / AI Model Settings](#73-yolo--ai-model-settings)
- [7.4 Validation Thresholds](#74-validation-thresholds)
- [7.5 Barcode Scanner Settings](#75-barcode-scanner-settings)
- [7.6 Database Settings](#76-database-settings)
- [7.7 Server Settings](#77-server-settings)
- [7.8 Adding a New Inspection Profile](#78-adding-a-new-inspection-profile)

---

## 7.1 File Location and How to Edit

All system-wide settings are stored in a single Python configuration file:

```
SOP_Compliance\config.py
```

This path is relative to the project root folder. The full path on a typical installation will look like:

```
C:\Firewall_SOP\SOP_Compliance\config.py
```

### Editing the File

You can open and edit `config.py` with any plain-text editor:

- **Notepad** — built into Windows (suitable for simple changes)
- **Notepad++** — recommended for syntax highlighting (free download)
- **Visual Studio Code** — recommended for engineers (free download)

### After Saving Changes

Every time you modify and save `config.py`, you must **restart the application** for the changes to take effect:

1. Go to the terminal / command window where the app is running.
2. Press **Ctrl + C** to stop the application.
3. Double-click **`Run_App.bat`** to restart it.

> **⚠️ WARNING:** `config.py` is a **Python source file**. Incorrect edits can crash the application. Follow these rules when editing:
> - Do not change indentation (spaces at the beginning of lines).
> - Keep all quotation marks in place — do not change `"` to `'` or remove them.
> - Do not delete any lines or variable names unless you are certain of the effect.
> - If the application fails to start after an edit, re-check the edited line carefully and restore any accidentally deleted characters.

> **📝 NOTE:** It is strongly recommended to make a **backup copy** of `config.py` before editing it. Copy the file and rename the copy `config.py.bak` so you can restore it if needed.

> **⚠️ IMPORTANT (`settings.json` Override Rule):** If anyone has clicked **Save Changes** in the browser **Admin → Dynamic Settings** modal, toggled the **Blur Zone**, or switched profiles in the UI, the app creates **`SOP_Compliance\settings.json`**. On startup, `settings.json` **overrides** `config.py` for `CONFIDENCE_THRESHOLD`, `OVERLAP_THRESHOLD`, `NEAR_DISTANCE_THRESHOLD`, `OK_HOLD_SECONDS`, `DEFAULT_PROFILE`, `BLUR_ZONE_ENABLED`, `DEFAULT_BLUR_ZONE`, and TML `gauge_configs`. If your edits to those variables in `config.py` do not appear to take effect, open **⚙️ Admin → Reset** (or delete `SOP_Compliance\settings.json`) and restart.

---

## 7.2 Camera Settings

These settings control how the system connects to the inspection camera.

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `LIVE_CAMERA_URL` | `"rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101"` | Full RTSP stream URL for the Hikvision IP camera. Update this value if the camera's IP address changes or if the login credentials are changed. |
| `DEFAULT_SOURCE` | `"video"` | Selects the startup video input. Valid options are `"live"`, `"video"`, or `"demo"`. Use `"video"` for pre-recorded testing, or `"live"` for live camera mode. |
| `DEFAULT_VIDEO_PATH` | *(path to `video.mp4`)* | File path to the test video file. Only used when `DEFAULT_SOURCE = "video"`. Automatically uses `SOP_Compliance\video.mp4` if present. |
| `CAMERA_INDEX` | `0` | Index of a USB or locally-connected camera (fallback when no RTSP source URL is passed in `"live"` mode). `0` = first USB camera, `1` = second, etc. |

### Switching to Live Camera Mode

**From the Web Dashboard (Recommended at Runtime):**
1. In the **top-left corner of the dashboard header**, change the dropdown from `Pre-recorded Video` to **`Live Camera`**.
2. The backend switches immediately (`POST /source` with `mode="live"`) and connects to `LIVE_CAMERA_URL` (the Hikvision RTSP stream).

**In `SOP_Compliance\config.py`:**
1. Open `SOP_Compliance\config.py`.
2. Locate `DEFAULT_SOURCE`. Valid mode names are `"live"`, `"video"`, and `"demo"` (do **not** use `"camera"`).
   ```python
   DEFAULT_SOURCE = "live"
   ```
3. Verify that `LIVE_CAMERA_URL` contains the correct IP address and credentials for your Hikvision camera.
4. Save and restart the application. *(Note: On startup, `app.py` checks `DEFAULT_SOURCE == "video"` to pass `DEFAULT_VIDEO_PATH`; if `DEFAULT_SOURCE = "live"` falls back to USB `CAMERA_INDEX` instead of the RTSP URL, select **Live Camera** once in the dashboard header dropdown to bind `LIVE_CAMERA_URL`.)*

### Updating the Camera IP Address

If the camera's IP address changes on the network:

1. Open `SOP_Compliance\config.py`.
2. Find the `LIVE_CAMERA_URL` line.
3. Replace the IP address portion (`192.168.1.66`) with the new IP address:
   ```python
   LIVE_CAMERA_URL = "rtsp://admin:Wedit@2024@<NEW_IP>:554/Streaming/Channels/101"
   ```
4. Save and restart.

> **📝 NOTE:** The default camera credentials embedded in the RTSP URL are `admin` (username) and `Wedit@2024` (password). If the camera's login credentials are changed, update this URL accordingly.

---

## 7.3 YOLO / AI Model Settings

These settings control how the AI detection model processes video frames. Changes here directly affect detection accuracy and system performance.

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `CONFIDENCE_THRESHOLD` | `0.10` | Minimum confidence score (0.0 to 1.0) for a detection to be accepted. Lower values detect more objects but increase false positives. Raise this value (e.g., to `0.30`) if the system is triggering on objects that are not gauges. |
| `IOU_THRESHOLD` | `0.15` | Intersection-over-Union (IoU) threshold for Non-Maximum Suppression (NMS). Controls how overlapping detection boxes are merged. Lower values merge more aggressively. |
| `IMGSZ` | `1024` | The pixel size of the image fed into the YOLO model during inference. This **must match** the image size used when the model was trained. Do not change this unless you are retraining the model. |
| `DEVICE` | `"0"` | The compute device used for inference. See device options table below. |
| `TARGET_FPS` | `10` | Target number of inference frames analysed per second. Reducing this value lowers GPU load on slower machines. Increasing it may improve detection responsiveness but requires more GPU resources. |
| `LIVE_IMGSZ` | `1024` | Image size used specifically when processing the live camera stream. Should match `IMGSZ`. |

### Device Options

| `DEVICE` Value | Meaning |
|----------------|---------|
| `"0"` | Use the first GPU (CUDA device 0) — recommended for best performance. |
| `"1"` | Use a second GPU (if installed). |
| `"cpu"` | Use the CPU only — significantly slower; use only if no GPU is available. |

> **⚠️ WARNING:** Do **not** change `IMGSZ` or `LIVE_IMGSZ` unless you have retrained the YOLO model at a different image size. A mismatch between the config value and the model's training size will degrade detection accuracy significantly.

> **📝 NOTE:** If you observe many false detections (e.g., gauges being reported as checked when nothing is there), try **raising** `CONFIDENCE_THRESHOLD` in steps of `0.05` and observing the effect. If real gauges are being missed, **lower** the threshold.

---

## 7.4 Validation Thresholds

These settings fine-tune how the system decides whether a gauge has been correctly positioned on a part. These are advanced settings — only change them if instructed to do so or if detection behaviour is incorrect.

| Setting | Default Value | Unit | Description |
|---------|---------------|------|-------------|
| `OVERLAP_THRESHOLD` | `0.15` | Ratio (0.0–1.0) | Minimum overlap ratio required for the `fully_inside` spatial check. The gauge detection bounding box must overlap the part's bounding box by at least this fraction to be considered "on the part." |
| `NEAR_DISTANCE_THRESHOLD` | `50` | Pixels | Maximum pixel distance allowed between a gauge and the part area for the `near` spatial check method. Gauge must be within this distance to be counted. |
| `IGNORE_LEFT_OF_X` | `320` | Pixels | Any detection whose bounding box centre is to the left of this x-coordinate (in pixels) is ignored. This aligns with the blur zone boundary to prevent false detections in the obscured region. |
| `OK_HOLD_FRAMES` | `3` | Frames | Number of **consecutive** frames a gauge must be detected in the correct position before that checkpoint is marked as OK. Prevents flickering or momentary false detections from triggering an OK. |
| `OK_HOLD_SECONDS` | `1.0` | Seconds | Minimum elapsed time (in addition to `OK_HOLD_FRAMES`) that the gauge must remain in position before the checkpoint is confirmed OK. |
| `GAUGE_GRACE_FRAMES` | `15` | Frames | After a gauge leaves the camera's view, the system waits this many frames before declaring the gauge "lost." This prevents transient occlusions from resetting a checkpoint. |
| `PART_CLEAR_TIME_COMPLETE` | `3.0` | Seconds | After an inspection cycle finishes with a **PASS** result, the system waits this long before resetting and accepting the next part. This prevents double-counting. |
| `PART_CLEAR_TIME_INSPECTING` | `8.0` | Seconds | If the part leaves the camera's view **mid-inspection** (before all gauges are checked), the system waits this long before resetting the cycle. This handles cases where the part briefly disappears. |

> **📝 NOTE:** `OK_HOLD_FRAMES` and `OK_HOLD_SECONDS` work together — both conditions must be satisfied before a checkpoint is marked OK. This dual-condition approach prevents false OK detections caused by momentary overlaps.

---

## 7.5 Barcode Scanner Settings

These settings control how the keyboard-wedge barcode scanner is used to identify parts and auto-switch inspection profiles.

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `SCAN_LISTENER_ENABLED` | `True` | Master switch for barcode scanning. Set to `False` to completely disable barcode input and profile auto-switching. |
| `SCAN_AUTO_SWITCH` | `True` | When `True`, scanning a recognised barcode automatically switches the inspection profile. Set to `False` to log scans without switching profiles. |
| `SCAN_PART_PREFIXES` | *(see below)* | A dictionary mapping profile names to their barcode prefixes. See the table below. |
| `SCAN_SWITCH_HOLD_SECONDS` | `2.0` | After a barcode triggers a profile switch, the current result display is held on screen for this many seconds before the dashboard switches to the new profile view. |
| `SCAN_SWITCH_MAX_WAIT` | `10.0` | Safety timeout in seconds. If the system is waiting to switch profiles but the current part never leaves the camera frame, the switch is forced after this many seconds. |

### Default Barcode Prefix Mapping

```python
SCAN_PART_PREFIXES = {
    "TML": ("005724",),
    "HMI": ("33100-2A160",),
}
```

| Profile | Barcode Prefix | Part Type |
|---------|---------------|-----------|
| `TML` | `005724` | TML Part — 7 gauge checkpoints |
| `HMI` | `33100-2A160` | HMI Part — 7 checkpoints (4 U-gauges) |

When a scanned barcode **starts with** the listed prefix, the corresponding profile is activated.

> **📝 NOTE:** Barcode prefixes are matched from the **beginning** of the barcode string. For example, a barcode of `005724-00123` matches the `TML` prefix `005724`. The match is not case-sensitive by default.

> **📝 NOTE:** To add support for a new part type, see [Section 7.8 — Adding a New Inspection Profile](#78-adding-a-new-inspection-profile).

---

## 7.6 Database Settings

These settings control the connection to the SQL database where inspection results are stored.

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `DB_ENABLED` | `True` | Master switch for database logging. Set to `False` to disable all database writes (useful for testing without a database). |
| `DB_TYPE` | `"mssql"` | Database engine type. Use `"mssql"` for Microsoft SQL Server (default), or `"mysql"` for MySQL/MariaDB. |
| `DB_HOST` | `"localhost\\SQLEXPRESS"` | Hostname or IP address of the database server. `localhost\\SQLEXPRESS` refers to a local SQL Server Express instance. For a remote server, replace with the server's IP address (e.g., `"192.168.1.100"`). |
| `DB_PORT` | `1433` | Network port used to connect to the database. Default for MSSQL: `1433`. Default for MySQL: `3306`. |
| `DB_USER` | `""` | Database login username. An empty string (`""`) uses **Windows Authentication** for MSSQL — no username/password required. For MySQL or SQL authentication, enter the username here. |
| `DB_PASSWORD` | `""` | Database login password. Empty string = Windows Authentication (MSSQL only). |
| `DB_NAME` | `"firewall_sop"` | The name of the database to connect to. This database must already exist on the server (or will be created on first run, depending on configuration). |
| `DB_TABLE` | `"inspection_logs"` | The name of the table within the database where inspection records are written. |
| `DB_DRIVER` | `"ODBC Driver 17 for SQL Server"` | The name of the ODBC driver installed on the PC for MSSQL connections. Must exactly match the driver name as it appears in Windows ODBC Data Source Administrator. |

### Authentication Modes for MSSQL

| Mode | `DB_USER` | `DB_PASSWORD` | When to Use |
|------|-----------|---------------|-------------|
| **Windows Authentication** | `""` (empty) | `""` (empty) | When the application runs as a Windows user that has access to SQL Server. This is the default and recommended mode. |
| **SQL Server Authentication** | `"sa"` or username | Your password | When the app runs as a service account without Windows AD integration, or when connecting to a remote SQL Server. |

> **⚠️ WARNING:** If you change `DB_TYPE` from `"mssql"` to `"mysql"`, you must also update `DB_HOST`, `DB_PORT` (`3306`), `DB_USER`, `DB_PASSWORD`, and ensure the Python MySQL driver **`pymysql`** (included in `requirements.txt`) is installed. For MSSQL, `db_logger.py` uses **`pyodbc`** or **`pymssql`**. See Chapter 8 for the switching procedure.

> **📝 NOTE:** Verify the ODBC driver name on your PC by opening **Windows ODBC Data Source Administrator** (search for "ODBC" in the Windows Start menu) → **Drivers** tab → look for the driver name listed there and ensure it matches `DB_DRIVER` exactly, including capitalisation.

---

## 7.7 Server Settings

These settings control the web server that hosts the dashboard.

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `HOST` | `"0.0.0.0"` | The network interface the web server binds to. `"0.0.0.0"` means the dashboard is accessible from any device on the local network (not just the local PC). Change to `"127.0.0.1"` to restrict access to the local machine only. |
| `PORT` | `8000` | The TCP port the web server listens on. The dashboard is then available at `http://<server-ip>:8000`. Change this if port 8000 is already in use by another application. |
| `ADMIN_PASSWORD` | `"1234"` | The password required to access the Admin panel in the web dashboard. **Change this immediately after installation.** See [Section 6.4](Chapter_06_Admin_Functions.md#64-changing-the-admin-password). |

### Access URLs Based on `HOST` Setting

| `HOST` Value | Who Can Access the Dashboard |
|-------------|------------------------------|
| `"0.0.0.0"` | Any PC on the same local network: `http://<IPC-IP-address>:8000` |
| `"127.0.0.1"` | Only the IPC running the software: `http://localhost:8000` |

> **📝 NOTE:** If you change `PORT` to a non-default value (e.g., `9000`), remember to access the dashboard at the new port: `http://localhost:9000`. Also update any firewall rules or IT documentation accordingly.

---

## 7.8 Adding a New Inspection Profile

This section provides a step-by-step guide for adding support for a new part type. As an example, we will add a part called **"XYZ"**.

> **⚠️ WARNING:** Adding a new inspection profile requires a trained YOLO model (`.pt` file) for the new part type, as well as reference gauge images. This is a task for a trained AI/ML engineer in coordination with the IT maintainer. Do not attempt this without the required model file.

---

### Prerequisites

Before beginning, ensure you have the following ready:

- [ ] A trained YOLO model file for the new part (e.g., `xyz_model.pt`)
- [ ] Reference images of each gauge for the new part
- [ ] Knowledge of the barcode prefix used for the new part
- [ ] The names of the gauge classes and part classes the new model detects

---

### Step-by-Step Procedure

**Step 1 — Place the Model File**

1. Copy the trained YOLO model file (e.g., `xyz_model.pt`) to:
   ```
   SOP_Compliance\models\
   ```

**Step 2 — Open `config.py`**

1. Navigate to the project folder.
2. Open `SOP_Compliance\config.py` in a text editor.

**Step 3 — Add the Profile to the `PROFILES` Dictionary**

1. Find the `PROFILES` dictionary in `config.py`. It will look similar to this structure:
   ```python
   PROFILES = {
       "TML": { ... },
       "HMI": { ... },
   }
   ```
2. Add a new entry for your part type, following the exact dictionary schema used by `"TML"` and `"HMI"` in `config.py`:
   ```python
   "XYZ": {
       "display_name": "XYZ Part",
       "model_path": os.path.join(BASE_DIR, "models", "xyz_model.pt"),
       "engine_path": os.path.join(BASE_DIR, "models", "xyz_model.engine"),  # optional TRT

       # Gauge classes (ID -> exact YOLO class name)
       "gauge_classes": {
           0: "Gauge 1",
           1: "Gauge 2",
       },

       # Part / inspection area classes (ID -> exact YOLO class name)
       "part_classes": {
           2: "Part",
           3: "Hole A",
       },

       # Combined class map (all class IDs -> names)
       "class_names": {
           0: "Gauge 1",
           1: "Gauge 2",
           2: "Part",
           3: "Hole A",
       },

       # Reference images served from /reference_images/ (checkpoint id -> filename)
       "gauge_images": {
           1: "xyz_gauge1.png",
           2: "xyz_gauge2.png",
       },

       # SOP validation checkpoints
       "checkpoints": [
           {
               "id": 1,
               "name": "Gauge 1",
               "gauge_class": "Gauge 1",
               "part_class": "Part",
               "method": "fully_inside",
               "description": "Gauge 1 fully inside XYZ Part",
           },
           {
               "id": 2,
               "name": "Gauge 2",
               "gauge_class": "Gauge 2",
               "part_class": "Hole A",
               "method": "near",
               "near_distance_threshold": 50,
               "description": "Gauge 2 near Hole A",
           },
       ],
   },
   ```
3. Note that `gauge_classes`, `part_classes`, `class_names`, and `gauge_images` MUST be Python dictionaries (`{id: name}`), **not** lists — `app.py` calls `.keys()` on `gauge_classes` at startup. Fill in the exact class IDs and names from your trained YOLO model.

**Step 4 — Add the Barcode Prefix**

1. Find the `SCAN_PART_PREFIXES` dictionary in `config.py`.
2. Add a new entry for the new part:
   ```python
   SCAN_PART_PREFIXES = {
       "TML": ("005724",),
       "HMI": ("33100-2A160",),
       "XYZ": ("YOUR_BARCODE_PREFIX",),    # <-- Add this line
   }
   ```
3. Replace `YOUR_BARCODE_PREFIX` with the actual prefix used on the new part's barcode labels.

**Step 5 — Add Reference Gauge Images**

1. Copy the reference images for each gauge of the new part into:
   ```
   SOP_Compliance\Reference_gauge_images\
   ```
2. Ensure the filenames in the `gauge_images` dictionary (from Step 3) match the actual filenames inside `Reference_gauge_images\` exactly, including capitalisation.

**Step 6 — Restart the Application**

1. Press **Ctrl + C** in the terminal to stop the application.
2. Double-click **`Run_App.bat`** to restart it.
3. Watch the terminal output for any error messages on startup.

**Step 7 — Test the New Profile**

1. Scan a barcode that starts with the new part's prefix (or manually switch to the "XYZ" profile from the dashboard).
2. Confirm the dashboard shows the correct number of checkpoints for the new part.
3. Test a physical part to verify the AI model detects gauges correctly.

> **📝 NOTE:** If the application fails to start after adding a new profile, check the terminal for a Python error message. The most common cause is a typo in `config.py` — check that all commas, brackets, and quotation marks are in place.

---

*End of Chapter 7*

---

> **Previous Chapter:** [Chapter 6 — Admin / Supervisor Functions](Chapter_06_Admin_Functions.md)
> **Next Chapter:** [Chapter 8 — Database & Inspection Logs](Chapter_08_Database_Logs.md)
