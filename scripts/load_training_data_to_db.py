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
import os
import sys
import pandas as pd
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
import json
from datetime import datetime, timezone

# Ensure parent directory is in path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.db import AsyncSessionLocal
from app.models.all_models import Asset, PriceHistory
from app.core.symbols import normalize_symbol

async def ensure_assets(session, tickers):
    """Creates assets in the DB if they don't exist."""
    logger.info(f"Ensuring {len(tickers)} assets exist in DB...")
    for t in tickers:
        normalized = normalize_symbol(t)
        stmt = insert(Asset).values(
            ticker=normalized,
            name=normalized,
            asset_class="UNKNOWN",
            provider="Apex-History"
        ).on_conflict_do_nothing(index_elements=['ticker'])
        await session.execute(stmt)
    await session.commit()

async def load_training_data():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parquet_path = os.path.join(root_dir, "data", "training", "market_training_long.parquet")
    
    if not os.path.exists(parquet_path):
        logger.error(f"Training dataset not found at {parquet_path}. Run dataset builder first.")
        sys.exit(1)
        
    logger.info(f"Reading training data: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    
    # Ensure timezone-aware
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    
    unique_symbols = df['symbol'].unique()
    
    async with AsyncSessionLocal() as session:
        # 1. Sync assets
        await ensure_assets(session, unique_symbols)
        
        # 2. Get asset ID mapping
        res = await session.execute(select(Asset.id, Asset.ticker))
        asset_map = {ticker: asset_id for asset_id, ticker in res.all()}
        
        # 3. Process records in chunks
        chunk_size = 100
        total_rows = len(df)
        inserted_rows = 0
        
        for i in range(0, total_rows, chunk_size):
            chunk = df.iloc[i:i+chunk_size]
            records = []
            for _, row in chunk.iterrows():
                ticker = normalize_symbol(row['symbol'])
                if ticker not in asset_map:
                    continue
                
                records.append({
                    "asset_id": asset_map[ticker],
                    "timestamp": row['timestamp'].to_pydatetime(),
                    "price": float(row['close']),
                    "volume": float(row['volume']) if pd.notnull(row['volume']) else 0.0,
                    "provider": "Apex-Training-Data",
                    "provider_ts": row['timestamp'].timestamp(),
                    "ingest_ts": datetime.now(timezone.utc).timestamp(),
                    "lag_ms": 0.0
                })
            
            if records:
                stmt = insert(PriceHistory).values(records).on_conflict_do_nothing(
                    index_elements=['asset_id', 'timestamp']
                )
                await session.execute(stmt)
                inserted_rows += len(records)
                
            logger.info(f"Ingested {min(i+chunk_size, total_rows)} / {total_rows} rows...")
            
        await session.commit()
        
        # 4. Verification Query
        count_res = await session.execute(select(func.count(PriceHistory.asset_id)))
        final_count = count_res.scalar()
        
        logger.info(f"Final DB Row Count: {final_count}")

    # Write proof artifact
    proof_dir = os.path.join(root_dir, "proofs", "final", "database")
    os.makedirs(proof_dir, exist_ok=True)
    proof_path = os.path.join(proof_dir, "database_load_proof.json")
    
    proof_data = {
        "status": "success",
        "action": "load_historical_training_data",
        "rows_processed": total_rows,
        "rows_inserted": inserted_rows,
        "final_db_count": final_count,
        "assets_in_db": len(asset_map),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    with open(proof_path, "w") as f:
        json.dump(proof_data, f, indent=4)
        
    logger.info(f"Audit Proof: {proof_path}")

async def main():
    try:
        await load_training_data()
    except Exception as e:
        logger.error(f"Database Load Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
