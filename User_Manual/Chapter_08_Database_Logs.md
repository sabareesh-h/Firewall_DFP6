# Chapter 8 — Database & Inspection Logs

**Firewall DFP6 SOP Compliance System**  
*Delphi-TVS Technologies Limited*

---

> **👥 Intended Audience:** This chapter is written for **IT Maintainers, Quality Engineers, and Database Administrators (DBAs)**.

---

## Table of Contents

- [8.1 What Is Logged Per Inspection](#81-what-is-logged-per-inspection)
- [8.2 Viewing the Database](#82-viewing-the-database)
- [8.3 Database Schema (`inspection_logs` Table)](#83-database-schema-inspection_logs-table)
- [8.4 Switching Between MSSQL and MySQL](#84-switching-between-mssql-and-mysql)
- [8.5 Backing Up and Restoring the Database](#85-backing-up-and-restoring-the-database)
- [8.6 `synced_to_it` Column — IT Integration](#86-synced_to_it-column--it-integration)

---

## 8.1 What Is Logged Per Inspection

The background logger (`SOP_Compliance/db_logger.py`) automatically writes one row to the `inspection_logs` table inside the `firewall_sop` database every time an inspection cycle finishes (both PASS and FAIL/incomplete cycles).

Because logging runs in a dedicated background thread using a queue, database writes add virtually zero delay (`< 0.01 ms` overhead) to the live camera and YOLO inspection pipeline. If the database server is temporarily unreachable, pending inspection records remain queued in memory and are retried automatically every few seconds once connectivity returns.

### Fields Recorded

| Field | Data Type | Description |
|---|---|---|
| `id` | Auto-increment integer | Unique sequential record ID (primary key) |
| `part_id` | Text (up to 60 chars) | Scanned part barcode / identifier (or fallback part label if no barcode was scanned) |
| `timestamp` | DateTime (`YYYY-MM-DD HH:MM:SS`) | Local date and time when the inspection cycle completed |
| `compound_status` | Integer (`1` or `0`) | `1` = All gauges checked and PASS (`result == "OK"`)<br>`0` = One or more gauges missed / NG / incomplete |
| `cycle_time` | Decimal (`6,1`) | Total duration of the inspection cycle in seconds (rounded to 1 decimal place) |
| `synced_to_it` | Integer (`0` or `1`) | Integration flag for IT/MES systems (always written as `0` by this application) |

> **📝 NOTE:** Database logging can be disabled completely for offline testing by setting `DB_ENABLED = False` in `SOP_Compliance/config.py` and restarting the application.

---

## 8.2 Viewing the Database

Two helper batch scripts are provided in the root project folder (and inside `Software/`) so maintainers and quality staff can quickly inspect recent records without installing heavy SQL client tools.

### Viewing Microsoft SQL Server (MSSQL) Logs

1. Double-click **`View_MSSQL_Database.bat`** in the project folder.
2. It runs `view_database.py`, which queries the **latest 25 records** from `inspection_logs` on `localhost\SQLEXPRESS` (`firewall_sop` database) using Windows Authentication.
3. A terminal table displays `ID`, `PART ID`, `TIMESTAMP`, `STATUS` (`1 [PASS - OK]` or `0 [FAIL/INC]`), `CYCLE`, and `SYNCED`.
4. Press **Enter** to close the window.

> **📝 NOTE:** `view_database.py` connects specifically to `SERVER=localhost\SQLEXPRESS` using `DRIVER={SQL Server}` and `Trusted_Connection=yes`. If your MSSQL instance is on a different host/instance name or uses SQL Server username/password authentication, either inspect the database via **SQL Server Management Studio (SSMS)** or update the connection string inside `view_database.py`.

### Viewing MySQL Logs

1. Double-click **`View_Database.bat`** in the project folder.
2. It automatically locates `mysql.exe` (including MySQL Server 8.0 / 8.4 default paths) and queries the **latest 20 records** from `firewall_sop.inspection_logs` using user `sop_user` (password `Sop@1234`).
3. If the table is empty or missing, it prints the available databases and tables for quick diagnostics.
4. Press any key to close the window.

### Viewing Recent Records in the Web Dashboard

Operators and supervisors can also view the **5 most recent inspections** from the current session directly in the **Recent Inspection Logs** panel at the bottom of the web dashboard (`http://localhost:8000`). Records performed while Supervisor Bypass was active display a `BYPASS` tag in the UI log table.

---

## 8.3 Database Schema (`inspection_logs` Table)

You do **not** need to create the database or table manually when using SQL Server Express (or after running `Setup_MySQL.bat` for MySQL). On startup, `db_logger.py` automatically creates the `firewall_sop` database (if missing) and the `inspection_logs` table with indexes.

### Microsoft SQL Server (MSSQL) Schema

```sql
CREATE TABLE [inspection_logs] (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    part_id         NVARCHAR(60) NOT NULL,
    timestamp       DATETIME NOT NULL,
    compound_status TINYINT NOT NULL,
    cycle_time      DECIMAL(6,1) NULL,
    synced_to_it    TINYINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_part_id   ON [inspection_logs] (part_id);
CREATE INDEX idx_timestamp ON [inspection_logs] (timestamp);
CREATE INDEX idx_synced    ON [inspection_logs] (synced_to_it);
```

### MySQL Schema

```sql
CREATE TABLE IF NOT EXISTS `inspection_logs` (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    part_id         VARCHAR(60) NOT NULL,
    timestamp       DATETIME NOT NULL,
    compound_status TINYINT(1) NOT NULL,
    cycle_time      DECIMAL(6,1) DEFAULT NULL,
    synced_to_it    TINYINT(1) NOT NULL DEFAULT 0,
    INDEX idx_part_id (part_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_synced (synced_to_it)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **📝 NOTE:** Both `DB_NAME` (`"firewall_sop"`) and `DB_TABLE` (`"inspection_logs"`) are configurable in `SOP_Compliance/config.py`.

---

## 8.4 Switching Between MSSQL and MySQL

Follow these steps if you need to switch the application from Microsoft SQL Server to MySQL, or vice versa.

1. **Stop the application** cleanly (`Ctrl + C` in the command window).
2. Ensure the target database engine is installed and running:
   - **If switching to MSSQL:** Install `SQL2022-SSEI-Expr.exe` (Basic) and ensure the `SQL Server (SQLEXPRESS)` service is running. Verify an ODBC SQL Server driver (e.g., `ODBC Driver 17 for SQL Server`, `ODBC Driver 18 for SQL Server`, or `SQL Server`) is installed, or rely on `pymssql` (included in `requirements.txt`).
   - **If switching to MySQL:** Install `mysql-installer.msi` and run `Setup_MySQL.bat` once to create the `firewall_sop` database and `sop_user` account (`Sop@1234`). Python uses `pymysql` (included in `requirements.txt`).
3. Open **`SOP_Compliance\config.py`** in a text editor and update the database section:

   **Settings for MSSQL (Default):**
   ```python
   DB_ENABLED  = True
   DB_TYPE     = "mssql"
   DB_HOST     = "localhost\\SQLEXPRESS"
   DB_PORT     = 1433
   DB_USER     = ""        # Empty = Windows Authentication
   DB_PASSWORD = ""
   DB_NAME     = "firewall_sop"
   DB_TABLE    = "inspection_logs"
   DB_DRIVER   = "ODBC Driver 17 for SQL Server"
   ```

   **Settings for MySQL:**
   ```python
   DB_ENABLED  = True
   DB_TYPE     = "mysql"
   DB_HOST     = "localhost"
   DB_PORT     = 3306
   DB_USER     = "sop_user"
   DB_PASSWORD = "Sop@1234"
   DB_NAME     = "firewall_sop"
   DB_TABLE    = "inspection_logs"
   ```

4. Save `config.py` and restart the application with **`Run_App.bat`** (or **`Run_Software.bat`**).
5. Watch the terminal output for:
   - `db_logger: MSSQL Database 'firewall_sop' and table 'inspection_logs' are ready.` (or MySQL equivalent)
   - `db_logger: MSSQL connection established.`
6. Run a test inspection and verify the record appears using `View_MSSQL_Database.bat` or `View_Database.bat`.

> **⚠️ WARNING:** Switching database engines does **not** migrate historical records from the old database to the new one. Back up or export existing records before switching.

---

## 8.5 Backing Up and Restoring the Database

Schedule regular backups (recommended: **monthly** minimum, or **weekly** on high-volume lines) and store backup files on a separate drive or network share — never solely on the IPC's local C: drive.

### Microsoft SQL Server (MSSQL) Backup & Restore

**Backup using SQL Server Management Studio (SSMS):**
1. Open **SSMS** and connect to `localhost\SQLEXPRESS` (Windows Authentication).
2. Expand **Databases** → right-click **`firewall_sop`** → **Tasks** → **Back Up...**
3. Confirm Backup type is **Full**.
4. Under **Destination**, specify a `.bak` path (e.g., `D:\Backups\firewall_sop_YYYYMMDD.bak`).
5. Click **OK** and wait for the completion message.

**Backup using Command Prompt (`sqlcmd`):**
```cmd
sqlcmd -S localhost\SQLEXPRESS -E -Q "BACKUP DATABASE [firewall_sop] TO DISK = N'D:\Backups\firewall_sop_backup.bak' WITH NOFORMAT, INIT, NAME = N'firewall_sop-Full'"
```

**Restore using SSMS:**
1. Open **SSMS**, stop the SOP Compliance application first so no connections are open.
2. Right-click **Databases** → **Restore Database...**
3. Select **Device** → browse to your `.bak` file → click **OK**.
4. Under **Options**, check **Overwrite the existing database (WITH REPLACE)** if restoring over an active database, then click **OK**.
5. Restart the SOP Compliance application.

### MySQL Backup & Restore

**Backup using `mysqldump`:**
1. Open Command Prompt (ensure MySQL `bin` directory is in PATH or `cd` into `C:\Program Files\MySQL\MySQL Server 8.x\bin\`).
2. Run:
   ```cmd
   mysqldump -u sop_user -p firewall_sop > firewall_sop_backup_YYYYMMDD.sql
   ```
3. Enter the password (`Sop@1234` unless changed) when prompted.

**Restore using `mysql`:**
1. Stop the SOP Compliance application.
2. Run:
   ```cmd
   mysql -u sop_user -p firewall_sop < firewall_sop_backup_YYYYMMDD.sql
   ```
3. Enter the password when prompted, then restart the application.

---

## 8.6 `synced_to_it` Column — IT Integration

The `synced_to_it` column (indexed via `idx_synced`) is reserved for integration with Delphi-TVS central IT systems (such as MES, ERP, or Power BI quality dashboards).

### How the Handshake Works

1. The SOP Compliance application **always inserts new rows with `synced_to_it = 0`** and never modifies `synced_to_it` afterward.
2. An external IT sync script / ETL service polls `inspection_logs` periodically for unsynchronised rows:
   ```sql
   SELECT id, part_id, timestamp, compound_status, cycle_time
   FROM inspection_logs
   WHERE synced_to_it = 0
   ORDER BY id ASC;
   ```
3. After the external IT system confirms the rows have been uploaded to the central database, the sync job marks them as transferred:
   ```sql
   UPDATE inspection_logs
   SET synced_to_it = 1
   WHERE id IN (...);
   ```

> **⚠️ WARNING:** Do **not** delete rows where `synced_to_it = 0` during database archiving or cleanup. Always confirm records have `synced_to_it = 1` (or have been manually exported) before purging old records.

---

*End of Chapter 8*

| Previous Chapter | Next Chapter |
|---|---|
| [Chapter 7 — Configuration Reference (`config.py`)](./Chapter_07_Configuration_Reference.md) | [Chapter 9 — Updating the Software](./Chapter_09_Updating_Software.md) |
