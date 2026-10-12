"""
Redis client setup for task queue and caching.
"""

import redis.asyncio as aioredis
from config import settings


redis = None


async def init_redis():
    """Initialize Redis connection on startup."""
    global redis
    redis = aioredis.from_url(settings.REDIS_URL)
    print("✓ Redis connected")


async def close_redis():
    """Close Redis connection on shutdown."""
    global redis
    if redis:
        await redis.close()
        print("✓ Redis closed")


async def get_redis():
    """Get Redis instance."""
    return redis
