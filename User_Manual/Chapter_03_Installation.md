# Chapter 3 — Software Installation (First-Time Setup)

**Firewall DFP6 SOP Compliance System**
*Delphi-TVS Technologies Limited*

---

> **📝 NOTE:** Complete every section of this chapter **in the order it appears** before attempting to run the application. Skipping a step may cause the application to fail at startup.

---

## Table of Contents

- [3.1 Installing Python 3.11](#31-installing-python-311)
- [3.2 Installing Visual C++ Runtime](#32-installing-visual-c-runtime)
- [3.3 Installing the Database](#33-installing-the-database)
  - [3.3.1 Microsoft SQL Server Express (Recommended)](#331-microsoft-sql-server-express-primary--recommended)
  - [3.3.2 MySQL (Alternative)](#332-mysql-alternative)
- [3.4 Setting Up the Python Environment](#34-setting-up-the-python-environment)
- [3.5 Offline / USB Installation](#35-offline--usb-installation)
- [3.6 AI Model Files](#36-ai-model-files)
- [3.7 First-Time Run Verification Checklist](#37-first-time-run-verification-checklist)

---

## 3.1 Installing Python 3.11

Python is the programming language the application runs on. It must be installed before anything else.

**Installer file:** `python-3.11.9-amd64.exe`
*(Found in the `Software/` folder of the project, or on the USB drive.)*

### Steps

1. Locate `python-3.11.9-amd64.exe` in the `Software/` folder and double-click it.
2. The Python installer window opens.

> **⚠️ WARNING:** Before clicking anything else, look at the **bottom** of the installer window for the checkbox labelled **"Add Python 3.11 to PATH"**. You **must** tick this box. If you skip this step, the application will not start and you will need to uninstall and reinstall Python.

3. Tick the **"Add Python 3.11 to PATH"** checkbox.
4. Click **"Install Now"**.
5. Wait for the progress bar to complete (typically 1–3 minutes).
6. Click **"Close"** when the installer reports success.

### Verifying the Installation

7. Press **Win+R** on the keyboard, type `cmd`, and press **Enter**. A black Command Prompt window opens.
8. Type the following command and press **Enter**:
   ```
   python --version
   ```
9. The response should read:
   ```
   Python 3.11.9
   ```

> **📝 NOTE:** If you see `"python is not recognized as an internal or external command"`, the PATH checkbox was not ticked during installation. Uninstall Python from Windows Settings → Apps, then repeat the steps above.

---

## 3.2 Installing Visual C++ Runtime

The Visual C++ Runtime is a Microsoft library required by OpenCV and PyTorch — the two components that handle the camera feed and AI processing. Without it, those components will crash immediately on startup.

**Installer file:** `vc_redist.x64.exe`
*(Found in the `Software/` folder or on the USB drive.)*

### Steps

1. Locate `vc_redist.x64.exe` and double-click it.
2. Tick the checkbox to accept the license agreement.
3. Click **"Install"**.
4. Wait for the installation to complete (typically under 1 minute).
5. If prompted to restart the PC, click **"Restart"** and allow the PC to reboot before continuing.

> **📝 NOTE:** `Run_App.bat` automatically checks for the Visual C++ Runtime when it launches. If the runtime is missing, it silently runs `vc_redist.x64.exe` in the background before starting the application. However, it is best practice to install it manually during first-time setup to avoid any delays.

---

## 3.3 Installing the Database

The application uses a database to record every inspection result. You must install **one** of the two supported database engines. **Microsoft SQL Server Express is the recommended choice** for all Delphi-TVS shop-floor deployments.

| Database Engine | When to Use |
|---|---|
| **Microsoft SQL Server Express** | Default for all shop-floor IPCs. No username/password required. Easiest to set up. |
| **MySQL** | Use only if SQL Server Express cannot be installed, or if an existing MySQL server is already available on the network. |

---

### 3.3.1 Microsoft SQL Server Express (Primary — Recommended)

**Installer file:** `SQL2022-SSEI-Expr.exe`
*(Found in the `Software/` folder or on the USB drive.)*

#### Steps

1. Locate `SQL2022-SSEI-Expr.exe` and double-click it.
2. The SQL Server installer opens. Select the **"Basic"** installation type when prompted.
3. Read and accept the license terms by clicking **"Accept"**.
4. Leave the installation path at its default and click **"Install"**.
5. Wait for the installation to finish. This may take **10–15 minutes**.
6. Click **"Close"** when the installer reports that the installation has succeeded. A restart is usually not required.

#### How the Application Connects

The application uses **Windows Authentication** to connect to SQL Server. This means no username or password is needed — SQL Server automatically trusts the Windows user account that is running the application.

The database (`firewall_sop`) and table (`inspection_logs`) are **created automatically the first time `Run_App.bat` is launched**. No manual database setup is required.

#### Default `config.py` Settings for SQL Server Express

The following values are already set by default in `config.py`. **No changes are needed** unless your IT team has installed SQL Server under a different instance name.

```python
DB_TYPE     = "mssql"
DB_HOST     = "localhost\\SQLEXPRESS"
DB_PORT     = 1433
DB_USER     = ""        # Empty = Windows Authentication
DB_PASSWORD = ""
DB_NAME     = "firewall_sop"
DB_DRIVER   = "ODBC Driver 17 for SQL Server"
```

> **📝 NOTE:** The double backslash (`\\`) in `localhost\\SQLEXPRESS` is required by the Python configuration format. This represents a single backslash in the actual server address (`localhost\SQLEXPRESS`).

---

### 3.3.2 MySQL (Alternative)

Use this path only if directed to by your IT department or project engineer.

**Installer file:** `mysql-installer.msi`
*(Found in the `Software/` folder or on the USB drive.)*

#### Steps

1. Locate `mysql-installer.msi` and double-click it.
2. Follow the installation wizard. When asked for setup type, choose **"Server Only"**.
3. When prompted, set a **root password** for MySQL. Write this password down — you will need it in Step 6.
4. Complete the remaining wizard steps and finish the installation.
5. After MySQL is installed, navigate back to the project folder and double-click **`Setup_MySQL.bat`**.
6. The script will ask for your MySQL root password. Enter it and press **Enter**.
7. The script automatically:
   - Creates the `firewall_sop` database
   - Creates a dedicated application user (`sop_user`) and grants permissions
   - *(The `inspection_logs` table itself is created automatically by the application on first launch.)*

#### Credentials Created by `Setup_MySQL.bat`

| Setting | Value |
|---|---|
| Username | `sop_user` |
| Password | `Sop@1234` |
| Database | `firewall_sop` |

#### Updating `config.py` for MySQL

After running `Setup_MySQL.bat`, open `config.py` and change the database settings to the following:

```python
DB_TYPE     = "mysql"
DB_HOST     = "localhost"
DB_PORT     = 3306
DB_USER     = "sop_user"
DB_PASSWORD = "Sop@1234"
DB_NAME     = "firewall_sop"
```

> **⚠️ WARNING:** Save `config.py` after making these changes, then close and reopen Notepad to confirm the values were saved correctly before proceeding.

---

## 3.4 Setting Up the Python Environment

The application uses a **virtual environment** — an isolated folder (`venv/`) that contains all the Python libraries the application needs. This prevents conflicts with any other Python software on the same PC.

**Script:** `setup_environment.bat`
*(Found in the root project folder.)*

### What This Script Does

- Creates a virtual environment in the `venv/` subfolder of the project
- Downloads and installs all required Python packages (e.g., FastAPI, Ultralytics YOLO, OpenCV, PyTorch, pyodbc)
- If local package wheels (`.whl` files) are present in the `wheels/` folder, it installs from them instead of downloading

### Steps

1. Navigate to the root project folder in Windows Explorer.
2. Double-click **`setup_environment.bat`**.
3. A command window opens and begins downloading and installing packages. **Do not close this window.**
4. Wait for the process to complete. This takes **5–15 minutes** depending on internet connection speed.
5. When the script finishes, look for a message such as **"Setup complete"** at the bottom of the window.
6. Press any key or close the window if prompted.

> **⚠️ WARNING:** If the command window closes immediately with an error, Python may not have been added to PATH correctly. Return to [Section 3.1](#31-installing-python-311) and verify the Python installation.

> **📝 NOTE:** If the IPC does not have internet access, do **not** run `setup_environment.bat`. Instead, follow the offline procedure in [Section 3.5](#35-offline--usb-installation).

---

## 3.5 Offline / USB Installation

This section describes how to deploy the application to an IPC that has **no internet connection**. The process involves two machines: a **developer/source PC** (with internet and the full project) and the **target IPC** (offline shop-floor machine).

---

### Step A — Exporting from the Developer / Source PC

Perform these steps on the **developer PC**, not the IPC.

1. Insert a USB drive into the developer PC.
2. Navigate to the root project folder in Windows Explorer.
3. Double-click **`Export_To_USB.bat`**.
4. The script will ask for the **USB drive letter** (e.g., `E:`). Type the drive letter and press **Enter**.
5. When asked to choose an export option, select:

   | Option | When to Use |
   |---|---|
   | **1 — Full Export** | First-time setup on a new IPC. Copies code, packages, installers, and wheels. |
   | **2 — Code Update Only** | Updating an IPC that is already set up. Copies only updated code and AI models. |

6. For first-time setup, type `1` and press **Enter**.
7. Wait for the export to complete. The script will confirm when done.
8. Safely eject the USB drive using the Windows system tray (bottom-right corner → USB icon → "Eject").

---

### Step B — Installing on the Offline IPC

Perform these steps on the **target IPC** with the USB drive plugged in.

1. Plug the USB drive into the IPC.
2. Open Windows Explorer and navigate to the USB drive (e.g., `E:\Firewall_SOP_Offline\`).
3. Run **`python-3.11.9-amd64.exe`**:
   - Tick **"Add Python 3.11 to PATH"**
   - Click **"Install Now"** and wait for completion
4. Run **`vc_redist.x64.exe`**:
   - Accept the license and click **"Install"**
   - Restart if prompted
5. *(Skip this step if using SQL Server Express)* Run **`mysql-installer.msi`** to install MySQL, then run **`Setup_MySQL.bat`** to create the database and user account.
6. *(Skip this step if using MySQL)* Run **`SQL2022-SSEI-Expr.exe`**, choose **"Basic"**, and complete the installation.
7. Run **`Setup_Offline.bat`**:
   - This installs all Python packages from the USB `wheels/` folder without needing internet
   - Wait for it to complete and confirm success
8. Manually copy the `SOP_Compliance/models/` folder from the developer PC to the same location on the IPC. See [Section 3.6](#36-ai-model-files) for the list of required files.
9. Run **`Run_App.bat`** (or **`Run_Software.bat`** if using the packaged Software folder). The application will create the database table automatically on first run.

---

### Fast-Path: Code-Only Update (Already-Set-Up IPC)

Use this path when the IPC is already installed and working, and you only need to push updated code or AI model files.

**On the developer PC:**
1. Run `Export_To_USB.bat`
2. Choose **Option 2 — Code Update Only**
3. Eject the USB drive

**On the IPC:**
1. Plug in the USB drive
2. Navigate to the USB drive in Windows Explorer
3. Double-click **`Update_From_USB.bat`**
4. The script copies only updated code and model files — no reinstallation of Python, databases, or packages is needed

---

## 3.6 AI Model Files

The AI model weight files contain the trained neural network that detects parts, inspection areas, hands, and gauges in the camera image. Because these files are very large, they are **not** stored in Git repositories. If deploying from a Git clone, copy them manually; if deploying from a USB created by `Export_To_USB.bat`, confirm they were copied into `SOP_Compliance\models\`.

> **📝 NOTE (Standalone Portable `Software\` Package):** For completely zero-install IPC deployments, the project also includes a standalone `Software\` folder (exportable via `Export_Software_To_USB.bat`) that already bundles a portable Python 3.11 runtime (`Software\python\`), compiled bytecode (`app.pyc`, `config.pyc`), models, and offline wheels. Launch it directly with **`Run_Software.bat`** (or `Firewall_SOP.exe`).

> **⚠️ WARNING:** The application cannot perform any inspection without these model files. Copy them before the system goes live on the shop floor.

### Required Model Files

Place all model files in the following folder on the IPC:
```
SOP_Compliance\models\
```

| File | Purpose | Required? |
|---|---|---|
| `best_v2.pt` | TML part inspection — primary AI model weights | **Required** |
| `best_hmi_v2.pt` | HMI part inspection — primary AI model weights | **Required** |
| `best.engine` | TensorRT optimised model for TML (faster inference on NVIDIA GPUs) | Optional |
| `best_hmi_v2.engine` | TensorRT optimised model for HMI (faster inference on NVIDIA GPUs) | Optional |

### How to Copy the Model Files

1. On the **developer PC**, open Windows Explorer and navigate to `SOP_Compliance\models\`.
2. Copy `best_v2.pt` and `best_hmi_v2.pt` (and the `.engine` files if available) to a USB drive.
3. On the **IPC**, paste the files into `SOP_Compliance\models\`.
4. Confirm that both `.pt` files are present before running the application for the first time.

> **📝 NOTE:** The `.engine` files (TensorRT format) provide a speed improvement on NVIDIA GPUs only. They are pre-compiled for a specific GPU model; an `.engine` file built on one GPU may not work on a different GPU. The `.pt` files work on any machine and are always required. If `.engine` files are absent, the application automatically uses the `.pt` files.

---

## 3.7 First-Time Run Verification Checklist

Before starting the application for the first time, work through the checklist below. Tick each item only after you have confirmed it is correct. If any item cannot be ticked, refer to the relevant section in this chapter to resolve the issue.

| ✅ | Verification Item | Reference |
|----|---|---|
| ☐ | Python 3.11 installed — `python --version` returns `Python 3.11.9` | §3.1 |
| ☐ | Visual C++ Runtime installed (`vc_redist.x64.exe` run successfully) | §3.2 |
| ☐ | Database installed (SQL Server Express **or** MySQL) | §3.3 |
| ☐ | Database credentials correct in `config.py` | §3.3 |
| ☐ | Python virtual environment set up (`setup_environment.bat` completed with no errors) | §3.4 |
| ☐ | Model files copied: `best_v2.pt` **and** `best_hmi_v2.pt` present in `SOP_Compliance\models\` | §3.6 |
| ☐ | Hikvision camera connected to the LAN — ping `192.168.1.66` from the IPC returns a reply | — |
| ☐ | Camera RTSP URL confirmed and set correctly in `config.py` | — |
| ☐ | Barcode scanner plugged into an IPC USB port and recognised by Windows | — |
| ☐ | `Run_App.bat` launches without errors in the command window | Ch. 4 |
| ☐ | Browser opens automatically to `http://localhost:8000` and the dashboard loads | Ch. 4 |
| ☐ | Live camera feed is visible in the dashboard | Ch. 4 |
| ☐ | Test barcode scan switches the inspection profile correctly (TML ↔ HMI) | Ch. 5 |
| ☐ | Test inspection result appears in the database (verify using `View_MSSQL_Database.bat` or `View_Database.bat`) | Ch. 8 |

> **📝 NOTE:** Keep this completed checklist as a record of the installation. If a problem arises later, the checklist helps maintenance engineers quickly identify which components were confirmed working at setup time.

---

*End of Chapter 3*

| Previous Chapter | Next Chapter |
|---|---|
| [Chapter 2 — System Requirements & Hardware Setup](./Chapter_02_System_Requirements.md) | [Chapter 4 — Starting & Stopping the Application](./Chapter_04_Starting_Stopping.md) |
