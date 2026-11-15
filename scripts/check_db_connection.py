import os
import sys
import psycopg2

required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
missing = [name for name in required if not os.getenv(name)]
if missing:
    print("Missing required environment variables: " + ", ".join(missing))
    sys.exit(2)

try:
    with psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            print("Database connection successful:", cursor.fetchone()[0] == 1)
except Exception as exc:
    print(f"Database connection failed: {type(exc).__name__}: {exc}")
    sys.exit(1)
