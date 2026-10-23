"""Long-running maintenance loops: stale budget reservation sweep and retention purge.

Each loop runs forever and never dies: a failing pass is logged and the next
interval retries. When Redis is configured, each pass first takes a short
``SET NX EX`` lock so only one worker runs a given task per interval. Without
Redis (single process) the task simply runs. Both tasks are idempotent, so a
Redis outage that prevents locking degrades to every worker running the pass,
never to lost or double-applied work.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from sqlalchemy.orm import sessionmaker

from daily_agent.config import Settings
from daily_agent.db import get_engine
from daily_agent.redis_client import get_redis
from daily_agent.retention import purge_expired
from daily_agent.services import reclaim_stale_reservations

logger = logging.getLogger(__name__)

# First runs are spread out so a fleet restart does not sweep in lockstep.
MAX_STARTUP_JITTER_SECONDS = 30.0


def _lock_key(task: str) -> str:
    return f"karmi:maintenance:{task}"


async def _acquire_interval_lock(settings: Settings, task: str, interval: int) -> bool:
    """True when this worker should run ``task`` this interval."""
    client = get_redis(settings)
    if client is None:
        return True
    try:
        acquired = await asyncio.to_thread(
            client.set, _lock_key(task), "1", nx=True, ex=interval
        )
    except Exception:
        logger.warning("maintenance lock unavailable for %s; running locally", task, exc_info=True)
        return True
    return bool(acquired)


def _sweep_reservations_blocking() -> int:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        return reclaim_stale_reservations(session)


def _purge_blocking(settings: Settings) -> dict[str, int]:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return purge_expired(factory, settings)


async def _interval_loop(
    settings: Settings,
    task: str,
    interval: int,
    action: Callable[[], Awaitable[object]],
) -> None:
    await asyncio.sleep(random.uniform(0, min(float(interval), MAX_STARTUP_JITTER_SECONDS)))
    while True:
        try:
            if await _acquire_interval_lock(settings, task, interval):
                await action()
        except Exception:
            logger.exception("maintenance task %s failed; retrying next interval", task)
        await asyncio.sleep(interval)


async def _sweep_reservations_once() -> None:
    reclaimed = await asyncio.to_thread(_sweep_reservations_blocking)
    if reclaimed:
        logger.info("reservation sweep reclaimed %d stale holds", reclaimed)


async def run_maintenance_loops(settings: Settings) -> None:
    """Run the reservation sweep and (if enabled) retention purge until cancelled."""

    async def purge_once() -> None:
        deleted = await asyncio.to_thread(_purge_blocking, settings)
        if any(deleted.values()):
            logger.info("retention purge deleted rows: %s", deleted)

    loops = [
        _interval_loop(
            settings,
            "reservation_sweep",
            settings.reservation_sweep_interval_seconds,
            _sweep_reservations_once,
        )
    ]
    if settings.retention_purge_enabled:
        loops.append(
            _interval_loop(
                settings,
                "retention_purge",
                settings.retention_purge_interval_seconds,
                purge_once,
            )
        )
    await asyncio.gather(*loops)
