"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Manages WebSocket clients and broadcasts real-time market, news, and system events.
"""
import asyncio
import logging
import json
import time
from typing import List
from fastapi import WebSocket, WebSocketDisconnect
from app.core.redis_client import redis_bus

logger = logging.getLogger("WebSocketBroadcaster")

class LiveStreamManager:
    """
    Manages active WebSocket connections.
    Broadcasts real-time events from Redis channels.
    Includes Delivery Heartbeats for UI proof.
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.message_count = 0
        self.last_broadcast_time = time.time()

    async def connect(self, websocket: WebSocket):
        """Accepts a new connection and logs the handshake."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🟢 [WS-HANDSHAKE] Client Connected. Active listeners: {len(self.active_connections)}")
        
        # Immediate Proof for DevTools
        await websocket.send_json({
            "type": "system", 
            "timestamp": time.time(),
            "payload": {
                "message": "APEX AI TERMINAL SYNCHRONIZED",
                "version": "1.0.0-HARDENED"
            }
        })

    def disconnect(self, websocket: WebSocket):
        """Cleanup dead connections."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"🔴 [WS-DROP] Client Disconnected. Active listeners: {len(self.active_connections)}")

    async def listen_for_pings(self, websocket: WebSocket):
        """Listen for client pings to keep connection alive."""
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": time.time()})
        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.debug(f"WS Listen Loop Exit: {e}")
            self.disconnect(websocket)

    async def broadcast_from_redis(self, channel: str):
        """
        Background loop listening to Redis Pub/Sub.
        FIXED: Non-blocking task delivery per listener.
        """
        logger.info(f"📡 [WS-START] Broadcaster loop active for: {channel}")
        
        event_type_map = {
            "market_ticks": "market_tick",
            "ai_signals": "ai_signal",
            "account_balance": "status",
            "news_scored": "news_scored",
            "recommendations": "recommendation"
        }
        event_type = event_type_map.get(channel, channel)

        while True:
            try:
                async for message in redis_bus.subscribe(channel):
                    if not self.active_connections: continue
                        
                    try:
                        payload = json.loads(message) if isinstance(message, str) else message
                        envelope = json.dumps({
                            "type": event_type,
                            "timestamp": time.time(),
                            "payload": payload
                        })
                        
                        self.message_count += 1
                        disconnected = []
                        for connection in self.active_connections:
                            try:
                                await connection.send_text(envelope)
                            except:
                                disconnected.append(connection)
                        
                        for client in disconnected: self.disconnect(client)
                            
                    except Exception as e:
                        logger.error(f"Broadcaster Dispatch Error [{channel}]: {e}")
            except Exception as e:
                logger.error(f"Pub/Sub Critical Logic Failure: {e}. Retry in 5s...")
                await asyncio.sleep(5)

    async def run_heartbeat(self):
        """Proof of Life: Proof in UI that the link is alive."""
        while True:
            await asyncio.sleep(10)
            if self.active_connections:
                heartbeat = json.dumps({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "payload": {
                        "tps": round(self.message_count / 10.0, 2),
                        "status": "Healthy"
                    }
                })
                self.message_count = 0 
                for connection in self.active_connections:
                    try: await connection.send_text(heartbeat)
                    except: pass

stream_manager = LiveStreamManager()
