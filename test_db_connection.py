from db import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), COUNT(*) FROM appointments")
        database, count = cur.fetchone()

        print("Connected:", database)
        print("Appointment count:", count)