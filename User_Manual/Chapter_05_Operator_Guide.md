# Chapter 5 — Operator Daily-Use Guide (Shop Floor)

**Firewall DFP6 SOP Compliance System**
**Delphi-TVS Technologies Limited**

---

> **📝 NOTE:** This chapter is written for shop-floor operators. No technical knowledge is needed. Read through this chapter fully before your first shift. Keep this guide nearby at the workstation.

---

## 5.1 Dashboard Overview

When the system is running, you will see the **inspection dashboard** open in the browser on the screen at your workstation. The address is **http://localhost:8000**.

The dashboard has several areas. Here is what each one does:

---

### 5.1.1 Live Camera Feed (Center Panel)

This is the **live video** from the camera mounted above the inspection table.

- **Grey box** around a gauge = gauge detected, **not checked yet**
- **Glowing green box** around a gauge = gauge is currently **being held in position** (check in progress)
- **Solid green box** around a gauge = gauge check **completed (OK)** ✅
- **Faint yellow dashed box** = detected part outline
- **Left side of the video is blurred** — this is **normal and intentional**. The system hides the left part of the frame that is not needed for inspection. See [Section 5.7](#57-privacy--blur-zone--what-it-is) for more details.

> **📝 NOTE:** Keep the **right side of the inspection table** clear and well-lit at all times. This is the area the camera uses to detect your gauges.

---

### 5.1.2 Gauge Check Points Panel (Right Sidebar)

This panel displays a progress counter (`0 / 7 Completed`), a progress bar, and the list of **all 7 gauges you must check** for the current part (with small reference images showing what each tool looks like).

| Colour / State | What It Means |
|---|---|
| **Grey / Not Checked** | You have not checked this gauge yet |
| **Highlighted / In Progress** | Gauge is in position — keep holding briefly until it turns green |
| **Green / OK** ✅ | The gauge check is confirmed and locked in |

Work through the checkpoints **from top to bottom**. The panel updates in real time as the camera detects each gauge.

---

### 5.1.3 Current Application & Left Sidebar

The left sidebar shows:
- **Part No.**: Displays the barcode number you scanned.
- **Production Summary**: Running **Total Count**, **Pass Count**, and **Fail Count** for the session.
- **Connection Status**: Shows whether **Model** and **Camera** are `Connected` (green) or `Offline` (red).
- **Current Application (`Part Type`)**: Shows which part type is currently active:
  - **TML** — the 7-gauge TML firewall inspection
  - **HMI** — the 7-checkpoint HMI inspection (includes U-gauges)

The profile **changes automatically** when you scan a part barcode. Always confirm the active button matches your physical part before starting inspection.

---

### 5.1.4 Final Result Card & Recent Logs

Below the Gauge Check Points panel on the right is the **Final Result** card (with a `↻ Reset Inspection` button), and at the bottom of the screen is **Recent Inspection Logs** (showing the last 5 completed parts).

- **Waiting for Part** — Place a part on the table to start.
- **Under Progress** (blue spinning ring) — Inspection is running; finish checking the remaining gauges.
- **PASS** ✅ (green) — All 7 checkpoints completed correctly. The part can move to the next station.
- **FAIL** ❌ (red) — One or more gauges were missed or incomplete. See [Section 5.5](#55-reading-the-results--what-to-do) for what to do.

> **⚠️ SAFETY & BYPASS BANNERS (Top of Screen):**
> - **Red pulsing banner `⚠️ SAFETY: Use gloves when handling the part!`** — The camera detected bare hands without gloves. Put on safety gloves immediately before handling the part.
> - **Red warning strip `⚠ BYPASS ACTIVE`** — Emergency supervisor bypass is turned ON and the system is **not** actually checking gauges. **Stop and call your supervisor immediately** to turn bypass OFF.

---

## 5.2 Starting a New Inspection (Step-by-Step)

Follow these steps at the **beginning of each shift** and before **each new part**.

1. **Check that the system is running.**
   Look at the screen. The browser should show the dashboard at **http://localhost:8000**. You should also see a black command window open in the background. If you do not see this, contact your supervisor or IT — do **not** try to start the system yourself.

2. **Pick up the barcode scanner** and scan the barcode label on the part or its traveller card.

   - If the barcode **starts with `005724`** → the system will switch to **TML Part** mode.
   - If the barcode **starts with `33100-2A160`** → the system will switch to **HMI Part** mode.

   > **📝 NOTE:** You do not need to press any button. The scanner sends the barcode to the system automatically when you scan.

3. **Look at the Profile Indicator** on the dashboard. Confirm it shows the correct part type (TML or HMI). If it shows the wrong type, **do not proceed** — scan the barcode again or see [Section 5.6](#56-manual-profile-switching-without-barcode-scanner).

4. **Place the part on the inspection table** in the camera's view area (the right side of the table, in the unblurred zone).

5. **Wait for the system to detect the part.** You will see a bounding box appear around the part in the live camera feed. Once the box appears, the system is ready.

6. **Begin the inspection** using the steps in [Section 5.3](#53-tml-part--inspection-procedure) (for TML) or [Section 5.4](#54-hmi-part--inspection-procedure) (for HMI).

> **⚠️ WARNING:** Always confirm the profile is correct **before** you begin checking gauges. Checking gauges on the wrong profile will record an incorrect result in the system.

---

## 5.3 TML Part — Inspection Procedure

Use this section when the **Profile Indicator shows: TML Part**.

There are **7 gauges** to check, in the order listed below. Complete them **in order**, one at a time. Wait for each checkpoint to show ✅ OK before moving to the next.

---

### Checkpoint 1 — Distance Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the Distance Gauge from the gauge rack. |
| **Apply** | Place the Distance Gauge **fully inside** the TML part body. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The Distance Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 2 — Pin Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the Pin Gauge from the gauge rack. |
| **Apply** | Apply the Pin Gauge to the **DS Thread area** of the part. The gauge should overlap the DS Thread clearly. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The Pin Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 3 — Dia Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the Dia Gauge from the gauge rack. |
| **Apply** | Bring the Dia Gauge close to the **DS Thread area** of the part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The Dia Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 4 — M6 Thread Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the M6 Thread Gauge from the gauge rack. |
| **Apply** | Apply the M6 Gauge near the **Top Hole area** of the part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The M6 Thread Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 5 — M8 Thread Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the M8 Thread Gauge from the gauge rack. |
| **Apply** | Apply the M8 Gauge near the **Top Hole area** of the part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The M8 Thread Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 6 — 11mm Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the 11mm Gauge from the gauge rack. |
| **Apply** | Apply the 11mm Gauge near the **Outlet** of the part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The 11mm Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 7 — 13mm Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the 13mm Gauge from the gauge rack. |
| **Apply** | Apply the 13mm Gauge near the **Inlet** of the part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The 13mm Gauge checkpoint shows ✅ OK. |

---

### TML Inspection Complete

When all 7 checkpoints show ✅ OK, the **Final Result Banner turns green** and shows **PASS**.

> **⚠️ WARNING:** If the banner shows **FAIL** or any checkpoint shows ❌ NG, do **NOT** pass the part to the next station. See [Section 5.5](#55-reading-the-results--what-to-do).

---

## 5.4 HMI Part — Inspection Procedure

Use this section when the **Profile Indicator shows: HMI Part**.

There are **7 checkpoints** to complete, in the order listed below. The last four use **U-Gauges** — special gauges stored in a rack in a specific order (top to bottom). Complete all steps **in order** and wait for each ✅ OK before moving on.

> **⚠️ WARNING:** Always pick up U-Gauges **from their correct position** in the rack (see the rack label or the order below). After use, **return each U-Gauge to its exact position** in the rack. The system identifies each U-Gauge by its rack position. If the gauges are mixed up, the system will record incorrect results.

---

### Checkpoint 1 — 11mm Pin Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the 11mm Pin Gauge from its resting rack. |
| **Apply** | Apply the 11mm Pin Gauge near the **Inlet Hole** or **Outlet Hole** of the HMI part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The 11mm Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 2 — 8mm Pin Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the 8mm Pin Gauge from its resting rack. |
| **Apply** | Apply the 8mm Pin Gauge near the **Inlet Hole** or **Outlet Hole** of the HMI part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The 8mm Gauge checkpoint shows ✅ OK. |

---

### Checkpoint 3 — Outer Seal Gauge

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the Outer Seal Gauge from its rest position. |
| **Apply** | Place the Outer Seal Gauge **fully inside** the HMI part body. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The Outer Seal checkpoint shows ✅ OK. |

---

### Checkpoint 4 — Inlet Go (U-Gauge) — **Top U-Gauge in Rack**

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the **top** U-Gauge from the U-Gauge rack. This is the **Inlet Go** gauge. |
| **Apply** | Apply the U-Gauge to the **Inlet Hole** of the HMI part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The Inlet Go checkpoint shows ✅ OK. |
| **Return** | Place the U-Gauge back in the **top position** of the rack. |

---

### Checkpoint 5 — Inlet NoGo (U-Gauge) — **2nd U-Gauge in Rack**

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the **second** U-Gauge from the top of the U-Gauge rack. This is the **Inlet NoGo** gauge. |
| **Apply** | Apply the U-Gauge to the **Inlet Hole** of the HMI part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The Inlet NoGo checkpoint shows ✅ OK. |
| **Return** | Place the U-Gauge back in the **second position** of the rack. |

---

### Checkpoint 6 — LP Go (U-Gauge) — **3rd U-Gauge in Rack**

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the **third** U-Gauge from the top of the U-Gauge rack. This is the **LP Go** gauge. |
| **Apply** | Apply the U-Gauge to the **Outlet Hole** of the HMI part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The LP Go checkpoint shows ✅ OK. |
| **Return** | Place the U-Gauge back in the **third position** of the rack. |

---

### Checkpoint 7 — LP NoGo (U-Gauge) — **Bottom U-Gauge in Rack**

| Step | What to Do |
|------|-----------|
| **Pick up** | Take the **bottom** U-Gauge from the U-Gauge rack. This is the **LP NoGo** gauge. |
| **Apply** | Apply the U-Gauge to the **Outlet Hole** of the HMI part. |
| **Wait** | Hold it in position. Watch the Checkpoint Panel. |
| **Confirm** | The LP NoGo checkpoint shows ✅ OK. |
| **Return** | Place the U-Gauge back in the **bottom position** of the rack. |

---

### U-Gauge Rack — Quick Reference

Always pick up and return U-Gauges in this order:

| Rack Position | Gauge Name | Used On |
|:---:|---|---|
| **1st (Top)** | Inlet Go | Inlet Hole |
| **2nd** | Inlet NoGo | Inlet Hole |
| **3rd** | LP Go | Outlet Hole |
| **4th (Bottom)** | LP NoGo | Outlet Hole |

---

### HMI Inspection Complete

When all 7 checkpoints show ✅ OK, the **Final Result Banner turns green** and shows **PASS**.

> **⚠️ WARNING:** If the banner shows **FAIL** or any checkpoint shows ❌ NG, do **NOT** pass the part to the next station. See [Section 5.5](#55-reading-the-results--what-to-do).

---

## 5.5 Reading the Results — What to Do

After completing all checkpoints, the dashboard shows the final result. Use the table below to decide what action to take:

| Result | What It Means | What You Must Do |
|--------|--------------|-----------------|
| ✅ **PASS** (green banner, all checkpoints ✅ OK) | All gauges were correctly checked | The part **can move** to the next station |
| ❌ **NG / FAIL** (red banner, one or more ❌ NG) | One or more gauges were not applied correctly | **Re-check** the failed gauge(s). Apply them again correctly and wait for ✅ OK |
| ⬜ **PENDING** (some checkpoints still showing ⬜) | Inspection is not finished | Continue checking the remaining gauges in order |

> **⚠️ WARNING:** If you re-check a failed gauge and it **still shows ❌ NG**, do **NOT** pass the part. Place it aside and **call your supervisor immediately**.

> **📝 NOTE:** Every inspection result — PASS or FAIL — is saved to the system automatically. You do not need to write anything down or press a save button.

---

## 5.6 Manual Profile Switching (Without Barcode Scanner)

If the barcode scanner is not working or is not available, you can switch the part profile manually from the dashboard without logging into Admin:

1. Look at the **left sidebar**, inside the **Current Application** card under **Part Type**.
2. Click either the **TML** button or the **HMI** button — whichever matches the part you are inspecting.
3. Confirm the clicked button turns blue (active) and the **Gauge Check Points** list updates to match your part.
4. Proceed with the inspection as described in [Section 5.3](#53-tml-part--inspection-procedure) or [Section 5.4](#54-hmi-part--inspection-procedure).

> **📝 NOTE:** The barcode scanner is the preferred and faster method. Manual switching should only be used when the scanner is unavailable. Report the scanner issue to your supervisor or IT team so it can be fixed.

---

## 5.7 Privacy / Blur Zone — What It Is

You will notice that the **left part of the camera feed looks blurred or grey**. This is completely normal.

- The blur is **intentional** — it hides parts of the camera view that are not needed for inspection (such as the surrounding area and anything outside the inspection zone).
- The AI system still works correctly on the **unblurred (right) area** of the frame.
- You do **not** need to do anything about the blur zone.
- The size of the blur zone is set by the IT/maintenance team. Operators **cannot and should not** change it.

> **📝 NOTE:** If you notice the **inspection table area itself appears blurred** (not just the left side), report this to your supervisor or IT team. The blur zone may need to be adjusted.

**What operators should do:**
- Keep the **right side of the inspection table** clear of any objects that are not part of the current inspection.
- Make sure the work area is **well-lit** so the camera can detect gauges clearly.
- Do not place your arms, tools, or other objects in the camera's view unless you are actively applying a gauge.

---

## 5.8 End of Shift

Follow these steps at the end of your shift:

1. **Do not close the browser** (the dashboard tab) unless a supervisor or IT staff member tells you to.
2. **Do not close the black command window** running in the background. The system needs it to keep working.
3. The system **saves all inspection records automatically** — you do not need to do anything to save results.
4. If you have been told to **shut down the system completely**, follow the steps in **Chapter 4, Section 4.4 — Stopping the Application**. Do not shut it down unless instructed.

> **📝 NOTE:** Even if the screen goes dark (screen saver), the system is still running. Touch the mouse or keyboard to wake the screen. The dashboard will still show correctly.

> **⚠️ WARNING:** Closing the black command window or the browser without following the proper shutdown procedure may cause inspection records to be lost for the parts inspected just before shutdown. Always ask IT or your supervisor before closing anything.

---

## Quick-Reference Card

> **📝 NOTE:** The table below is a quick summary for experienced operators. New operators should read the full chapter above first.

**Before Each Part:**
1. Scan the barcode → check the Profile Indicator matches the part type
2. Place the part in camera view → wait for the bounding box to appear

**TML Part — 7 Gauges in Order:**

| # | Gauge | Location on Part |
|---|-------|-----------------|
| 1 | Distance Gauge | Inside TML part body |
| 2 | Pin Gauge | DS Thread area |
| 3 | Dia Gauge | DS Thread area |
| 4 | M6 Thread Gauge | Top Hole area |
| 5 | M8 Thread Gauge | Top Hole area |
| 6 | 11mm Gauge | Outlet |
| 7 | 13mm Gauge | Inlet |

**HMI Part — 7 Checkpoints in Order:**

| # | Gauge | Location on Part |
|---|-------|-----------------|
| 1 | 11mm Pin Gauge | Inlet / Outlet Hole |
| 2 | 8mm Pin Gauge | Inlet / Outlet Hole |
| 3 | Outer Seal Gauge | Inside HMI part body |
| 4 | Inlet Go U-Gauge (rack top) | Inlet Hole |
| 5 | Inlet NoGo U-Gauge (rack 2nd) | Inlet Hole |
| 6 | LP Go U-Gauge (rack 3rd) | Outlet Hole |
| 7 | LP NoGo U-Gauge (rack bottom) | Outlet Hole |

**After All Checkpoints:**
- ✅ Green PASS banner → Part moves to next station
- ❌ Red FAIL/NG banner → Re-check failed gauge; if still NG → call supervisor

---

*End of Chapter 5*

---
*Firewall DFP6 SOP Compliance System — User Manual*
*Delphi-TVS Technologies Limited — Confidential*
