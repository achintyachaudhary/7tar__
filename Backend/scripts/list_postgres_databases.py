"""List all databases on the configured PostgreSQL server."""

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.db.database import DATABASE_URL, is_postgres


def main() -> None:
    if not is_postgres():
        print(f"DATABASE_URL is not PostgreSQL: {DATABASE_URL}")
        return

    engine = create_engine(
        DATABASE_URL,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT datname "
                    "FROM pg_database "
                    "WHERE datistemplate = false "
                    "ORDER BY datname"
                )
            ).fetchall()
    except OperationalError as exc:
        print(f"Could not connect to PostgreSQL: {exc}")
        print(
            "If PostgreSQL runs in WSL, start it there first:\n"
            "  wsl sudo service postgresql start"
        )
        raise SystemExit(1) from exc

    if not rows:
        print("No databases found.")
        return

    print(f"PostgreSQL databases ({len(rows)}):")
    for (name,) in rows:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
