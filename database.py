"""Supabase storage via REST API — conversations + admin content management."""

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


def init_db() -> None:
    """Verify Supabase connection."""
    r = httpx.get(_url("courses"), headers=_get_headers(), params={"select": "id", "limit": "1"})
    r.raise_for_status()


# ── Conversations ─────────────────────────────────────────────────

def append(chat_id: str, role: str, content: str) -> None:
    httpx.post(_url("conversations"), headers=_get_headers(), json={
        "chat_id": chat_id, "role": role, "content": content, "created_at": _now(),
    }).raise_for_status()


def tail(chat_id: str, n: int = 20) -> list[dict]:
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
    httpx.post(_url("content_sections"), headers=headers, json={
        "section_key": section_key, "title": title, "body": body, "updated_at": _now(),
    }).raise_for_status()


# ── Rules CRUD ─────────────────────────────────────────────────────

def get_all_rules() -> list[dict]:
    r = httpx.get(_url("rules"), headers=_get_headers(), params={
        "select": "*", "order": "id",
    })
    r.raise_for_status()
    return r.json()


def upsert_rule(rule_key: str, title: str, body: str, is_active: bool = True) -> None:
    headers = {**_get_headers(), "Prefer": "resolution=merge-duplicates,return=representation"}
    httpx.post(_url("rules"), headers=headers, json={
        "rule_key": rule_key, "title": title, "body": body, "is_active": is_active, "updated_at": _now(),
    }).raise_for_status()


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
