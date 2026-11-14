# Chapter 9 — Updating the Software

**Firewall DFP6 SOP Monitoring System**
*Delphi-TVS Technologies Limited*

---

## Overview

This chapter describes how to update the Firewall DFP6 SOP Compliance Software. There are three update scenarios, each with its own procedure:

| Scenario | When to Use | Section |
|----------|-------------|---------|
| Code-only update via USB | Python scripts or AI model files have changed on an offline IPC; Python and all packages are already installed | [9.1](#91-code-only-update-fast-path-via-usb) |
| Online Git update (`Update_App.bat`) | IPC has internet & Git installed and runs directly from the Git repository | [9.1.3](#913-online-update-via-git-update_appbat) |
| AI model weights only | A new or improved YOLO model has been trained by the development team | [9.2](#92-updating-ai-model-weights) |
| Full re-install on a new IPC | Replacing or rebuilding the industrial PC from scratch (including standalone `Software/` export via `Export_Software_To_USB.bat`) | [9.3](#93-full-re-install-on-a-new-ipc-machine) |

> **📝 NOTE:** Always stop the application before performing any update. Never overwrite files while the application is running — this can corrupt the software.

---

## 9.1 Code-Only Update (Fast Path via USB)

**Use this procedure when:** only the Python source code or AI model files have changed, and the target IPC already has Python 3.11 and all required packages installed from a previous setup.

This is the fastest and most common update path.

### 9.1.1 On the Developer / Source PC

1. Make all required code changes and verify they work correctly on the development machine.
2. Insert a USB flash drive into the developer PC.
3. Open the `SOP_Compliance` root folder in Windows Explorer.
4. Double-click **`Export_To_USB.bat`**.
5. When prompted, type the USB drive letter (for example, `E`) and press **Enter**.
6. When the menu appears, choose **Option 2 — Code Update Only** and press **Enter**.

   > **📝 NOTE:** Option 2 copies only the Python source files and model files. It does **not** copy the Python installer, VC++ runtime, or offline packages. This keeps the USB export small and fast.

7. Wait for the script to finish — it will display a "Copy complete" confirmation message.
8. Safely eject the USB drive using the Windows system tray icon before removing it physically.

### 9.1.2 On the IPC (Target Machine)

1. If the application is currently running, click the command window and press **Ctrl + C** to stop it. Wait until the prompt returns.
2. Plug the USB drive into the IPC.
3. Open the USB drive in Windows Explorer.
4. Double-click **`Update_From_USB.bat`**.
5. The script will copy the updated files from the USB drive into the `SOP_Compliance` folder on the IPC, overwriting the old versions.
6. Wait for the script to display a "Update complete" message.
7. Remove the USB drive.
8. Double-click **`Run_App.bat`** to restart the application.
9. Open a browser and go to **http://localhost:8000** to confirm the system starts correctly.

> **⚠️ WARNING:** Do not unplug the USB drive while `Update_From_USB.bat` is still running. Interrupting the copy mid-way can leave files in a partially overwritten state, causing the application to fail on next start.

### 9.1.3 Online Update via Git (`Update_App.bat`)

If the machine is connected to the internet and uses a Git clone:
1. Stop the application (`Ctrl + C`).
2. Double-click **`Update_App.bat`** in the root folder.
3. The script discards local runtime changes to `SOP_Compliance/settings.json`, pulls the latest code from `origin main`, and silently updates `requirements.txt` packages inside `venv/`.
4. Re-copy `.pt` model files if a new model version was released (Git does not store `.pt` weights) and launch `Run_App.bat`.

---

## 9.2 Updating AI Model Weights

**Use this procedure when:** the AI/development team has trained a new or improved YOLO model and has provided a new `.pt` model file.

> **📝 NOTE:** Model files use the `.pt` (PyTorch) format. If optional TensorRT `.engine` files (`best.engine` for TML or `best_hmi_v2.engine` for HMI) exist in `SOP_Compliance\models\`, `YOLODetector` loads them automatically in place of `.pt` for 3–5× faster GPU inference.

### Step-by-Step Procedure

1. Stop the application by pressing **Ctrl + C** in the command window, or by closing the command window.

2. Using Windows Explorer, navigate to the models folder:
   ```
   C:\...\SOP_Compliance\models\
   ```

3. Locate the existing model file(s) and replace them with the new file(s) provided by the development team:

   | Profile | Old File Name | New File to Drop In |
   |---------|--------------|---------------------|
   | TML Part | `best_v2.pt` | New `.pt` file from development team |
   | HMI Part | `best_hmi_v2.pt` | New `.pt` file from development team |

   > **📝 NOTE:** You may keep the old file as a backup by renaming it first (for example, rename `best_v2.pt` to `best_v2_backup_YYYYMMDD.pt`) before copying in the new one.

4. **Delete any stale TensorRT `.engine` files in `models\`** (`best.engine`, `best_hmi_v2.engine`).
   - Do **not** leave old `.engine` files next to a new `.pt` file — otherwise `app.py` will keep loading the old compiled engine instead of your new `.pt` weights!
   - Once deleted, `app.py` automatically falls back to your new `.pt` weights.
   - *(Optional)* To recompile a TensorRT `.engine` for maximum GPU speed on that specific IPC, run `SOP_Compliance\export_tensorrt.py` (ensure `IMGSZ` inside `export_tensorrt.py` matches `IMGSZ = 1024` in `config.py`).

5. **If the new model file has a different filename** (not `best_v2.pt` or `best_hmi_v2.pt`), you must update `config.py` to point to the new file:
   - Open `SOP_Compliance\config.py` in Notepad.
   - Find the `PROFILES` section.
   - Update the `model_path` entry for the relevant profile to match the new filename.
   - Save and close the file.

6. Double-click **`Run_App.bat`** to restart the application.

7. Watch the command window for model load messages. A successful load will display lines similar to:
   ```
   Model loaded: models/best_v2.pt
   YOLOv8 detected X classes
   ```
   If you see any error referencing the model file, verify the filename and path in `config.py`.

8. Perform a test inspection to confirm that detection is working correctly with the new model.

> **⚠️ WARNING:** Never swap model files while the application is running. The YOLO model is loaded into GPU memory at startup — replacing the file on disk mid-run does nothing and may cause data corruption if the application tries to reload.

---

## 9.3 Full Re-Install on a New IPC Machine

**Use this procedure when:** replacing the industrial PC, or setting up the system on a new machine for the first time.

> **📝 NOTE:** Refer to **Chapter 3 (Installation and Initial Setup)** for the complete step-by-step installation guide. The summary below is a quick reference checklist.

### Pre-Requisites Checklist

Before starting, ensure you have:

| Item | Required |
|------|----------|
| USB drive with full export (from `Export_To_USB.bat` → Option 1) | ✅ |
| New IPC powered on and running Windows | ✅ |
| IPC connected to the same LAN as the Hikvision camera | ✅ |
| New IPC's camera URL / IP address confirmed | ✅ |
| Database server credentials for the new environment | ✅ |

### Summary Steps

1. On the **source/developer PC**, insert a USB drive and run `Export_To_USB.bat`. Choose **Option 1 — Full Export**. Wait for completion and eject the USB safely.

2. On the **new IPC**, install the prerequisites from the USB drive in this order:
   1. `python-3.11.9-amd64.exe` — Python interpreter (check "Add Python 3.11 to PATH")
   2. `vc_redist.x64.exe` — Visual C++ Runtime libraries
   3. SQL Server Express installer (or MySQL) — the database engine
   4. ODBC Driver 17 for SQL Server (if using MSSQL)

3. Run **`Setup_Offline.bat`** from the USB drive to create the Python virtual environment and install all packages without internet access.

4. Copy the AI model files manually from the USB to the IPC:
   ```
   USB:\models\best_v2.pt       → IPC:\SOP_Compliance\models\best_v2.pt
   USB:\models\best_hmi_v2.pt   → IPC:\SOP_Compliance\models\best_hmi_v2.pt
   ```

5. Open `SOP_Compliance\config.py` on the new IPC and update the following settings for the new machine's environment:

   | Setting | What to Update |
   |---------|----------------|
   | `LIVE_CAMERA_URL` | RTSP URL with the camera's IP address on this LAN |
   | `DB_HOST` | Hostname or IP of the database server |
   | `DB_USER` | Database username |
   | `DB_PASSWORD` | Database password |
   | `DB_NAME` | Database name (typically `firewall_sop`) |
   | `ADMIN_PASSWORD` | Change from default `1234` to a secure password |

6. Double-click **`Run_App.bat`** to start the application.

7. Open a browser and go to **http://localhost:8000** to confirm the system is running.

8. Perform a full test inspection for both TML and HMI part profiles to verify end-to-end operation.

---

## 9.4 Checking the Installed Version

You can check the currently installed software version in two ways:

### Method 1: Check `config.py`

1. Open `SOP_Compliance\config.py` in Notepad.
2. Look for the line:
   ```python
   APP_VERSION = "1.0.0"
   ```
3. The version number is the value in quotes.

### Method 2: Check the Dashboard

1. Open a browser and go to **http://localhost:8000**.
2. The current version number is displayed in the **footer or header** of the dashboard.

| Version | Notes |
|---------|-------|
| **1.0.0** | Current production release |

> **📝 NOTE:** When contacting the development team for support or requesting a model update, always provide the version number so the team can ensure compatibility.

---

*End of Chapter 9*

| ← Previous Chapter | Next Chapter → |
|-------------------|----------------|
| [Chapter 8 — Database & Inspection Logs](./Chapter_08_Database_Logs.md) | [Chapter 10 — Troubleshooting](./Chapter_10_Troubleshooting.md) |
