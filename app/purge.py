"""Retention: delete cases (and their uploaded files) older than RETENTION_DAYS. Run via cron: python -m app.purge"""
import datetime as dt
import shutil

from . import config
from .models import Case, SessionLocal


def purge() -> int:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=config.RETENTION_DAYS)
    n = 0
    with SessionLocal() as db:
        for case in db.query(Case).filter(Case.created_at < cutoff).all():
            shutil.rmtree(config.UPLOAD_DIR / str(case.org_id) / str(case.id), ignore_errors=True)
            db.delete(case)
            n += 1
        db.commit()
    return n


if __name__ == "__main__":
    print(f"purged {purge()} cases")
