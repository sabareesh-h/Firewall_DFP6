# Chapter 6 — Admin / Supervisor Functions

**Firewall DFP6 SOP Monitoring System**
*Delphi-TVS Technologies Limited*

---

> **👥 Intended Audience:** This chapter is written for **Supervisors** and **IT / Maintenance Engineers**.
> Shop-floor operators do not need access to the Admin panel under normal conditions.

---

## Table of Contents

- [6.1 Logging In to the Admin Panel](#61-logging-in-to-the-admin-panel)
- [6.2 Supervisor Bypass — Emergency Use Only](#62-supervisor-bypass--emergency-use-only)
- [6.3 Switching Inspection Profiles Manually](#63-switching-inspection-profiles-manually)
- [6.4 Changing the Admin Password](#64-changing-the-admin-password)
- [6.5 Enabling / Disabling the Blur Zone](#65-enabling--disabling-the-blur-zone)

---

## 6.1 Logging In to the Admin Panel

The Admin panel provides access to system controls that must not be available to general operators. It is password-protected and accessible from within the web dashboard.

### Where to Find the Admin Login

Open the web dashboard in your browser:

```
http://localhost:8000
```

Look for the **⚙️ Admin** button located in the **top-right corner** of the dashboard header. Clicking it opens the Admin Login modal.

### Login Steps

1. Open the web dashboard at `http://localhost:8000`.
2. Click the **⚙️ Admin** button in the top-right corner of the header bar.
3. Enter the **Supervisor PIN** when prompted (default: `1234`).
4. Click **Login**.
5. The **Dynamic Settings** modal opens, giving access to:
   - **Supervisor Bypass** (emergency enable/disable with PIN)
   - **Global Settings** (Confidence Threshold, Overlap Threshold, Near Distance Threshold, Dwell Time, Visual Deadzone)
   - **Privacy Blur Zone** (enable checkbox and `X1 (%)`, `Y1 (%)`, `X2 (%)`, `Y2 (%)` fields)
   - **Individual Gauge Settings** (per-checkpoint method, near distance, and overlap thresholds)
   - **Save Changes** (writes `SOP_Compliance/settings.json`) and **Reset** (deletes `settings.json` and restores `config.py` defaults)

> **⚠️ WARNING:** The default PIN is `1234`. This must be changed immediately after installation before the system is put into production. See [Section 6.4](#64-changing-the-admin-password) for instructions.

> **📝 NOTE:** When you click **Save Changes** in Dynamic Settings, values are saved to `SOP_Compliance\settings.json`. While `settings.json` exists, it overrides the matching defaults in `config.py` on startup. Click **Reset** in Dynamic Settings to clear `settings.json` and return to `config.py` defaults.

---

## 6.2 Supervisor Bypass — Emergency Use Only

### What Is the Supervisor Bypass?

The **Supervisor Bypass** is an emergency control that forces every inspection checkpoint to report **OK** automatically, regardless of what the camera actually sees. Its sole purpose is to keep the production line running when the AI inspection system is malfunctioning — for example, when:

- The camera has failed or disconnected.
- The YOLO model has encountered a critical error.
- A network issue is preventing the camera feed from reaching the system.

> **⚠️ WARNING:** The Supervisor Bypass is strictly for **emergency use only**. When bypass is active, the system does **not** verify that an operator has checked any gauges. All parts will be recorded as inspected without real verification. Any parts produced during a bypass period **must** be manually re-inspected.

---

### How to Enable the Supervisor Bypass

1. Log in to the Admin panel (`⚙️ Admin` → enter PIN → **Login**, see [Section 6.1](#61-logging-in-to-the-admin-panel)).
2. Under the **Supervisor Bypass** section at the top of the modal, type the **Supervisor PIN** into the PIN box (`config.ADMIN_PASSWORD` is verified on the server when enabling).
3. Click the red **Enable Bypass** button and confirm the warning popup.
4. Observe the dashboard:
   - A red **`⚠ BYPASS ACTIVE — every gauge is reported CHECKED without inspection. Supervisor only.`** strip appears across the top of the page.
   - The status label inside the modal updates from `Bypass: OFF — normal inspection`.
   - All gauge checkpoints immediately display as **OK**, regardless of the actual camera state.
5. Notify the responsible engineer immediately so repairs can begin.

---

### How to Disable the Supervisor Bypass

1. Open the Admin modal (`⚙️ Admin` → enter PIN → **Login**).
2. Under **Supervisor Bypass**, click the grey **Disable** button (no PIN is required to turn bypass OFF).
3. The `BYPASS ACTIVE` warning strip disappears, and normal AI-based inspection resumes **immediately**. (If a part was on the table with fabricated OKs, the active inspection cycle resets automatically so it restarts with real checking.)

---

### Bypass Safety Rules

The following rules are **mandatory** and must be enforced at all times:

| Rule | Details |
|------|---------|
| **Bypass is never saved** | The bypass is always OFF when the application starts or restarts. It must be manually enabled each time it is needed. |
| **Password always required** | Enabling the bypass always requires the Admin password. It cannot be turned on by an operator. |
| **Re-inspect bypass parts** | All parts produced while bypass was active must be flagged and manually re-inspected by a qualified inspector. |
| **Database logging continues** | The bypass does **not** stop the database from recording inspection events. All records during the bypass period are still saved (and tagged `BYPASS` in the UI Recent Inspection Logs). |
| **Check at start of each shift** | The supervisor must confirm the bypass is OFF at the beginning of every shift before production starts. |

> **⚠️ WARNING:** Never leave the Supervisor Bypass ON unintentionally. Always verify bypass status at the start of each shift. An unnoticed active bypass means the system is not performing real inspection — defective parts may pass undetected.

---

## 6.3 Switching Inspection Profiles Manually

### Normal Behaviour (Automatic Switching)

Under normal operating conditions, the inspection profile switches **automatically** when a barcode is scanned:

| Barcode Prefix | Profile Selected |
|----------------|-----------------|
| `005724...` | TML Part (7 gauges) |
| `33100-2A160...` | HMI Part (7 checkpoints including 4 U-gauges) |

No manual intervention is needed for routine production.

---

### When Manual Switching Is Needed

You may need to switch the profile manually when:

- The barcode scanner is unavailable or malfunctioning.
- You are testing the system without scanning parts.
- A specific profile needs to be forced for a batch run.

---

### Steps to Switch the Profile Manually

Manual switching does **not** require opening the Admin modal — it is available directly in the dashboard's left sidebar:

1. Look at the **left sidebar** inside the **Current Application** card, under **Part Type**.
2. Click the desired profile button:
   - **TML** — for TML parts (7 gauge checkpoints)
   - **HMI** — for HMI parts (7 checkpoints, 4 U-gauges)
3. The button highlights in blue and the dashboard updates **immediately** (both models are pre-loaded in GPU memory). No restart is needed.
4. Note that a manual switch also cancels any pending barcode auto-switch and updates `active_profile` in `settings.json`.

> **📝 NOTE:** Switching the profile while a part is currently being inspected (mid-cycle) will **reset the current inspection cycle**. The in-progress inspection will be discarded. Only switch profiles between parts, not while gauging is in progress.

---

## 6.4 Changing the Admin Password

> **⚠️ WARNING:** The default password `1234` must be changed before the system is used in production. Using the default password leaves the Admin panel unsecured.

The Admin PIN is checked in two places and **both must be updated** to match:
- `SOP_Compliance\config.py` (`ADMIN_PASSWORD`) — verified by the backend server when enabling **Supervisor Bypass** (`POST /bypass`).
- `SOP_Compliance\frontend\app.js` (`verifyAdminPin()`) — verified in the browser when opening **Dynamic Settings** (`⚙️ Admin`).

> **📝 NOTE:** If your IPC runs the compiled standalone `Software/` package (`app.pyc` and `config.pyc`), editing `.py` files has no effect unless `.pyc` bytecode is recompiled from source on the developer PC. On source deployments (`Run_App.bat`), editing `config.py` and `frontend/app.js` takes effect after restarting.

---

### Step 1 — Update `config.py`

1. Navigate to the project folder and open the following file in a text editor (Notepad, Notepad++, or VS Code):

   ```
   SOP_Compliance\config.py
   ```

2. Find the line that reads:

   ```python
   ADMIN_PASSWORD = "1234"
   ```

3. Replace `1234` with your new password. For example:

   ```python
   ADMIN_PASSWORD = "Sup3rv!sor#2024"
   ```

4. Save the file.

---

### Step 2 — Update the Frontend

1. Open the following file in a text editor:

   ```
   SOP_Compliance\frontend\app.js
   ```

2. Use the text editor's **Find** function (usually `Ctrl + F`) to search for the old password string (e.g., `1234`).
3. Replace every occurrence with the same new password you set in `config.py`.
4. Save the file.

---

### Step 3 — Restart the Application

1. Go to the command window where the application is running.
2. Press **Ctrl + C** to stop the application.
3. Double-click **`Run_App.bat`** to restart it.
4. Test the new password by logging in to the Admin panel.

> **⚠️ WARNING:** Use a **strong password** (mix of letters, numbers, and symbols). Do **not** share the Admin password with shop-floor operators. If the password is forgotten, it must be manually reset in both files by an IT engineer with access to the server.

> **📝 NOTE:** Keep a secure record of the Admin password in your IT documentation. If it is lost, the files must be edited directly on the server.

---

## 6.5 Enabling / Disabling the Blur Zone

### What Is the Blur Zone?

The **Blur Zone** is a configurable region of the camera frame that is blurred in the live feed **and** excluded from YOLO detections. Its purpose is twofold:
1. **Operator privacy:** Obscures the left side of the frame (operator body/hands/personal surroundings) before streaming video to the dashboard.
2. **Detection cleanliness:** Any detection whose centre falls inside an active blur zone is automatically dropped so tools or movement outside the inspection table cannot trigger false checks.

| State | Behaviour |
|---|---|
| **Enabled (ON)** | The configured zone is Gaussian-blurred on the live stream, and any YOLO detection centred inside the zone is ignored by SOP validation. |
| **Disabled (OFF)** | The full, unblurred camera frame is shown and all detections across the frame are evaluated. |

---

### Toggling or Resizing the Blur Zone from the Dashboard

**Quick On/Off Toggle:**
1. Look at the **camera header bar** (above the video feed) for the **Blur Zone** switch.
2. Click the toggle to switch the blur zone **ON** or **OFF**. The setting persists immediately to `SOP_Compliance\settings.json`.

**Changing Blur Zone Size (Admin Modal):**
1. Click **⚙️ Admin** → enter Supervisor PIN → **Login**.
2. Scroll to **Privacy Blur Zone** (`Blur this area and ignore all detections inside it`).
3. Adjust the percentage values `X1 (%)`, `Y1 (%)`, `X2 (%)`, `Y2 (%)` (0–100% of frame width/height; default is `0.0, 0.0, 36.0, 100.0`).
4. Click **Save Changes**.

> **📝 NOTE:** Changes made in the UI are saved to `SOP_Compliance\settings.json` and override `BLUR_ZONE_ENABLED` / `DEFAULT_BLUR_ZONE` in `config.py` until **Reset** is clicked in Dynamic Settings.

---

### Configuring the Blur Zone in `config.py`

For permanent changes to the blur zone, edit the configuration file:

```
SOP_Compliance\config.py
```

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `BLUR_ZONE_ENABLED` | `True` | Set to `True` to enable blur zone by default, `False` to disable. |
| `DEFAULT_BLUR_ZONE` | `[0.0, 0.0, 0.36, 1.0]` | Coordinates of the blurred region as normalized values (0.0 to 1.0): `[x_start, y_start, x_end, y_end]`. |

**Understanding the Default Blur Zone Coordinates:**

The default value `[0.0, 0.0, 0.36, 1.0]` means:

| Coordinate | Value | Meaning |
|------------|-------|---------|
| `x_start` | `0.0` | Starts at the left edge of the frame |
| `y_start` | `0.0` | Starts at the top edge of the frame |
| `x_end` | `0.36` | Ends 36% from the left (covers left 36% of the width) |
| `y_end` | `1.0` | Extends to the bottom edge of the frame |

This blurs a vertical strip covering the **left 36%** of the camera frame, full height.

**Example — Custom Blur Zone:**

To blur the left 50% of the frame:

```python
BLUR_ZONE_ENABLED = True
DEFAULT_BLUR_ZONE = [0.0, 0.0, 0.50, 1.0]
```

After editing `config.py`, restart the application for the change to take effect.

---

*End of Chapter 6*

---

> **Next Chapter:** [Chapter 7 — Configuration Reference (`config.py`)](Chapter_07_Configuration_Reference.md)
