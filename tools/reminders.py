"""Reminders tool — schedule messages using APScheduler backed by SQLite."""

import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from config import DATABASE_PATH
from tools import TOOL_REGISTRY

# ── Scheduler setup ────────────────────────────────────────────────
_jobstore_url = f"sqlite:///{DATABASE_PATH}"
_scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=_jobstore_url)},
    job_defaults={"misfire_grace_time": 3600},
)


def start_scheduler() -> None:
    if not _scheduler.running:
        _scheduler.start()


def _send_reminder(chat_id: str, message: str) -> None:
    from tools.whatsapp import send_reply
    try:
        send_reply(chat_id, f"⏰ תזכורת: {message}")
    except Exception as e:
        print(f"Failed to send reminder to {chat_id}: {e}")


# ── Tool functions ─────────────────────────────────────────────────

def schedule_reminder(chat_id: str, remind_at_iso: str, message: str) -> str:
    """Schedule a reminder for a specific time.

    Args:
        chat_id: Phone number to send reminder to (filled by framework)
        remind_at_iso: ISO 8601 datetime for when to send the reminder
        message: The reminder message text
    """
    try:
        remind_at = datetime.fromisoformat(remind_at_iso)
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=timezone.utc)
    except ValueError:
        return f"תאריך לא תקין: {remind_at_iso}. השתמשי בפורמט ISO 8601."

    if remind_at <= datetime.now(timezone.utc):
        return "לא ניתן לקבוע תזכורת בעבר. בחרי זמן עתידי."

    job_id = f"reminder_{uuid.uuid4().hex[:8]}"
    _scheduler.add_job(
        _send_reminder,
        trigger="date",
        run_date=remind_at,
        args=[chat_id, message],
        id=job_id,
    )
    local_time = remind_at.strftime("%d/%m/%Y %H:%M")
    return f"תזכורת נקבעה ל-{local_time}: {message} (מזהה: {job_id})"


def list_reminders(chat_id: str) -> str:
    """List all pending reminders for a chat.

    Args:
        chat_id: Phone number to list reminders for (filled by framework)
    """
    jobs = _scheduler.get_jobs()
    user_jobs = [j for j in jobs if j.args and j.args[0] == chat_id]

    if not user_jobs:
        return "אין תזכורות פעילות."

    lines = ["התזכורות שלך:"]
    for j in user_jobs:
        time_str = j.next_run_time.strftime("%d/%m/%Y %H:%M") if j.next_run_time else "?"
        msg = j.args[1] if len(j.args) > 1 else ""
        lines.append(f"- {time_str}: {msg} (מזהה: {j.id})")
    return "\n".join(lines)


def cancel_reminder(reminder_id: str) -> str:
    """Cancel a scheduled reminder.

    Args:
        reminder_id: The reminder ID returned when it was scheduled
    """
    try:
        _scheduler.remove_job(reminder_id)
        return f"תזכורת {reminder_id} בוטלה."
    except Exception:
        return f"לא נמצאה תזכורת עם מזהה {reminder_id}."


# ── Register in TOOL_REGISTRY ──────────────────────────────────────

TOOL_REGISTRY["schedule_reminder"] = {
    "schema": {
        "name": "schedule_reminder",
        "description": (
            "קביעת תזכורת לזמן מסוים. "
            "chat_id will be filled by the framework; leave empty."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "מזהה הצ'אט (ימולא אוטומטית)"},
                "remind_at_iso": {"type": "string", "description": "מתי לשלוח תזכורת (ISO 8601, e.g. 2026-08-02T10:00:00+03:00)"},
                "message": {"type": "string", "description": "תוכן התזכורת"},
            },
            "required": ["chat_id", "remind_at_iso", "message"],
        },
    },
    "fn": schedule_reminder,
}

TOOL_REGISTRY["list_reminders"] = {
    "schema": {
        "name": "list_reminders",
        "description": "הצגת כל התזכורות הפעילות. chat_id will be filled by the framework; leave empty.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "מזהה הצ'אט (ימולא אוטומטית)"},
            },
            "required": ["chat_id"],
        },
    },
    "fn": list_reminders,
}

TOOL_REGISTRY["cancel_reminder"] = {
    "schema": {
        "name": "cancel_reminder",
        "description": "ביטול תזכורת לפי מזהה.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {"type": "string", "description": "מזהה התזכורת לביטול"},
            },
            "required": ["reminder_id"],
        },
    },
    "fn": cancel_reminder,
}
