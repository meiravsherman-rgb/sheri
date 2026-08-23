# CLAUDE.md — Sherman Bot (שרי הבוטית)

## Language
Respond in Hebrew (עברית).

## Project
WhatsApp AI bot for Merav Sherman — שיטת שרמן, בריאות נשית טבעית.
FastAPI + Claude Sonnet 4.6 + Supabase + Render.

## Deploy Flow (MANDATORY after every change)
After ANY code change, always do all 3 steps:
```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeFolder/sherman-bot"
git add <changed-files> && git commit -m "..." && git push origin main
```
Then trigger Render deploy:
```bash
curl -s -X POST "https://api.render.com/v1/services/srv-d9nkll0ae00c739unv9g/deploys" \
  -H "Authorization: Bearer rnd_1rN8woUts7GDBXhHxghDfx9XA8J5" \
  -H "Content-Type: application/json" -d '{}'
```
Check status:
```bash
curl -s "https://api.render.com/v1/services/srv-d9nkll0ae00c739unv9g/deploys/{DEPLOY_ID}" \
  -H "Authorization: Bearer rnd_1rN8woUts7GDBXhHxghDfx9XA8J5" | python -c "import sys,json;print(json.load(sys.stdin).get('status',''))"
```
Live URL: https://sheri-bot.onrender.com

## Testing
- Always test locally BEFORE deploying when possible: `cd sherman-bot && python -c "from database import ..."`
- After deploy, verify with: `curl -s https://sheri-bot.onrender.com/health`
- For CRM changes, test with: `curl -s -b "admin_token=sheri2024" https://sheri-bot.onrender.com/crm/api/dashboard`

## Communication Guidelines
When the user's prompt is vague or could lead to rework, ASK for clarification before implementing. Examples:
- "תוסיף פיצ'ר X" → ask: "יש פרטים נוספים? למשל: [concrete options]"
- If a feature has both manual and auto aspects → ask upfront instead of implementing one and then the other
- Group related changes into one commit+deploy cycle

## Key Architecture Rules
- Database: Supabase REST API via httpx (NOT supabase-py — crashes on Render free tier)
- DDL (CREATE/ALTER TABLE): use psycopg2 directly against Postgres pooler
- CRM settings (statuses, tags, sources): stored in `crm_settings` table, not hardcoded
- Admin/CRM UI: embedded HTML in Python files (admin.py, crm.py), NOT separate React app
- Auth: cookie-based (`admin_token=sheri2024`)
- **Behavioral prompt**: hardcoded in `prompt.py` (BEHAVIORAL_PROMPT constant) — approved by Merav, NOT editable via admin
- **Admin panel**: business content only (courses, FAQ, content sections, docs, coupon) — no behavioral rules/notes/questionnaire
- **CRM**: redesigned with sidebar nav, green/gold palette, drawer panel for lead details, mobile tab bar
- **Knowledge base filter**: `note_*`, `guide_*`, `sec_coupon_*` prefixed sections excluded from bot prompt

## Supabase Connection (for DDL)
```python
psycopg2.connect(
    host='aws-0-eu-central-1.pooler.supabase.com', port=6543,
    dbname='postgres', user='postgres.widuuwkywkwbvvaywguc',
    password='XO0VQEWR0pVM3j0d', sslmode='require'
)
```

## Git
- Repo: `meiravsherman-rgb/sheri` on GitHub
- Always commit with `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Commit messages in English, concise
