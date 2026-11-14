import sys
import os

# Add SOP_Compliance to path
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(base_dir, "SOP_Compliance"))

try:
    import pyodbc
    conn = pyodbc.connect(
        "DRIVER={SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=firewall_sop;Trusted_Connection=yes;",
        timeout=5
    )
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 25 id, part_id, timestamp, compound_status, cycle_time, synced_to_it 
        FROM [inspection_logs] 
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()

    print("\n" + "=" * 98)
    print("                      FIREWALL SOP - MSSQL INSPECTION DATABASE")
    print("=" * 98)
    print(f"{'ID':<6} | {'PART ID':<20} | {'TIMESTAMP':<20} | {'STATUS':<16} | {'CYCLE':<10} | {'SYNCED'}")
    print("-" * 98)

    if not rows:
        print(" [No inspection rows recorded yet]")
    else:
        for r in rows:
            status_text = "1 [PASS - OK]" if r[3] == 1 else "0 [FAIL/INC]"
            time_str = str(r[2]).split(".")[0]
            cycle_str = f"{r[4]}s" if r[4] is not None else "N/A"
            print(f"{r[0]:<6} | {str(r[1]):<20} | {time_str:<20} | {status_text:<16} | {cycle_str:<10} | {r[5]}")

    print("=" * 98)
    print(" Legend: 1 = All gauges checked (PASS) | 0 = Incomplete / Not checked\n")
    conn.close()
except Exception as e:
    print(f"\n[ERROR] Could not connect to MSSQL: {e}\n")

input("Press Enter to close this window...")
