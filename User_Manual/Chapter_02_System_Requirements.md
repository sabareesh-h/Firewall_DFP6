# Chapter 2 — System Requirements & Hardware Setup

**Document:** Firewall DFP6 SOP Compliance System — User Manual  
**Audience:** IT / Maintenance Engineers  
**Purpose:** Describes the minimum hardware, software, network, and peripheral requirements to install and operate the system correctly.

---

## 2.1 Minimum PC / IPC Specifications

The software runs on a Windows Industrial PC (IPC) permanently stationed on the shop floor. The table below lists the minimum and recommended specifications. Meeting only the minimum specification is acceptable for initial deployment, but the **recommended** column is strongly advised for sustained production use.

| Component | Minimum | Recommended |
|---|---|---|
| **Operating System** | Windows 10 (64-bit) | Windows 11 (64-bit) |
| **CPU** | Intel Core i5, 8th Generation or newer | Intel Core i7 or Intel Xeon |
| **RAM** | 8 GB | 16 GB |
| **GPU** | NVIDIA GPU with CUDA support (GTX 1060 or better) | NVIDIA RTX series (e.g., RTX 3060 or higher) |
| **Storage (Free Space)** | 20 GB | 50 GB (to allow for database growth over time) |
| **Network Interface** | Ethernet, 100 Mbps LAN | Gigabit Ethernet |
| **Display** | Any monitor | 1080p (Full HD) monitor or better |
| **USB Ports** | 1 × free USB-A port | 2 × USB-A ports (1 for scanner, 1 spare) |

> **⚠️ WARNING:** A CUDA-capable NVIDIA GPU is **strongly required** for real-time performance. Without it, the AI inference engine falls back to CPU mode, reducing throughput to approximately **1–2 frames per second** — far too slow for live inspection. If you must run without a GPU temporarily (e.g., for testing), set `DEVICE = "cpu"` in `config.py`. Do **not** use CPU mode in production.

> **📝 NOTE:** "CUDA support" means the NVIDIA GPU must have a compute capability of 3.5 or higher and have the NVIDIA CUDA toolkit installed on the IPC. Most GTX 10-series and later cards qualify. Refer to NVIDIA's official CUDA GPU list at https://developer.nvidia.com/cuda-gpus to confirm your card.

### Software Prerequisites (Pre-installed on IPC)

Before running the application installer, confirm the following are present on the IPC:

| Software | Version | Purpose |
|---|---|---|
| Python | 3.11 (64-bit) | Core runtime for all application code (or embedded portable Python in `Software\python\`) |
| NVIDIA GeForce / CUDA Driver | Driver `550+` (check via `nvidia-smi`) | Enables GPU inference for PyTorch / YOLO |
| Microsoft SQL Server Express | 2022 (`SQL2022-SSEI-Expr.exe`) | Primary database (alternatively MySQL) |
| Git (optional) | Any recent version | For pulling updates via `Update_App.bat` |

> **📝 NOTE (Windows Power Plan):** On the shop-floor IPC, set Windows Power Options to **High Performance** (or **Ultimate Performance**) via `Win + R` → `powercfg.cpl`. This prevents Windows timer throttling (15.6 ms timer), which otherwise causes pre-recorded video playback to run slowly (~0.8× speed).

> **📝 NOTE:** All Python package dependencies (FastAPI, Ultralytics YOLO, OpenCV, pynput, etc.) are installed automatically by running `setup_environment.bat` (online) or `Setup_Offline.bat` (offline USB). You do not need to install them manually.

---

## 2.2 Camera Setup — Hikvision IP Camera

### Camera Overview

The system uses a single **Hikvision IP camera** mounted overhead, pointed directly down at the inspection table. The camera streams live video to the IPC using the RTSP (Real-Time Streaming Protocol) over the local network.

| Property | Value |
|---|---|
| **Camera Brand / Type** | Hikvision IP Camera with RTSP support |
| **Mounting Position** | Overhead — directly above the inspection table |
| **Field of View** | Must fully cover the part and the operator's hands during gauging |
| **Network Protocol** | RTSP (Real-Time Streaming Protocol) over LAN |
| **Default RTSP URL** | `rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101` |
| **Camera IP Address (default)** | `192.168.1.66` |

### Physical Installation

1. Mount the camera on a rigid bracket directly above the inspection table. The lens must point straight down (± 5° tolerance).
2. Ensure the entire inspection surface — including where the operator places both the part and all gauges — is visible in the camera frame.
3. Run an Ethernet cable from the camera to the same network switch that the IPC is connected to.
4. Power the camera via PoE (Power over Ethernet) from the switch, or connect a separate power adapter if the switch does not support PoE.
5. Confirm the camera is powered on (indicator light active).

### Connecting the IPC Directly to the Camera (Static IP Setup)

If the Hikvision camera is connected directly to a dedicated Ethernet port on the IPC (instead of an office DHCP network), set a static IPv4 address on that Ethernet adapter so both devices are on the `192.168.1.x` subnet:

1. Press `Win + R`, type `ncpa.cpl`, and press **Enter**.
2. Right-click the Ethernet adapter connected to the camera → **Properties**.
3. Double-click **Internet Protocol Version 4 (TCP/IPv4)**.
4. Select **Use the following IP address** and enter:
   - **IP address:** `192.168.1.100` *(any unused IP from `.2` to `.254`, except `.66`)*
   - **Subnet mask:** `255.255.255.0`
   - **Default gateway:** leave blank *(or `192.168.1.1`)*
5. Click **OK** → **OK**.

### Verifying Network Connectivity to the Camera

Before starting the application, verify the IPC can reach the camera:

1. Open a Command Prompt on the IPC (`Win + R` → type `cmd` → press Enter).
2. Run the following command, replacing the IP if yours is different:
   ```
   ping 192.168.1.66
   ```
3. If you receive replies (e.g., `Reply from 192.168.1.66: bytes=32 time<1ms TTL=64`), the camera is reachable. Proceed.
4. If the ping **times out**, check:
   - The Ethernet cable is seated firmly at both ends.
   - The camera and IPC are on the same network subnet.
   - No firewall rule is blocking ICMP between the IPC and the camera.

### Changing the Camera IP Address

If the camera's IP address changes (e.g., after a network reconfiguration or camera replacement), you must update the RTSP URL in the software configuration:

1. On the IPC, open File Explorer and navigate to the application folder (e.g., `C:\Firewall SOP\SOP_Compliance\`).
2. Open the file **`config.py`** in Notepad or any text editor.
3. Find the line that begins with `LIVE_CAMERA_URL`.  
   It will look similar to this:
   ```python
   LIVE_CAMERA_URL = "rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101"
   ```
4. Replace only the IP address portion (`192.168.1.66`) with the new IP address of the camera. For example, if the new IP is `192.168.1.80`:
   ```python
   LIVE_CAMERA_URL = "rtsp://admin:Wedit@2024@192.168.1.80:554/Streaming/Channels/101"
   ```
5. Save the file (`Ctrl + S`).
6. Restart the application by running **`Run_App.bat`**.

> **📝 NOTE:** The camera username (`admin`) and password (`Wedit@2024`) embedded in the RTSP URL can also be updated in this same line if the camera credentials change. Refer to your Hikvision camera's web interface (accessed via browser at `http://<camera-IP>`) to manage camera credentials.

### Testing Without a Physical Camera

If the camera is not yet installed (e.g., during initial software testing or troubleshooting), the system can use a pre-recorded video file (and can also be switched at runtime using the top-left source dropdown in the dashboard header):

1. Open **`SOP_Compliance\config.py`** in a text editor.
2. Check the `DEFAULT_SOURCE` setting. Valid values are `"live"`, `"video"`, and `"demo"`:
   ```python
   DEFAULT_SOURCE = "video"
   ```
3. Confirm `DEFAULT_VIDEO_PATH` points to your `.mp4` test video (by default, `SOP_Compliance\video.mp4` is used if present).
4. Save and restart the application. To switch back to the Hikvision camera while running, select **Live Camera** from the top-left dropdown in the dashboard header.

> **⚠️ WARNING:** Video-file mode (`"video"`) and `"demo"` mode are for testing only. Never leave them active in production — select **Live Camera** so the system monitors the real inspection table.

---

## 2.3 Barcode Scanner Setup

### Scanner Overview

The system uses a standard **USB keyboard-wedge barcode scanner**. This type of scanner requires no special driver — the operating system treats it as a USB keyboard. When a barcode is scanned, the scanner sends the barcode string as a sequence of keystrokes followed by an Enter key.

| Property | Value |
|---|---|
| **Scanner Type** | USB keyboard-wedge (HID-class, plug-and-play) |
| **Driver Required** | None — Windows recognises it as a USB keyboard automatically |
| **Connection** | Any available USB-A port on the IPC |
| **Input Capture Method** | Global OS-level keyboard hook via `pynput` Python library |
| **Window Focus Required?** | No — the scanner is captured globally; no application window needs to be active |

### Physical Installation

1. Plug the barcode scanner's USB cable into any available USB-A port on the IPC.
2. Wait 5–10 seconds for Windows to automatically recognise the device.
3. Open **Notepad** on the IPC, click inside it, and scan a test barcode. The barcode number should appear in Notepad. This confirms the scanner is functioning correctly as a keyboard input device.

> **📝 NOTE:** The SOP Compliance Software captures barcode input at the OS level using a **global keyboard hook** (via the `pynput` library). This means the scanner is captured even when the browser dashboard or another application is in the foreground. Importantly, the hook is **passive** — the existing Firewall software also receives every scan unchanged, so there is no interference with its operation.

### How the Scanner Triggers Inspection Profiles

When a barcode is scanned, the application reads the barcode string and automatically selects the inspection profile based on the **barcode prefix**:

| Barcode Prefix | Inspection Profile Selected |
|---|---|
| Starts with `005724` | **TML Part** (7 gauge checks) |
| Starts with `33100-2A160` | **HMI Part** (7 checkpoints including U-Gauges) |
| Any other prefix | Silently ignored — no profile change |

### Enabling or Disabling the Barcode Listener

The barcode scan listener can be turned on or off in `config.py`:

1. Open **`config.py`** in a text editor.
2. Find the line:
   ```python
   SCAN_LISTENER_ENABLED = True
   ```
3. Change to `False` to disable, or `True` to enable.
4. Save the file and restart the application.

> **📝 NOTE:** The required Python library for the global keyboard hook (`pynput`) is installed automatically when you run `setup_environment.bat`. You do not need to install it separately.

### Required Python Package

| Package | Purpose | Installed By |
|---|---|---|
| `pynput` | Captures global keyboard events from the barcode scanner | `setup_environment.bat` (automatic) |

---

## 2.4 Network and IP Address Overview

### Application Server Binding

The application web server (FastAPI) binds to **all network interfaces** on the IPC using address `0.0.0.0`, port `8000`. This means the dashboard is accessible from:

| Access Point | URL |
|---|---|
| Same IPC (local access) | `http://localhost:8000` |
| Any other PC on the same LAN | `http://<IPC-IP-address>:8000` |

To find the IPC's IP address, open a Command Prompt and run:
```
ipconfig
```
Look for the **IPv4 Address** under the active Ethernet adapter (e.g., `192.168.1.100`).

### Network Architecture Summary

```
[ Hikvision Camera ]  ←— Ethernet LAN —→  [ Windows IPC ]  ←— Browser —→  [ Supervisor PC / Tablet ]
  192.168.1.66 (RTSP)                     Port 8000 (HTTP/WebSocket)         http://<IPC-IP>:8000
```

### Security Recommendations

> **⚠️ WARNING:** Because the application server accepts connections from any device on the LAN (port 8000), anyone on the factory network can open the dashboard. For production deployments, apply the following restrictions:

1. **Restrict port 8000 using Windows Defender Firewall:**
   1. Open the **Start Menu**, search for **"Windows Defender Firewall with Advanced Security"**, and open it.
   2. Click **Inbound Rules** → **New Rule…**
   3. Select **Port** → click Next.
   4. Select **TCP**, enter `8000` as the specific port → click Next.
   5. Select **Allow the connection** → click Next.
   6. Under the **Scope** tab (edit the rule after creation), restrict **Remote IP addresses** to trusted IPs only (e.g., the supervisor's PC and the IPC itself).
   7. Name the rule (e.g., `SOP Dashboard Port 8000`) and click **Finish**.

2. **Change the Admin Password** from the default (`1234`) by editing `ADMIN_PASSWORD` in `config.py` before go-live.

3. **Camera network isolation:** Where possible, place the Hikvision camera on a separate VLAN or network segment accessible only by the IPC — not by general office PCs.

### Port Reference Table

| Port | Protocol | Purpose | Direction |
|---|---|---|---|
| `8000` | HTTP / WebSocket | Web dashboard and real-time status updates | Inbound to IPC |
| `554` | RTSP (TCP/UDP) | Live video stream from Hikvision camera | Outbound from IPC to camera |
| `1433` | TCP | Microsoft SQL Server Express (default port) | Local (loopback) or LAN |
| `3306` | TCP | MySQL (if used as alternative database) | Local (loopback) or LAN |

> **📝 NOTE:** SQL Server and MySQL ports do **not** need to be opened on the Windows Firewall if the database runs on the same IPC as the application (which is the default deployment). Only open these ports if you are running the database on a separate server.

---

*End of Chapter 2 — Continue to Chapter 3: Installation & First-Time Setup*
