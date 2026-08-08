"""WhatsApp message sending via Meta Cloud API. Framework-only, not an LLM tool."""

import httpx

from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID

_API_URL = f"https://graph.facebook.com/v25.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
_HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
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


def send_template(phone: str, template_name: str, language: str = "he") -> dict:
    """Send a template message (for messages outside 24h window)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
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
