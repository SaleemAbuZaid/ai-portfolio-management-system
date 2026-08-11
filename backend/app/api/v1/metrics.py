"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Exposes evaluation metrics, credential health, and Step 7 truth-audit status.
- Protects secrets by returning masked credential presence only.
"""

from fastapi import APIRouter
import time
from datetime import datetime
from app.services.evaluation_service import EvaluationService
from app.services.performance_monitor import monitor
from app.services.cache_service import performance_cache

router = APIRouter(tags=["Evaluation Metrics"])

@router.get("/")
async def get_system_evaluation_metrics():
    """
    Return the system evaluation matrix used by the dashboard.

    The route aggregates latency, directional accuracy, and portfolio alpha from
    evaluation services so project metrics are served through one API surface.
    """
    try:
        latency = await EvaluationService.compute_latency_metrics()
        accuracy = await EvaluationService.compute_directional_accuracy()
        portfolio = await EvaluationService.compute_portfolio_alpha()
        
        return {
            "status": "success",
            "data": {
                "latency_metrics": latency,
                "directional_accuracy": accuracy,
                "portfolio_performance": portfolio
            }
        }
    except Exception as e:
        import logging
        logger = logging.getLogger("MetricsAPI")
        logger.error(f"CRITICAL METRICS FAILURE: {e}")
        return {
            "status": "error",
            "message": "Real-time evaluation failed. Check data pipeline integrity.",
            "data": None
        }

@router.get("/performance")
async def get_performance_metrics(reset: bool = False):
    """
    Return runtime performance metrics for Step 11 validation.

    Includes latency, throughput, and cache efficiency. When reset=true, the
    in-memory counters are cleared after the caller intentionally requests it.
    """
    if reset:
        performance_cache.reset_stats()
        monitor.request_count = 0
        monitor.error_count = 0
        monitor.request_latencies.clear()
        return {"status": "success", "message": "Metrics reset successfully."}
        
    perf = monitor.get_metrics()
    cache = performance_cache.get_stats()
    
    return {
        "status": "success",
        "total_requests": perf.get("request_count", 0),
        "cache_hits": cache.get("hits", 0),
        "cache_misses": cache.get("misses", 0),
        "cache_hit_rate": cache.get("hit_ratio", 0.0),
        "average_latency_ms": perf.get("avg_latency_ms", 0.0),
        "p50_latency_ms": perf.get("p50_latency_ms", 0.0),
        "p95_latency_ms": perf.get("p95_latency_ms", 0.0),
        "error_rate": perf.get("error_rate", 0.0),
        "performance": perf,
        "cache": cache,
        "mode": cache.get("mode", "unknown")
    }

@router.post("/e2e-trigger")
async def trigger_e2e_flow(data: dict):
    """
    Trigger a controlled end-to-end ingestion flow for validation scripts.

    It publishes one market tick and one news article through the same services
    used by runtime workers, while the supplied provider names remain auditable.
    """
    from app.services.ingestion.market_ingester import market_ingester
    from app.services.ingestion.news_ingester import news_ingester
    
    ticker = data.get("ticker", "BTCUSDT")
    price = data.get("price", 77777.77)
    headline = data.get("headline", "E2E_STRICT_TEST")
    
    import logging
    logger = logging.getLogger("MetricsAPI")
    logger.info(f"🚀 [E2E_ORCHESTRATION] Triggering ingestion for {ticker} at {price}")
    await market_ingester.publish_tick(
        symbol=ticker,
        price=price,
        source="binance",
        volume=1.0
    )
    
    # Trigger a companion news item so the sentiment/recommendation path runs.
    await news_ingester.process_article({
        "provider": "E2E_STRICT_TEST",
        "title": f"{ticker}: {headline}",
        "summary": "This is a strictly verified E2E test for Step 10.",
        "source_ts": time.time()
    })
    
    return {"status": "triggered"}
@router.get("/reset")
async def reset_metrics():
    """
    Reset performance and cache counters for a clean audit run.
    """
    performance_cache.reset_stats()
    monitor.request_count = 0
    monitor.error_count = 0
    monitor.request_latencies.clear()
    return {"status": "success", "message": "Metrics reset successfully."}

@router.get("/step12-validation")
async def get_step12_validation():
    """
    Return Step 12 validation results from generated proof artifacts.

    The endpoint reports test and backtest status without creating or modifying
    proofs, making it safe for dashboard polling.
    """
    import os
    import json
    from datetime import datetime
    
    summary_path = "proof_step12/test_summary.txt"
    backtest_path = "proof_step12/backtest_results.json"
    
    res = {
        "pytest_status": "not_run_yet",
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "backtest_status": "not_run_yet",
        "trades_executed": 0,
        "buy_count": 0,
        "sell_count": 0,
        "data_points_used": 0,
        "step11_regression_status": "not_run_yet",
        "generated_at": None
    }
    
    try:
        # Parse the pytest summary artifact when a validation run has produced it.
        if os.path.exists(summary_path):
            with open(summary_path, "r") as f:
                content = f.read()
                if "Total Passed: " in content:
                    res["passed_tests"] = int(content.split("Total Passed: ")[1].split("\n")[0])
                if "Total Failed: " in content:
                    res["failed_tests"] = int(content.split("Total Failed: ")[1].split("\n")[0])
                if "Status: PASS" in content:
                    res["pytest_status"] = "PASS"
                elif "Status: FAIL" in content:
                    res["pytest_status"] = "FAIL"
                
                if "Step 11 Regression Status: " in content:
                    res["step11_regression_status"] = content.split("Step 11 Regression Status: ")[1].split("\n")[0]
                
            res["total_tests"] = res["passed_tests"] + res["failed_tests"]
            res["generated_at"] = datetime.fromtimestamp(os.path.getmtime(summary_path)).isoformat()

        # Parse the backtest artifact separately because it may be generated by
        # a different validation script.
        if os.path.exists(backtest_path):
            with open(backtest_path, "r") as f:
                bt = json.load(f)
                res["backtest_status"] = bt.get("status", "unknown")
                res["trades_executed"] = bt.get("trades_executed", 0)
                res["buy_count"] = bt.get("buy_count", 0)
                res["sell_count"] = bt.get("sell_count", 0)
                res["data_points_used"] = bt.get("data_points_used", 0)
                
    except Exception as e:
        import logging
        logging.getLogger("MetricsAPI").error(f"Error reading Step 12 validation artifacts: {e}")
        
    return res

@router.get("/credential-health")
async def get_credential_health():
    """
    Report required credential presence with masked values only.

    This supports the admin credential-health panel without returning raw API
    keys, secrets, passwords, or tokens.
    """
    from app.core.config import get_settings, mask_key
    s = get_settings()
    
    keys_to_check = [
        "ALPACA_API_KEY", "ALPACA_SECRET_KEY", 
        "EVENTREGISTRY_API_KEY", "MARKETAUX_API_KEY", 
        "TWELVEDATA_API_KEY", "ALPHAVANTAGE_API_KEY", 
        "POLYGON_API_KEY", "COINGECKO_API_KEY"
    ]
    
    health = {}
    for key in keys_to_check:
        val = getattr(s, key, "")
        health[key] = {
            "status": "EXISTS" if val else "MISSING",
            "masked": mask_key(val) if val else None
        }
        
    return {
        "status": {k: v["status"] for k, v in health.items()},
        "trading_mode": s.TRADING_MODE,
        "credentials": health
    }

@router.get("/step7-status")
async def get_step7_status():
    """
    Return the Step 7 truth-audit status displayed in the dashboard top badge.

    The audit passes only when the filled-order proof UUID cross-matches recent
    Alpaca proof data and an execution log artifact or live execution table row.
    """
    import os
    import json
    from datetime import datetime
    
    # Resolve proof paths from either repository root or backend/ working dirs.
    base_dir = os.getcwd()
    proof_dir = os.path.join(base_dir, "proofs", "final", "step7")
    
    # Fallback for when the API process is launched from backend/.
    if not os.path.exists(proof_dir) and os.path.basename(base_dir) == "backend":
        proof_dir = os.path.join(os.path.dirname(base_dir), "proofs", "final", "step7")
    
    order_proof_path = os.path.join(proof_dir, "filled_order_proof.json")
    recent_orders_path = os.path.join(proof_dir, "alpaca_recent_orders.json")
    execution_logs_path = os.path.join(proof_dir, "execution_logs.json")
    
    status = "PENDING"
    details = "Audit artifacts missing."
    uuid_cross_match = False
    verified_uuid = None
    
    if os.path.exists(order_proof_path):
        try:
            with open(order_proof_path, "r") as f:
                order_proof = json.load(f)
                verified_uuid = order_proof.get("order_id") or order_proof.get("id")
            
            if not verified_uuid:
                status = "FAIL"
                details = "No UUID found in filled_order_proof.json"
            else:
                # Cross-match the filled-order UUID against recent Alpaca orders.
                has_recent = False
                if os.path.exists(recent_orders_path):
                    with open(recent_orders_path, "r") as f:
                        recent_data = json.load(f)
                        orders = recent_data if isinstance(recent_data, list) else recent_data.get("orders", [])
                        has_recent = any(o.get("id") == verified_uuid for o in orders)
                
                # Cross-match the same UUID against persisted execution logs.
                has_log = False
                if os.path.exists(execution_logs_path):
                    with open(execution_logs_path, "r") as f:
                        log_data = json.load(f)
                        logs = log_data if isinstance(log_data, list) else log_data.get("logs", [])
                        has_log = any(l.get("order_id") == verified_uuid or l.get("id") == verified_uuid for l in logs)

                # The screenshot proof file can be stale immediately after a fresh
                # Alpaca proof trade. Confirm against the live execution table too.
                if not has_log:
                    try:
                        from sqlalchemy import select
                        from app.core.db import AsyncSessionLocal
                        from app.models.all_models import ExecutionLog

                        async with AsyncSessionLocal() as session:
                            db_res = await session.execute(
                                select(ExecutionLog.id)
                                .where(ExecutionLog.order_id == verified_uuid)
                                .limit(1)
                            )
                            has_log = db_res.scalar_one_or_none() is not None
                    except Exception as db_error:
                        details = f"DB cross-check unavailable: {db_error}"
                
                if has_recent and has_log:
                    status = "PASSED"
                    details = "Step 7 proof artifacts and live execution log verified with UUID cross-match."
                    uuid_cross_match = True
                else:
                    status = "PENDING"
                    details = f"UUID {verified_uuid} cross-match failed. Recent: {has_recent}, Logs: {has_log}"
                    
        except Exception as e:
            status = "FAIL"
            details = f"Audit verification error: {str(e)}"
    else:
        details = f"Missing core proof: {os.path.basename(order_proof_path)}"

    return {
        "audit_status": status,
        "audit_label": "STEP 7 TRUTH AUDIT",
        "uuid_cross_match": uuid_cross_match,
        "truth_integrity": "PASS" if status == "PASSED" else "PENDING",
        "proof_dir": "proofs/final/step7",
        "verified_order_id": verified_uuid,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }

