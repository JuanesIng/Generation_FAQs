from faq_common import get_db_connection

try:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM chat_messages;")
            print(f"Filas en chat_messages: {cursor.fetchone()[0]}")

            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
            )
            print("Tablas:", [row[0] for row in cursor.fetchall()])

    print("Conexión cerrada correctamente.")
except Exception as exc:
    print(f"Error: {exc}")