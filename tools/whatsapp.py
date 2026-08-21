"""WhatsApp message sending via Meta Cloud API. Framework-only, not an LLM tool."""

import logging

import httpx

from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, MANAGER_PHONE

logger = logging.getLogger("sheri")

_API_URL = f"https://graph.facebook.com/v25.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
_HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json; charset=utf-8",
}


def send_reply(phone: str, text: str) -> dict:
    """Send a text message to a WhatsApp number.

    Args:
        phone: Phone number in international format without + (e.g. '972501234567')
        text: Message text to send
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(_API_URL, headers=_HEADERS, json=payload)
        resp.raise_for_status()
        return resp.json()


def send_template(phone: str, template_name: str, language: str = "he",
                   body_params: list[str] | None = None) -> dict:
    """Send a template message (for messages outside 24h window).

    Args:
        phone: Phone number in international format without + (e.g. '972501234567')
        template_name: Approved template name
        language: Template language code (default 'he')
        body_params: List of strings for {{1}}, {{2}}, etc. in the body
    """
    template: dict = {
        "name": template_name,
        "language": {"code": language},
    }
    if body_params:
        template["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": p} for p in body_params
                ],
            }
        ]
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": template,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(_API_URL, headers=_HEADERS, json=payload)
        resp.raise_for_status()
        return resp.json()


def send_buttons(phone: str, body_text: str, buttons: list[dict]) -> dict:
    """Send an interactive reply-buttons message (max 3 buttons, 20 chars each).

    Args:
        phone: Phone number in international format without + (e.g. '972501234567')
        body_text: Message body text
        buttons: List of dicts with 'id' and 'title' keys
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]
                ]
            },
        },
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(_API_URL, headers=_HEADERS, json=payload)
        resp.raise_for_status()
        return resp.json()


def mark_as_read(message_id: str) -> dict:
    """Mark an incoming message as read (blue checkmarks)."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(_API_URL, headers=_HEADERS, json=payload)
        resp.raise_for_status()
        return resp.json()


# ── Alerts to Merav ───────────────────────────────────────────────

def _alert_merav(text: str) -> None:
    """Send an alert message to Merav's WhatsApp."""
    try:
        send_reply(MANAGER_PHONE, text)
        logger.info(f"Alert sent to Merav: {text[:60]}")
    except Exception as e:
        logger.error(f"Failed to alert Merav: {e}")


def alert_hot_lead(name: str, course: str) -> None:
    """Alert Merav about a hot lead who received a purchase link."""
    _alert_merav(f"ליד חם! {name} מעוניינת ב{course}. שלחתי לה קישור.")


def alert_purchase(name: str, course: str, amount: float) -> None:
    """Alert Merav about a new purchase."""
    _alert_merav(f"רכישה! {name} רכשה {course} ב-{amount:.0f}₪")


def alert_cold_lead(name: str, course: str) -> None:
    """Alert Merav about a lead who got a link 3 days ago but didn't purchase."""
    _alert_merav(f"{name} קיבלה קישור ל{course} לפני 3 ימים ולא רכשה")


def alert_returning_lead(name: str) -> None:
    """Alert Merav about a returning lead."""
    _alert_merav(f"ליד חוזר! {name} חזרה לשיחה")


def send_purchase_confirmation(phone: str, name: str) -> None:
    """Send purchase confirmation message to customer."""
    text = (
        f"היי {name}, ברוכה הבאה לשיטת שרמן.\n"
        "מאחלת לך צפייה מהנה ומועילה.\n"
        "לכל עניין, הרגישי בנוח לפנות אלי כאן"
    )
    try:
        send_reply(phone, text)
        logger.info(f"Purchase confirmation sent to {phone}")
    except Exception as e:
        logger.error(f"Failed to send purchase confirmation to {phone}: {e}")
