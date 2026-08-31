# CRM Improvements — Design Spec
**Date:** 2026-08-31
**Project:** Sherman Bot (שרי)
**Status:** Approved

---

## Tasks Overview

| # | Task | Type | Files |
|---|------|------|-------|
| 1 | רכישות Cardcom בכרטיס לקוחה | Bug fix | database.py, crm.py |
| 2 | טאב WhatsApp בסרגל צד | Feature | crm.py, main.py, database.py |
| 3 | תיוג אוטומטי לפי עניין בקורסים | Feature | agent.py, tools/, database.py |
| 4 | שם לקוחה ברשימת רכישות | Enhancement | crm.py, database.py |
| 5 | סטטוס "לקוחה" בפילטר | Bug fix | database.py, crm.py |
| 6 | תיקון חיפוש כפול + חיפוש טלפון | Bug fix | crm.py, database.py |
| 7 | Highlights בדשבורד | Feature | crm.py, database.py |

**Deferred:** Google Drive auto-access on purchase (waiting for credentials)

---

## Task 1: רכישות Cardcom בכרטיס לקוחה (Bug Fix)

### Problem
Purchases created via Cardcom webhook appear in the main "Purchases" tab but not in the lead's drawer "Purchases" tab. Likely cause: phone format mismatch between `purchases.lead_phone` and the query parameter sent from the drawer.

### Solution
- Investigate phone format stored by `create_purchase()` in Cardcom webhook flow
- Ensure `normalize_phone()` is applied consistently:
  - In `create_purchase()` when saving `lead_phone`
  - In the drawer API query when fetching purchases by phone
- Verify the drawer JS sends the correct phone format to `/purchases?lead_phone=...`

### Acceptance Criteria
- After a Cardcom purchase, the purchase appears in the lead's drawer "רכישות" tab
- Existing purchases also display correctly

---

## Task 2: טאב WhatsApp בסרגל צד (Feature)

### Overview
New sidebar tab "WhatsApp" showing active conversations (24h window) with ability to send manual messages.

### UI Design
**Sidebar:** New nav item "WhatsApp" with chat icon, placed between "לידים" and "רכישות"

**Tab Content:**
```
┌─────────────────────────────────────────┐
│ שיחות פעילות (חלון 24 שעות)            │
├─────────────────────────────────────────┤
│ [Avatar] שם הלקוחה          15:32 היום  │
│          הודעה אחרונה...               │
├─────────────────────────────────────────┤
│ [Avatar] שם לקוחה 2         אתמול 22:10│
│          הודעה אחרונה...               │
└─────────────────────────────────────────┘
```

**Chat View (on click):**
```
┌─────────────────────────────────────────┐
│ ← חזרה    שם הלקוחה    📋 פרטים       │
├─────────────────────────────────────────┤
│                                         │
│  [Chat messages - WhatsApp style]       │
│                                         │
├─────────────────────────────────────────┤
│ [הקלד הודעה...              ] [שלח ➤]  │
└─────────────────────────────────────────┘
```

### Backend
- **New API:** `GET /crm/api/whatsapp/active` — returns leads with `last_contact` within 24h, plus their last message
- **New API:** `POST /crm/api/whatsapp/send` — sends message via Meta Cloud API from Sheri's number
  - Body: `{ "phone": "972...", "message": "..." }`
  - Uses existing `send_whatsapp_message()` from `tools/whatsapp.py`
  - Saves message to `conversations` table with role="assistant"
- **Existing API:** `GET /crm/api/leads/{phone}/conversations` — reuse for chat history

### Constraints
- Only leads with `last_contact` within 24 hours are shown (Meta 24h messaging window)
- Manual messages are sent as regular text (not templates) — only works within 24h window
- Messages appear as if from Sheri (the bot's number)

---

## Task 3: תיוג אוטומטי לפי עניין בקורסים (Feature)

### Overview
The Claude agent (in agent.py) will automatically tag leads based on course interest detected during conversation.

### New Tool: `tag_lead`
```python
{
    "name": "tag_lead",
    "description": "תייגי את הלקוחה כשהיא מתעניינת בקורס או נושא ספציפי. אפשר לתייג מספר תגים.",
    "input_schema": {
        "type": "object",
        "properties": {
            "phone": {"type": "string", "description": "מספר הטלפון של הלקוחה"},
            "tag": {"type": "string", "description": "שם התג, לדוגמה: מדריכות, יסודות, הקלה בכאבים"}
        },
        "required": ["phone", "tag"]
    }
}
```

### Implementation
- New file: `tools/tagging.py` — contains `tag_lead(phone, tag)` function
- Function adds the tag to the lead's `tags[]` array (if not already present)
- Auto-creates the tag in `crm_settings.tags` if it doesn't exist (with default color)
- Agent system prompt updated: instruct the agent to tag leads when course interest is detected

### Prompt Addition (in prompt.py)
```
כשלקוחה מתעניינת בקורס או בנושא ספציפי — השתמשי בכלי tag_lead כדי לתייג אותה.
דוגמאות: אם שואלת על קורס מדריכות → תייגי "מדריכות".
אם מתעניינת ביסודות → תייגי "יסודות שיטת שרמן".
אפשר לתייג מספר תגים אם מתעניינת במספר קורסים.
```

---

## Task 4: שם לקוחה ברשימת רכישות (Enhancement)

### Problem
The main "Purchases" tab shows: phone, course, amount, date, method — but no customer name.

### Solution
- **Backend:** `get_purchases()` in database.py — join/enrich with lead name from `leads` table
  - After fetching purchases, batch-fetch lead names by phone numbers
  - Return `lead_name` field in each purchase object
- **Frontend:** Add "שם" column to purchases table, before "טלפון"
  - Name is clickable → `openLead(phone)` to open the lead's drawer

### Table After Change
```
| שם (link) | טלפון | קורס | סכום | תאריך | אמצעי |
```

---

## Task 5: סטטוס "לקוחה" בפילטר (Bug Fix)

### Problem
Status "לקוחה" is set by the Cardcom webhook (`update_lead(phone, status="לקוחה")`) but doesn't appear in the status filter dropdown.

### Root Cause
The filter dropdown is populated from `crm_settings.statuses`. If "לקוחה" was never added there, it won't show.

### Solution
- In `seed_db.py` or initialization: ensure "לקוחה" is included in default statuses
- In the API that loads settings: if a lead has a status not in the settings list, auto-add it
- Fallback: on CRM load, scan distinct statuses from `leads` table and merge with settings

### Chosen Approach
Add "לקוחה" to the default statuses in the settings initialization, and add a safety check: when loading the filter, merge `crm_settings.statuses` with distinct statuses actually used in `leads` table.

---

## Task 6: תיקון חיפוש כפול + חיפוש טלפון (Bug Fix)

### Problem 1: Duplicate Search Fields
Two search inputs exist in the leads tab. Only one is needed.

### Solution 1
Remove the duplicate. Keep only the local search input in the leads tab header.

### Problem 2: Phone Search Doesn't Work
Searching for "0508806087" doesn't find the lead because the DB stores phones as "9728806087" (normalized).

### Solution 2
In `get_leads()` (database.py): normalize the search term before querying.
```python
if search:
    normalized_search = normalize_phone(search) if search.startswith("05") else search
    params["or"] = f"(name.ilike.%{search}%,phone.ilike.%{normalized_search}%)"
```
This way searching "0508806087" converts to "9728806087" for the phone match, while keeping the original for name match.

---

## Task 7: Highlights בדשבורד (Feature)

### Overview
New section on the dashboard showing recent important activity.

### Data Source
Query `lead_events` table for:
- `event_type = "purchase"` — רכישה חדשה
- `event_type = "new_lead"` — ליד חדש (need to log this event)
- `event_type = "handoff"` — העברה למירב

### Display Rules
- Show events from last 3 days OR last 10 events — **whichever is more**
- Sorted newest first

### UI Design
```
┌─────────────────────────────────────────┐
│ 📌 פעולות אחרונות                       │
├─────────────────────────────────────────┤
│ 💰 דנה כהן רכשה "יסודות שיטת שרמן"    │
│    540₪ · היום 14:32                    │
├─────────────────────────────────────────┤
│ 👤 ליד חדש: מיכל לוי (050-123-4567)    │
│    היום 12:15                           │
├─────────────────────────────────────────┤
│ 🔄 העברה למירב: שרה אברהם             │
│    "רוצה לדבר על קורס מדריכות"         │
│    אתמול 18:20                          │
└─────────────────────────────────────────┘
```

### Backend
- **New API:** `GET /crm/api/highlights` — returns recent events
  - Query: `lead_events` WHERE `event_type IN ('purchase', 'new_lead', 'handoff')` ORDER BY `created_at DESC`
  - Logic: fetch last 3 days; if < 10 results, fetch until 10
  - Enrich with lead name from `leads` table

### New Event Logging
- `new_lead` event: add `log_lead_event(phone, "new_lead", {...})` in `upsert_lead_from_message()` when a truly new lead is created

---

## Dependencies Between Tasks

```
Task 5 (status fix) → independent
Task 6 (search fix) → independent
Task 1 (purchases in drawer) → independent
Task 4 (name in purchases) → independent
Task 3 (auto-tagging) → independent
Task 7 (highlights) → needs "new_lead" event logging
Task 2 (WhatsApp tab) → independent but largest
```

All tasks are independent and can be implemented in any order. Task 2 (WhatsApp) is the largest.
