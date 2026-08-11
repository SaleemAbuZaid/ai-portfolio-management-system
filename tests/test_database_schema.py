"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Project source/configuration file supporting the APEX AI Portfolio Management System.
"""
import pytest
from sqlalchemy import inspect

@pytest.mark.asyncio
async def test_database_tables_exist(controlled_db_session):
    """Verify all required tables exist in the database."""
    async with controlled_db_session() as session:
        connection = await session.connection()
        tables = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        
        required_tables = [
            "users", "portfolios", "assets", "portfolio_assets",
            "price_history", "news", "sentiment", "events",
            "predictions", "recommendations", "execution_logs"
        ]
        for table in required_tables:
            assert table in tables, f"Table {table} missing from database"

@pytest.mark.asyncio
async def test_database_indexes_exist(controlled_db_session):
    """Verify critical performance indexes exist."""
    async with controlled_db_session() as session:
        connection = await session.connection()
        indexes = await connection.run_sync(
            lambda sync_conn: [
                index["name"]
                for table in inspect(sync_conn).get_table_names()
                for index in inspect(sync_conn).get_indexes(table)
            ]
        )

        assert len(indexes) > 0
        tables_with_indexes = ["price_history", "news", "predictions", "recommendations"]
        for table in tables_with_indexes:
            assert any(table in idx for idx in indexes), f"No index found for table {table}"
