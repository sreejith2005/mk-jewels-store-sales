from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import Config
from core.logger import get_logger
from reports.daily_report import generate_daily_report
from storage.db import Database


logger = get_logger(__name__)


def _run_nightly_report() -> None:
    try:
        generate_daily_report()
    except Exception:
        logger.exception("Nightly coaching report job failed.")


def _run_transcript_cleanup() -> None:
    db = Database()
    try:
        deleted_count = db.delete_events_older_than(7)
        logger.info("7-day transcript cleanup deleted %s events.", deleted_count)
    except Exception:
        logger.exception("7-day transcript cleanup job failed.")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        _run_nightly_report,
        CronTrigger(hour=Config.REPORT_HOUR, minute=0, timezone="Asia/Kolkata"),
        id="nightly_coaching_report",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_transcript_cleanup,
        CronTrigger(hour=2, minute=0, timezone="Asia/Kolkata"),
        id="transcript_cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: nightly report at %s:00, cleanup at 02:00 Asia/Kolkata",
        Config.REPORT_HOUR,
    )
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler) -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
