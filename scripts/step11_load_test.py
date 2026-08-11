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
import argparse
import asyncio
import aiohttp
import time
import json
import statistics
from pathlib import Path

async def one_request(session, url):
    start = time.perf_counter()
    try:
        async with session.get(url, timeout=10) as resp:
            text = await resp.text()
            latency_ms = (time.perf_counter() - start) * 1000

            source = None
            try:
                body = json.loads(text)
                source = body.get("source")
            except Exception:
                pass

            return {
                "url": url,
                "status": resp.status,
                "latency_ms": latency_ms,
                "ok": 200 <= resp.status < 500,
                "source": source
            }
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "url": url,
            "status": "ERROR",
            "latency_ms": latency_ms,
            "ok": False,
            "error": str(e)
        }

async def run_load_test(base_url, rps, duration):
    endpoints = [
        f"{base_url}/health",
        f"{base_url}/api/v1/market/AAPL",
        f"{base_url}/api/v1/news/latest",
        f"{base_url}/api/v1/metrics/performance",
    ]

    results = []
    tasks = []

    timeout = aiohttp.ClientTimeout(total=5)
    connector = aiohttp.TCPConnector(limit=1000)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        interval = 1.0 / rps
        test_start = time.perf_counter()
        end_time = test_start + duration
        next_request_time = test_start
        sent = 0

        while time.perf_counter() < end_time:
            if sent >= (rps * duration):
                break
            url = endpoints[sent % len(endpoints)]
            tasks.append(asyncio.create_task(one_request(session, url)))
            sent += 1

            next_request_time = test_start + (sent * interval)
            sleep_time = next_request_time - time.perf_counter()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


        results = await asyncio.gather(*tasks)

    total_time = time.perf_counter() - test_start
    latencies = [r["latency_ms"] for r in results if isinstance(r["latency_ms"], (int, float))]
    success = [r for r in results if r["ok"]]
    errors = [r for r in results if not r["ok"]]

    def percentile(values, p):
        if not values:
            return None
        values = sorted(values)
        k = int((len(values) - 1) * p)
        return values[k]

    summary = {
        "target_rps": rps,
        "duration_seconds": duration,
        "actual_duration_seconds": round(total_time, 3),
        "total_requests": len(results),
        "actual_rps": round(len(results) / total_time, 2),
        "successful_requests": len(success),
        "failed_requests": len(errors),
        "error_rate_percent": round((len(errors) / len(results)) * 100, 2) if results else 0,
        "average_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "p50_latency_ms": round(percentile(latencies, 0.50), 2) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 0.95), 2) if latencies else None,
        "p99_latency_ms": round(percentile(latencies, 0.99), 2) if latencies else None,
        "cache_responses": sum(1 for r in results if r.get("source") == "cache"),
        "db_or_api_responses": sum(1 for r in results if r.get("source") in ["db", "api"]),
    }

    Path("proof_step11").mkdir(exist_ok=True)
    with open("proof_step11/11_load_test_full_output.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rps", type=int, default=100)
    parser.add_argument("--duration", type=int, default=10)
    args = parser.parse_args()

    asyncio.run(run_load_test(args.base_url, args.rps, args.duration))