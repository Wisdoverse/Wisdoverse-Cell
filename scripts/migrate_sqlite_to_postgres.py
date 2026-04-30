"""
SQLite → PostgreSQL 数据迁移脚本

从 feishu-to-openproject 的 SQLite 数据库迁移数据到 project_cell 的 PostgreSQL。

用法:
    python scripts/migrate_sqlite_to_postgres.py \
        --sqlite-path /path/to/app.db \
        --pg-url postgresql+asyncpg://user:pass@host:5432/projectcell
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
    """从 SQLite 读取所有记录"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(f"SELECT {', '.join(columns)} FROM {table}")
        rows = [dict(row) for row in cursor.fetchall()]
        print(f"  读取 {table}: {len(rows)} 条记录")
        return rows
    except sqlite3.OperationalError as e:
        print(f"  跳过 {table}: {e}")
        return []
    finally:
        conn.close()


async def write_postgres(pg_url: str, table: str, columns: list[str], rows: list[dict]):
    """写入 PostgreSQL"""
    if not rows:
        return

    engine = create_async_engine(pg_url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    col_names = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    async with async_session() as session:
        for row in rows:
            # 过滤掉 None 值的列，保留有值的
            filtered = {k: v for k, v in row.items() if k in columns}
            try:
                await session.execute(text(insert_sql), filtered)
            except Exception as e:
                print(f"  写入失败: {e} | row={filtered}")
        await session.commit()

    await engine.dispose()
    print(f"  写入 {table}: {len(rows)} 条记录")


async def migrate(sqlite_path: str, pg_url: str):
    """执行迁移"""
    print("=" * 60)
    print("SQLite → PostgreSQL 数据迁移")
    print(f"  源: {sqlite_path}")
    print(f"  目标: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    print("=" * 60)

    for table_config in TABLES_TO_MIGRATE:
        print(f"\n📋 迁移 {table_config['sqlite_table']} → {table_config['pg_table']}")
        rows = read_sqlite(sqlite_path, table_config["sqlite_table"], table_config["columns"])
        if rows:
            await write_postgres(pg_url, table_config["pg_table"], table_config["columns"], rows)

    print("\n✅ 迁移完成")


def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 数据迁移")
    parser.add_argument("--sqlite-path", required=True, help="SQLite 数据库路径")
    parser.add_argument("--pg-url", required=True, help="PostgreSQL 连接 URL (asyncpg)")
    args = parser.parse_args()

    asyncio.run(migrate(args.sqlite_path, args.pg_url))


if __name__ == "__main__":
    main()
