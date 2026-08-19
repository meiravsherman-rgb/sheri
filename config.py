"""Configuration loader — reads .env and spec.json."""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# ── Meta WhatsApp API ──────────────────────────────────────────────
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

# ── LLM ────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Supabase ───────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))

# ── Manager ────────────────────────────────────────────────────────
MANAGER_PHONE = os.getenv("MANAGER_PHONE", "972503189636")
MANAGER_NAME = os.getenv("MANAGER_NAME", "מירב שרמן")

# ── Spec ───────────────────────────────────────────────────────────
_spec_path = BASE_DIR / "spec.json"
if _spec_path.exists():
    with open(_spec_path, encoding="utf-8") as f:
        SPEC = json.load(f)
else:
    print("ERROR: spec.json not found. Run wa-characterize first.")
    sys.exit(1)

# ── Knowledge base ─────────────────────────────────────────────────
_kb_path = BASE_DIR / "knowledge-base.md"
if _kb_path.exists():
    with open(_kb_path, encoding="utf-8") as f:
        KNOWLEDGE_BASE = f.read()
else:
    KNOWLEDGE_BASE = ""

# ── Validate required vars ─────────────────────────────────────────
_required = {
    "WHATSAPP_ACCESS_TOKEN": WHATSAPP_ACCESS_TOKEN,
    "WHATSAPP_PHONE_NUMBER_ID": WHATSAPP_PHONE_NUMBER_ID,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    print(f"ERROR: Missing required env vars: {', '.join(_missing)}")
    print("Check your .env file.")
    sys.exit(1)
