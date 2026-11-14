# SOP Compliance Software — Firewall DFP6

## User Manual & Maintenance Guide

---

| Document Property | Value |
|---|---|
| **Product Name** | SOP Compliance Software — Fire Wall DFP6 |
| **Company** | Delphi-TVS Technologies Limited |
| **Department** | DFP6 Department (Vision Quality Systems) |
| **Software Version** | `1.0.0` (verified in `SOP_Compliance/config.py`) |
| **Document Date** | November 2026 |
| **Target Platform** | Windows 10 / 11 (64-bit) Industrial PC (IPC) with NVIDIA CUDA GPU |

---

## Document Purpose

This manual provides complete instructions for operating, administering, installing, configuring, updating, troubleshooting, and maintaining the **Firewall DFP6 SOP Compliance System**. It is designed so that any operator, supervisor, or maintenance/IT engineer can keep the system running smoothly on the shop floor — including performing a full re-installation on a new Industrial PC (IPC) — without prior knowledge of the codebase.

---

## How to Use This Manual (By Role)

Use the guide below to jump directly to the chapters relevant to your role:

| Role | Primary Responsibilities | Recommended Chapters |
|---|---|---|
| **Shop-Floor Operator** | Runs daily part inspections, scans barcodes, applies gauges, reads PASS/FAIL results | **Chapter 1** (Overview), **Chapter 4** (Starting/Stopping), **Chapter 5** (Operator Daily-Use Guide), **Appendix D** (Quick-Reference Card) |
| **Supervisor / Admin** | Monitors line status, handles NG parts, activates/disables emergency Supervisor Bypass, switches profiles manually | **Chapter 1**, **Chapter 5**, **Chapter 6** (Admin Functions), **Chapter 12** (§12.3 Bypass Safety), **Appendix D** |
| **Maintainer / IT Engineer** | Installs software (online or offline USB), edits `config.py`, manages SQL Server / MySQL database, updates models/code, troubleshoots issues | **All chapters** — especially **Chapters 2, 3, 7, 8, 9, 10, 11, 12** and **Appendices A, B, C, E** |

> **📝 NOTE:** Print **Appendix D (Quick-Reference Card)** and **Chapter 11 (Daily/Weekly Checklists)** and keep laminated copies at the shop-floor inspection station.

---

## Table of Contents

| Section | Title | Description | File |
|---|---|---|---|
| **Cover** | **Cover Page & Table of Contents** | Document overview, role guide, and navigation links | [Chapter_00_Cover_and_TOC.md](./Chapter_00_Cover_and_TOC.md) |
| **Chapter 1** | **Introduction** | What the software does, TML & HMI inspection profiles, system architecture diagram, and personnel roles | [Chapter_01_Introduction.md](./Chapter_01_Introduction.md) |
| **Chapter 2** | **System Requirements & Hardware Setup** | IPC/GPU specs, High Performance power plan, Hikvision RTSP camera setup, static IP setup, USB barcode scanner, and LAN/Firewall ports | [Chapter_02_System_Requirements.md](./Chapter_02_System_Requirements.md) |
| **Chapter 3** | **Software Installation (First-Time Setup)** | Installing Python 3.11, Visual C++ Runtime, SQL Server Express / MySQL, Python virtual environment, offline USB deployment, portable `Software/` option, and AI model files | [Chapter_03_Installation.md](./Chapter_03_Installation.md) |
| **Chapter 4** | **Starting & Stopping the Application** | Launching via `Run_App.bat` / `Run_Software.bat`, startup sequence, accessing the dashboard locally or over LAN, clean shutdown, and Windows auto-start | [Chapter_04_Starting_Stopping.md](./Chapter_04_Starting_Stopping.md) |
| **Chapter 5** | **Operator Daily-Use Guide (Shop Floor)** | Plain-language shop-floor guide: dashboard panels, glove safety banner, barcode scanning, TML & HMI step-by-step gauging, U-gauge rack order, PASS/FAIL handling, and blur zone | [Chapter_05_Operator_Guide.md](./Chapter_05_Operator_Guide.md) |
| **Chapter 6** | **Admin / Supervisor Functions** | Admin PIN login, Dynamic Settings modal, emergency Supervisor Bypass (`Enable Bypass` / `Disable`), manual profile switching, changing passwords, and Blur Zone controls | [Chapter_06_Admin_Functions.md](./Chapter_06_Admin_Functions.md) |
| **Chapter 7** | **Configuration Reference (`config.py`)** | Complete guide to `config.py` and `settings.json` precedence, camera/AI/validation/scanner/DB/server settings, and adding new inspection profiles | [Chapter_07_Configuration_Reference.md](./Chapter_07_Configuration_Reference.md) |
| **Chapter 8** | **Database & Inspection Logs** | Logged fields, viewing logs (`View_MSSQL_Database.bat` / `View_Database.bat`), SQL schema, switching MSSQL ↔ MySQL, backup/restore, and `synced_to_it` IT integration | [Chapter_08_Database_Logs.md](./Chapter_08_Database_Logs.md) |
| **Chapter 9** | **Updating the Software** | Code-only USB updates (`Export_To_USB.bat` → `Update_From_USB.bat`), Git updates (`Update_App.bat`), updating `.pt` AI weights & TensorRT engines, full re-install, and checking version | [Chapter_09_Updating_Software.md](./Chapter_09_Updating_Software.md) |
| **Chapter 10** | **Troubleshooting** | Step-by-step diagnostics for startup failures, `c10.dll` errors, camera black screen, slow video playback, barcode scanner, database logging, AI detection accuracy, and stuck bypass | [Chapter_10_Troubleshooting.md](./Chapter_10_Troubleshooting.md) |
| **Chapter 11** | **Maintenance Schedule & Checklist** | Daily (operator), weekly (maintainer), monthly (admin/IT), and annual/as-needed checklists plus printable log template | [Chapter_11_Maintenance_Schedule.md](./Chapter_11_Maintenance_Schedule.md) |
| **Chapter 12** | **Security & Safety Notes** | Admin password policy, network exposure & Windows Firewall rules, Supervisor Bypass safety rules, privacy blur zone, and data retention/compliance | [Chapter_12_Security_Safety.md](./Chapter_12_Security_Safety.md) |
| **Appendices** | **Appendices A–E** | **A:** Glossary, **B:** File & Folder Reference, **C:** API Endpoint Reference, **D:** Operator Quick-Reference Card, **E:** Contact & Escalation List | [Appendices.md](./Appendices.md) |

---

*Delphi-TVS Technologies Limited — Tomorrow's Engineering Today*
