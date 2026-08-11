"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Provides the Redis cache/event-bus client used by ingestion, API health, and dashboard telemetry.
"""
import redis.asyncio as redis
import json
import logging
import asyncio
from typing import Optional, AsyncGenerator, Any, Dict, Set, List

logger = logging.getLogger("RedisBus")

class InternalMesh:
    """Fallback in-memory event mesh when Redis is unavailable."""
    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._state: Dict[str, Any] = {}
        logger.warning("Initializing Internal Memory Mesh (Redis Fallback active)")

    async def publish(self, channel: str, message: Any):
        payload = message if isinstance(message, str) else json.dumps(message)
        if channel in self._subscribers:
            for queue in list(self._subscribers[channel]):
                try:
                    await queue.put(payload)
                except Exception:
                    continue

    async def subscribe(self, channel: str) -> AsyncGenerator[Any, None]:
        queue = asyncio.Queue()
        if channel not in self._subscribers:
            self._subscribers[channel] = set()
        self._subscribers[channel].add(queue)
        
        try:
            while True:
                yield await queue.get()
        finally:
            if channel in self._subscribers and queue in self._subscribers[channel]:
                self._subscribers[channel].remove(queue)

    def set(self, key: str, value: str):
        self._state[key] = value

    def get(self, key: str) -> Optional[str]:
        return self._state.get(key)

    def delete(self, key: str):
        if key in self._state:
            del self._state[key]

class RedisBus:
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.fallback: InternalMesh = InternalMesh()
        self._url: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, url: Optional[str] = None):
        from .config import get_settings
        settings = get_settings()
        if not url:
            url = settings.REDIS_URL
            
        try:
            current_loop = asyncio.get_running_loop()
            
            # 🛡️ LOOP SAFETY: If we detect a loop change (common in pytest-asyncio),
            # we MUST reset the client to avoid "Future attached to different loop" errors.
            if self.client:
                if self._loop != current_loop:
                    logger.debug("Loop change detected. Resetting Redis client.")
                    await self.close()
                else:
                    try:
                        # 🔹 Fix: ping() is a coroutine in redis.asyncio
                        await self.client.ping()
                        if self._url == url:
                            return
                    except:
                        await self.close()

            self._url = url
            self._loop = current_loop
            self.client = redis.from_url(
                self._url, 
                encoding="utf-8", 
                decode_responses=True,
                socket_timeout=10.0,
                socket_connect_timeout=10.0,
                max_connections=500,
                retry_on_timeout=True
            )
            await self.client.ping()
            logger.info(f"Connected to Redis Event Mesh at {self._url}")
        except Exception as e:
            if settings.LIVE_VERIFY_MODE:
                logger.critical(f"CRITICAL: Redis connection failed in LIVE_VERIFY_MODE: {e}")
                raise RuntimeError(f"STRICT_FAIL: Redis unavailable at {url}")
            logger.error(f"Redis connection failed: {e}. Falling back to Internal Mesh.")
            self.client = None

    async def publish(self, channel: str, message: Any):
        from .config import get_settings
        if self.client:
            try:
                payload = message if isinstance(message, str) else json.dumps(message)
                await self.client.publish(channel, payload)
                return
            except Exception as e:
                if get_settings().LIVE_VERIFY_MODE:
                    raise RuntimeError(f"STRICT_FAIL: Redis publish failed in live mode: {e}")
                logger.error(f"Redis publish failed: {e}. Switching to fallback.")
                self.client = None

        if get_settings().LIVE_VERIFY_MODE:
            raise RuntimeError(f"STRICT_FAIL: Attempted publish without Redis in LIVE_VERIFY_MODE")
        await self.fallback.publish(channel, message)

    async def subscribe(self, channel: str) -> AsyncGenerator[Any, None]:
        from .config import get_settings
        if self.client:
            try:
                pubsub = self.client.pubsub()
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        yield message["data"]
                return
            except Exception:
                if get_settings().LIVE_VERIFY_MODE:
                    raise RuntimeError("STRICT_FAIL: Redis subscription lost in live mode")
                self.client = None

        if get_settings().LIVE_VERIFY_MODE:
            raise RuntimeError("STRICT_FAIL: Attempted subscription without Redis in LIVE_VERIFY_MODE")
        async for msg in self.fallback.subscribe(channel):
            yield msg

    async def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False):
        from .config import get_settings
        if self.client:
            try:
                return await self.client.set(key, value, ex=ex, nx=nx)
            except Exception as e:
                if get_settings().LIVE_VERIFY_MODE:
                    raise RuntimeError(f"STRICT_FAIL: Redis set failed in live mode: {e}")
                logger.error(f"Redis set failed for {key}: {e}. Switching to fallback.")
                self.client = None
        
        if get_settings().LIVE_VERIFY_MODE:
            raise RuntimeError(f"STRICT_FAIL: Attempted set without Redis in LIVE_VERIFY_MODE")
        self.fallback.set(key, value)

    async def get(self, key: str) -> Optional[str]:
        from .config import get_settings
        if self.client:
            try:
                return await self.client.get(key)
            except Exception as e:
                if get_settings().LIVE_VERIFY_MODE:
                    raise RuntimeError(f"STRICT_FAIL: Redis get failed in live mode: {e}")
                logger.error(f"Redis get failed for {key}: {e}. Switching to fallback.")
                self.client = None
        
        if get_settings().LIVE_VERIFY_MODE:
            raise RuntimeError(f"STRICT_FAIL: Attempted get without Redis in LIVE_VERIFY_MODE")
        return self.fallback.get(key)

    async def delete(self, *keys: str):
        from .config import get_settings
        if self.client:
            try:
                await self.client.delete(*keys)
                return
            except Exception as e:
                if get_settings().LIVE_VERIFY_MODE:
                    raise RuntimeError(f"STRICT_FAIL: Redis delete failed in live mode: {e}")
                logger.error(f"Redis delete failed for {keys}: {e}. Switching to fallback.")
                self.client = None
        
        if get_settings().LIVE_VERIFY_MODE:
            raise RuntimeError(f"STRICT_FAIL: Attempted delete without Redis in LIVE_VERIFY_MODE")
        for k in keys:
            self.fallback.delete(k)

    async def keys(self, pattern: str = "*") -> List[str]:
        if self.client:
            try:
                return await self.client.keys(pattern)
            except Exception as e:
                logger.error(f"Redis keys failed: {e}")
                return []
        return [k for k in self.fallback._state.keys() if pattern == "*" or pattern in k]


    async def close(self):
        if self.client:
            try:
                await self.client.close()
            except:
                pass
            self.client = None
            self._loop = None

redis_bus = RedisBus()
