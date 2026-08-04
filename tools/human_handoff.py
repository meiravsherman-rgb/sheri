"""Human handoff tool — notifies Merav when a customer needs personal attention."""

from config import MANAGER_PHONE, MANAGER_NAME
from tools import TOOL_REGISTRY
from tools.whatsapp import send_reply


def request_human_handoff(chat_id: str, reason: str, summary: str) -> str:
    """Send a notification to Merav with customer details and conversation summary.

    Args:
        chat_id: Customer phone (filled by framework)
        reason: Why the handoff is needed
        summary: Brief summary of the conversation so far
    """
    notification = (
        f"📋 העברה מ-שרי הבוטית\n\n"
        f"👤 לקוחה: {chat_id}\n"
        f"📌 סיבה: {reason}\n"
        f"💬 סיכום: {summary}\n\n"
        f"💡 ניתן ליצור קשר ישירות עם הלקוחה."
    )
    try:
        send_reply(MANAGER_PHONE, notification)
        # Log handoff event in CRM
        try:
            from database import log_lead_event
            log_lead_event(chat_id, "handoff", {"reason": reason, "summary": summary})
        except Exception:
            pass
        return f"העברתי את הפרטים ל{MANAGER_NAME}. היא תיצור איתך קשר בהקדם."
    except Exception as e:
        return f"לא הצלחתי להעביר את ההודעה ל{MANAGER_NAME} ({e}). אנא נסי שוב מאוחר יותר."


TOOL_REGISTRY["request_human_handoff"] = {
    "schema": {
        "name": "request_human_handoff",
        "description": (
            "העברת השיחה למירב שרמן (מענה אנושי). "
            "השתמשי כשהלקוחה מבקשת שיחה אישית, שואלת שאלה רפואית, "
            "מביעה חוסר שביעות רצון, מעוניינת בטיפול/ליווי אישי, "
            "או כשאין לך תשובה מתוך המידע הקיים. "
            "chat_id will be filled by the framework; leave empty."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "מזהה הצ'אט (ימולא אוטומטית)",
                },
                "reason": {
                    "type": "string",
                    "description": "סיבת ההעברה",
                },
                "summary": {
                    "type": "string",
                    "description": "סיכום קצר של השיחה עד כה",
                },
            },
            "required": ["chat_id", "reason", "summary"],
        },
    },
    "fn": request_human_handoff,
}
