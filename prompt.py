"""System prompt generator — builds the bot's personality from spec.json + DB content."""

from config import SPEC, KNOWLEDGE_BASE
from database import build_knowledge_base, build_rules_text, get_all_sections

# ── In-memory prompt cache ────────────────────────────────────────
_prompt_cache: str | None = None


def invalidate_cache():
    """Call after any admin save to force prompt rebuild on next message."""
    global _prompt_cache
    _prompt_cache = None


def _dynamic_knowledge() -> str:
    """Build knowledge base from DB. Falls back to static file if DB is empty."""
    try:
        kb = build_knowledge_base()
        if kb:
            return kb
    except Exception:
        pass
    return KNOWLEDGE_BASE


def _dynamic_rules() -> str:
    """Build rules from DB. Falls back to spec.json if DB is empty."""
    try:
        rules = build_rules_text()
        if rules:
            return rules
    except Exception:
        pass
    # Fallback to spec.json
    spec_rules = SPEC.get("behavioral_rules", {})
    lines = []
    for i, (key, body) in enumerate(spec_rules.items(), 1):
        lines.append(f"{i}. {body}")
    return "\n".join(lines)


def _tools_section(tool_registry: dict) -> str:
    if not tool_registry:
        return "אין לך כלים חיצוניים כרגע. ענה מהידע שלך בלבד."
    lines = ["יש לך הכלים הבאים. השתמשי בהם כשצריך:"]
    for name, td in tool_registry.items():
        desc = td["schema"].get("description", "")
        lines.append(f"- `{name}`: {desc}")
    return "\n".join(lines)


def build_system_prompt(tool_registry: dict) -> str:
    global _prompt_cache
    if _prompt_cache is not None:
        return _prompt_cache
    _prompt_cache = _build_fresh(tool_registry)
    return _prompt_cache


def _build_fresh(tool_registry: dict) -> str:
    identity = SPEC["identity"]
    scope = SPEC["scope"]
    handoff = SPEC.get("handoff", {})
    rules = SPEC.get("behavioral_rules", {})
    extras = SPEC.get("extras", {})

    prompt = f"""את שֶרי הבוטית — הבוטית האישית של שיטת שרמן, בריאות נשית טבעית.

## הזהות שלך
- שמך: {identity['name']}
- את נקבה, תמיד מדברת בלשון נקבה על עצמך
- הסגנון שלך: {identity['tone_description']}
- {identity.get('name_transliteration', '')}
- אמוג'ים: שימוש עדין בלבד — 🌸💕🙂

## דוגמה לברכת פתיחה (ללקוחה חדשה בלבד)
{identity['greeting_example']}

## שפה
- ענייני בשפה שבה הלקוחה כותבת (עברית/אנגלית)
- אורך תשובה: בינוני — לא קצר מדי, לא ארוך מדי
- שפה לא מוחלטת: השתמשי ב'מקווה', 'רוצה', 'אשמח', 'ייתכן' — הימנעי מ'בטוח', 'מובטח', 'תמיד'

## תחומי מענה (in scope)
{chr(10).join('- ' + s for s in scope['in_scope'])}

## מחוץ לתחום (out of scope)
{chr(10).join('- ' + s for s in scope['out_of_scope'])}
כשמישהי שואלת על נושא מחוץ לתחום: {scope['out_of_scope_response']}

## כללי התנהגות חשובים

{_dynamic_rules()}

## העברה למירב (human handoff)
העבירי את השיחה למירב במקרים הבאים:
{chr(10).join('- ' + c for c in handoff.get('trigger_conditions', []))}

כשמעבירה — השתמשי בכלי `request_human_handoff` עם סיכום קצר של השיחה וסיבת ההפניה.
**חשוב:** לעולם לא להמציא תשובות. אם אין לך מידע במאגר הידע — העבירי למירב.

## מאגר ידע

{_dynamic_knowledge()}

## כלים
{_tools_section(tool_registry)}
"""
    return prompt
