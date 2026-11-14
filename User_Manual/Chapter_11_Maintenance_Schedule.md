# Chapter 11 — Maintenance Schedule & Checklist

**Firewall DFP6 SOP Monitoring System**
*Delphi-TVS Technologies Limited*

---

## Overview

This chapter provides structured maintenance checklists for all roles involved in operating and supporting the Firewall DFP6 SOP Compliance System. Regular maintenance ensures:

- Continuous and accurate AI inspection performance
- Reliable data logging and traceability
- Early detection of hardware or software issues before they cause downtime

Maintenance tasks are grouped by frequency and the responsible role:

| Frequency | Responsible Role | Section |
|-----------|-----------------|---------|
| Daily | Shop-floor Operator | [11.1](#111-daily-checks-operator) |
| Weekly | Maintenance Technician | [11.2](#112-weekly-checks-maintainer) |
| Monthly | Admin / IT Engineer | [11.3](#113-monthly-checks-admin--it) |
| Annual / As-Needed | IT / Development Team | [11.4](#114-annual--as-needed-tasks) |

> **📝 NOTE:** Print the relevant checklist section and display it at the workstation. Operators and technicians should physically tick off each item and sign/date the printed sheet for quality record purposes.

---

## 11.1 Daily Checks (Operator)

**Who:** Shop-floor operator assigned to the firewall inspection station.
**When:** At the start of every shift, before the first part is inspected.
**Time required:** Approximately 5 minutes.

| ✅ | Task | How to Perform |
|----|------|----------------|
| ☐ | Confirm application is running and dashboard loads | Open browser → go to **http://localhost:8000** → page should load within 5 seconds |
| ☐ | Check camera feed is live and clear | Look at the camera panel on the dashboard — it should show a clear, moving live video image with no freezing or black screen |
| ☐ | Confirm the correct inspection profile is loaded | Look at the profile indicator on the dashboard — it must match the part type being produced that shift (TML Part or HMI Part) |
| ☐ | Verify that supervisor bypass is OFF | Check the status bar or admin panel — bypass must show **OFF** at the start of every shift |
| ☐ | Run one test inspection at the start of shift | Place a known-good part in the inspection area, check all gauges in the correct sequence, and confirm the system shows a **PASS** result |
| ☐ | Clean the camera lens if dust or condensation is present | Wipe gently with a **dry microfibre cloth** only — do not use liquids, sprays, or paper towels near the lens |

> **⚠️ WARNING:** If the camera feed shows a black screen, is frozen, or the dashboard does not load, **do not begin production**. Contact your maintenance team immediately. Parts inspected without a functioning AI system cannot be verified for compliance.

> **⚠️ WARNING:** If the supervisor bypass shows **ON** at the start of a shift and no authorised supervisor has enabled it, do not proceed. Contact your team leader immediately — this may indicate the bypass was left on from a previous shift.

> **📝 NOTE:** If a test inspection with a known-good part shows a FAIL result, do not use the system. Report the fault to the maintenance team before inspecting any production parts.

---

## 11.2 Weekly Checks (Maintainer)

**Who:** Maintenance technician or designated line engineer.
**When:** Once per week, preferably at the start of the working week or during a planned maintenance slot.
**Time required:** Approximately 15–20 minutes.

| ✅ | Task | How to Perform |
|----|------|----------------|
| ☐ | Verify database is logging inspection results correctly | Run **`View_MSSQL_Database.bat`** (or **`View_Database.bat`** for MySQL) — confirm that new records have been added since the previous week's check |
| ☐ | Review any NG (Not Good) results for patterns | Query the database for records where `compound_status = 0` (FAIL). Check if failures are linked to a specific time, operator, part batch, or gauge position |
| ☐ | Check the application command window or logs for errors | Review the console output for any `ERROR` or `WARNING` lines. Pay attention to lines from `db_logger`, `scan_listener`, or model loading sections |
| ☐ | Inspect camera physical mounting | Physically check the camera bracket — confirm it has not shifted, loosened, or tilted. The camera must point straight down at the inspection area |
| ☐ | Check barcode scanner USB connection | Unplug and re-plug the barcode scanner USB. Open Notepad and scan a test barcode to confirm characters are typed correctly |
| ☐ | Check disk space on the IPC | Open Windows Explorer → right-click the **C: drive** → **Properties** → confirm at least **5 GB free space** is available |

> **📝 NOTE:** Disk space is consumed primarily by the Python virtual environment, model files, and application logs. If space is running low, work with the IT team to archive old log files.

> **📝 NOTE:** Reviewing NG results for patterns is important for proactive quality management. For example, if most failures occur in the first hour of a shift, it may indicate an operator training issue rather than a system fault.

---

## 11.3 Monthly Checks (Admin / IT)

**Who:** System administrator or IT engineer responsible for the IPC.
**When:** Once per month. Schedule during a planned maintenance window to avoid disrupting production.
**Time required:** Approximately 30–45 minutes.

| ✅ | Task | How to Perform |
|----|------|----------------|
| ☐ | Backup the database | Follow the database backup procedure in **Chapter 8.5**. Confirm the backup file is saved to a network drive or external storage — not only on the IPC's local disk |
| ☐ | Review inspection log data for the month | Export or query the database for all records from the past 30 days. Review total part count, PASS rate, FAIL rate, and average cycle time |
| ☐ | Check for software updates | Contact the development team to confirm whether a new version of the software or AI model is available |
| ☐ | Verify admin password is not the default | Open `SOP_Compliance\config.py` → check the `ADMIN_PASSWORD` value. If it still reads `"1234"`, change it immediately (see Chapter 12.1 for instructions) |
| ☐ | Test the emergency supervisor bypass procedure | Log in to the admin panel → enable bypass → verify the dashboard changes state → disable bypass → verify normal AI inspection resumes |
| ☐ | Check GPU temperature and performance | Use **GPU-Z** or the **NVIDIA System Management Interface** (`nvidia-smi` in Command Prompt) to check GPU temperature (should be below 80°C under load) and memory usage |
| ☐ | Review Windows Update status on the IPC | Go to **Settings → Windows Update** → install any pending security or quality updates. Schedule a maintenance restart as needed |

> **⚠️ WARNING:** Always take a database backup **before** installing Windows Updates or making any configuration changes to the IPC. If an update causes a compatibility problem, the backup allows you to restore quickly.

> **📝 NOTE:** Monthly review of PASS/FAIL data can reveal trends in inspection quality, operator compliance, or gauge wear. Share this data with the quality team as part of monthly quality review meetings.

---

## 11.4 Annual / As-Needed Tasks

These tasks are not on a fixed schedule but must be performed when the specified trigger condition occurs.

| Task | Trigger Condition | Responsible Role | Action to Take |
|------|-------------------|-----------------|----------------|
| **AI model retraining** | Detection accuracy drops below acceptable levels; new gauge types are added to the inspection; false positive rate increases significantly | AI/Development Team | Contact the development team. Provide sample images of detection failures. The team will retrain the YOLO model and deploy a new `.pt` file (see Chapter 9.2) |
| **Camera replacement** | Camera hardware fails physically; image quality degrades despite cleaning; RTSP stream becomes unreliable | Maintenance Technician + IT | Replace the Hikvision camera with the same model. Update `LIVE_CAMERA_URL` in `config.py` with the new camera's IP address (see Chapter 2 for camera setup) |
| **Database archiving** | The `inspection_logs` table grows to more than 50,000 records; database queries slow noticeably | IT Engineer | Archive records older than the retention period to a separate archive table or export them to Excel. Consult your quality and compliance team for the required retention period |
| **IPC hardware servicing** | The IPC shows performance degradation; fan noise increases; system overheats or throttles | IT / Facilities | Clean internal cooling fans and heat sinks. Check thermal paste on CPU and GPU. Service must be performed by a qualified technician. Keep the IPC powered off during servicing |
| **Adding a new inspection profile** | A new part type must be inspected by the system (beyond TML and HMI parts) | Development Team + IT | Follow the instructions in **Chapter 7.8 — Adding a New Inspection Profile** in `config.py`. A new YOLO model trained for the new part's gauges will be required |
| **Password change** | Staff changes in the team; potential security compromise; routine security policy | IT / Admin | Update `ADMIN_PASSWORD` in `config.py` and the matching value in `SOP_Compliance/frontend/app.js`. Communicate the new password only to authorised personnel |
| **IPC operating system reinstall** | Severe OS corruption; unrecoverable system failure | IT Engineer | Re-image the IPC. Then follow Chapter 9.3 (Full Re-Install on a New IPC Machine) to restore the application from the USB export |

> **⚠️ WARNING:** AI model retraining requires expertise in machine learning and access to labelled training data. Do not attempt to modify or retrain the model without involvement from the development team. Deploying an incorrectly trained model may cause the inspection system to pass defective parts.

---

## Maintenance Log Template

It is recommended that a physical or digital maintenance log is kept at the inspection station. The following template can be used for weekly and monthly checks:

| Date | Check Type | Performed By | Findings / Notes | Sign-off |
|------|-----------|--------------|-----------------|---------|
| DD/MM/YYYY | Daily / Weekly / Monthly | Name | (Any anomalies or actions taken) | Signature |
| | | | | |
| | | | | |

> **📝 NOTE:** Keep completed maintenance logs on file for a minimum of 1 year, or as required by your site's quality management system (QMS).

---

*End of Chapter 11*

| ← Previous Chapter | Next Chapter → |
|-------------------|----------------|
| Chapter 10 — Troubleshooting | Chapter 12 — Security & Safety Notes |
