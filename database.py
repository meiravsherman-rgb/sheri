"""Supabase storage via REST API — conversations + admin content management."""

import json
from datetime import datetime, timezone

import httpx

from config import SUPABASE_URL, SUPABASE_KEY

_headers = None


def _get_headers() -> dict:
    global _headers
    if _headers is None:
        _headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
    return _headers


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_phone(phone: str) -> str:
    """Normalize Israeli phone to 972... format (internal storage key)."""
    phone = phone.strip().replace("-", "").replace(" ", "").replace("+", "")
    if phone.startswith("05"):
        phone = "972" + phone[1:]
    elif phone.startswith("5") and len(phone) == 9:
        phone = "972" + phone
    return phone


def display_phone(phone: str) -> str:
    """Convert 972... to 05... for display."""
    if phone and phone.startswith("972") and len(phone) >= 12:
        return "0" + phone[3:]
    return phone


def init_db() -> None:
    """Verify Supabase connection."""
    r = httpx.get(_url("courses"), headers=_get_headers(), params={"select": "id", "limit": "1"})
    r.raise_for_status()


# ── Conversations ─────────────────────────────────────────────────

def append(chat_id: str, role: str, content: str) -> None:
    chat_id = normalize_phone(chat_id)
    httpx.post(_url("conversations"), headers=_get_headers(), json={
        "chat_id": chat_id, "role": role, "content": content, "created_at": _now(),
    }).raise_for_status()


def tail(chat_id: str, n: int = 20) -> list[dict]:
    chat_id = normalize_phone(chat_id)
    r = httpx.get(_url("conversations"), headers=_get_headers(), params={
        "select": "role,content",
        "chat_id": f"eq.{chat_id}",
        "order": "id.desc",
        "limit": str(n),
    })
    r.raise_for_status()
    rows = r.json()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


# ── Message dedup ─────────────────────────────────────────────────

def is_seen(message_id: str) -> bool:
    r = httpx.get(_url("seen_messages"), headers=_get_headers(), params={
        "select": "message_id",
        "message_id": f"eq.{message_id}",
        "limit": "1",
    })
    r.raise_for_status()
    return len(r.json()) > 0


def mark_seen(message_id: str) -> None:
    headers = {**_get_headers(), "Prefer": "resolution=merge-duplicates,return=representation"}
    httpx.post(_url("seen_messages"), headers=headers, json={
        "message_id": message_id, "created_at": _now(),
    }).raise_for_status()


# ── FAQ CRUD ───────────────────────────────────────────────────────

def get_all_faq() -> list[dict]:
    r = httpx.get(_url("faq"), headers=_get_headers(), params={
        "select": "*", "order": "sort_order,id",
    })
    r.raise_for_status()
    return r.json()


def upsert_faq(faq_id: int | None, question: str, answer: str, sort_order: int = 0) -> int:
    now = _now()
    if faq_id:
        httpx.patch(_url("faq"), headers=_get_headers(), params={"id": f"eq.{faq_id}"}, json={
            "question": question, "answer": answer, "sort_order": sort_order, "updated_at": now,
        }).raise_for_status()
        return faq_id
    else:
        r = httpx.post(_url("faq"), headers=_get_headers(), json={
            "question": question, "answer": answer, "sort_order": sort_order, "updated_at": now,
        })
        r.raise_for_status()
        return r.json()[0]["id"]


def delete_faq(faq_id: int) -> None:
    httpx.delete(_url("faq"), headers=_get_headers(), params={"id": f"eq.{faq_id}"}).raise_for_status()


# ── Courses CRUD ───────────────────────────────────────────────────

def get_all_courses() -> list[dict]:
    r = httpx.get(_url("courses"), headers=_get_headers(), params={
        "select": "*", "order": "sort_order,id",
    })
    r.raise_for_status()
    return r.json()


def upsert_course(course_id: int | None, **fields) -> int:
    fields["updated_at"] = _now()
    if course_id:
        httpx.patch(_url("courses"), headers=_get_headers(), params={"id": f"eq.{course_id}"}, json=fields).raise_for_status()
        return course_id
    else:
        r = httpx.post(_url("courses"), headers=_get_headers(), json=fields)
        r.raise_for_status()
        return r.json()[0]["id"]


def delete_course(course_id: int) -> None:
    httpx.delete(_url("courses"), headers=_get_headers(), params={"id": f"eq.{course_id}"}).raise_for_status()


# ── Content Sections CRUD ─────────────────────────────────────────

def get_all_sections() -> list[dict]:
    r = httpx.get(_url("content_sections"), headers=_get_headers(), params={
        "select": "*", "order": "id",
    })
    r.raise_for_status()
    return r.json()


def get_section(section_key: str) -> dict | None:
    r = httpx.get(_url("content_sections"), headers=_get_headers(), params={
        "select": "*", "section_key": f"eq.{section_key}", "limit": "1",
    })
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def upsert_section(section_key: str, title: str, body: str) -> None:
    headers = {**_get_headers(), "Prefer": "resolution=merge-duplicates,return=representation"}
    httpx.post(
        _url("content_sections") + "?on_conflict=section_key",
        headers=headers,
        json={"section_key": section_key, "title": title, "body": body, "updated_at": _now()},
    ).raise_for_status()


def delete_section(section_key: str) -> None:
    httpx.delete(_url("content_sections"), headers=_get_headers(), params={"section_key": f"eq.{section_key}"}).raise_for_status()


# ── Rules CRUD ─────────────────────────────────────────────────────

def get_all_rules() -> list[dict]:
    r = httpx.get(_url("rules"), headers=_get_headers(), params={
        "select": "*", "order": "id",
    })
    r.raise_for_status()
    return r.json()


def upsert_rule(rule_key: str, title: str, body: str, is_active: bool = True) -> None:
    headers = {**_get_headers(), "Prefer": "resolution=merge-duplicates,return=representation"}
    httpx.post(
        _url("rules") + "?on_conflict=rule_key",
        headers=headers,
        json={"rule_key": rule_key, "title": title, "body": body, "is_active": is_active, "updated_at": _now()},
    ).raise_for_status()


def delete_rule(rule_key: str) -> None:
    httpx.delete(_url("rules"), headers=_get_headers(), params={"rule_key": f"eq.{rule_key}"}).raise_for_status()


# ── Build knowledge base from DB ──────────────────────────────────

def build_knowledge_base() -> str:
    """Build the full knowledge base text from DB content."""
    parts = []

    # Skip keys handled elsewhere or no longer needed
    _skip_prefixes = ("guide_", "sec_coupon_", "note_")
    for s in get_all_sections():
        key = s.get("section_key", "")
        body = (s.get("body") or "").strip()
        if not body:
            continue
        if any(key.startswith(p) for p in _skip_prefixes):
            continue
        parts.append(f"## {s['title']}\n\n{body}")

    courses = [c for c in get_all_courses() if c.get("is_active")]
    if courses:
        parts.append("## קורסים\n")
        lines = ["| קורס | מחיר | למי מתאים | קישור רכישה |", "|-------|------|-----------|-------------|"]
        for c in courses:
            lines.append(f"| {c['name']} | {c['price']} | {c['audience']} | {c['purchase_url']} |")
        parts.append("\n".join(lines))

    faqs = get_all_faq()
    if faqs:
        parts.append("## שאלות ותשובות\n")
        for f in faqs:
            parts.append(f"**ש: {f['question']}**\nת: {f['answer']}\n")

    return "\n\n---\n\n".join(parts) if parts else ""


def build_rules_text() -> str:
    """Build behavioral rules text from DB."""
    all_rules = [r for r in get_all_rules() if r.get("is_active")]
    if not all_rules:
        return ""

    # Separate actual rules from questionnaire answers
    behavior_rules = []
    guide_answers = []
    for r in all_rules:
        key = r.get("rule_key", "")
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        # Skip entries with no meaningful content
        if not title and not body:
            continue
        if key.startswith("guide_"):
            if body:  # Only include guide answers that have actual content
                guide_answers.append(r)
        elif key.startswith("feedback_"):
            if body:  # Only include feedback with content
                behavior_rules.append(r)
        else:
            behavior_rules.append(r)

    lines = []
    # Behavioral rules as numbered list
    for i, r in enumerate(behavior_rules, 1):
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        if title and body:
            lines.append(f"{i}. **{title}:** {body}")
        elif body:
            lines.append(f"{i}. {body}")

    # Guide answers as preferences section
    if guide_answers:
        lines.append("\n## העדפות מירב (מתוך שאלון דיוק)")
        for r in guide_answers:
            title = (r.get("title") or "").strip()
            body = (r.get("body") or "").strip()
            if title and body:
                lines.append(f"- **{title}** → {body}")
            elif body:
                lines.append(f"- {body}")

    return "\n".join(lines)


# ── Leads CRUD ─────────────────────────────────────────────────────

def upsert_lead_from_message(phone: str, name: str, source: str | None = None, tags: list[str] | None = None) -> None:
    """Create lead if new, update last_contact and name if existing."""
    phone = normalize_phone(phone)
    now = _now()
    existing = get_lead(phone)
    if existing:
        # Update: keep first_contact, update last_contact
        updates: dict = {"last_contact": now, "updated_at": now}
        # Only set name if lead has no name yet (don't overwrite manual CRM edits)
        existing_name = (existing.get("name") or "").strip()
        if not existing_name and name:
            updates["name"] = name
        update_lead(phone, **updates)
    else:
        # New lead
        data: dict = {
            "phone": phone,
            "name": name,
            "last_contact": now,
            "first_contact": now,
            "updated_at": now,
        }
        if source is not None:
            data["source"] = source
        if tags is not None:
            data["tags"] = tags
        httpx.post(_url("leads"), headers=_get_headers(), json=data).raise_for_status()


def get_leads(status: str = "", search: str = "", tag: str = "") -> list[dict]:
    params = {"select": "*", "order": "last_contact.desc"}
    if status:
        params["status"] = f"eq.{status}"
    if search:
        # Normalize phone search: 05... → 972... for DB match
        phone_search = normalize_phone(search) if search.replace("-", "").replace(" ", "").startswith("05") else search
        params["or"] = f"(name.ilike.%{search}%,phone.ilike.%{phone_search}%)"
    if tag:
        params["tags"] = f"cs.{{{tag}}}"
    r = httpx.get(_url("leads"), headers=_get_headers(), params=params)
    r.raise_for_status()
    return r.json()


def get_lead(phone: str) -> dict | None:
    phone = normalize_phone(phone)
    r = httpx.get(_url("leads"), headers=_get_headers(), params={
        "select": "*", "phone": f"eq.{phone}", "limit": "1",
    })
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def update_lead(phone: str, **fields) -> None:
    phone = normalize_phone(phone)
    fields["updated_at"] = _now()
    httpx.patch(_url("leads"), headers=_get_headers(), params={"phone": f"eq.{phone}"}, json=fields).raise_for_status()


def create_lead_manual(phone: str, name: str, source: str = "manual") -> None:
    phone = normalize_phone(phone)
    now = _now()
    httpx.post(_url("leads"), headers=_get_headers(), json={
        "phone": phone, "name": name, "source": source,
        "first_contact": now, "last_contact": now, "updated_at": now,
    }).raise_for_status()


# ── Lead Events ────────────────────────────────────────────────────

def log_lead_event(phone: str, event_type: str, event_data: dict = None) -> None:
    import json
    phone = normalize_phone(phone)
    httpx.post(_url("lead_events"), headers=_get_headers(), json={
        "lead_phone": phone,
        "event_type": event_type,
        "event_data": json.dumps(event_data or {}, ensure_ascii=False),
        "created_at": _now(),
    }).raise_for_status()


def get_lead_timeline(phone: str, limit: int = 50) -> list[dict]:
    phone = normalize_phone(phone)
    r = httpx.get(_url("lead_events"), headers=_get_headers(), params={
        "select": "*",
        "lead_phone": f"eq.{phone}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    r.raise_for_status()
    return r.json()


def get_lead_conversations(phone: str, limit: int = 1000) -> list[dict]:
    phone = normalize_phone(phone)
    r = httpx.get(_url("conversations"), headers=_get_headers(), params={
        "select": "role,content,created_at",
        "chat_id": f"eq.{phone}",
        "order": "id.desc",
        "limit": str(limit),
    })
    r.raise_for_status()
    return list(reversed(r.json()))


# ── Purchases ──────────────────────────────────────────────────────

def create_purchase(lead_phone: str, course_name: str, amount: float,
                    course_id: int = None, payment_method: str = "cardcom",
                    notes: str = "") -> int:
    lead_phone = normalize_phone(lead_phone)
    now = _now()
    data = {
        "lead_phone": lead_phone, "course_name": course_name, "amount": amount,
        "payment_method": payment_method, "notes": notes,
        "purchased_at": now, "created_at": now,
    }
    if course_id:
        data["course_id"] = course_id
    r = httpx.post(_url("purchases"), headers=_get_headers(), json=data)
    r.raise_for_status()
    purchase_id = r.json()[0]["id"]
    # Update lead total_paid
    lead = get_lead(lead_phone)
    if lead:
        new_total = float(lead.get("total_paid", 0) or 0) + amount
        update_lead(lead_phone, total_paid=new_total)
    return purchase_id


def get_purchases(lead_phone: str = "") -> list[dict]:
    params = {"select": "*", "order": "purchased_at.desc"}
    if lead_phone:
        params["lead_phone"] = f"eq.{lead_phone}"
    r = httpx.get(_url("purchases"), headers=_get_headers(), params=params)
    r.raise_for_status()
    return r.json()


# ── Dashboard Stats ────────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    """Get summary stats for CRM dashboard."""
    leads = get_leads()
    total = len(leads)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    new_this_month = sum(1 for l in leads if l.get("created_at", "") >= month_start)

    # Status funnel
    funnel = {}
    for l in leads:
        s = l.get("status", "חדש")
        funnel[s] = funnel.get(s, 0) + 1

    # Revenue
    all_purchases = get_purchases()
    total_revenue = sum(float(p.get("amount", 0)) for p in all_purchases)
    month_revenue = sum(float(p.get("amount", 0)) for p in all_purchases if p.get("purchased_at", "") >= month_start)

    # Conversion
    registered = funnel.get("נרשמה", 0) + funnel.get("לקוחה", 0)
    conversion = round(registered / total * 100, 1) if total > 0 else 0

    # Upcoming followups
    followups = [l for l in leads if l.get("next_followup")]
    followups.sort(key=lambda l: l["next_followup"])

    # Top courses by revenue
    course_revenue = {}
    for p in all_purchases:
        cn = p.get("course_name", "אחר")
        course_revenue[cn] = course_revenue.get(cn, 0) + float(p.get("amount", 0))
    top_courses = sorted(course_revenue.items(), key=lambda x: x[1], reverse=True)[:5]

    # Needs attention: leads with no activity in 7+ days and not closed
    from datetime import timedelta
    week_ago = (now - timedelta(days=7)).isoformat()
    closed_statuses = {"נרשמה", "לקוחה"}
    needs_attention = [
        l for l in leads
        if l.get("status", "חדש") not in closed_statuses
        and l.get("last_contact", "") < week_ago
    ][:5]

    return {
        "total_leads": total,
        "new_this_month": new_this_month,
        "month_revenue": month_revenue,
        "total_revenue": total_revenue,
        "conversion_rate": conversion,
        "funnel": funnel,
        "upcoming_followups": followups[:5],
        "top_courses": [{"name": n, "revenue": r} for n, r in top_courses],
        "needs_attention": needs_attention,
    }


# ── CRM Settings ──────────────────────────────────────────────────

def get_crm_settings() -> dict:
    """Get all CRM settings as a dict of {key: value}."""
    r = httpx.get(_url("crm_settings"), headers=_get_headers(), params={"select": "*"})
    r.raise_for_status()
    result = {}
    for row in r.json():
        val = row["setting_value"]
        # Fix double-encoded JSON strings (stored as '"[...]"' instead of '[...]')
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, (list, dict)):
                    val = parsed
            except (json.JSONDecodeError, ValueError):
                pass
        result[row["setting_key"]] = val
    return result


def update_crm_setting(setting_key: str, setting_value) -> None:
    """Update a single CRM setting."""
    httpx.patch(
        _url("crm_settings"), headers=_get_headers(),
        params={"setting_key": f"eq.{setting_key}"},
        json={"setting_value": setting_value, "updated_at": _now()},
    ).raise_for_status()


# ── Followup Queries ──────────────────────────────────────────────

def get_leads_for_followup(hours_since_link: float, max_followup_count: int) -> list[dict]:
    """Get leads that need a follow-up message.

    Returns leads where:
    - link_sent_at is set and older than hours_since_link hours
    - followup_count < max_followup_count
    - opt_in_marketing = true
    - followup_stopped = false
    - status is NOT 'נרשמה' or 'לא רלוונטי'
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_since_link)).isoformat()

    r = httpx.get(_url("leads"), headers=_get_headers(), params={
        "select": "*",
        "link_sent_at": f"lt.{cutoff}",
        "opt_in_marketing": "eq.true",
        "followup_stopped": "eq.false",
        "followup_count": f"lt.{max_followup_count}",
        "status": "not.in.(נרשמה,לא רלוונטי)",
        "order": "link_sent_at.asc",
    })
    r.raise_for_status()
    return r.json()


def set_opt_in(phone: str, opt_in: bool) -> None:
    """Set marketing opt-in status for a lead."""
    phone = normalize_phone(phone)
    now = _now()
    if opt_in:
        update_lead(phone, opt_in_marketing=True, opt_in_date=now)
    else:
        update_lead(phone, opt_in_marketing=False, opt_out_date=now, followup_stopped=True)


def mark_link_sent(phone: str, course_name: str) -> None:
    """Record that a purchase link was sent to this lead."""
    from datetime import datetime, timezone, timedelta
    phone = normalize_phone(phone)
    now = datetime.now(timezone.utc)
    # First followup: 3 hours from now
    next_followup = (now + timedelta(hours=3)).isoformat()
    update_lead(phone, link_sent_at=now.isoformat(), link_course_name=course_name,
                followup_count=0, last_followup_at=None, status="קיבלה קישור",
                next_followup=next_followup)
    log_lead_event(phone, "link_sent", {"course": course_name})


def increment_followup(phone: str) -> None:
    """Increment followup count after sending a follow-up message."""
    from datetime import datetime, timezone, timedelta
    phone = normalize_phone(phone)
    lead = get_lead(phone)
    if lead:
        count = (lead.get("followup_count") or 0) + 1
        now = datetime.now(timezone.utc)
        # Schedule next followup based on count
        if count == 1:
            # After 3h message → next at 23h from link sent
            next_fu = (now + timedelta(hours=20)).isoformat()
        elif count == 2:
            # After 23h message → next alert to Merav at 3 days
            next_fu = (now + timedelta(days=2)).isoformat()
        else:
            next_fu = None  # No more scheduled followups
        update_lead(phone, followup_count=count, last_followup_at=now.isoformat(),
                    next_followup=next_fu)


def update_lead_score(phone: str, points: int) -> None:
    """Add points to lead score."""
    phone = normalize_phone(phone)
    lead = get_lead(phone)
    if lead:
        new_score = (lead.get("lead_score") or 0) + points
        update_lead(phone, lead_score=new_score)


def get_coupon_code() -> str:
    """Get the active coupon code from content_sections, or empty string."""
    section = get_section("sec_coupon_code")
    if section:
        return (section.get("body") or "").strip()
    return ""


def register_manual_purchase(phone: str, course_name: str, amount: float,
                              payment_method: str, course_id: int = None,
                              notes: str = "") -> int:
    """Register a manual purchase (not via Cardcom) and update lead status."""
    phone = normalize_phone(phone)
    pid = create_purchase(phone, course_name, amount, course_id, payment_method, notes)
    update_lead(phone, status="נרשמה", followup_stopped=True)
    log_lead_event(phone, "purchase", {"course": course_name, "amount": amount, "method": payment_method})
    return pid


# ── Questionnaire Seed ────────────────────────────────────────────

_GUIDE_QUESTIONS = [
    # (key, title/question, group, storage_type, sort_order)
    # storage_type: "rule" → rules table, "section" → content_sections table
    ("guide_tone", "האם הטון של שרי מתאים? יותר מדי רשמי? יותר מדי חברי? תני דוגמה לתשובה שלא בדיוק בטון שלך.", "טון ושפה", "rule", 1),
    ("guide_response_length", "האם אורך התשובות נכון? ארוכות מדי? קצרות מדי? מה האורך האידיאלי?", "טון ושפה", "rule", 2),
    ("guide_expressions_use", "יש ביטויים או מילים שאת משתמשת בהם הרבה עם לקוחות ושהבוט צריך להשתמש?", "טון ושפה", "rule", 3),
    ("guide_expressions_avoid", "יש ביטויים שהבוט לא צריך להשתמש בהם? שאת לא הייתה אומרת ככה?", "טון ושפה", "rule", 4),
    ("guide_corrections", "האם יש מידע שהבוט אמר שהוא לא מדויק? מה צריך לתקן?", "תוכן וידע", "section", 5),
    ("guide_top_questions", "מהן 5 השאלות שלקוחות שואלות הכי הרבה? כתבי את השאלה ואת התשובה המדויקת.", "תוכן וידע", "section", 6),
    ("guide_missing_topics", "יש נושאים שהבוט לא יודע עליהם ושלקוחות שואלות? (למשל: הכשרת מדריכות, ליווי אישי)", "תוכן וידע", "section", 7),
    ("guide_objections", "מהן 3 ההתנגדויות הנפוצות? ואיך את עונה עליהן? (למשל: 'יקר לי', 'אין לי זמן')", "תוכן וידע", "section", 8),
    ("guide_funnel_goal", "מה המטרה העיקרית של הבוט? שלקוחה תירשם לקורס? תשאיר פרטים? תתקשר? תיכנס לשיעור חינמי?", "משפך שיווקי", "rule", 9),
    ("guide_special_offer", "האם יש הצעה מיוחדת ללקוחות חדשות? (שיעור טעימה, מדריך חינמי, הנחה?)", "משפך שיווקי", "section", 10),
    ("guide_offer_timing", "באיזה שלב בשיחה הבוט צריך להציע קורס? מיד? רק אחרי ששאלה? אחרי שהבין את הבעיה?", "משפך שיווקי", "rule", 11),
    ("guide_course_selection", "כשלקוחה מתלבטת בין קורסים — מה הקריטריון שעוזר להחליט? (גיל, בעיה, שלב בחיים?)", "משפך שיווקי", "section", 12),
    ("guide_handoff_conditions", "באילו מצבים את רוצה שהבוט יעביר אלייך במקום לענות? (ליווי אישי, תלונה, שאלה רפואית?)", "העברה לנציג", "rule", 13),
    ("guide_handoff_message", "מה הבוט צריך לומר ללקוחה כשהוא מעביר אלייך? ומה לא לומר?", "העברה לנציג", "rule", 14),
    ("guide_positive_feedback", "מה הדבר הכי טוב שראית בתשובות הבוט? מה הפתיע אותך לטובה?", "כללי", "rule", 15),
    ("guide_urgent_fix", "מה הדבר הכי בעייתי שראית? מה הכי דחוף לתקן?", "כללי", "rule", 16),
    ("guide_success_stories", "יש סיפורי הצלחה קצרים של לקוחות שהבוט יכול לשתף? (בלי שמות)", "כללי", "section", 17),
    ("guide_seasonal", "יש תקופות בשנה שבהן יש מבצעים, קורסים חדשים, או שינויים שהבוט צריך לדעת?", "כללי", "section", 18),
]


def seed_questionnaire() -> None:
    """Seed the 18 guide questions into existing tables (idempotent)."""
    all_rules = get_all_rules()
    all_sections = get_all_sections()
    rule_keys = {r["rule_key"] for r in all_rules}
    section_keys = {s["section_key"] for s in all_sections}
    for key, title, group, storage, order in _GUIDE_QUESTIONS:
        if storage == "rule" and key not in rule_keys:
            upsert_rule(key, title, "", is_active=True)
        elif storage == "section" and key not in section_keys:
            upsert_section(key, title, "")
