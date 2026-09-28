"""Background worker: Peppol outbox, inbox polling and SuperFaktúra sync.

MVP runs as a simple loop (``python -m app.worker``). The functions it calls
are idempotent, so moving them to Celery/RQ beat schedules in V1 is mechanical.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.integrations import sync as sf_sync
from app.models import Company, Integration
from app.peppol import service
from app.peppol.access_point import get_access_point

log = logging.getLogger("efaktura.worker")
SYNC_EVERY = timedelta(minutes=30)


def tick() -> None:
    ap = get_access_point()
    with SessionLocal() as db:
        service.process_outbox(db, ap)
        for company in db.scalars(select(Company).where(Company.dic.is_not(None))):
            try:
                service.poll_inbox(db, company, ap)
            except Exception:
                log.exception("inbox poll failed for company %s", company.id)
        cutoff = datetime.now(UTC) - SYNC_EVERY
        for integ in db.scalars(select(Integration).where(Integration.kind == "superfaktura")):
            last = integ.last_sync_at.replace(tzinfo=UTC) if integ.last_sync_at and not integ.last_sync_at.tzinfo \
                else integ.last_sync_at
            if last is None or last < cutoff:
                try:
                    sf_sync.sync(db, integ)
                except Exception:
                    log.exception("superfaktura sync failed for integration %s", integ.id)


def main(interval: float = 30.0) -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    while True:
        tick()
        time.sleep(interval)


if __name__ == "__main__":
    main()
