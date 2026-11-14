"""
db_logger.py — Database Background Inspection Logger (MSSQL & MySQL)
====================================================================
Logs every completed inspection (part_id, timestamp, compound_status,
cycle_time) to Microsoft SQL Server (MSSQL) or MySQL WITHOUT blocking
the camera or YOLO inference loop.

Supported Engines:
  • "mssql": Uses pyodbc (Windows built-in driver) or pymssql.
  • "mysql": Uses pymysql (pure-Python).

Design:
  • All writes happen in a dedicated background thread via a Queue.
  • The inference loop drops one tiny dict into the queue and returns
    immediately (<0.01 ms overhead — invisible to the camera pipeline).
  • If the database is temporarily unreachable, records are queued and
    retried automatically once the connection is restored.
  • A `synced_to_it` column (default 0) is reserved for IT systems to flag.

Compound Status values stored in `compound_status` (TINYINT/BIT):
  1 — All gauges checked, inspection PASS (result == "OK")
  0 — One or more gauges not checked, inspection INCOMPLETE / NG
"""

import logging
import queue
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── Internal state ──────────────────────────────────────────────────────────
_queue: "queue.Queue[dict | None]" = queue.Queue()
_worker_thread: threading.Thread | None = None
_db_available: bool = False
_config = None


# ─── Public API ───────────────────────────────────────────────────────────────

def init() -> None:
    """Start background worker thread."""
    global _worker_thread, _config
    try:
        import config as _cfg
        _config = _cfg
    except ImportError:
        logger.error("db_logger: cannot import config — DB logging disabled.")
        return

    if not getattr(_config, "DB_ENABLED", False):
        logger.info("db_logger: DB_ENABLED=False — database logging is OFF.")
        return

    db_type = getattr(_config, "DB_TYPE", "mssql").lower()
    logger.info(f"db_logger: initializing for engine '{db_type.upper()}' ...")

    _worker_thread = threading.Thread(
        target=_worker_loop,
        name="db-logger-worker",
        daemon=True,
    )
    _worker_thread.start()
    logger.info("db_logger: background worker started.")


def log_inspection(part_id: str, compound_status: int, cycle_time_seconds: float) -> None:
    """Queue one inspection record (non-blocking)."""
    if _config is None or not getattr(_config, "DB_ENABLED", False):
        return

    record = {
        "part_id":          part_id,
        "compound_status":  compound_status,          # 1 or 0
        "cycle_time":       round(cycle_time_seconds, 1),
        "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _queue.put(record)


def shutdown() -> None:
    """Gracefully stop worker."""
    if _worker_thread is not None and _worker_thread.is_alive():
        _queue.put(None)
        _worker_thread.join(timeout=5)
        logger.info("db_logger: worker stopped.")


def _get_config():
    """Ensure config is loaded."""
    global _config
    if _config is None:
        try:
            import config as _cfg
            _config = _cfg
        except ImportError:
            pass
    return _config


# ─── MSSQL Connection & Setup ────────────────────────────────────────────────

def _connect_mssql(select_db=True):
    """Connect to Microsoft SQL Server using pyodbc or pymssql."""
    cfg = _get_config()
    host = getattr(cfg, "DB_HOST", "localhost")
    port = getattr(cfg, "DB_PORT", 1433)
    user = getattr(cfg, "DB_USER", "")
    password = getattr(cfg, "DB_PASSWORD", "")
    db_name = getattr(cfg, "DB_NAME", "firewall_sop") if select_db else "master"

    # Try 1: pyodbc (Standard Windows driver)
    try:
        import pyodbc
        available_drivers = pyodbc.drivers()
        driver = getattr(cfg, "DB_DRIVER", "SQL Server")
        if driver not in available_drivers:
            for d in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
                if d in available_drivers:
                    driver = d
                    break

        # Determine server connection string
        # For named instances (like localhost\SQLEXPRESS), do not append port
        server_str = f"{host},{port}" if ("," not in host and "\\" not in host and port) else host

        if user and password:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server_str};"
                f"DATABASE={db_name};"
                f"UID={user};"
                f"PWD={password};"
                f"TrustServerCertificate=yes;"
            )
        else:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server_str};"
                f"DATABASE={db_name};"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
            )
        return pyodbc.connect(conn_str, timeout=5, autocommit=True)
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pyodbc connect attempt failed: {e}")

    # Try 2: pymssql (Self-contained pure TDS connector)
    try:
        import pymssql
        # For pymssql, split host and instance name if present
        if "\\" in host:
            srv_host, srv_instance = host.split("\\", 1)
            return pymssql.connect(
                server=srv_host,
                instance=srv_instance,
                user=user if user else None,
                password=password if password else None,
                database=db_name,
                timeout=5,
                autocommit=True,
            )
        else:
            return pymssql.connect(
                server=host,
                port=port,
                user=user if user else None,
                password=password if password else None,
                database=db_name,
                timeout=5,
                autocommit=True,
            )
    except Exception as e:
        raise RuntimeError(f"Could not connect to MSSQL via pyodbc or pymssql: {e}")


def _ensure_mssql():
    """Create MSSQL database and table if not existing."""
    conn = _connect_mssql(select_db=False)
    cursor = conn.cursor()
    db_name = _config.DB_NAME
    table_name = _config.DB_TABLE

    try:
        cursor.execute(f"""
            IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'{db_name}')
            BEGIN
                CREATE DATABASE [{db_name}];
            END
        """)
        conn.close()

        conn = _connect_mssql(select_db=True)
        cursor = conn.cursor()
        cursor.execute(f"""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[{table_name}]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [{table_name}] (
                    id              INT IDENTITY(1,1) PRIMARY KEY,
                    part_id         NVARCHAR(60) NOT NULL,
                    timestamp       DATETIME NOT NULL,
                    compound_status TINYINT NOT NULL,
                    cycle_time      DECIMAL(6,1) NULL,
                    synced_to_it    TINYINT NOT NULL DEFAULT 0
                );
                CREATE INDEX idx_part_id ON [{table_name}] (part_id);
                CREATE INDEX idx_timestamp ON [{table_name}] (timestamp);
                CREATE INDEX idx_synced ON [{table_name}] (synced_to_it);
            END
        """)
        conn.close()
        logger.info(f"db_logger: MSSQL Database '{db_name}' and table '{table_name}' are ready.")
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─── MySQL Connection & Setup (Kept for fallback) ────────────────────────────

def _connect_mysql(select_db=True):
    import pymysql
    return pymysql.connect(
        host=_config.DB_HOST,
        port=_config.DB_PORT,
        user=_config.DB_USER,
        password=_config.DB_PASSWORD,
        database=_config.DB_NAME if select_db else None,
        connect_timeout=5,
        autocommit=True,
    )


def _ensure_mysql():
    import pymysql
    conn = _connect_mysql(select_db=False)
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{_config.DB_NAME}` CHARACTER SET utf8mb4;")
        cur.execute(f"USE `{_config.DB_NAME}`;")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS `{_config.DB_TABLE}` (
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
        """)
    conn.close()
    logger.info(f"db_logger: MySQL Database '{_config.DB_NAME}' and table '{_config.DB_TABLE}' ready.")
    return True


# ─── Engine Dispatcher ───────────────────────────────────────────────────────

def _connect():
    db_type = getattr(_config, "DB_TYPE", "mssql").lower()
    if db_type == "mssql":
        return _connect_mssql(select_db=True)
    return _connect_mysql(select_db=True)


def _ensure_database_and_table() -> bool:
    db_type = getattr(_config, "DB_TYPE", "mssql").lower()
    try:
        if db_type == "mssql":
            return _ensure_mssql()
        return _ensure_mysql()
    except Exception as exc:
        logger.warning(f"db_logger: {db_type.upper()} setup failed — {exc}")
        return False


def _insert(conn, record: dict) -> None:
    db_type = getattr(_config, "DB_TYPE", "mssql").lower()
    cursor = conn.cursor()
    table = _config.DB_TABLE

    if db_type == "mssql":
        sql = f"INSERT INTO [{table}] (part_id, timestamp, compound_status, cycle_time) VALUES (?, ?, ?, ?)"
        cursor.execute(sql, (
            record["part_id"],
            record["timestamp"],
            record["compound_status"],
            record["cycle_time"]
        ))
    else:
        sql = f"INSERT INTO `{table}` (part_id, timestamp, compound_status, cycle_time) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (
            record["part_id"],
            record["timestamp"],
            record["compound_status"],
            record["cycle_time"]
        ))


# ─── Worker Loop ─────────────────────────────────────────────────────────────

def _worker_loop() -> None:
    global _db_available
    db_type = getattr(_config, "DB_TYPE", "mssql").upper()
    time.sleep(2)

    _db_available = _ensure_database_and_table()
    if not _db_available:
        logger.warning(f"db_logger: {db_type} not reachable at startup — will retry when records arrive.")

    conn = None
    retry_delay = 5

    while True:
        record = _queue.get()
        if record is None:
            break

        while not _db_available:
            logger.info(f"db_logger: Retrying {db_type} connection/setup …")
            _db_available = _ensure_database_and_table()
            if not _db_available:
                time.sleep(retry_delay)
                continue

        if conn is None:
            try:
                conn = _connect()
                logger.info(f"db_logger: {db_type} connection established.")
            except Exception as exc:
                logger.warning(f"db_logger: Connect failed — {exc}. Record queued for retry.")
                _queue.put(record)
                time.sleep(retry_delay)
                continue

        try:
            _insert(conn, record)
            logger.debug(f"db_logger: Saved → part={record['part_id']} status={record['compound_status']} time={record['cycle_time']}s")
        except Exception as exc:
            logger.warning(f"db_logger: Insert failed ({exc}) — reconnecting …")
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            _queue.put(record)
            time.sleep(2)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    logger.info("db_logger: worker exited.")
