"""Follow-up scheduler — runs the followup cycle every 15 minutes."""

import logging
import threading
import time

logger = logging.getLogger("sheri")

_INTERVAL_SECONDS = 15 * 60  # 15 minutes


def _followup_loop():
    """Background loop that runs followup cycle."""
    while True:
        try:
            from followup import run_followup_cycle
            run_followup_cycle()
        except Exception as e:
            logger.error(f"Followup cycle error: {e}", exc_info=True)
        time.sleep(_INTERVAL_SECONDS)


def _weekly_report_loop():
    """Background loop for weekly report — checks every hour, sends on Sunday 9:00 Israel."""
    while True:
        try:
            from followup import _israel_hour
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            # Israel time day of week (0=Monday, 6=Sunday)
            # UTC+3 approximate
            israel_hour_val = _israel_hour()
            # Sunday = 6 in Python weekday
            israel_weekday = (now.weekday() + (1 if israel_hour_val < now.hour else 0)) % 7
            # Approximate: if it's Sunday and 9:00 Israel time
            if now.weekday() == 6 and israel_hour_val == 9:
                from followup import send_weekly_report
                send_weekly_report()
        except Exception as e:
            logger.error(f"Weekly report check error: {e}")
        time.sleep(3600)  # Check every hour


def start_followup_scheduler():
    """Start background threads for followup and weekly report."""
    t1 = threading.Thread(target=_followup_loop, daemon=True, name="followup-cron")
    t1.start()
    logger.info("Followup cron started (every 15 min)")

    t2 = threading.Thread(target=_weekly_report_loop, daemon=True, name="weekly-report")
    t2.start()
    logger.info("Weekly report cron started")
