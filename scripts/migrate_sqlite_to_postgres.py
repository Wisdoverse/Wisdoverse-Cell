"""
SQLite to PostgreSQL data migration script.

Migrates data from the feishu-to-openproject SQLite database to the wisdoverse_cell
PostgreSQL database.

Usage:
    python scripts/migrate_sqlite_to_postgres.py \
        --sqlite-path /path/to/app.db \
        --pg-url postgresql+asyncpg://user:pass@host:5432/wisdoverse-cell
"""
import argparse
import asyncio
import sqlite3

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TABLES_TO_MIGRATE = [
    {
        "sqlite_table": "sync_mappings",
        "pg_table": "sync_mappings",
        "columns": [
            "op_work_package_id", "feishu_record_id", "op_project_id",
            "title", "last_op_update", "last_feishu_update", "created_at", "updated_at",
        ],
    },
    {
        "sqlite_table": "subtask_mappings",
        "pg_table": "sync_agent_subtask_mappings",
        "columns": [
            "parent_op_id", "feishu_record_id", "subtask_name",
            "subtask_status", "created_at", "updated_at",
        ],
    },
    {
        "sqlite_table": "sync_logs",
        "pg_table": "sync_agent_logs",
        "columns": [
            "sync_type", "status", "records_processed",
            "error_message", "started_at", "completed_at",
        ],
    },
    {
        "sqlite_table": "conversation_history",
        "pg_table": "chat_agent_conversation_histories",
        "columns": ["user_id", "messages", "created_at", "updated_at"],
    },
]


def read_sqlite(db_path: str, table: str, columns: list[str]) -> list[dict]:
    """Read all records from SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(f"SELECT {', '.join(columns)} FROM {table}")
        rows = [dict(row) for row in cursor.fetchall()]
        print(f"  Read {table}: {len(rows)} records")
        return rows
    except sqlite3.OperationalError as e:
        print(f"  Skipping {table}: {e}")
        return []
    finally:
        conn.close()


async def write_postgres(pg_url: str, table: str, columns: list[str], rows: list[dict]):
    """Write records to PostgreSQL."""
    if not rows:
        return

    engine = create_async_engine(pg_url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    col_names = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    async with async_session() as session:
        for row in rows:
            # Keep only columns supported by the target table.
            filtered = {k: v for k, v in row.items() if k in columns}
            try:
                await session.execute(text(insert_sql), filtered)
            except Exception as e:
                print(f"  Write failed: {e} | row={filtered}")
        await session.commit()

    await engine.dispose()
    print(f"  Wrote {table}: {len(rows)} records")


async def migrate(sqlite_path: str, pg_url: str):
    """Run the migration."""
    print("=" * 60)
    print("SQLite to PostgreSQL data migration")
    print(f"  Source: {sqlite_path}")
    print(f"  Target: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    print("=" * 60)

    for table_config in TABLES_TO_MIGRATE:
        print(f"\nMigrating {table_config['sqlite_table']} -> {table_config['pg_table']}")
        rows = read_sqlite(sqlite_path, table_config["sqlite_table"], table_config["columns"])
        if rows:
            await write_postgres(pg_url, table_config["pg_table"], table_config["columns"], rows)

    print("\nMigration complete")


def main():
    parser = argparse.ArgumentParser(description="SQLite to PostgreSQL data migration")
    parser.add_argument("--sqlite-path", required=True, help="SQLite database path")
    parser.add_argument("--pg-url", required=True, help="PostgreSQL connection URL (asyncpg)")
    args = parser.parse_args()

    asyncio.run(migrate(args.sqlite_path, args.pg_url))


if __name__ == "__main__":
    main()
