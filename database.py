"""Supabase storage — conversations + admin content management."""

from datetime import datetime, timezone

from supabase import create_client

from config import SUPABASE_URL, SUPABASE_KEY

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """No-op — tables are managed in Supabase."""
    _get_client()


# ── Conversations ─────────────────────────────────────────────────

def append(chat_id: str, role: str, content: str) -> None:
    _get_client().table("conversations").insert({
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "created_at": _now(),
    }).execute()


def tail(chat_id: str, n: int = 20) -> list[dict]:
    result = (_get_client().table("conversations")
              .select("role, content")
              .eq("chat_id", chat_id)
              .order("id", desc=True)
              .limit(n)
              .execute())
    rows = result.data or []
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ── Message dedup ─────────────────────────────────────────────────

def is_seen(message_id: str) -> bool:
    result = (_get_client().table("seen_messages")
              .select("message_id")
              .eq("message_id", message_id)
              .limit(1)
              .execute())
    return len(result.data or []) > 0


def mark_seen(message_id: str) -> None:
    (_get_client().table("seen_messages")
     .upsert({"message_id": message_id, "created_at": _now()})
     .execute())


# ── FAQ CRUD ───────────────────────────────────────────────────────

def get_all_faq() -> list[dict]:
    result = (_get_client().table("faq")
              .select("*")
              .order("sort_order")
              .order("id")
              .execute())
    return result.data or []


def upsert_faq(faq_id: int | None, question: str, answer: str, sort_order: int = 0) -> int:
    now = _now()
    if faq_id:
        (_get_client().table("faq")
         .update({"question": question, "answer": answer, "sort_order": sort_order, "updated_at": now})
         .eq("id", faq_id)
         .execute())
        return faq_id
    else:
        result = (_get_client().table("faq")
                  .insert({"question": question, "answer": answer, "sort_order": sort_order, "updated_at": now})
                  .execute())
        return result.data[0]["id"]


def delete_faq(faq_id: int) -> None:
    _get_client().table("faq").delete().eq("id", faq_id).execute()


# ── Courses CRUD ───────────────────────────────────────────────────

def get_all_courses() -> list[dict]:
    result = (_get_client().table("courses")
              .select("*")
              .order("sort_order")
              .order("id")
              .execute())
    return result.data or []


def upsert_course(course_id: int | None, **fields) -> int:
    now = _now()
    fields["updated_at"] = now
    if course_id:
        (_get_client().table("courses")
         .update(fields)
         .eq("id", course_id)
         .execute())
        return course_id
    else:
        result = (_get_client().table("courses")
                  .insert(fields)
                  .execute())
        return result.data[0]["id"]


def delete_course(course_id: int) -> None:
    _get_client().table("courses").delete().eq("id", course_id).execute()


# ── Content Sections CRUD ─────────────────────────────────────────

def get_all_sections() -> list[dict]:
    result = (_get_client().table("content_sections")
              .select("*")
              .order("id")
              .execute())
    return result.data or []


def get_section(section_key: str) -> dict | None:
    result = (_get_client().table("content_sections")
              .select("*")
              .eq("section_key", section_key)
              .limit(1)
              .execute())
    rows = result.data or []
    return rows[0] if rows else None


def upsert_section(section_key: str, title: str, body: str) -> None:
    now = _now()
    (_get_client().table("content_sections")
     .upsert({"section_key": section_key, "title": title, "body": body, "updated_at": now},
             on_conflict="section_key")
     .execute())


# ── Rules CRUD ─────────────────────────────────────────────────────

def get_all_rules() -> list[dict]:
    result = (_get_client().table("rules")
              .select("*")
              .order("id")
              .execute())
    return result.data or []


def upsert_rule(rule_key: str, title: str, body: str, is_active: bool = True) -> None:
    now = _now()
    (_get_client().table("rules")
     .upsert({"rule_key": rule_key, "title": title, "body": body, "is_active": is_active, "updated_at": now},
             on_conflict="rule_key")
     .execute())


# ── Build knowledge base from DB ──────────────────────────────────

def build_knowledge_base() -> str:
    """Build the full knowledge base text from DB content."""
    parts = []

    for s in get_all_sections():
        parts.append(f"## {s['title']}\n\n{s['body']}")

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
    rules = [r for r in get_all_rules() if r.get("is_active")]
    if not rules:
        return ""
    lines = []
    for i, r in enumerate(rules, 1):
        lines.append(f"{i}. **{r['title']}:** {r['body']}")
    return "\n".join(lines)
