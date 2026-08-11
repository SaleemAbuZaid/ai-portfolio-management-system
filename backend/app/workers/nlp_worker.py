"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Runs NLP processing jobs that enrich news with sentiment and event data.
"""
import time, json, asyncio
from loguru import logger
from app.core.redis_client import redis_bus

class NLPWorker:
    def __init__(self):
        logger.info("NLP Worker initialized in Passive/Legacy mode.")

    async def run(self):
        await redis_bus.connect()
        logger.info("NLP Worker (Passive) online. News pipeline is now owned by NewsIngester.")
        # 🛡️ DEFENSE OPTIMIZATION:
        # News scoring and persistence is now handled directly by NewsIngester 
        # to ensure atomic operations and avoid race conditions/double-writes.
        while True:
            await asyncio.sleep(3600)


nlp_worker = NLPWorker()

if __name__ == "__main__":
    asyncio.run(nlp_worker.run())
