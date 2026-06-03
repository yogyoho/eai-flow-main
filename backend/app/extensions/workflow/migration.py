"""Migration: add template metadata fields and template_approvals table.

Run: docker exec deer-flow-gateway python -m app.extensions.workflow.migration
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.extensions.config import get_extensions_config

logger = logging.getLogger(__name__)

MIGRATION_STATEMENTS = [
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS template_status VARCHAR(20) NOT NULL DEFAULT 'draft'",
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS visible_dept_ids JSONB",
    "ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
    """CREATE TABLE IF NOT EXISTS template_approvals (
        id UUID PRIMARY KEY,
        template_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
        requester_id UUID NOT NULL REFERENCES users(id),
        reviewer_id UUID REFERENCES users(id),
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        comment TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        reviewed_at TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS ix_template_approvals_template_id ON template_approvals(template_id)",
]


async def run_migration():
    config = get_extensions_config()
    engine = create_async_engine(config.database.url)
    async with engine.begin() as conn:
        for stmt in MIGRATION_STATEMENTS:
            await conn.execute(text(stmt))
    await engine.dispose()
    logger.info("Migration complete: template metadata + approval table")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migration())
