import getpass
import psycopg

password = getpass.getpass("PostgreSQL password: ")

try:
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="healthai",
        user="postgres",
        password=password,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT current_database(),
                       current_user,
                       COUNT(*)
                FROM appointments
            """)

            database, username, appointment_count = cur.fetchone()

            print("Connection successful!")
            print(f"Database: {database}")
            print(f"User: {username}")
            print(f"Appointments: {appointment_count}")

except psycopg.Error as error:
    print("Database connection or query failed.")
    print(f"Error: {error}")