"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Processes execution events and records broker order outcomes for auditability.
"""
import asyncio
import logging
import json
import time
from datetime import datetime, timezone
from typing import Dict

from app.core.redis_client import redis_bus
from app.models.schemas.domain_schemas import AISignal
from app.services.broker.alpaca_adapter import AlpacaAdapter
from app.models.schemas.execution_schemas import OrderRequest
from app.core.db import AsyncSessionLocal
from app.models.all_models import ExecutionLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExecutionEngine")


class ExecutionWorker:
    """
    Process AI signals and record Alpaca Paper execution outcomes.

    The worker subscribes to Redis ``ai_signals``, applies latency/risk checks,
    submits accepted BUY/SELL signals to Alpaca Paper, and persists execution
    logs so the dashboard can verify provider order UUIDs.
    """
    def __init__(self):
        self.broker = AlpacaAdapter()
        # Local paper state is used for risk/sizing between broker acknowledgements.
        self.paper_cash_balance = 100000.00
        self.portfolio_holdings = {
            "Cash (USD)": 100000.00,
            "XAU/USD": 0.0,
            "BTC/USD": 0.0,
            "EUR/USD": 0.0,
            "GBP/USD": 0.0,
            "WTI/USD": 0.0
        }
        
        # Execution cost assumptions used by the local sizing/risk layer.
        self.FEE_RATE = 0.0005        # 0.05% Exchange Fee
        self.SLIPPAGE_MAX = 0.0002    # 0.02% Max Slippage
        
        # Risk controls reject stale signals and halt execution after drawdown breach.
        self.hwm_aum = 0.0            # High-Water Mark for Drawdown calc
        self.risk_halt = False        # Circuit Breaker State
        self.MDD_LIMIT = 0.10         # 10% Hard-stop limit
        # Reliability Controls
        self.LATENCY_MAX_MS = 10000 # Allows slower Docker validation environments.
        self.MAX_SIGNAL_AGE_SEC = 15

    async def run(self):
        """
        Start the execution loop and listen for AI signal messages.

        Each accepted signal is checked for staleness and drawdown risk before
        order submission, then the resulting provider acknowledgement is logged.
        """
        await redis_bus.connect()
        await self.broker.connect()

        initial_aum = await self._calculate_total_aum()
        logger.info(f"Execution Engine Online. AUM: ${initial_aum:,.2f}. Waiting for AI Signals...")
        
        # Publish initial local portfolio state for dashboard consumers.
        valuations = await self._get_portfolio_valuations(0.0)
        current_aum = await self._calculate_total_aum()

        await redis_bus.set("account_state", json.dumps({
            "aum": current_aum, 
            "holdings": self.portfolio_holdings,
            "cash": self.paper_cash_balance
        }))
        await redis_bus.publish("account_balance", {
            "aum": round(current_aum, 2),
            "holdings": valuations
        })
        
        async for msg in redis_bus.subscribe("ai_signals"):
            try:
                # Redis may deliver JSON strings or already-decoded dicts.
                if isinstance(msg, str):
                    signal = AISignal.model_validate_json(msg)
                else:
                    signal = AISignal.model_validate(msg)
                
                if signal.action == "WATCH": continue # WATCH is advisory only.

                # Reject stale signals so execution proof is based on recent inputs.
                now_ts = datetime.now(timezone.utc).timestamp()
                signal_latency_ms = (now_ts - (signal.signal_ts or signal.ingest_ts or now_ts)) * 1000
                if signal_latency_ms > self.LATENCY_MAX_MS:
                    logger.warning(f"⚠️ [RISK] STALE SIGNAL REJECTED: {signal.ticker} | Latency: {signal_latency_ms:.0f}ms > {self.LATENCY_MAX_MS}ms")
                    await redis_bus.publish("system_incident", {
                        "type": "STALE_DATA_REJECTION",
                        "ticker": signal.ticker,
                        "latency_ms": signal_latency_ms
                    })
                    continue

                # Circuit breaker stops new orders after the configured drawdown.
                current_aum = await self._calculate_total_aum()
                if self.hwm_aum > 0:
                    drawdown = (self.hwm_aum - current_aum) / self.hwm_aum
                    if drawdown > self.MDD_LIMIT:
                        if not self.risk_halt:
                            logger.error(f"🚨 [CRITICAL] MDD BREACH: {drawdown*100:.2f}% > {self.MDD_LIMIT*100:.0f}%. EXECUTIONS HALTED.")
                            self.risk_halt = True
                            await redis_bus.publish("system_incident", {
                                "type": "CIRCUIT_BREAKER_TRIP",
                                "drawdown_pct": round(drawdown*100, 2),
                                "hwm": round(self.hwm_aum, 2),
                                "aum": round(current_aum, 2)
                            })
                        continue # Reject trades while halted.

                # Reset halt if AUM recovered (manual reset or market recovery)
                if self.risk_halt and current_aum >= self.hwm_aum * 0.95:
                    self.risk_halt = False
                    logger.info("🟢 [RISK] HWM Recovered. Resuming executions.")

                tick_raw = await redis_bus.get(f"latest:tick:{signal.ticker}")
                if not tick_raw: continue
                    
                tick_data = json.loads(tick_raw) if isinstance(tick_raw, (str, bytes)) else tick_raw
                current_price = float(tick_data.get('price', 1.0))

                # Apply a small deterministic slippage assumption before sizing.
                slippage = 1.00002 if "BUY" in signal.action else 0.99998
                execution_price = current_price * slippage
                
                # Capped Kelly-style sizing uses recommendation confidence as
                # the probability proxy and limits any single position to 10%.
                p = signal.confidence
                q = 1.0 - p
                kelly_fraction = max(0, p - q) # Simplified Kelly for b=1.
                
                # Safety Cap: 10% of AUM per position max
                safe_fraction = min(kelly_fraction, 0.10)
                
                total_valuation = await self._calculate_total_aum()
                max_risk_usd = total_valuation * safe_fraction
                
                # Ensure we have a minimum liquidity requirement ($50 min)
                if max_risk_usd < 50:
                    logger.info(f"⏭️ [SIZING] Signal ignored for {signal.ticker}. Sizing {max_risk_usd:.2f} < $50 min.")
                    continue
                    
                quantity = round(max_risk_usd / execution_price, 6)
                
                if "BUY" in signal.action:
                    total_cost = (quantity * execution_price) * (1 + self.FEE_RATE)
                    if self.paper_cash_balance >= total_cost:
                        req = OrderRequest(
                            symbol=signal.ticker,
                            side="BUY",
                            qty=quantity,
                            signal_id=signal.signal_id
                        )
                        ack = await self.broker.submit_order(req)
                        
                        if ack.order_id and self._is_real_alpaca_uuid(ack.order_id):
                            # Update local balance for filled or pending orders to prevent over-trading
                            if ack.status == "filled":
                                self.paper_cash_balance -= total_cost
                                self.portfolio_holdings[signal.ticker] = self.portfolio_holdings.get(signal.ticker, 0.0) + quantity
                                await self._emit_execution(signal, "BUY", quantity, execution_price, total_cost - (quantity * execution_price), ack)
                            else:
                                # Mark as pending but don't update holdings until fill confirmation (in a real system we'd poll)
                                # For this project, we record the pending state honestly.
                                await self._emit_execution(signal, "BUY", quantity, execution_price, 0.0, ack)
                        else:
                            logger.error(f"Alpaca rejected paper BUY order for {signal.ticker} or returned non-Alpaca ID.")
                        
                elif "SELL" in signal.action:
                    current_qty = self.portfolio_holdings.get(signal.ticker, 0.0)
                    if current_qty > 0: 
                        sell_qty = min(quantity, current_qty)
                        
                        req = OrderRequest(
                            symbol=signal.ticker,
                            side="SELL",
                            qty=sell_qty,
                            signal_id=signal.signal_id
                        )
                        ack = await self.broker.submit_order(req)
                        
                        if ack.order_id and self._is_real_alpaca_uuid(ack.order_id):
                            if ack.status == "filled":
                                gross_revenue = sell_qty * execution_price
                                fee = gross_revenue * self.FEE_RATE
                                net_revenue = gross_revenue - fee
                                
                                self.paper_cash_balance += net_revenue
                                self.portfolio_holdings[signal.ticker] -= sell_qty
                                await self._emit_execution(signal, "SELL", sell_qty, execution_price, fee, ack)
                            else:
                                await self._emit_execution(signal, "SELL", sell_qty, execution_price, 0.0, ack)
                        else:
                            logger.error(f"Alpaca rejected paper SELL order for {signal.ticker} or returned non-Alpaca ID.")
                        
            except Exception as e:
                logger.error(f"Execution Error: {e}")

    def _is_real_alpaca_uuid(self, order_id: str) -> bool:
        """
        Return True only for valid Alpaca-style UUID order IDs.

        This prevents simulated/internal IDs from being accepted as provider
        execution proof in Step 7 and dashboard audit views.
        """
        if not order_id: return False
        try:
            import uuid
            val = uuid.UUID(order_id)
            return val.version == 4
        except ValueError:
            return False

    async def _emit_execution(self, signal: AISignal, side: str, quantity: float, price: float, fee: float = 0.0, ack: any = None):
        """
        Publish and persist one execution acknowledgement.

        The payload is sent to Redis for live UI updates and written to
        ExecutionLog so later audits can inspect provider, status, and order ID.
        """
        now_ts = time.time()
        ingest_ts = getattr(signal, "ingest_ts", now_ts) or now_ts
        latency_ms = (now_ts - ingest_ts) * 1000
        
        status = "PENDING"
        order_id = None
        filled_qty = 0.0
        filled_price = 0.0
        
        if ack:
            order_id = ack.order_id
            status = str(ack.status).upper()
            if status == "FILLED":
                filled_qty = quantity
                filled_price = price
        
        payload = {
            "symbol": signal.ticker,
            "side": side,
            "quantity": quantity,
            "execution_price": round(price, 4),
            "commission_fee": round(fee, 2),
            "latency_ms": round(latency_ms, 2),
            "status": status,
            "order_id": order_id,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_ts": now_ts,
            "pnl_realized": 0.0
        }
        
        logger.info(f"✅ EXECUTION LOGGED: {side} {quantity} {signal.ticker} | Status: {status} | OrderID: {order_id}")
        
        # Broadcast to the event bus for live dashboard consumers.
        await redis_bus.publish("trade_executed", json.dumps(payload))
        
        # Persist the same event for E2E audit and Step 7 UUID verification.
        try:
            async with AsyncSessionLocal() as session:
                log_entry = ExecutionLog(
                    asset_id=signal.asset_id if hasattr(signal, 'asset_id') else 1,
                    signal_id=signal.signal_id,
                    action=side,
                    quantity=quantity,
                    price=price,
                    execution_ts=now_ts,
                    timestamp=datetime.now(timezone.utc),
                    status=status,
                    order_id=order_id,
                    provider="Alpaca Paper",
                    filled_qty=filled_qty,
                    filled_avg_price=filled_price,
                    submitted_at=datetime.now(timezone.utc) if status != "FILLED" else None,
                    filled_at=datetime.now(timezone.utc) if status == "FILLED" else None
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist ExecutionLog: {e}")

        # Update local portfolio state after the event has been recorded.
        valuations = await self._get_portfolio_valuations(price, signal.ticker)
        current_aum = await self._calculate_total_aum()
        
        # Update the high-water mark used by drawdown risk control.
        if current_aum > self.hwm_aum:
            self.hwm_aum = current_aum
            # logger.debug(f"[HWM] New High-Water Mark: ${self.hwm_aum:,.2f}")
                
        await redis_bus.publish("account_balance", {
            "aum": round(current_aum, 2),
            "holdings": valuations,
            "cash": round(self.paper_cash_balance, 2)
        })
        await redis_bus.set("account_state", json.dumps({
            "aum": current_aum,
            "hwm": self.hwm_aum,
            "holdings": self.portfolio_holdings,
            "cash": self.paper_cash_balance
        }))

    async def _calculate_total_aum(self) -> float:
        """
        Calculate local paper AUM from cash plus cached market prices.

        Redis prices may be live, delayed, or fallback; execution risk logic uses
        the latest cached value while provider provenance is shown elsewhere.
        """
        total_val = self.paper_cash_balance
        for ticker, qty in self.portfolio_holdings.items():
            if ticker == "Cash (USD)" or qty <= 0: continue
            
            # Use the last cached price for local risk sizing.
            tick_str = await redis_bus.get(f"tick:{ticker}")
            price = 0.0
            if tick_str:
                price_data = json.loads(tick_str) if isinstance(tick_str, (str, bytes)) else tick_str
                price = float(price_data.get('price', 0.0))
            
            total_val += (qty * price)
        return float(total_val)

    async def _get_portfolio_valuations(self, current_asset_price: float, current_ticker: str = "") -> Dict[str, float]:
        """Return USD-valued holdings for account-balance dashboard updates."""
        vals = {"Cash (USD)": self.paper_cash_balance}
        for ticker, qty in self.portfolio_holdings.items():
            if ticker == "Cash (USD)": continue
            if ticker == current_ticker and current_asset_price > 0:
                vals[ticker] = qty * current_asset_price
            else:
                # Fetch price for other assets
                tick_str = await redis_bus.get(f"tick:{ticker}")
                price = 0.0
                if tick_str:
                    price_data = json.loads(tick_str) if isinstance(tick_str, (str, bytes)) else tick_str
                    price = float(price_data.get('price', 0.0))
                vals[ticker] = qty * price
        return vals

if __name__ == "__main__":
    worker = ExecutionWorker()
    asyncio.run(worker.run())

# Singleton for API access
execution_worker = ExecutionWorker()
