"""FastAPI app — Meta WhatsApp Cloud API webhook."""

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    WHATSAPP_APP_SECRET,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_VERIFY_TOKEN,
)
from database import init_db, is_seen, mark_seen, upsert_lead_from_message, append
from admin import router as admin_router
from crm import router as crm_router
from seed_db import seed
from tools.whatsapp import send_reply, send_buttons, mark_as_read

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sheri")

# ── Welcome buttons (shown on first message) ─────────────────────
WELCOME_BUTTONS = [
    {"id": "btn_method", "title": "מידע ראשוני על השיטה"},
    {"id": "btn_courses", "title": "קורסים"},
    {"id": "btn_talk", "title": "שיחה אישית"},
]

WELCOME_BUTTONS_TEXT = "בחרי אחת מהאפשרויות:"

# Map button IDs to natural language so the agent understands intent
BUTTON_TO_MESSAGE = {
    "btn_method": "ספרי לי מידע ראשוני על השיטה",
    "btn_courses": "אשמח לשמוע על הקורסים",
    "btn_talk": "אני רוצה שיחה אישית",
}

# 14-day re-engagement template button responses (quick_reply)
REENGAGEMENT_BUTTONS = {
    "כן, אשמח לעזרה": "want_help",
    "אצטרף בהמשך": "join_later",
    "ויתרתי, תודה": "gave_up",
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
    except Exception as e:
        logger.warning(f"Seed/init warning: {e}")
    # Import tools to populate TOOL_REGISTRY
    import tools.human_handoff  # noqa: F401
    import tools.marketing  # noqa: F401
    try:
        import tools.reminders  # noqa: F401
        from tools.reminders import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Reminders disabled: {e}")

    # Start follow-up cron job (every 15 minutes)
    try:
        from followup_scheduler import start_followup_scheduler
        start_followup_scheduler()
        logger.info("Follow-up scheduler started")
    except Exception as e:
        logger.warning(f"Follow-up scheduler disabled: {e}")

    logger.info("Sheri bot started")
    yield
    # Shutdown
    logger.info("Sheri bot stopping")


app = FastAPI(title="שרי הבוטית", lifespan=lifespan)

# ── CORS — allow only our own domain ─────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sheri-bot.onrender.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(admin_router)
app.include_router(crm_router)


# ── Chat simulator API ────────────────────────────────────────────

class ChatRequest(BaseModel):
    phone: str
    name: str
    message: str


class ResetRequest(BaseModel):
    phone: str


def _check_auth(request: Request):
    """Auth check for simulator endpoints."""
    token = request.cookies.get("admin_token")
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        from admin import _active_sessions, _cleanup_sessions, ADMIN_PASSWORD
        _cleanup_sessions()
        if token in _active_sessions:
            return
        if token == ADMIN_PASSWORD:
            return
    except ImportError:
        pass
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/chat", dependencies=[Depends(_check_auth)])
async def api_chat(request: Request, req: ChatRequest):
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


@app.post("/api/reset", dependencies=[Depends(_check_auth)])
async def api_reset(request: Request, req: ResetRequest):
    """Clear conversation history for a phone number (simulator only)."""
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


# ── Cardcom payment webhook (via Make) ─────────────────────────────

CARDCOM_SECRET = "sheri_cardcom_2026"

CARDCOM_PRODUCT_MAP = {
    "SH.BASICS": "קורס יסודות",
    "SH.PAIN.RELIEF": "קורס הקלה בכאב",
    "SH.PMP": "הקלה בתופעות קדם וסתיות",
}


class CardcomProduct(BaseModel):
    id: str | None = None
    price: str | float | None = None


class CardcomWebhook(BaseModel):
    secret: str
    phone: str
    name: str | None = ""
    email: str | None = ""
    amount: float | None = 0
    products: list[CardcomProduct] = []


@app.post("/webhook/cardcom")
async def cardcom_webhook(payload: CardcomWebhook):
    """Receive payment notification from Cardcom via Make."""
    if payload.secret != CARDCOM_SECRET:
        logger.warning("Cardcom webhook: invalid secret")
        return Response(content="Forbidden", status_code=403)

    if not payload.phone:
        return {"status": "error", "message": "missing phone"}

    # Filter empty/null products, parse price strings, normalize IDs
    def _parse_price(val) -> float:
        if val is None or val == "" or val == "null":
            return 0
        try:
            return float(str(val).replace(",", "").replace("₪", "").strip())
        except (ValueError, TypeError):
            return 0

    products = [p for p in payload.products if p.id and str(p.id).strip()]
    for p in products:
        p.price = _parse_price(p.price)
    if not products:
        return {"status": "error", "message": "no products"}

    # Expand SH.FULL to all 3 courses (split price equally)
    expanded = []
    for p in products:
        pid = p.id.strip().upper()
        price = p.price or 0
        if pid == "SH.FULL":
            per_course = price / 3 if price else 0
            expanded.append({"code": "SH.BASICS", "name": CARDCOM_PRODUCT_MAP["SH.BASICS"], "price": per_course})
            expanded.append({"code": "SH.PAIN.RELIEF", "name": CARDCOM_PRODUCT_MAP["SH.PAIN.RELIEF"], "price": per_course})
            expanded.append({"code": "SH.PMP", "name": CARDCOM_PRODUCT_MAP["SH.PMP"], "price": per_course})
        else:
            name = CARDCOM_PRODUCT_MAP.get(pid)
            if name:
                expanded.append({"code": pid, "name": name, "price": price})
            else:
                logger.warning(f"Cardcom webhook: unknown product ID '{pid}'")

    courses = expanded

    if not courses:
        return {"status": "error", "message": "no valid products"}

    from database import (
        normalize_phone, create_purchase, upsert_lead_from_message,
        update_lead, log_lead_event,
    )
    from tools.whatsapp import send_purchase_confirmation, alert_purchase

    phone = normalize_phone(payload.phone)
    customer_name = (payload.name or "").strip() or "לקוחה"
    total_amount = payload.amount or 0

    # Upsert lead
    try:
        upsert_lead_from_message(phone, customer_name, source="Cardcom")
    except Exception as e:
        logger.warning(f"Cardcom webhook: failed to upsert lead: {e}")

    # Create purchases + log events
    course_names = []
    for c in courses:
        try:
            create_purchase(phone, c["name"], amount=c["price"], payment_method="cardcom",
                            notes=f"Cardcom product: {c['code']}")
            log_lead_event(phone, "purchase", {"course": c["name"], "source": "cardcom",
                                               "product_id": c["code"], "amount": c["price"]})
            course_names.append(c["name"])
        except Exception as e:
            logger.error(f"Cardcom webhook: failed to create purchase for {c['code']}: {e}")

    # Update lead status
    try:
        update_lead(phone, status="לקוחה")
    except Exception as e:
        logger.warning(f"Cardcom webhook: failed to update lead status: {e}")

    # Send WhatsApp confirmation to customer
    try:
        send_purchase_confirmation(phone, customer_name)
    except Exception as e:
        logger.warning(f"Cardcom webhook: failed to send confirmation: {e}")

    # Alert Merav
    try:
        alert_purchase(customer_name, " + ".join(course_names), total_amount)
    except Exception as e:
        logger.warning(f"Cardcom webhook: failed to alert Merav: {e}")

    logger.info(f"Cardcom webhook: {customer_name} ({phone}) purchased {course_names}")
    return {"status": "ok", "courses": course_names}


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
        logger.error("WHATSAPP_APP_SECRET not configured — rejecting webhook")
        return False
    if not signature:
        return False
    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ── Incoming messages (Meta sends POST) ────────────────────────────
@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.body()

    # Verify webhook signature (MANDATORY — Meta always sends x-hub-signature-256)
    signature = request.headers.get("x-hub-signature-256", "")
    if not _verify_signature(body, signature):
        logger.warning("Invalid or missing webhook signature")
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


async def _handle_reengagement_response(sender_phone: str, btn_title: str, contacts: list[dict]) -> None:
    """Handle 14-day re-engagement template button responses."""
    from database import update_lead, log_lead_event, get_lead

    lead = get_lead(sender_phone)
    name = (lead.get("name") if lead else "") or ""
    action = REENGAGEMENT_BUTTONS[btn_title]

    log_lead_event(sender_phone, "reengagement_response", {"button": btn_title, "action": action})

    if action == "want_help":
        reply = f"שמחה לשמוע, {name}! איך אוכל לעזור לך? ספרי לי מה את מחפשת ואשמח לכוון אותך."
        send_reply(sender_phone, reply)
        append(sender_phone, "user", btn_title)
        append(sender_phone, "assistant", reply)

    elif action == "join_later":
        reply = "נהדר. אני תמיד פה לשירותך."
        send_reply(sender_phone, reply)
        update_lead(sender_phone, status="אצטרף בהמשך", followup_stopped=True)
        append(sender_phone, "user", btn_title)
        append(sender_phone, "assistant", reply)

    elif action == "gave_up":
        reply = "אני תמיד פה לשירותך. אם בעתיד תרצי לחזור, מוזמנת באהבה."
        send_reply(sender_phone, reply)
        update_lead(sender_phone, status="לא רלוונטי", followup_stopped=True)
        append(sender_phone, "user", btn_title)
        append(sender_phone, "assistant", reply)

    logger.info(f"Reengagement response from {sender_phone}: {action}")


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
        btn_title = btn_reply.get("title", "")
        sender_phone = msg.get("from", "")

        # Check if this is a 14-day re-engagement button response
        if btn_title in REENGAGEMENT_BUTTONS:
            await _handle_reengagement_response(sender_phone, btn_title, contacts)
            return

        text = BUTTON_TO_MESSAGE.get(btn_id, btn_title)
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

    # Handle opt-out keyword
    if text.strip() in ("הסירי", "הסר", "הסירי אותי", "הסר אותי"):
        try:
            from database import set_opt_in, log_lead_event
            set_opt_in(sender_phone, False)
            log_lead_event(sender_phone, "opted_out", {"method": "keyword"})
            opt_out_reply = "בסדר גמור, הוסרת מרשימת העדכונים. אם בעתיד תרצי לחזור, מוזמנת באהבה."
            send_reply(sender_phone, opt_out_reply)
            append(sender_phone, "user", text)
            append(sender_phone, "assistant", opt_out_reply)
            logger.info(f"Opt-out processed for {sender_phone}")
            return
        except Exception as e:
            logger.error(f"Opt-out error for {sender_phone}: {e}")

    # Check if this is a new user (no prior conversations)
    from database import tail
    is_new_user = len(tail(sender_phone, 1)) == 0

    # Check if returning lead (has previous conversations but new session)
    if not is_new_user:
        try:
            from database import get_lead, get_purchases
            lead = get_lead(sender_phone)
            purchases = get_purchases(sender_phone) if lead else []
            if lead and purchases:
                from tools.whatsapp import alert_returning_lead
                alert_returning_lead(lead.get("name") or sender_name or "לקוחה")
        except Exception:
            pass

    # Process with AI agent
    try:
        from agent import handle_message, generate_ai_summary
        reply = handle_message(sender_phone, sender_name, text)

        if is_new_user:
            # New user: single message with agent reply + welcome buttons
            try:
                send_buttons(sender_phone, reply, WELCOME_BUTTONS)
            except Exception as e:
                logger.warning(f"Failed to send welcome buttons: {e}")
                send_reply(sender_phone, reply)  # Fallback to plain text
        else:
            send_reply(sender_phone, reply)
        logger.info(f"Agent reply sent to {sender_phone}")

        # Generate AI summary for CRM
        try:
            generate_ai_summary(sender_phone)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Agent error for {sender_phone}: {e}", exc_info=True)
        send_reply(sender_phone, AUTO_REPLY)
        append(sender_phone, "assistant", AUTO_REPLY)
