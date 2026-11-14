# Chapter 4 — Starting & Stopping the Application

**Firewall DFP6 SOP Compliance System**
*Delphi-TVS Technologies Limited*

---

> **📝 NOTE:** Complete [Chapter 3 — Software Installation](./Chapter_03_Installation.md) in full before attempting to start the application for the first time.

---

## Table of Contents

- [4.1 Launching the Application](#41-launching-the-application)
- [4.2 What Happens Automatically on Startup](#42-what-happens-automatically-on-startup)
- [4.3 Accessing the Dashboard](#43-accessing-the-dashboard)
- [4.4 Stopping the Application](#44-stopping-the-application)
- [4.5 Auto-Start on Windows Boot (Optional)](#45-auto-start-on-windows-boot-optional)

---

## 4.1 Launching the Application

There are two launcher scripts, depending on which folder layout is being used on the IPC. Use the one that applies to your installation:

| Launcher Script | Location | When to Use |
|---|---|---|
| `Run_App.bat` | Root project folder | Source / virtual-environment (`venv\`) installation |
| `Run_Software.bat` *(or `Firewall_SOP.exe`)* | `Software\` subfolder | Standalone portable delivery layout (uses embedded `Software\python\` and compiled `app.pyc`) |

If you are unsure which applies, check whether `Run_App.bat` exists in the root folder. If it does, use that one.

### Steps to Launch

1. Open **Windows Explorer** and navigate to the folder containing `Run_App.bat` (or `Run_Software.bat`).
2. Double-click **`Run_App.bat`**.
3. A black command window (terminal) opens. Several startup messages will scroll through the window — this is normal.

> **⚠️ WARNING:** **Do not close the black command window.** This window is the application server. If you close it, the application stops immediately and all ongoing inspections will be interrupted.

4. After approximately **3 seconds**, your default web browser (Chrome or Edge recommended) opens automatically and navigates to:
   ```
   http://localhost:8000
   ```
5. The SOP Compliance dashboard loads in the browser and the live camera feed begins streaming.

The application is now running and ready to accept barcode scans and perform inspections.

---

## 4.2 What Happens Automatically on Startup

When `Run_App.bat` is double-clicked, it performs a series of checks and starts the application components in order. Understanding this sequence helps maintenance engineers diagnose startup errors.

| Step | What Happens | If It Fails |
|---|---|---|
| **1. VC++ Runtime check** | Checks whether `vcruntime140_1.dll` is present in the Windows `System32` folder. If missing, silently runs `vc_redist.x64.exe` to install it. | Rare — manually run `vc_redist.x64.exe` from the `Software\` folder. |
| **2. Virtual environment check** | Checks whether `venv\Scripts\activate.bat` exists in the project folder. | If missing, an error message is shown. Run `setup_environment.bat` and try again. |
| **3. AI model file check** | Checks whether `SOP_Compliance\models\best_v2.pt` exists. | If missing, a warning is printed but the application continues to start. The TML inspection will not function. Copy the model file (see §3.6). |
| **4. Browser launch** | Waits 3 seconds, then opens `http://localhost:8000` in the default browser. | If the browser does not open, manually type the URL into Chrome or Edge. |
| **5. Server start** | Activates the Python virtual environment. Starts `app.py` using the `uvicorn` web server. Loads both the TML model (`best_v2.pt`) and the HMI model (`best_hmi_v2.pt`) into GPU memory. | Error messages appear in the command window. See Chapter 10 — Troubleshooting. |
| **6. Inference loop begins** | The camera RTSP stream is opened. YOLO object detection starts running at the configured target frame rate (default: **10 FPS**). The barcode scanner listener (`scan_listener.py`) is activated and waits for input. | If the camera feed does not appear, check the RTSP URL and camera network connectivity (§3.7 checklist). |

> **📝 NOTE:** Loading the AI models into GPU memory takes a few seconds after the browser opens. The dashboard may show a brief "Connecting…" state during this time. This is normal — wait 5–10 seconds for the camera feed to appear.

---

## 4.3 Accessing the Dashboard

The SOP Compliance dashboard is a web-based interface that works in any modern browser. It can be accessed from the IPC itself or from any other PC on the same local network.

| Access From | URL to Enter in Browser |
|---|---|
| The IPC itself | `http://localhost:8000` |
| Any other PC on the same LAN | `http://<IPC-IP-address>:8000` |

**Recommended browsers:** Google Chrome or Microsoft Edge (latest versions).

### Finding the IPC's IP Address

If you need to access the dashboard from another PC on the network, you must first find the IPC's IP address:

1. On the **IPC**, press **Win+R**, type `cmd`, and press **Enter**.
2. Type the following command and press **Enter**:
   ```
   ipconfig
   ```
3. Look for the section labelled **"Ethernet adapter"** (or similar). The IPC's IP address is shown next to **"IPv4 Address"**. It typically looks like `192.168.x.x`.
4. On the other PC, open Chrome or Edge and type the full URL, substituting the IP address you found:
   ```
   http://192.168.1.50:8000
   ```
   *(Replace `192.168.1.50` with the actual IPC IP address.)*

> **📝 NOTE:** The IPC's IP address may change if it is assigned by a DHCP server (most factory networks do this). Ask your IT department to assign the IPC a **static (fixed) IP address** so the dashboard URL remains constant.

---

## 4.4 Stopping the Application

Stop the application only when explicitly required — for example, during maintenance, configuration changes, or end-of-shift shutdown if the IPC is being powered off.

> **⚠️ WARNING:** Do **not** force-stop the application while an inspection cycle is in progress. Stopping mid-cycle may leave an incomplete record in the `inspection_logs` database table, which can affect compliance reporting.

### Stopping Methods

| Method | Steps | When to Use |
|---|---|---|
| **Clean stop (recommended)** | 1. Click anywhere inside the black command window to focus it. 2. Press **Ctrl+C** on the keyboard. 3. If asked `"Terminate batch job (Y/N)?"`, type `Y` and press **Enter**. | Preferred method — allows the server to shut down gracefully. |
| **Close the window** | Click the **✕** (close button) on the black command window. | Acceptable if a clean stop is not possible, but slightly less graceful. |

After stopping, the browser dashboard will show a connection error — this is expected because the server is no longer running.

### Restarting After a Stop

To restart the application after stopping it, simply double-click `Run_App.bat` again (see [Section 4.1](#41-launching-the-application)).

---

## 4.5 Auto-Start on Windows Boot (Optional)

For shop-floor IPCs that must be ready immediately when the PC is switched on each morning, the application can be configured to start automatically on Windows startup. This removes the need for an operator to manually launch `Run_App.bat`.

> **📝 NOTE:** For auto-start to operate without an operator logging in, the Windows user account must be configured for **automatic login**. This is a security-sensitive setting. Contact your IT department to configure automatic login safely and in line with your site's security policy.

### Steps to Configure Auto-Start

1. **Create a shortcut to `Run_App.bat`:**
   - In Windows Explorer, right-click **`Run_App.bat`**.
   - Hover over **"Send to"** in the context menu.
   - Click **"Desktop (create shortcut)"**.
   - A new shortcut named `Run_App.bat - Shortcut` appears on the Desktop.

2. **Open the Windows Startup folder:**
   - Press **Win+R** on the keyboard.
   - Type `shell:startup` and press **Enter**.
   - A Windows Explorer window opens showing the Startup folder (typically located at `C:\Users\<username>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`).

3. **Move the shortcut into the Startup folder:**
   - Drag the `Run_App.bat - Shortcut` from the Desktop into the Startup folder window that just opened.
   - Alternatively, cut (Ctrl+X) the shortcut from the Desktop and paste (Ctrl+V) it into the Startup folder.

4. **Test the auto-start configuration:**
   - Click **Start** → **Power** → **Restart**.
   - After the PC restarts and Windows loads, confirm that the black command window and the browser dashboard open automatically within 10–15 seconds of the Desktop appearing.

> **⚠️ WARNING:** If the PC requires a login password, the auto-start shortcut will **not** run until an operator logs in. For fully automated startup (no operator login needed), coordinate with your IT department to enable Windows automatic login for the designated IPC user account.

### Disabling Auto-Start

To stop the application from launching automatically:

1. Press **Win+R**, type `shell:startup`, and press **Enter**.
2. Find the `Run_App.bat` shortcut in the Startup folder.
3. Delete the shortcut. The application will no longer start automatically; it must be launched manually from the project folder.

---

*End of Chapter 4*

| Previous Chapter | Next Chapter |
|---|---|
| [Chapter 3 — Software Installation](./Chapter_03_Installation.md) | [Chapter 5 — Operator Daily-Use Guide (Shop Floor)](./Chapter_05_Operator_Guide.md) |
