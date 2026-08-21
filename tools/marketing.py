"""Marketing funnel tools — opt-in, link tracking, lead scoring."""

import logging
from tools import TOOL_REGISTRY

logger = logging.getLogger("sheri")


# ── Opt-In Tool ───────────────────────────────────────────────────

def _set_marketing_opt_in(chat_id: str, opt_in: bool) -> str:
    from database import set_opt_in, log_lead_event
    try:
        set_opt_in(chat_id, opt_in)
        action = "opted_in" if opt_in else "opted_out"
        log_lead_event(chat_id, action, {"method": "bot_conversation"})
        if opt_in:
            return "ההסכמה לקבלת עדכונים נשמרה בהצלחה."
        else:
            return "הלקוחה הוסרה מרשימת העדכונים."
    except Exception as e:
        logger.error(f"Opt-in error for {chat_id}: {e}")
        return f"שגיאה בשמירת ההסכמה: {e}"


TOOL_REGISTRY["set_marketing_opt_in"] = {
    "schema": {
        "description": "שמירת הסכמה או ביטול הסכמה של לקוחה לקבלת עדכונים שיווקיים בוואטסאפ. opt_in=true להסכמה, opt_in=false לביטול.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "מספר טלפון הלקוחה"},
                "opt_in": {"type": "boolean", "description": "true להסכמה, false לביטול"},
            },
            "required": ["chat_id", "opt_in"],
        },
    },
    "fn": _set_marketing_opt_in,
}


# ── Link Tracking Tool ───────────────────────────────────────────

def _track_link_sent(chat_id: str, course_name: str) -> str:
    from database import mark_link_sent, update_lead_score
    from tools.whatsapp import alert_hot_lead
    from database import get_lead, display_phone
    try:
        mark_link_sent(chat_id, course_name)
        update_lead_score(chat_id, 20)
        # Alert Merav
        lead = get_lead(chat_id)
        name = (lead.get("name") if lead else "") or display_phone(chat_id)
        alert_hot_lead(name, course_name)
        return f"קישור לרכישת {course_name} תועד. מירב קיבלה התראה."
    except Exception as e:
        logger.error(f"Link tracking error for {chat_id}: {e}")
        return f"שגיאה בתיעוד הקישור: {e}"


TOOL_REGISTRY["track_link_sent"] = {
    "schema": {
        "description": "תיעוד שליחת קישור רכישה ללקוחה. קורא לזה אחרי ששלחת קישור לרכישת קורס. זה מפעיל מעקב אוטומטי.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "מספר טלפון הלקוחה"},
                "course_name": {"type": "string", "description": "שם הקורס שנשלח לו קישור"},
            },
            "required": ["chat_id", "course_name"],
        },
    },
    "fn": _track_link_sent,
}


# ── Lead Scoring Tool ────────────────────────────────────────────

def _update_lead_score(chat_id: str, points: int) -> str:
    from database import update_lead_score
    try:
        update_lead_score(chat_id, points)
        return f"ניקוד הליד עודכן ב-{points}+ נקודות."
    except Exception as e:
        logger.error(f"Lead score error for {chat_id}: {e}")
        return f"שגיאה בעדכון ניקוד: {e}"


TOOL_REGISTRY["update_lead_score"] = {
    "schema": {
        "description": "עדכון ניקוד ליד. השתמשי כשלקוחה שואלת על קורס (+10), מחיר (+15), קיבלה קישור (+20), או מבקשת לדבר עם מירב (+25).",
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "מספר טלפון הלקוחה"},
                "points": {"type": "integer", "description": "מספר נקודות להוסיף"},
            },
            "required": ["chat_id", "points"],
        },
    },
    "fn": _update_lead_score,
}
