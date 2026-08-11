"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Runs lightweight startup migrations that keep the local schema aligned with current models.
"""
import logging
from sqlalchemy import text
from app.core.db import AsyncSessionLocal
from app.core.config import get_settings

logger = logging.getLogger("Migrations")
settings = get_settings()

async def run_migrations():
    """
    Ensures the database schema matches the required graduation project features.
    Handles manual ALTER TABLE commands for SQLite and PostgreSQL.
    """
    logger.info("🛠️ Running database schema migrations...")
    
    is_sqlite = "sqlite" in settings.DATABASE_URL.lower()
    
    async with AsyncSessionLocal() as session:
        try:
            if is_sqlite:
                # SQLite - Check for columns individually
                # Note: SQLite ALTER TABLE is limited, but we can add columns if they don't exist
                # Columns for portfolios table
                portfolios_cols = [
                    ("risk_profile", "VARCHAR"),
                    ("cash", "DOUBLE PRECISION"),
                    ("total_value", "DOUBLE PRECISION"),
                    ("updated_at", "TIMESTAMP")
                ]
                
                # Columns for users table
                users_cols = [
                    ("gender", "VARCHAR"),
                    ("avatar_url", "VARCHAR")
                ]
                
                for col_name, col_type in portfolios_cols:
                    try:
                        await session.execute(text(f"ALTER TABLE portfolios ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"✅ Added column {col_name} to portfolios table.")
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.debug(f"⏭️ Column {col_name} already exists in portfolios.")
                        else:
                            logger.warning(f"⚠️ Error adding column {col_name} to portfolios: {e}")

                for col_name, col_type in users_cols:
                    try:
                        await session.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"✅ Added column {col_name} to users table.")
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.debug(f"⏭️ Column {col_name} already exists in users.")
                        else:
                            logger.warning(f"⚠️ Error adding column {col_name} to users: {e}")
            else:
                # PostgreSQL
                queries = [
                    "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS risk_profile VARCHAR",
                    "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS cash DOUBLE PRECISION",
                    "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS total_value DOUBLE PRECISION",
                    "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE",
                    # User table hardening
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS requested_role VARCHAR(20)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by INTEGER",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(255)"
                ]
                for query in queries:
                    await session.execute(text(query))
                logger.info("✅ PostgreSQL schema check complete.")
            
            await session.commit()
            logger.info("🏁 Migrations completed successfully.")
        except Exception as e:
            logger.error(f"❌ Migration failure: {e}")
            await session.rollback()

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migrations())
