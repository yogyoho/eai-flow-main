"""Database connection and session management for extensions module."""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.extensions.config import get_extensions_config

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


_engine = None
_session_factory = None


def get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        config = get_extensions_config()
        _engine = create_async_engine(
            config.database.url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (dependency for FastAPI)."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get database session as context manager."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database tables."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def migrate_db() -> None:
    """Run lightweight column migrations for existing tables."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE departments ADD COLUMN IF NOT EXISTS "
                "description VARCHAR(1000)"
            )
        )

        # === RBAC Enhancement Migration ===
        # 1. Add columns to roles table
        await conn.execute(
            text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 10")
        )
        await conn.execute(
            text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS parent_role_id UUID REFERENCES roles(id)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_roles_parent_role_id ON roles(parent_role_id)")
        )

        # 2. Add columns to users table
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS emp_no VARCHAR(50)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS hire_date DATE")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_users_is_deleted ON users(is_deleted)")
        )

        # 3. Add columns to departments table
        await conn.execute(
            text("ALTER TABLE departments ADD COLUMN IF NOT EXISTS code VARCHAR(50)")
        )
        await conn.execute(
            text("ALTER TABLE departments ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'")
        )

        # 4. Create user_departments association table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_departments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                dept_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
                is_primary BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, dept_id)
            )
        """))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_user_departments_user_id ON user_departments(user_id)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_user_departments_dept_id ON user_departments(dept_id)")
        )

        # 5. Migrate existing data: copy dept_id to user_departments as primary
        await conn.execute(text("""
            INSERT INTO user_departments (id, user_id, dept_id, is_primary, created_at)
            SELECT gen_random_uuid(), id, dept_id, TRUE, NOW()
            FROM users WHERE dept_id IS NOT NULL
            ON CONFLICT (user_id, dept_id) DO NOTHING
        """))

        # 6. Initialize built-in role levels
        await conn.execute(
            text("UPDATE roles SET level = 100 WHERE code IN ('superadmin', 'super_admin')")
        )
        await conn.execute(
            text("UPDATE roles SET level = 50 WHERE code IN ('admin', 'administrator')")
        )
        await conn.execute(
            text("UPDATE roles SET level = 30 WHERE code = 'dept_manager'")
        )
        await conn.execute(
            text("UPDATE roles SET level = 20 WHERE code = 'team_leader'")
        )
        await conn.execute(
            text("UPDATE roles SET level = 10 WHERE code IN ('user', 'normal_user')")
        )
        await conn.execute(
            text("UPDATE roles SET level = 1 WHERE code = 'guest'")
        )
        # Default level for any roles not matching above
        await conn.execute(
            text("UPDATE roles SET level = 10 WHERE level IS NULL OR level = 0")
        )
        # === End RBAC Enhancement Migration ===

        # Create ai_documents table if not exists (for existing deployments)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id),
                source_thread_id VARCHAR(100),
                title VARCHAR(255) NOT NULL,
                content TEXT,
                folder VARCHAR(255) NOT NULL DEFAULT '默认文件夹',
                is_starred BOOLEAN NOT NULL DEFAULT FALSE,
                is_shared BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_documents_user_id ON ai_documents(user_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_documents_source_thread_id ON ai_documents(source_thread_id)"
        ))

        # Create user_memories table for per-user memory isolation
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_memories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                memory_data JSONB NOT NULL DEFAULT '{}',
                version VARCHAR(10) NOT NULL DEFAULT '1.0',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(user_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id)"
        ))
        await conn.execute(
            text(
                "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS "
                "kb_type VARCHAR(50) NOT NULL DEFAULT 'ragflow'"
            )
        )

        # Create scrap_drafts table for web scraper
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scrap_drafts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id),
                source_url VARCHAR(2048) NOT NULL,
                source_title VARCHAR(500),
                schema_name VARCHAR(100) NOT NULL,
                schema_display_name VARCHAR(200),
                raw_content TEXT,
                structured_data TEXT,
                title VARCHAR(500) NOT NULL,
                tags TEXT[] DEFAULT '{}',
                category VARCHAR(100),
                source_provider VARCHAR(50) DEFAULT 'browser_use_local',
                scrape_date TIMESTAMP DEFAULT NOW(),
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                knowledge_base_id UUID REFERENCES knowledge_bases(id),
                document_id VARCHAR(100),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_scrap_drafts_user_id ON scrap_drafts(user_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_scrap_drafts_status ON scrap_drafts(status)"
        ))

        # --- Knowledge Factory: extraction domains ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS extraction_domains (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                parent_domain VARCHAR(100),
                standard_chapters JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # --- Knowledge Factory: extraction templates ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS extraction_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                domain VARCHAR(100) NOT NULL,
                name VARCHAR(200) NOT NULL,
                version VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                root_sections_json JSONB NOT NULL DEFAULT '[]',
                cross_section_rules JSONB,
                completeness_score INT DEFAULT 0,
                source_report_ids UUID[],
                parent_template_id UUID REFERENCES extraction_templates(id),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(domain, name, version)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_extraction_templates_domain ON extraction_templates(domain)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_extraction_templates_status ON extraction_templates(status)"
        ))

        # --- Knowledge Factory: template versions ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS extraction_template_versions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                template_id UUID REFERENCES extraction_templates(id) ON DELETE CASCADE,
                version VARCHAR(50) NOT NULL,
                changelog TEXT,
                snapshot_json JSONB NOT NULL,
                published_by UUID REFERENCES users(id),
                published_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # --- Knowledge Factory: extraction tasks ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS extraction_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                domain VARCHAR(100),
                name VARCHAR(200),
                source_report_ids UUID[] NOT NULL DEFAULT '{}',
                target_template_id UUID REFERENCES extraction_templates(id),
                config JSONB NOT NULL DEFAULT '{}',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                progress INT NOT NULL DEFAULT 0,
                steps JSONB DEFAULT '[]',
                result_template_json JSONB,
                error_message TEXT,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_extraction_tasks_status ON extraction_tasks(status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_extraction_tasks_created_by ON extraction_tasks(created_by)"
        ))

        # --- Knowledge Factory: template sections ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS template_sections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                template_id UUID REFERENCES extraction_templates(id) ON DELETE CASCADE,
                section_id VARCHAR(100) NOT NULL,
                title VARCHAR(200),
                level INT DEFAULT 1,
                required BOOLEAN NOT NULL DEFAULT TRUE,
                purpose TEXT,
                content_contract JSONB,
                compliance_rules TEXT[],
                rag_sources VARCHAR(200)[],
                generation_hint TEXT,
                example_snippet TEXT,
                completeness_score INT,
                UNIQUE(template_id, section_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_template_sections_template ON template_sections(template_id)"
        ))

        # --- Laws: regulations and standards ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS laws (
                id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::varchar,
                title VARCHAR(500) NOT NULL,
                law_number VARCHAR(100),
                law_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                department VARCHAR(200),
                effective_date TIMESTAMPTZ,
                update_date TIMESTAMPTZ,
                ref_count INT NOT NULL DEFAULT 0,
                view_count INT NOT NULL DEFAULT 0,
                content TEXT,
                summary TEXT,
                ragflow_dataset_id VARCHAR(100),
                ragflow_document_id VARCHAR(100),
                is_synced VARCHAR(10) NOT NULL DEFAULT 'pending',
                last_sync_at TIMESTAMPTZ,
                metadata_json JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_laws_title ON laws(title)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_laws_law_number ON laws(law_number)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_laws_law_type ON laws(law_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_laws_status ON laws(status)"
        ))

        # --- Knowledge Factory: compliance rules ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS compliance_rules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                rule_id VARCHAR(50) NOT NULL UNIQUE,
                name VARCHAR(200) NOT NULL,
                type VARCHAR(50) NOT NULL,
                type_name VARCHAR(100) NOT NULL DEFAULT '',
                severity VARCHAR(20) NOT NULL,
                severity_name VARCHAR(50) NOT NULL DEFAULT '',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                description TEXT,
                industry VARCHAR(50) NOT NULL,
                industry_name VARCHAR(100) NOT NULL DEFAULT '',
                report_types VARCHAR(50)[] NOT NULL DEFAULT '{}',
                applicable_regions VARCHAR(50)[] NOT NULL DEFAULT '{}',
                national_level BOOLEAN NOT NULL DEFAULT TRUE,
                source_sections VARCHAR(200)[] NOT NULL DEFAULT '{}',
                target_sections VARCHAR(200)[] NOT NULL DEFAULT '{}',
                validation_config JSONB NOT NULL DEFAULT '{}',
                error_message TEXT,
                auto_fix_suggestion TEXT,
                seed_version VARCHAR(50),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rules_rule_id ON compliance_rules(rule_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rules_type ON compliance_rules(type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rules_severity ON compliance_rules(severity)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rules_industry ON compliance_rules(industry)"
        ))

        # --- Knowledge Factory: compliance rule logs ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS compliance_rule_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                rule_id UUID NOT NULL REFERENCES compliance_rules(id) ON DELETE CASCADE,
                thread_id UUID,
                document_id VARCHAR(200),
                check_result VARCHAR(20) NOT NULL,
                check_details JSONB,
                error_info TEXT,
                executed_by UUID REFERENCES users(id),
                executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rule_logs_rule ON compliance_rule_logs(rule_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rule_logs_thread ON compliance_rule_logs(thread_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compliance_rule_logs_document ON compliance_rule_logs(document_id)"
        ))

        # --- Laws: template relations ---
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS law_template_relations (
                id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::varchar,
                law_id VARCHAR(36) NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
                template_id VARCHAR(36) NOT NULL,
                section_title VARCHAR(200),
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_law_template_relations_law ON law_template_relations(law_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_law_template_relations_template ON law_template_relations(template_id)"
        ))


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def seed_db() -> None:
    """Seed initial data: create admin user and role if they don't exist."""
    from .auth.jwt import hash_password

    async with get_session_factory()() as session:
        # Check if admin role exists
        result = await session.execute(
            text("SELECT id FROM roles WHERE code = 'superadmin' LIMIT 1")
        )
        row = result.fetchone()

        if row is None:
            # Create superadmin role
            role_id = str(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO roles (id, name, code, permissions, is_system, level) "
                    "VALUES (:id, 'Super Admin', 'superadmin', :perms, true, 100)"
                ),
                {"id": role_id, "perms": ["*"]},
            )
            logger.info("Created superadmin role")

            # Create admin user
            user_id = str(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO users (id, username, email, password_hash, full_name, role_id, status) "
                    "VALUES (:id, 'admin', 'admin@eai.local', :pw_hash, 'Administrator', :role_id, 'active')"
                ),
                {"id": user_id, "pw_hash": hash_password("admin123"), "role_id": role_id},
            )
            logger.info("Created admin user (username: admin, password: admin123)")
            await session.commit()
        else:
            logger.info("Seed data already exists, skipping")
