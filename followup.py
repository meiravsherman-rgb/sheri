"""Follow-up cron job — sends scheduled messages and alerts to Merav."""

import logging
from datetime import datetime, timezone, timedelta

from database import (
    get_leads_for_followup, get_lead, get_leads,
    increment_followup, update_lead, log_lead_event,
    display_phone, normalize_phone,
)
from tools.whatsapp import (
    send_reply, alert_cold_lead, alert_purchase,
)

logger = logging.getLogger("sheri")

# Israel timezone offset (UTC+2 in winter, UTC+3 in summer)
# Using a simple approach: check if current month is in DST range
def _israel_hour() -> int:
    """Get current hour in Israel time."""
    now = datetime.now(timezone.utc)
    # Israel DST: last Friday before April 2 to last Sunday before October 31
    month = now.month
    is_dst = 4 <= month <= 10  # Approximate
    offset = 3 if is_dst else 2
    return (now.hour + offset) % 24


def _is_sending_hours() -> bool:
    """Check if current time is within allowed sending hours (9:00-20:00 Israel)."""
    hour = _israel_hour()
    return 9 <= hour < 20


FOLLOWUP_MESSAGES = {
    # followup_count 0 -> send message 1 (3 hours after link)
    0: {
        "hours": 3,
        "template": "היי {name}, מה שלומך? ראיתי שטרם רכשת את הקורס {course}. נתקלת באיזו שהיא בעיה? יש משהו שאני יכולה לעזור לך?",
    },
    # followup_count 1 -> send message 2 (23 hours after link)
    1: {
        "hours": 23,
        "template": "היי {name}, רציתי לשתף שנשים רבות שהתחילו עם שיטת שרמן, מספרות על שינוי משמעותי כבר בשבועות הראשונים. עדי לדוגמא, משתפת איך בעזרת הקורס הדיגיטלי, הווסת הפכה עבורה ממקור של סבל וקושי, למתנה של ממש",
    },
}

# Alert to Merav after 3 days (72 hours) — no message to customer
MERAV_ALERT_HOURS = 72

# 14-day template (needs Meta approval — placeholder for future)
REENGAGEMENT_HOURS = 14 * 24  # 336 hours


def run_followup_cycle():
    """Main follow-up cycle — called by cron every 15 minutes."""
    if not _is_sending_hours():
        logger.info("Outside sending hours (9:00-20:00 Israel), skipping followup cycle")
        return

    now = datetime.now(timezone.utc)
    processed = 0

    # Process each follow-up stage
    for followup_count, config in FOLLOWUP_MESSAGES.items():
        hours = config["hours"]
        template = config["template"]

        try:
            leads = get_leads_for_followup(hours_since_link=hours, max_followup_count=followup_count + 1)
        except Exception as e:
            logger.error(f"Failed to query leads for followup {followup_count}: {e}")
            continue

        for lead in leads:
            # Only process leads at exactly this stage
            current_count = lead.get("followup_count") or 0
            if current_count != followup_count:
                continue

            phone = lead["phone"]
            name = lead.get("name") or ""
            course = lead.get("link_course_name") or "הקורס"
            link_sent = lead.get("link_sent_at", "")

            # Verify timing — link must be older than required hours
            if link_sent:
                try:
                    link_dt = datetime.fromisoformat(link_sent.replace("Z", "+00:00"))
                    if (now - link_dt).total_seconds() < hours * 3600:
                        continue
                except (ValueError, TypeError):
                    continue

            # Check if customer responded after link was sent (skip if so)
            last_contact = lead.get("last_contact", "")
            if last_contact and link_sent and last_contact > link_sent:
                # Customer already responded — don't send followup
                continue

            # Send the message
            message = template.format(name=name, course=course)
            try:
                send_reply(phone, message)
                increment_followup(phone)
                log_lead_event(phone, "followup_sent", {
                    "message_number": followup_count + 1,
                    "course": course,
                })
                processed += 1
                logger.info(f"Followup {followup_count + 1} sent to {display_phone(phone)}")
            except Exception as e:
                logger.error(f"Failed to send followup to {phone}: {e}")

    # Merav alerts — 3 days after link, no purchase
    _send_merav_cold_alerts(now)

    if processed:
        logger.info(f"Followup cycle complete: {processed} messages sent")


def _send_merav_cold_alerts(now: datetime):
    """Send alerts to Merav for leads that got a link 3 days ago but didn't purchase."""
    try:
        # Get leads with link_sent_at older than 72 hours but not yet alerted
        leads = get_leads_for_followup(hours_since_link=MERAV_ALERT_HOURS, max_followup_count=999)
    except Exception:
        return

    for lead in leads:
        phone = lead["phone"]
        name = lead.get("name") or display_phone(phone)
        course = lead.get("link_course_name") or "קורס"
        link_sent = lead.get("link_sent_at", "")
        followup_count = lead.get("followup_count") or 0

        # Only alert once (when followup_count is exactly 2 — after both messages sent)
        if followup_count != 2:
            continue

        # Check timing
        if link_sent:
            try:
                link_dt = datetime.fromisoformat(link_sent.replace("Z", "+00:00"))
                hours_since = (now - link_dt).total_seconds() / 3600
                # Alert between 72-96 hours (3-4 days) to avoid re-alerting
                if not (72 <= hours_since <= 96):
                    continue
            except (ValueError, TypeError):
                continue

        try:
            alert_cold_lead(name, course)
            log_lead_event(phone, "merav_alert", {"type": "cold_lead_3d", "course": course})
            # Increment followup_count to 3 so we don't alert again
            increment_followup(phone)
            logger.info(f"Cold lead alert sent to Merav for {display_phone(phone)}")
        except Exception as e:
            logger.error(f"Failed to send cold lead alert for {phone}: {e}")


def send_weekly_report():
    """Send a weekly summary report to Merav via WhatsApp."""
    from tools.whatsapp import _alert_merav
    from database import get_purchases, get_dashboard_stats

    try:
        stats = get_dashboard_stats()
        total = stats.get("total_leads", 0)
        new_month = stats.get("new_this_month", 0)
        revenue = stats.get("month_revenue", 0)
        funnel = stats.get("funnel", {})

        lines = [
            "דוח שבועי - שרי הבוטית",
            f"סה\"כ לידים: {total}",
            f"חדשים החודש: {new_month}",
            f"הכנסות החודש: {revenue:.0f}₪",
            "",
            "משפך:",
        ]
        for status, count in funnel.items():
            lines.append(f"  {status}: {count}")

        attention = stats.get("needs_attention", [])
        if attention:
            lines.append("")
            lines.append("דורשים תשומת לב:")
            for l in attention[:3]:
                lines.append(f"  {l.get('name', '')} ({display_phone(l.get('phone', ''))})")

        _alert_merav("\n".join(lines))
        logger.info("Weekly report sent to Merav")
    except Exception as e:
        logger.error(f"Failed to send weekly report: {e}")
