# Chapter 12 — Security & Safety Notes

**Firewall DFP6 SOP Monitoring System**
*Delphi-TVS Technologies Limited*

---

## Overview

This chapter covers the security controls and safety policies that govern the operation of the Firewall DFP6 SOP Compliance System. It is intended for **IT administrators, system owners, and supervisors**.

Ensuring the integrity of this system is critical — it is the final verification gate before a part passes inspection. Any tampering, misconfiguration, or misuse of the bypass function may allow defective parts to reach the customer.

| Topic | Section |
|-------|---------|
| Admin password policy | [12.1](#121-admin-password-policy) |
| Network exposure and firewall configuration | [12.2](#122-network-exposure) |
| Supervisor bypass safety rules | [12.3](#123-supervisor-bypass-safety-rules) |
| Camera privacy blur zone | [12.4](#124-privacy-blur-zone--data-protection) |
| Data retention and compliance | [12.5](#125-data-retention-and-compliance) |

---

## 12.1 Admin Password Policy

The admin password controls access to the Admin Panel in the browser dashboard. The admin panel allows users to:
- Enable or disable the supervisor bypass
- Change inspection profiles manually
- Access configuration and system settings

### Default Password — Change Required Before Go-Live

> **⚠️ WARNING:** The system ships with the default admin password `1234`. This password is documented in this manual and must be changed before the system is put into production on the shop floor. Failure to change the default password means any person who has seen this manual can access and disable the AI inspection system.

### How to Change the Admin Password

The password is stored in two places and **both must be updated** to match:

**Step 1 — Update `config.py`:**
1. On the IPC, navigate to the `SOP_Compliance` folder.
2. Open `config.py` in Notepad.
3. Find the line:
   ```python
   ADMIN_PASSWORD = "1234"
   ```
4. Replace `"1234"` with your chosen password, keeping the quotes:
   ```python
   ADMIN_PASSWORD = "YourNewPassword"
   ```
5. Save and close the file.

**Step 2 — Update `app.js`:**
1. In the `SOP_Compliance` folder, navigate to `frontend\`.
2. Open `app.js` in Notepad.
3. Find the matching password reference and update it to the same value you entered in `config.py`.
4. Save and close the file.

**Step 3 — Restart the application:**
1. Stop the application (Ctrl + C in the command window).
2. Run `Run_App.bat` again.
3. Test the new password by clicking Admin in the dashboard.

### Password Strength Recommendations

| Recommendation | Reason |
|----------------|--------|
| Minimum 8 characters | Short passwords are easily guessed |
| Mix of letters and numbers | Increases the number of possible combinations |
| Avoid common words or dates | Words like "admin", "1234", or the company name are tried first by anyone attempting to guess |
| Do not reuse the password from other systems | Isolates this system if another password is compromised |

### Password Access Control

| Rule | Detail |
|------|--------|
| **Do not share with operators** | Operators should not have access to the admin panel. The bypass is a supervisor-only control. |
| **Limit knowledge to authorised personnel** | Only the system owner, IT admin, and designated supervisors should know the password. |
| **If the password is forgotten** | Access `config.py` directly on the IPC (requires physical access to the machine or remote desktop access). The password is stored in plain text in `config.py`. |

> **📝 NOTE:** Because the password is stored in plain text in `config.py`, physical access to the IPC must be controlled. The IPC should be in a locked cabinet or restricted area where shop-floor operators cannot access it directly.

---

## 12.2 Network Exposure

### How the Application Binds to the Network

The FastAPI application server binds to the address `0.0.0.0` on port **8000**. This means:

- It is accessible from **any device on the same Local Area Network (LAN)**, not just the IPC itself.
- Any user on the network who knows the IPC's IP address can open `http://<IPC_IP>:8000` in a browser and view the dashboard.

This is intentional — it allows supervisors to monitor the inspection from their workstations without needing to be at the IPC. However, it also means unauthorised access is possible if no network-level controls are in place.

### Recommended Network Security Actions

> **⚠️ WARNING:** Do **not** expose port 8000 to the internet or to a network that is not physically secured. The application has no HTTPS encryption and no session token system beyond the admin password.

#### Action 1 — Restrict Inbound Access by IP Address (Windows Firewall)

Configure Windows Defender Firewall to allow inbound connections on port 8000 **only from specific trusted IP addresses** (for example, the supervisor's workstation).

1. Press **Win + R**, type `wf.msc`, press **Enter**.
2. In the left panel, click **Inbound Rules**.
3. In the right panel, click **New Rule…**
4. Select **Port** → click **Next**.
5. Select **TCP**, enter **8000** → click **Next**.
6. Select **Allow the connection** → click **Next**.
7. Apply to all profiles (Domain, Private, Public) → click **Next**.
8. Give the rule a name (e.g., `SOP Dashboard Port 8000`) → click **Finish**.
9. Double-click the newly created rule → go to the **Scope** tab.
10. Under **Remote IP address**, select **These IP addresses** and add only the IPs of trusted machines (e.g., supervisor's workstation, IT admin PC).

#### Action 2 — Use an Isolated Production LAN

| Recommendation | Detail |
|----------------|--------|
| Place the IPC on an isolated production LAN segment | The IPC should not be on the same network segment as general office computers, Wi-Fi guest networks, or any network with internet access |
| Use a managed switch or VLAN | Configure the production LAN as a separate VLAN to prevent unauthorised devices from connecting |
| Do not connect the IPC to the internet | The application does not require internet access to operate. Keeping the IPC offline reduces the attack surface |

#### Action 3 — Do Not Expose to the Internet

If remote access to the IPC is required by IT or the development team:

- Use a **VPN** to create a secure tunnel into the production LAN — do not forward port 8000 to the internet.
- Use **Windows Remote Desktop (RDP)** over VPN instead of exposing the web dashboard externally.

---

## 12.3 Supervisor Bypass Safety Rules

### What the Bypass Does

The supervisor bypass is an emergency override that disables the AI inspection engine. When active:
- All checkpoints are shown as **OK (green)** on the dashboard regardless of actual camera analysis.
- Parts continue to be logged in the database as inspections, but the `compound_status` value reflects the bypass state rather than a genuine AI assessment.

### When the Bypass Is Permitted

> **⚠️ WARNING:** The supervisor bypass is intended **only** for genuine emergencies — specifically, when the AI inspection system itself is malfunctioning and production cannot be halted. It must **never** be used to skip a legitimate inspection or to pass a part that has not been verified.

| Permitted Use | Not Permitted |
|--------------|---------------|
| AI model fails to load and production is at risk of shutdown | Speeding up cycle time |
| Camera hardware failure mid-shift | Avoiding inspection of a suspicious part |
| Software error that prevents detection from running | Operator convenience |
| During initial system commissioning and calibration | Bypassing inspection for end-of-shift rush |

### Mandatory Bypass Safety Procedures

When the bypass must be activated, the following procedure must be followed:

1. The **supervisor or team leader** (not the operator) must log in to the admin panel using the admin password.
2. The supervisor must **physically document** the bypass activation — record the time, reason, and their name in the maintenance log.
3. Any parts inspected under bypass **must be held separately** and subjected to **manual visual inspection** by a qualified person before being released to the next process step.
4. The bypass must be **disabled as soon as the AI system is restored** — it must not be left on for the next shift.
5. After the bypass is disabled, the supervisor must verify that the AI system is functioning correctly by running a test inspection with a known-good part.

> **📝 NOTE:** The supervisor bypass automatically turns **OFF** every time the application is restarted. If a restart resolves the AI issue, the bypass will not carry over to the new session.

### Auditability

All inspection events during a bypass period are still written to the database with timestamps. The IT team and quality manager can query the database to identify any inspection period during which the bypass was active. This information is available for audit purposes.

> **📝 NOTE:** Consider implementing a site policy that requires the quality manager to be notified whenever the bypass is used, and that a written record of parts inspected under bypass is submitted to the QMS (Quality Management System).

---

## 12.4 Privacy Blur Zone — Data Protection

### What It Is

The Firewall DFP6 system uses a live IP camera that is mounted above the inspection station. To protect the privacy of operators working at the station, a **blur zone** is applied to the left portion of every camera frame in real time.

### How It Works

| Aspect | Detail |
|--------|--------|
| **Default blur zone** | Left **36%** of the camera frame |
| **Applied in real time** | The blur is applied by the application before the frame is displayed on the dashboard |
| **Not stored** | No unblurred footage is recorded or saved to disk |
| **AI detection excluded** | The YOLO model is configured to ignore any detections that fall within the blur zone, preventing false gauge detections from items outside the inspection area |

The blur zone is designed to:
- **Obscure the operator's face, hands, and personal items** from being displayed on the dashboard (which may be visible to other people in the area)
- **Prevent the AI from incorrectly identifying objects** outside the designated inspection area as gauges

### Adjusting the Blur Zone

If the default left-36% blur zone is insufficient for your site's privacy requirements, it can be adjusted either via **⚙️ Admin → Dynamic Settings → Privacy Blur Zone** (`X1 (%)`, `Y1 (%)`, `X2 (%)`, `Y2 (%)`) or in `config.py` using a 4-element normalised list `[x1, y1, x2, y2]`:

1. Open `SOP_Compliance\config.py` in Notepad.
2. Find the setting:
   ```python
   DEFAULT_BLUR_ZONE = [0.0, 0.0, 0.36, 1.0]
   ```
3. Increase `x2` (the 3rd value). For example, to blur the left 50% of the frame from top to bottom:
   ```python
   DEFAULT_BLUR_ZONE = [0.0, 0.0, 0.50, 1.0]
   ```
4. Save the file and restart the application. *(Note: if `SOP_Compliance\settings.json` exists, it overrides `config.py` defaults; use Admin **Save Changes** or **Reset** accordingly.)*

> **📝 NOTE:** Increasing the blur zone too much may cut off part of the inspection area where gauges are located, reducing detection coverage. Test any change with a live inspection to confirm that all gauges remain visible in the unblurred area.

> **📝 NOTE:** Each coordinate in `[x1, y1, x2, y2]` is a normalised fraction from `0.0` to `1.0` (`0.36` means 36% across, `0.50` means 50%, `1.0` means 100%).

---

## 12.5 Data Retention and Compliance

### What Data Is Stored

The database stores one record per inspection in the `inspection_logs` table. The columns in this table are:

| Column | Data Stored | Privacy Classification |
|--------|-------------|------------------------|
| `part_id` | Part barcode number scanned at inspection | Non-personal — identifies the part, not the person |
| `timestamp` | Date and time of the inspection | Non-personal |
| `compound_status` | Inspection result: `1` = PASS, `0` = FAIL | Non-personal |
| `cycle_time` | Duration of the inspection in seconds | Non-personal |
| `synced_to_it` | Whether the record has been synchronised to the central MES/ERP system: `1` = synced, `0` = pending | Non-personal |

> **📝 NOTE:** The database **does not store** operator names, employee IDs, or any other personally identifiable information (PII). The system is designed to track part compliance, not individual operator performance.

### Recommended Retention Period

The appropriate retention period for inspection records depends on your site's quality management requirements and applicable regulatory standards. General guidance for the automotive industry:

| Standard / Requirement | Typical Retention Period |
|------------------------|--------------------------|
| General automotive quality records | 3–5 years |
| Safety-critical component records | May require longer — consult your quality team |
| Customer-specific requirements (e.g., IATF 16949) | Follow the customer's control plan requirements |

> **📝 NOTE:** Consult your site's Quality Manager and Compliance Officer to determine the specific retention requirement applicable to Firewall DFP6 inspection records. This manual does not constitute legal or compliance advice.

### Integration with Central MES / ERP

The `synced_to_it` column in the database is provided to facilitate integration with the company's central Manufacturing Execution System (MES) or Enterprise Resource Planning (ERP) system.

| `synced_to_it` Value | Meaning |
|----------------------|---------|
| `0` | Record has been logged on the IPC but not yet transferred to the central system |
| `1` | Record has been successfully transferred and acknowledged by the central system |

The synchronisation mechanism itself is managed by the IT integration layer (not by this application). The IT team should configure a scheduled process to:
1. Query all records where `synced_to_it = 0`
2. Upload those records to the central system
3. Update `synced_to_it = 1` for successfully transferred records

### Data Archiving

When the `inspection_logs` table grows large (typically beyond 50,000 records), query performance may degrade. The IT team should:
1. Export records older than the required retention period to a separate archive table or an Excel/CSV file on a network drive.
2. Delete the archived records from the live `inspection_logs` table.
3. Confirm that archived records are stored in a location that is included in regular IT backup procedures.

> **⚠️ WARNING:** Do not delete records from `inspection_logs` that have not yet been synchronised to the central MES/ERP (`synced_to_it = 0`). Deleting unsynced records will cause a gap in the central quality record.

---

## Security & Safety Quick Reference

| Item | Required Action | Priority |
|------|----------------|----------|
| Change default admin password `1234` | Before go-live | 🔴 Critical |
| Restrict port 8000 access via Windows Firewall | Before go-live | 🔴 Critical |
| Place IPC on isolated production LAN | Before go-live | 🔴 Critical |
| Document and control bypass usage | Ongoing policy | 🟠 High |
| Review admin password periodically | Monthly | 🟡 Medium |
| Confirm blur zone is appropriate for the site | On installation | 🟡 Medium |
| Establish data retention policy | Before go-live | 🟡 Medium |
| Confirm MES/ERP synchronisation is working | After deployment | 🟡 Medium |

---

*End of Chapter 12*

| ← Previous Chapter | End of Manual |
|-------------------|---------------|
| Chapter 11 — Maintenance Schedule | — |

---

*Document prepared by Delphi-TVS Technologies Limited.*
*For support, contact the Firewall DFP6 development team.*
