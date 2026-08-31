"""Auto-tagging tool — tags leads based on course interest during conversation."""

from database import add_tag_to_lead, auto_create_tag_setting
from tools import TOOL_REGISTRY


def tag_lead(chat_id: str, tag: str) -> str:
    """Tag a lead with a course interest or topic.

    Args:
        chat_id: Customer phone (filled by framework)
        tag: Tag name, e.g. "מדריכות", "יסודות שיטת שרמן"
    """
    tag = tag.strip()
    if not tag:
        return "שגיאה: שם תג ריק"
    try:
        auto_create_tag_setting(tag)
        add_tag_to_lead(chat_id, tag)
        return f"הלקוחה תויגה: {tag}"
    except Exception as e:
        return f"שגיאה בתיוג: {e}"


TOOL_REGISTRY["tag_lead"] = {
    "schema": {
        "description": "תייגי את הלקוחה כשהיא מתעניינת בקורס או נושא ספציפי. אפשר לתייג מספר תגים.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "מספר הטלפון של הלקוחה (מוזרק אוטומטית)"},
                "tag": {"type": "string", "description": "שם התג, לדוגמה: מדריכות, יסודות, הקלה בכאבים"}
            },
            "required": ["chat_id", "tag"],
        },
    },
    "fn": tag_lead,
}
