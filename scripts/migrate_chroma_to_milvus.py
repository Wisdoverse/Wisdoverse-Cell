#!/usr/bin/env python3
"""Migrate requirement vectors from ChromaDB to Milvus.

Reads all requirements from PostgreSQL and re-indexes them into Milvus.
ChromaDB data is NOT read directly — PG is the source of truth.

Usage:
    # Dry run (shows what would be migrated)
    python scripts/migrate_chroma_to_milvus.py --dry-run

    # Run migration
    python scripts/migrate_chroma_to_milvus.py

    # With custom batch size
    python scripts/migrate_chroma_to_milvus.py --batch-size 50

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    MILVUS_URI (default: http://localhost:19530)
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.infra.embedder import embedder
from shared.infra.milvus_store import MilvusVectorStore
from shared.utils.logger import get_logger

logger = get_logger("migration.chroma_to_milvus")

COLLECTION_NAME = "requirements"
EMBEDDING_DIM = 384


async def count_requirements(session: AsyncSession) -> int:
    """Count total requirements in PostgreSQL."""
    from agents.capabilities.requirements.models.requirement import Requirement

    result = await session.execute(select(func.count(Requirement.id)))
    return result.scalar() or 0


async def fetch_requirements(
    session: AsyncSession, offset: int, limit: int
) -> list[dict]:
    """Fetch a batch of requirements from PostgreSQL."""
    from agents.capabilities.requirements.models.requirement import Requirement

    result = await session.execute(
        select(Requirement)
        .order_by(Requirement.created_at)
        .offset(offset)
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "category": r.category,
            "status": r.status,
            "priority": r.priority,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


def format_for_embedding(req: dict) -> str:
    """Format requirement text for embedding.

    Duplicates ``RequirementEmbedder.format_requirement_for_embedding`` —
    keep in sync with ``agents/capabilities/requirements/core/embedder.py``.
    """
    parts = [f"需求: {req['title']}"]
    if req.get("category"):
        parts.append(f"分类: {req['category']}")
    parts.append(f"描述: {req['description']}")
    return "\n".join(parts)


async def migrate(
    dry_run: bool = False,
    batch_size: int = 100,
) -> None:
    """Run the migration."""
    start_time = time.time()

    # 1. Connect to PostgreSQL
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        total = await count_requirements(session)

    if total == 0:
        logger.info("No requirements found in PostgreSQL. Nothing to migrate.")
        await engine.dispose()
        return

    logger.info(f"Found {total} requirements in PostgreSQL.")

    if dry_run:
        logger.info("[DRY RUN] Would migrate %d requirements to Milvus collection '%s'", total, COLLECTION_NAME)
        await engine.dispose()
        return

    # 2. Initialize Milvus
    milvus = MilvusVectorStore(uri=settings.milvus_uri, token=settings.milvus_token.get_secret_value())
    await milvus.initialize()
    await milvus.ensure_collection(COLLECTION_NAME, dimension=EMBEDDING_DIM)

    existing_count = await milvus.count(COLLECTION_NAME)
    logger.info(f"Milvus collection '{COLLECTION_NAME}' has {existing_count} existing vectors.")

    # 3. Migrate in batches
    migrated = 0
    errors = 0
    offset = 0

    while offset < total:
        async with session_factory() as session:
            batch = await fetch_requirements(session, offset, batch_size)

        if not batch:
            break

        # Generate embeddings
        texts = [format_for_embedding(r) for r in batch]
        try:
            embeddings = embedder.embed_batch(texts)
        except Exception as e:
            failed_ids = [r["id"] for r in batch]
            logger.error(
                "embedding_batch_failed",
                offset=offset,
                failed_ids=failed_ids,
                error=str(e),
            )
            errors += len(batch)
            offset += batch_size
            continue

        # Upsert to Milvus
        ids = [r["id"] for r in batch]
        metadatas = [
            {
                "title": r["title"],
                "category": r.get("category", "其他"),
                "status": r.get("status", ""),
                "priority": r.get("priority", ""),
                "created_at": r.get("created_at", ""),
            }
            for r in batch
        ]

        try:
            await milvus.upsert_batch(
                collection=COLLECTION_NAME,
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            migrated += len(batch)
            logger.info(f"  Migrated {migrated}/{total} ({migrated * 100 // total}%)")
        except Exception as e:
            failed_ids = [r["id"] for r in batch]
            logger.error(
                "milvus_upsert_batch_failed",
                offset=offset,
                failed_ids=failed_ids,
                error=str(e),
            )
            errors += len(batch)

        offset += batch_size

    # 4. Verify
    final_count = await milvus.count(COLLECTION_NAME)
    await milvus.close()
    await engine.dispose()

    elapsed = time.time() - start_time
    logger.info(
        "Migration complete",
        migrated=migrated,
        errors=errors,
        total_in_pg=total,
        total_in_milvus=final_count,
        elapsed_seconds=round(elapsed, 1),
    )

    if errors > 0:
        logger.warning(f"{errors} requirements failed to migrate. Re-run to retry.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Migrate requirement vectors from ChromaDB to Milvus")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for processing (default: 100)")
    args = parser.parse_args()

    asyncio.run(migrate(dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
