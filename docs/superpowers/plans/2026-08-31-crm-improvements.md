# CRM Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 CRM issues — 3 bug fixes, 3 new features, 1 enhancement — for Sherman Bot's CRM panel.

**Architecture:** All changes are in the existing FastAPI monolith. Backend changes in `database.py` and `crm.py` (API routes). Frontend changes in `crm.py` (embedded HTML/JS). One new tool file `tools/tagging.py`. No new dependencies.

**Tech Stack:** Python 3.12, FastAPI, Supabase REST API (httpx), Meta Cloud API, Claude Sonnet 4.6, embedded HTML/CSS/JS.

## Global Constraints

- Database access: httpx REST API only (no supabase-py SDK)
- UI: embedded HTML in Python files (no separate React app)
- Auth: cookie-based (`admin_token=sheri2024`)
- Phone format: `972...` in DB, `05...` in UI (normalize_phone / display_phone)
- Git: commit with `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Deploy: git push → trigger Render deploy via API
- Language: Hebrew RTL, Heebo font
- CRM file: `crm.py` — single file with APIRouter + embedded HTML (~1285 lines)

## IMPORTANT: Read before each task

Before touching any code, the implementing agent MUST read:
- `C:\Users\rafie\.claude\projects\c--Users-rafie-OneDrive--------ClaudeCodeClients\memory\project_sherman_bot.md`
- `c:\Users\rafie\OneDrive\מסמכים\ClaudeCodeClients\sherman-bot\CLAUDE.md`

---

### Task 1: Fix phone search + remove duplicate search field (Bug Fix)

**Files:**
- Modify: `database.py` — `get_leads()` function (line 320-330)
- Modify: `crm.py` — remove global search from topbar (line 530-533), update `loadLeads()` (line 902-908)

**Interfaces:**
- Modifies: `get_leads(status, search, tag)` — adds phone normalization to search parameter
- No new interfaces

- [ ] **Step 1: Fix phone normalization in `get_leads()`**

In `database.py`, modify `get_leads()` at line 320-330. Change the search handling to normalize phone numbers:

```python
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
```

- [ ] **Step 2: Remove duplicate global search from topbar**

In `crm.py`, find the topbar search div (around line 530-533):

```html
    <div class="search">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input type="text" id="globalSearch" placeholder="חיפוש..." oninput="if(currentTab==='leads')loadLeads()">
    </div>
```

Replace with empty div (keep the topbar structure):

```html
    <div class="search"></div>
```

- [ ] **Step 3: Remove globalSearch reference from loadLeads()**

In `crm.py`, find `loadLeads()` (around line 902-905):

```javascript
async function loadLeads() {
  const globalVal = document.getElementById('globalSearch')?.value||'';
  const localVal = document.getElementById('searchInput')?.value||'';
  const search = localVal || globalVal;
```

Replace with:

```javascript
async function loadLeads() {
  const search = document.getElementById('searchInput')?.value||'';
```

- [ ] **Step 4: Test locally**

Run: `python -c "from database import get_leads, normalize_phone; print(get_leads(search='0508806087'))"`

Expected: returns leads with phone matching `9728806087`

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add database.py crm.py
git commit -m "$(cat <<'EOF'
fix: normalize phone in search + remove duplicate search field

Phone numbers starting with 05 are now converted to 972 format
for DB matching. Removed duplicate global search input from topbar.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add "לקוחה" status to filter (Bug Fix)

**Files:**
- Modify: `crm.py` — `api_get_settings()` endpoint (line 207-209)
- Modify: `database.py` — `get_crm_settings()` (line 490-506)

**Interfaces:**
- Modifies: `get_crm_settings()` return value — merges distinct statuses from leads into settings
- No new interfaces

- [ ] **Step 1: Add status merging to settings API**

In `crm.py`, modify `api_get_settings()` at line 207-209 to merge distinct lead statuses into settings:

```python
@router.get("/api/settings", dependencies=[Depends(check_auth)])
async def api_get_settings():
    s = get_crm_settings()
    # Merge any lead statuses not in settings (e.g. "לקוחה" set by Cardcom webhook)
    existing_keys = {st.get("key") for st in (s.get("statuses") or [])}
    distinct_statuses = _get_distinct_lead_statuses()
    for status_key in distinct_statuses:
        if status_key and status_key not in existing_keys:
            s.setdefault("statuses", []).append({
                "key": status_key, "label": status_key,
                "color": "#95a5a6", "order": len(s.get("statuses", [])) + 1
            })
    return s
```

- [ ] **Step 2: Add helper function for distinct statuses**

In `crm.py`, add above the `api_get_settings` route (around line 206):

```python
def _get_distinct_lead_statuses() -> set[str]:
    """Get all distinct status values from leads table."""
    leads = get_leads()
    return {l.get("status") for l in leads if l.get("status")}
```

- [ ] **Step 3: Test**

Verify by visiting `/crm/api/settings` — the statuses array should include "לקוחה" if any lead has that status.

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add crm.py
git commit -m "$(cat <<'EOF'
fix: merge distinct lead statuses into CRM filter

Statuses like "לקוחה" set by Cardcom webhook now appear in the
status filter dropdown even if not manually added in settings.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Fix purchases in lead drawer (Bug Fix)

**Files:**
- Modify: `database.py` — `create_purchase()` (line 397-416)
- Modify: `crm.py` — `openLead()` JS function (line 966)

**Interfaces:**
- Modifies: `create_purchase()` — ensures `lead_phone` is normalized before saving
- No new interfaces

- [ ] **Step 1: Ensure phone normalization in create_purchase()**

In `database.py`, `create_purchase()` at line 397-399 — the `lead_phone` parameter is NOT normalized before saving. Add normalization:

```python
def create_purchase(lead_phone: str, course_name: str, amount: float,
                    course_id: int = None, payment_method: str = "cardcom",
                    notes: str = "") -> int:
    lead_phone = normalize_phone(lead_phone)
    now = _now()
```

- [ ] **Step 2: Ensure drawer sends normalized phone to purchases API**

In `crm.py`, check `openLead()` at line 966. The drawer fetches purchases with:

```javascript
apiFetch(`/purchases?lead_phone=${phone}`)
```

The `phone` here comes from the lead's `phone` field which is already in display format (05...) from `api_lead_detail`. The API endpoint `api_all_purchases` does NOT normalize the filter parameter. Fix this in `crm.py` API:

In `crm.py` at line 169-174, modify `api_all_purchases`:

```python
@router.get("/api/purchases", dependencies=[Depends(check_auth)])
async def api_all_purchases(lead_phone: str = ""):
    from database import normalize_phone
    phone_filter = normalize_phone(lead_phone) if lead_phone else ""
    purchases = get_purchases(phone_filter)
    for p in purchases:
        p["lead_phone"] = display_phone(p.get("lead_phone", ""))
    return purchases
```

- [ ] **Step 3: Test**

Verify that opening a lead's drawer shows their purchases in the "רכישות" tab.

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add database.py crm.py
git commit -m "$(cat <<'EOF'
fix: normalize phone in purchases for drawer display

Ensure create_purchase normalizes phone before saving, and the
purchases API normalizes the filter parameter for consistent matching.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add customer name to purchases table (Enhancement)

**Files:**
- Modify: `crm.py` — `api_all_purchases()` (line 169-174), `loadPurchases()` JS (line 1151-1167)
- Modify: `database.py` — `get_purchases()` (line 419-425)

**Interfaces:**
- Modifies: `get_purchases()` return — enriches each purchase with `lead_name` field
- No new interfaces

- [ ] **Step 1: Enrich purchases with lead names in database.py**

In `database.py`, modify `get_purchases()` at line 419-425:

```python
def get_purchases(lead_phone: str = "") -> list[dict]:
    params = {"select": "*", "order": "purchased_at.desc"}
    if lead_phone:
        params["lead_phone"] = f"eq.{lead_phone}"
    r = httpx.get(_url("purchases"), headers=_get_headers(), params=params)
    r.raise_for_status()
    purchases = r.json()
    # Enrich with lead names
    phones = list({p.get("lead_phone", "") for p in purchases if p.get("lead_phone")})
    if phones:
        leads_r = httpx.get(_url("leads"), headers=_get_headers(), params={
            "select": "phone,name",
            "phone": f"in.({','.join(phones)})",
        })
        leads_r.raise_for_status()
        name_map = {l["phone"]: l.get("name", "") for l in leads_r.json()}
        for p in purchases:
            p["lead_name"] = name_map.get(p.get("lead_phone", ""), "")
    return purchases
```

- [ ] **Step 2: Add name column to purchases table in JS**

In `crm.py`, modify `loadPurchases()` at line 1155-1166. Change the table header and rows:

```javascript
async function loadPurchases() {
  const purchases = await apiFetch('/purchases');
  if(!purchases) return;
  const total = purchases.reduce((s,p)=>s+Number(p.amount),0);
  document.getElementById('purchasesTable').innerHTML = purchases.length ? `
    <div style="padding:14px 16px;font-weight:800;font-size:15px;border-bottom:1px solid var(--border)">סה"כ: ${total.toLocaleString()}₪ <span style="color:var(--muted);font-weight:500;font-size:13px">(${purchases.length} רכישות)</span></div>
    <table>
    <tr><th>שם</th><th>טלפון</th><th>קורס</th><th>סכום</th><th>תאריך</th><th>אמצעי</th></tr>
    ${purchases.map(p=>`<tr>
      <td style="cursor:pointer;color:var(--green-dark);font-weight:600" onclick="openLead('${escapeHtml(p.lead_phone)}')">${escapeHtml(p.lead_name||'—')}</td>
      <td dir="ltr" style="cursor:pointer" onclick="openLead('${escapeHtml(p.lead_phone)}')">${escapeHtml(p.lead_phone)}</td>
      <td>${escapeHtml(p.course_name)}</td>
      <td style="font-weight:600;color:var(--green)">${p.amount}₪</td>
      <td>${fmtShortDate(p.purchased_at)}</td>
      <td>${escapeHtml(p.payment_method)}</td>
    </tr>`).join('')}
  </table>` : '<div class="empty-state"><div class="icon">🛒</div><p>אין רכישות עדיין</p></div>';
}
```

- [ ] **Step 3: Test**

Visit CRM → Purchases tab. Verify name column appears with clickable names.

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add database.py crm.py
git commit -m "$(cat <<'EOF'
feat: add customer name column to purchases table

Purchases are now enriched with lead names from the leads table.
Name column is clickable and opens the lead's drawer.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Auto-tagging leads by course interest (Feature)

**Files:**
- Create: `tools/tagging.py` — new tool for the Claude agent
- Modify: `agent.py` — add `tag_lead` to `FRAMEWORK_INJECTED_CHAT_ID` (line 15-23)
- Modify: `main.py` — import `tools.tagging` in lifespan (line 67)
- Modify: `prompt.py` — add tagging instructions to `BEHAVIORAL_PROMPT` (line 289)
- Modify: `database.py` — add `add_tag_to_lead()` function

**Interfaces:**
- Produces: `tag_lead(chat_id, tag)` tool — registered in `TOOL_REGISTRY`
- Produces: `add_tag_to_lead(phone, tag)` in database.py
- Consumed by: Claude agent via tool calling

- [ ] **Step 1: Add `add_tag_to_lead()` to database.py**

In `database.py`, add after `update_lead()` (around line 347):

```python
def add_tag_to_lead(phone: str, tag: str) -> None:
    """Add a tag to a lead's tags array if not already present."""
    phone = normalize_phone(phone)
    lead = get_lead(phone)
    if not lead:
        return
    tags = lead.get("tags") or []
    if tag not in tags:
        tags.append(tag)
        update_lead(phone, tags=tags)
```

- [ ] **Step 2: Add `auto_create_tag_setting()` to database.py**

In `database.py`, add after `add_tag_to_lead()`:

```python
def auto_create_tag_setting(tag: str) -> None:
    """Ensure a tag exists in CRM settings. Creates it with default color if missing."""
    settings = get_crm_settings()
    existing_tags = settings.get("tags") or []
    if any(t.get("key") == tag for t in existing_tags):
        return
    existing_tags.append({"key": tag, "color": "#95a5a6"})
    update_crm_setting("tags", existing_tags)
```

- [ ] **Step 3: Create `tools/tagging.py`**

Create the file `tools/tagging.py`:

```python
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
```

- [ ] **Step 4: Register tool in agent.py**

In `agent.py`, add `"tag_lead"` to `FRAMEWORK_INJECTED_CHAT_ID` at line 15-23:

```python
FRAMEWORK_INJECTED_CHAT_ID = {
    "schedule_reminder",
    "list_reminders",
    "cancel_reminder",
    "request_human_handoff",
    "set_marketing_opt_in",
    "track_link_sent",
    "update_lead_score",
    "tag_lead",
}
```

- [ ] **Step 5: Import tool in main.py lifespan**

In `main.py`, add after `import tools.marketing  # noqa: F401` (line 68):

```python
    import tools.tagging  # noqa: F401
```

- [ ] **Step 6: Add tagging instructions to prompt.py**

In `prompt.py`, add before the closing `"""` of `BEHAVIORAL_PROMPT` (line 289), just before the last line:

```python
## תיוג אוטומטי
כשלקוחה מתעניינת בקורס או בנושא ספציפי — השתמשי בכלי tag_lead כדי לתייג אותה.
דוגמאות:
- שואלת על קורס מדריכות → תייגי "מדריכות"
- מתעניינת ביסודות שיטת שרמן → תייגי "יסודות"
- שואלת על הקלה בכאבים → תייגי "הקלה בכאבים"
- מתעניינת במודעות לפוריות → תייגי "מודעות לפוריות"
אפשר לתייג מספר תגים אם מתעניינת במספר קורסים."""
```

- [ ] **Step 7: Test locally**

```bash
python -c "
from database import add_tag_to_lead, auto_create_tag_setting, get_lead
print('Testing add_tag...')
# Only test if a test lead exists
"
```

- [ ] **Step 8: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add tools/tagging.py agent.py main.py prompt.py database.py
git commit -m "$(cat <<'EOF'
feat: auto-tag leads by course interest via Claude tool

New tag_lead tool lets Claude auto-tag leads during conversation
when they show interest in specific courses. Tags are auto-created
in CRM settings if they don't exist.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Dashboard Highlights section (Feature)

**Files:**
- Modify: `database.py` — add `get_highlights()` function, add `new_lead` event logging
- Modify: `crm.py` — add API route + dashboard HTML + JS for highlights

**Interfaces:**
- Produces: `get_highlights()` in database.py — returns recent events
- Produces: `GET /crm/api/highlights` endpoint
- Modifies: `upsert_lead_from_message()` — adds `new_lead` event logging for truly new leads

- [ ] **Step 1: Add `new_lead` event logging in `upsert_lead_from_message()`**

In `database.py`, modify `upsert_lead_from_message()` at line 304-317. Add event logging when a new lead is created:

```python
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
        # Log new lead event for highlights
        try:
            log_lead_event(phone, "new_lead", {"name": name or "", "source": source or ""})
        except Exception:
            pass
```

- [ ] **Step 2: Add `get_highlights()` to database.py**

In `database.py`, add after `get_dashboard_stats()` (around line 486):

```python
def get_highlights() -> list[dict]:
    """Get recent important events for dashboard highlights.

    Returns events from last 3 days OR last 10, whichever is more.
    Event types: purchase, new_lead, handoff.
    """
    from datetime import timedelta
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

    # Fetch last 3 days
    r = httpx.get(_url("lead_events"), headers=_get_headers(), params={
        "select": "*",
        "event_type": "in.(purchase,new_lead,handoff)",
        "created_at": f"gte.{three_days_ago}",
        "order": "created_at.desc",
    })
    r.raise_for_status()
    events = r.json()

    # If less than 10, fetch more
    if len(events) < 10:
        r2 = httpx.get(_url("lead_events"), headers=_get_headers(), params={
            "select": "*",
            "event_type": "in.(purchase,new_lead,handoff)",
            "order": "created_at.desc",
            "limit": "10",
        })
        r2.raise_for_status()
        events = r2.json()

    # Enrich with lead names
    phones = list({e.get("lead_phone", "") for e in events if e.get("lead_phone")})
    name_map = {}
    if phones:
        lr = httpx.get(_url("leads"), headers=_get_headers(), params={
            "select": "phone,name",
            "phone": f"in.({','.join(phones)})",
        })
        lr.raise_for_status()
        name_map = {l["phone"]: l.get("name", "") for l in lr.json()}

    for e in events:
        e["lead_name"] = name_map.get(e.get("lead_phone", ""), "")
        e["lead_phone_display"] = display_phone(e.get("lead_phone", ""))

    return events
```

- [ ] **Step 3: Add highlights API route in crm.py**

In `crm.py`, add after `api_get_settings()` (around line 215):

```python
@router.get("/api/highlights", dependencies=[Depends(check_auth)])
async def api_highlights():
    from database import get_highlights
    return get_highlights()
```

- [ ] **Step 4: Add highlights HTML section to dashboard**

In `crm.py`, find the dashboard tab HTML (around line 537-547). Add a new row after the existing rows:

Find:
```html
    <div class="row r-2">
      <div class="panel"><div class="panel-h"><h3>פולואפים קרובים</h3></div><div id="followupsList"></div></div>
      <div class="panel"><div class="panel-h"><h3>דורשות תשומת לב</h3></div><div id="attentionList"></div></div>
    </div>
```

Add after it:
```html
    <div class="row r-1">
      <div class="panel"><div class="panel-h"><h3>פעולות אחרונות</h3></div><div id="highlightsList"></div></div>
    </div>
```

Also add CSS for `.r-1` — find the `.row.r-2` CSS rule and add `.r-1`:

In the `<style>` section, find where `.row` is defined and add:
```css
.row.r-1 { display: grid; grid-template-columns: 1fr; gap: 20px; margin-top: 20px; }
```

- [ ] **Step 5: Add highlights rendering JS to loadDashboard()**

In `crm.py`, at the end of `loadDashboard()` function (around line 889, after the "needs attention" block), add:

```javascript
  // Highlights
  const highlights = await apiFetch('/highlights');
  if (highlights) {
    document.getElementById('highlightsList').innerHTML = highlights.length ? highlights.map(e => {
      const data = typeof e.event_data === 'string' ? JSON.parse(e.event_data || '{}') : (e.event_data || {});
      const name = escapeHtml(e.lead_name || e.lead_phone_display || '');
      const phone = escapeHtml(e.lead_phone_display || '');
      let icon = '', text = '';
      if (e.event_type === 'purchase') {
        icon = '💰';
        text = '<b>' + name + '</b> רכשה "' + escapeHtml(data.course || '') + '" — ' + (data.amount || '') + '₪';
      } else if (e.event_type === 'new_lead') {
        icon = '👤';
        text = 'ליד חדש: <b>' + name + '</b> (' + phone + ')';
      } else if (e.event_type === 'handoff') {
        icon = '🔄';
        text = 'העברה למירב: <b>' + name + '</b>' + (data.reason ? ' — "' + escapeHtml(data.reason) + '"' : '');
      }
      return '<div class="list-item" style="cursor:pointer" onclick="openLead(\x27' + phone + '\x27)"><span class="highlight-icon">' + icon + '</span><span class="highlight-text">' + text + '</span><span class="meta">' + fmtDate(e.created_at) + '</span></div>';
    }).join('') : '<div class="empty-state"><div class="icon">📌</div><p>אין פעולות אחרונות</p></div>';
  }
```

- [ ] **Step 6: Add highlight CSS**

In the `<style>` section of `crm.py`, add:

```css
.highlight-icon { font-size: 18px; margin-inline-end: 10px; }
.highlight-text { flex: 1; font-size: 13px; line-height: 1.5; }
.highlight-text b { font-weight: 700; }
```

- [ ] **Step 7: Test**

Visit CRM dashboard. Verify "פעולות אחרונות" section appears with recent events.

- [ ] **Step 8: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add database.py crm.py
git commit -m "$(cat <<'EOF'
feat: add highlights section to CRM dashboard

Shows recent purchases, new leads, and handoffs. Displays last
3 days or 10 events (whichever is more). New leads now log a
new_lead event for tracking.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: WhatsApp tab in sidebar (Feature)

**Files:**
- Modify: `database.py` — add `get_active_conversations()` function
- Modify: `crm.py` — add sidebar nav item, new tab HTML, API routes, JS functions

**Interfaces:**
- Produces: `get_active_conversations()` in database.py
- Produces: `GET /crm/api/whatsapp/active` endpoint
- Produces: `POST /crm/api/whatsapp/send` endpoint
- Consumes: `send_reply()` from `tools/whatsapp.py`, `append()` from database.py

- [ ] **Step 1: Add `get_active_conversations()` to database.py**

In `database.py`, add after `get_lead_conversations()` (around line 393):

```python
def get_active_conversations() -> list[dict]:
    """Get leads with conversations in the last 24 hours (active WhatsApp window)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Get leads with recent activity
    r = httpx.get(_url("leads"), headers=_get_headers(), params={
        "select": "phone,name,last_contact,status,ai_summary",
        "last_contact": f"gte.{cutoff}",
        "order": "last_contact.desc",
    })
    r.raise_for_status()
    leads = r.json()

    # Get last message for each lead
    for lead in leads:
        phone = lead["phone"]
        msgs = httpx.get(_url("conversations"), headers=_get_headers(), params={
            "select": "role,content,created_at",
            "chat_id": f"eq.{phone}",
            "order": "id.desc",
            "limit": "1",
        })
        msgs.raise_for_status()
        msg_data = msgs.json()
        lead["last_message"] = msg_data[0] if msg_data else None
        lead["phone_display"] = display_phone(phone)

    return leads
```

- [ ] **Step 2: Add WhatsApp API routes in crm.py**

In `crm.py`, add after the highlights API route:

```python
@router.get("/api/whatsapp/active", dependencies=[Depends(check_auth)])
async def api_whatsapp_active():
    from database import get_active_conversations
    return get_active_conversations()


class WhatsAppSend(BaseModel):
    phone: str
    message: str


@router.post("/api/whatsapp/send", dependencies=[Depends(check_auth)])
async def api_whatsapp_send(req: WhatsAppSend):
    from database import normalize_phone, append
    from tools.whatsapp import send_reply
    phone = normalize_phone(req.phone)
    send_reply(phone, req.message)
    append(phone, "assistant", req.message)
    return {"ok": True}
```

Also add `WhatsAppSend` import — it uses `BaseModel` already imported.

- [ ] **Step 3: Add WhatsApp tab HTML**

In `crm.py`, find the purchases tab closing div (around line 571: `</div>`). Add after it:

```html
  <!-- WhatsApp -->
  <div id="tab-whatsapp" class="view">
    <div id="waList" class="wa-list"></div>
    <div id="waChat" class="wa-chat" style="display:none">
      <div class="wa-chat-header">
        <button class="btn btn-outline btn-small" onclick="showWaList()" style="margin-inline-end:12px">← חזרה</button>
        <span id="waChatName" style="font-weight:700;font-size:15px"></span>
        <button class="btn btn-outline btn-small" style="margin-inline-start:auto" onclick="openLead(waChatPhone)">פרטים</button>
      </div>
      <div class="wa-chat-messages" id="waChatMessages"></div>
      <div class="wa-chat-input">
        <input type="text" id="waMessageInput" placeholder="הקלד הודעה..." onkeydown="if(event.key==='Enter')sendWaMessage()">
        <button class="btn btn-green" onclick="sendWaMessage()">שלח</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 4: Add WhatsApp sidebar nav item**

In `crm.py`, find the sidebar nav items. After the "לידים" button (around line 608) and before the "רכישות" button, add:

```html
  <button class="nav-item" onclick="showTab('whatsapp',this)">
    <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    WhatsApp
  </button>
```

- [ ] **Step 5: Add WhatsApp mobile tab**

In `crm.py`, find the mobile tabbar. After the "לידים" tab and before "רכישות", add:

```html
  <div class="tab" onclick="showTabMobile('whatsapp',this)">
    <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    WhatsApp
  </div>
```

- [ ] **Step 6: Update showTab() to handle whatsapp tab**

In `crm.py`, find `showTab()` function (around line 728-731). Add the whatsapp case:

```javascript
  if (tab==='whatsapp') loadWhatsApp();
```

- [ ] **Step 7: Add WhatsApp CSS**

In the `<style>` section of `crm.py`, add:

```css
.wa-list .wa-item { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border-2); cursor: pointer; transition: .18s; }
.wa-list .wa-item:hover { background: var(--green-soft); }
.wa-item .wa-avatar { width: 42px; height: 42px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; color: #fff; flex-shrink: 0; }
.wa-item .wa-info { flex: 1; min-width: 0; }
.wa-item .wa-name { font-weight: 700; font-size: 14px; }
.wa-item .wa-last-msg { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wa-item .wa-time { font-size: 11px; color: var(--muted-2); font-weight: 600; white-space: nowrap; }
.wa-chat { display: flex; flex-direction: column; height: calc(100vh - 100px); }
.wa-chat-header { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--card); }
.wa-chat-messages { flex: 1; overflow-y: auto; padding: 16px; background: #e5ddd5; background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4cfc4' fill-opacity='.15'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E"); }
.wa-chat-input { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--border); background: var(--card); }
.wa-chat-input input { flex: 1; padding: 10px 14px; border: 1px solid var(--border); border-radius: 20px; font-family: inherit; font-size: 13px; }
.wa-chat-input input:focus { outline: none; border-color: var(--green); }
```

- [ ] **Step 8: Add WhatsApp JS functions**

In `crm.py`, add before the closing `</script>` tag (around line 1282):

```javascript
// WhatsApp
let waChatPhone = '';

async function loadWhatsApp() {
  const convos = await apiFetch('/whatsapp/active');
  if (!convos) return;
  document.getElementById('waList').style.display = 'block';
  document.getElementById('waChat').style.display = 'none';
  document.getElementById('waList').innerHTML = convos.length ? convos.map(c => {
    const lastMsg = c.last_message;
    const msgPreview = lastMsg ? escapeHtml((lastMsg.content || '').slice(0, 60)) : '';
    const msgTime = lastMsg ? fmtDate(lastMsg.created_at) : fmtDate(c.last_contact);
    return `<div class="wa-item" onclick="openWaChat('${escapeHtml(c.phone_display)}', '${escapeHtml(c.name || c.phone_display)}')">
      <div class="wa-avatar" style="background:${getAvatarColor(c.name)}">${escapeHtml(getInitials(c.name))}</div>
      <div class="wa-info"><div class="wa-name">${escapeHtml(c.name || c.phone_display)}</div><div class="wa-last-msg">${msgPreview}</div></div>
      <div class="wa-time">${msgTime}</div>
    </div>`;
  }).join('') : '<div class="empty-state"><div class="icon">💬</div><p>אין שיחות פעילות (24 שעות)</p></div>';
}

async function openWaChat(phone, name) {
  waChatPhone = phone;
  document.getElementById('waChatName').textContent = name;
  document.getElementById('waList').style.display = 'none';
  document.getElementById('waChat').style.display = 'flex';
  const convos = await apiFetch(`/leads/${phone}/conversations?limit=50`);
  const container = document.getElementById('waChatMessages');
  if (convos && convos.length) {
    container.innerHTML = convos.map(m =>
      `<div class="chat-msg ${m.role}"><div>${escapeHtml(m.content)}</div><div class="time">${fmtDate(m.created_at)}</div></div>`
    ).join('');
  } else {
    container.innerHTML = '<div class="empty-state"><div class="icon">💬</div><p>אין הודעות</p></div>';
  }
  container.scrollTop = container.scrollHeight;
}

function showWaList() {
  document.getElementById('waList').style.display = 'block';
  document.getElementById('waChat').style.display = 'none';
  loadWhatsApp();
}

async function sendWaMessage() {
  const input = document.getElementById('waMessageInput');
  const message = input.value.trim();
  if (!message || !waChatPhone) return;
  input.value = '';
  input.disabled = true;
  try {
    await apiFetch('/whatsapp/send', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({phone: waChatPhone, message})
    });
    toast('הודעה נשלחה!');
    openWaChat(waChatPhone, document.getElementById('waChatName').textContent);
  } catch(e) {
    toast('שגיאה בשליחה');
  }
  input.disabled = false;
  input.focus();
}
```

- [ ] **Step 9: Test**

Visit CRM → WhatsApp tab. Verify:
1. Active conversations list shows leads from last 24h
2. Clicking a conversation opens chat view
3. Sending a message works (only within 24h window)
4. Back button returns to list

- [ ] **Step 10: Commit**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git add database.py crm.py
git commit -m "$(cat <<'EOF'
feat: add WhatsApp tab with active conversations and manual messaging

New sidebar tab shows active conversations (24h window). Click to
open chat history and send manual messages via Meta Cloud API.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Final: Deploy and verify

- [ ] **Step 1: Push all changes**

```bash
cd "c:/Users/rafie/OneDrive/מסמכים/ClaudeCodeClients/sherman-bot"
git push origin main
```

- [ ] **Step 2: Trigger Render deploy**

```bash
curl -s -X POST "https://api.render.com/v1/services/srv-d9nkll0ae00c739unv9g/deploys" \
  -H "Authorization: Bearer rnd_1rN8woUts7GDBXhHxghDfx9XA8J5" \
  -H "Content-Type: application/json" -d '{}'
```

- [ ] **Step 3: Verify health**

```bash
curl -s https://sheri-bot.onrender.com/health
```

- [ ] **Step 4: Verify CRM functionality**

Open https://sheri-bot.onrender.com/crm and verify all 7 changes work.

---

## Deferred Task (Reminder)

**Google Drive auto-access on purchase** — waiting for:
1. Google Cloud project / Service Account credentials from Merav
2. Drive folder structure (one folder per course)
3. Whether Merav uses Google Workspace or regular Gmail
