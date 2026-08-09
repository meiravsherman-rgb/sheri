"""FastAPI app — Meta WhatsApp Cloud API webhook."""

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from config import (
    WHATSAPP_APP_SECRET,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_VERIFY_TOKEN,
)
from database import init_db, is_seen, mark_seen, upsert_lead_from_message, append, seed_questionnaire
from admin import router as admin_router
from crm import router as crm_router
from seed_db import seed
from tools.whatsapp import send_reply, send_buttons, mark_as_read

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sheri")

# ── Welcome buttons (shown on first message) ─────────────────────
WELCOME_BUTTONS = [
    {"id": "btn_courses", "title": "הקורסים שלנו"},
    {"id": "btn_method", "title": "מה זה שיטת שרמן?"},
    {"id": "btn_talk", "title": "שיחה עם מירב"},
]

WELCOME_BUTTONS_TEXT = "בחרי אחת מהאפשרויות:"

# Map button IDs to natural language so the agent understands intent
BUTTON_TO_MESSAGE = {
    "btn_courses": "אשמח לשמוע על הקורסים והמחירים",
    "btn_method": "ספרי לי מה זו שיטת שרמן",
    "btn_talk": "אני רוצה לדבר עם מירב",
}

# ── Static auto-reply (used while bot is in upgrade mode) ────────
AUTO_REPLY = """הי, ברוכה הבאה!
שמחה על העניין שאת מביעה בשיטת שרמן.
המערכת שלי נמצאת כרגע בשדרוג.
לכן, בשלב זה אני רק אוכל להעביר את הפניה שלך, ויחזרו אליך מהמשרד בהקדם.
את מוזמנת לפרט כאן מה הצורך שלך."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        init_db()
        seed()  # Populate admin tables if empty
        seed_questionnaire()  # Insert 18 guide questions if not exist
    except Exception as e:
        logger.warning(f"Seed/init warning: {e}")
    # Import tools to populate TOOL_REGISTRY
    import tools.human_handoff  # noqa: F401
    try:
        import tools.reminders  # noqa: F401
        from tools.reminders import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Reminders disabled: {e}")
    logger.info("Sheri bot started")
    yield
    # Shutdown
    logger.info("Sheri bot stopping")


app = FastAPI(title="שרי הבוטית", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(crm_router)


# ── Chat simulator API ────────────────────────────────────────────

class ChatRequest(BaseModel):
    phone: str
    name: str
    message: str


class ResetRequest(BaseModel):
    phone: str


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """Chat simulator endpoint — same agent, no WhatsApp."""
    try:
        from database import tail
        is_new_user = len(tail(req.phone, 1)) == 0

        upsert_lead_from_message(req.phone, req.name, source="סימולטור", tags=["סימולטור"])
        from agent import handle_message, generate_ai_summary
        reply = handle_message(req.phone, req.name, req.message)
        try:
            generate_ai_summary(req.phone)
        except Exception:
            pass

        result = {"reply": reply}
        if is_new_user:
            result["buttons"] = {
                "text": WELCOME_BUTTONS_TEXT,
                "options": WELCOME_BUTTONS,
            }
        return result
    except Exception as e:
        logger.error(f"Chat API error: {e}", exc_info=True)
        return {"reply": f"שגיאה: {e}"}


@app.post("/api/reset")
async def api_reset(req: ResetRequest):
    """Clear conversation history for a phone number."""
    from database import _url, _get_headers
    import httpx
    httpx.delete(_url("conversations"), headers=_get_headers(), params={"chat_id": f"eq.{req.phone}"}).raise_for_status()
    return {"status": "ok"}


# Serve chat simulator UI
_static_dir = Path(__file__).parent / "static"


@app.get("/simulator", response_class=Response)
@app.get("/simulator/", response_class=Response)
async def simulator():
    index = _static_dir / "index.html"
    if index.exists():
        return Response(content=index.read_text(encoding="utf-8"), media_type="text/html")
    return Response(content="Simulator not found", status_code=404)


@app.get("/health")
async def health():
    return {"status": "ok", "version": 1, "bot": "שרי הבוטית"}


# ── Webhook verification (Meta sends GET) ──────────────────────────
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed")
    return Response(content="Forbidden", status_code=403)


# ── Signature verification ─────────────────────────────────────────
def _verify_signature(body: bytes, signature: str) -> bool:
    if not WHATSAPP_APP_SECRET:
        return True  # Skip verification if no secret configured
    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ── Incoming messages (Meta sends POST) ────────────────────────────
@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.body()

    # Verify signature (skip if no signature header — local testing)
    signature = request.headers.get("x-hub-signature-256", "")
    if signature and WHATSAPP_APP_SECRET and not _verify_signature(body, signature):
        logger.warning("Invalid webhook signature")
        return Response(content="Invalid signature", status_code=403)

    data = await request.json()

    # Meta sends various webhook types — we only care about messages
    entries = data.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})

            # Skip status updates (delivered, read, etc.)
            if "messages" not in value:
                continue

            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id", "")

            # Only process messages for our phone number
            if phone_number_id != WHATSAPP_PHONE_NUMBER_ID:
                continue

            messages = value.get("messages", [])
            contacts = value.get("contacts", [])

            for msg in messages:
                await _process_message(msg, contacts)

    return {"status": "ok"}


async def _process_message(msg: dict, contacts: list[dict]) -> None:
    """Process a single incoming WhatsApp message."""
    message_id = msg.get("id", "")
    msg_type = msg.get("type", "")

    # Dedup
    if is_seen(message_id):
        return
    mark_seen(message_id)

    # Handle interactive messages (button clicks)
    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        btn_reply = interactive.get("button_reply", {})
        btn_id = btn_reply.get("id", "")
        text = BUTTON_TO_MESSAGE.get(btn_id, btn_reply.get("title", ""))
        sender_phone = msg.get("from", "")
    elif msg_type == "text":
        sender_phone = msg.get("from", "")
        text = msg.get("text", {}).get("body", "")
    else:
        logger.info(f"Skipping message type: {msg_type}")
        return

    if not sender_phone or not text:
        return

    # Get sender name from contacts
    sender_name = ""
    for contact in contacts:
        if contact.get("wa_id") == sender_phone:
            sender_name = contact.get("profile", {}).get("name", "")
            break

    logger.info(f"Message from {sender_phone} ({sender_name}): {text[:50]}...")

    # Track lead in CRM
    try:
        upsert_lead_from_message(sender_phone, sender_name, source="בוט וואטסאפ")
    except Exception as e:
        logger.warning(f"Failed to upsert lead: {e}")

    # Mark as read
    try:
        mark_as_read(message_id)
    except Exception as e:
        logger.warning(f"Failed to mark message as read: {e}")

    # Check if this is a new user (no prior conversations)
    from database import tail
    is_new_user = len(tail(sender_phone, 1)) == 0

    # Process with AI agent
    try:
        from agent import handle_message, generate_ai_summary
        reply = handle_message(sender_phone, sender_name, text)
        send_reply(sender_phone, reply)
        logger.info(f"Agent reply sent to {sender_phone}")

        # Send welcome buttons for new users
        if is_new_user:
            try:
                send_buttons(sender_phone, WELCOME_BUTTONS_TEXT, WELCOME_BUTTONS)
            except Exception as e:
                logger.warning(f"Failed to send welcome buttons: {e}")

        # Generate AI summary for CRM
        try:
            generate_ai_summary(sender_phone)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Agent error for {sender_phone}: {e}", exc_info=True)
        send_reply(sender_phone, AUTO_REPLY)
        append(sender_phone, "assistant", AUTO_REPLY)
