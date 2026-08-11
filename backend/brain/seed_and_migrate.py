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
import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.db import init_models
from app.core.migrations import run_migrations
from app.core.seed import seed_database
from app.core.redis_client import redis_bus

async def main():
    logging.basicConfig(level=logging.INFO)
    await redis_bus.connect()
    await init_models()
    await run_migrations()
    await seed_database()
    await redis_bus.close()

if __name__ == "__main__":
    asyncio.run(main())
