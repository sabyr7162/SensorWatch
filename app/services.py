import html
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from app.crud import delete_old_measurements
from app.database import SessionLocal

RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))
logger = logging.getLogger(__name__)

def check_threshold(thresholds: dict, current:dict):
    alerts = {}
    for key, value in current.items():
        if key in thresholds:
            limit = thresholds[key]
            min_val = limit.get('min')
            max_val = limit.get('max')

            if min_val is not None and value < min_val:
                alerts[f'{key}_min'] = f"{key} is lower than {min_val}\nCurrent: {value}"

            if max_val is not None and value > max_val:
                alerts[f'{key}_max'] = f'{key} is higher than {max_val}\nCurrent: {value}'
    return alerts 


def cleanup():
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    with SessionLocal() as session:
        return delete_old_measurements(session, cutoff)


async def cleanup_loop():
    while True:
        try:
            deleted = await asyncio.to_thread(cleanup)
            logger.info(f"Retention removed {deleted} measurements")
        except Exception as e:
            logger.exception(f"{e} exception occurred")
        await asyncio.sleep(24 * 3600)