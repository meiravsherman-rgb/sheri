"""CRM panel — lead tracking, timeline, purchases, settings for Merav."""

import csv
import io
import json
import os
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from database import (
    get_leads, get_lead, update_lead, create_lead_manual,
    log_lead_event, get_lead_timeline, get_lead_conversations,
    create_purchase, get_purchases, get_dashboard_stats,
    get_all_courses, get_crm_settings, update_crm_setting,
    display_phone,
)

router = APIRouter(prefix="/crm")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "sheri2024")


def check_auth(request: Request):
    token = request.cookies.get("admin_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Check session tokens from admin module
    try:
        from admin import _active_sessions, _cleanup_sessions
        _cleanup_sessions()
        if token in _active_sessions:
            return
    except ImportError:
        pass
    # Backwards compatible: also accept raw password
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── API Models ─────────────────────────────────────────────────────

class LeadUpdate(BaseModel):
    status: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    next_followup: str | None = None
    name: str | None = None
    conversation_summary: str | None = None
    followup_stopped: bool | None = None

class NewLead(BaseModel):
    phone: str
    name: str = ""
    source: str = "manual"

class NewPurchase(BaseModel):
    lead_phone: str
    course_name: str
    amount: float
    course_id: int | None = None
    payment_method: str = "cardcom"
    notes: str = ""

class BulkStatus(BaseModel):
    phones: list[str] = Field(..., max_length=100)
    status: str

class SettingUpdate(BaseModel):
    setting_key: str
    setting_value: list


# ── API Routes ─────────────────────────────────────────────────────

@router.get("/api/dashboard", dependencies=[Depends(check_auth)])
async def api_dashboard():
    stats = get_dashboard_stats()
    for l in stats.get("upcoming_followups", []):
        l["phone"] = display_phone(l.get("phone", ""))
    for l in stats.get("needs_attention", []):
        l["phone"] = display_phone(l.get("phone", ""))
    return stats


def _leads_display(leads: list[dict]) -> list[dict]:
    """Convert phone to display format for CRM."""
    for l in leads:
        l["phone"] = display_phone(l.get("phone", ""))
    return leads

@router.get("/api/leads", dependencies=[Depends(check_auth)])
async def api_leads(status: str = "", search: str = "", tag: str = ""):
    return _leads_display(get_leads(status=status, search=search, tag=tag))


@router.get("/api/leads/{phone}", dependencies=[Depends(check_auth)])
async def api_lead_detail(phone: str):
    lead = get_lead(phone)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead["phone"] = display_phone(lead.get("phone", ""))
    return lead


@router.patch("/api/leads/{phone}", dependencies=[Depends(check_auth)])
async def api_update_lead(phone: str, req: LeadUpdate):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    old = get_lead(phone)
    if not old:
        raise HTTPException(status_code=404, detail="Lead not found")
    if "status" in fields and fields["status"] != old.get("status"):
        log_lead_event(phone, "status_change", {
            "from": old.get("status"), "to": fields["status"]
        })
    if "notes" in fields and fields["notes"] != old.get("notes"):
        log_lead_event(phone, "note", {"text": fields["notes"][:100]})
    update_lead(phone, **fields)
    return {"ok": True}


@router.post("/api/leads", dependencies=[Depends(check_auth)])
async def api_create_lead(req: NewLead):
    create_lead_manual(req.phone, req.name, req.source)
    log_lead_event(req.phone, "status_change", {"from": None, "to": "חדש"})
    return {"ok": True}


@router.post("/api/leads/bulk-status", dependencies=[Depends(check_auth)])
async def api_bulk_status(req: BulkStatus):
    for phone in req.phones:
        old = get_lead(phone)
        if old and old.get("status") != req.status:
            log_lead_event(phone, "status_change", {"from": old.get("status"), "to": req.status})
            update_lead(phone, status=req.status)
    return {"ok": True, "count": len(req.phones)}


@router.get("/api/leads-export", dependencies=[Depends(check_auth)])
async def api_export_csv():
    leads = _leads_display(get_leads())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["phone", "name", "status", "source", "tags", "notes", "first_contact", "last_contact", "total_paid"])
    for l in leads:
        writer.writerow([
            l.get("phone", ""), l.get("name", ""), l.get("status", ""),
            l.get("source", ""), ",".join(l.get("tags") or []), l.get("notes", ""),
            l.get("first_contact", ""), l.get("last_contact", ""), l.get("total_paid", 0),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@router.get("/api/leads/{phone}/timeline", dependencies=[Depends(check_auth)])
async def api_timeline(phone: str, limit: int = 50):
    return get_lead_timeline(phone, limit)


@router.get("/api/leads/{phone}/conversations", dependencies=[Depends(check_auth)])
async def api_conversations(phone: str, limit: int = 1000):
    return get_lead_conversations(phone, limit)


@router.get("/api/purchases", dependencies=[Depends(check_auth)])
async def api_all_purchases(lead_phone: str = ""):
    from database import normalize_phone
    phone_filter = normalize_phone(lead_phone) if lead_phone else ""
    purchases = get_purchases(phone_filter)
    for p in purchases:
        p["lead_phone"] = display_phone(p.get("lead_phone", ""))
    return purchases


@router.post("/api/purchases", dependencies=[Depends(check_auth)])
async def api_create_purchase(req: NewPurchase):
    from database import normalize_phone
    phone = normalize_phone(req.lead_phone)
    pid = create_purchase(phone, req.course_name, req.amount,
                          req.course_id, req.payment_method, req.notes)
    log_lead_event(phone, "purchase", {
        "course": req.course_name, "amount": req.amount, "method": req.payment_method
    })
    # Update status and stop followups
    update_lead(phone, status="נרשמה", followup_stopped=True)
    # Send purchase confirmation and alert Merav
    try:
        from tools.whatsapp import send_purchase_confirmation, alert_purchase
        lead = get_lead(phone)
        name = (lead.get("name") if lead else "") or ""
        if name:
            send_purchase_confirmation(phone, name)
        alert_purchase(name or display_phone(phone), req.course_name, req.amount)
    except Exception:
        pass  # Don't fail the purchase if notification fails
    return {"id": pid}


@router.get("/api/courses-list", dependencies=[Depends(check_auth)])
async def api_courses_list():
    return [{"id": c["id"], "name": c["name"], "price": c["price"]}
            for c in get_all_courses() if c.get("is_active")]


def _get_distinct_lead_statuses() -> set[str]:
    """Get all distinct status values from leads table."""
    leads = get_leads()
    return {l.get("status") for l in leads if l.get("status")}


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


@router.post("/api/settings", dependencies=[Depends(check_auth)])
async def api_update_settings(req: SettingUpdate):
    update_crm_setting(req.setting_key, req.setting_value)
    return {"ok": True}


@router.get("/api/highlights", dependencies=[Depends(check_auth)])
async def api_highlights():
    from database import get_highlights
    return get_highlights()


# ── HTML Page ──────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
async def crm_page():
    return CRM_HTML


CRM_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRM — שיטת שרמן</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root {
  --gold: #FDD73B; --gold-soft: #FEF3C7;
  --green: #019D76; --green-dark: #017a5c; --green-soft: #E3F4EE;
  --orange: #F38120; --orange-soft: #FDE8D5;
  --hot: #EF5B3C; --hot-soft: #FCE4DE;
  --warm: #F3A712; --warm-soft: #FCEFD3;
  --cold: #4F94C4; --cold-soft: #E2EEF6;
  --bg: #F4F6F2; --card: #FFFFFF; --ink: #1E2B26;
  --muted: #75807A; --muted-2: #9aa49e;
  --border: #E9ECE5; --border-2: #EFF1EB;
  --shadow: 0 1px 2px rgba(30,43,38,.04), 0 8px 24px rgba(30,43,38,.05);
  --shadow-lg: 0 12px 40px rgba(30,43,38,.12);
  --radius: 18px;
  --transition: all .3s cubic-bezier(.4,0,.2,1);
  /* Legacy compat aliases */
  --pink: var(--green); --pink-dark: var(--green-dark); --pink-light: var(--green-soft); --pink-bg: var(--bg);
  --blue: var(--cold); --red: var(--hot); --gray: var(--muted); --dark: var(--ink);
  --purple: #8B5CF6; --teal: #14B8A6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body { font-family: 'Heebo', 'Segoe UI', sans-serif; background: var(--bg); color: var(--ink); direction: rtl; -webkit-font-smoothing: antialiased; }
::selection { background: var(--green-soft); }
button { font-family: inherit; cursor: pointer; border: none; background: none; }
a { color: inherit; text-decoration: none; }

/* App shell */
.app { display: grid; grid-template-columns: 1fr 250px; min-height: 100vh; }
@media(max-width:980px) { .app { grid-template-columns: 1fr; } }

/* Sidebar */
.sidebar { background: var(--card); border-left: 1px solid var(--border); padding: 22px 16px; display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh; }
@media(max-width:980px) { .sidebar { display: none; } }
.logo { display: flex; align-items: center; gap: 11px; padding: 6px 8px 22px; }
.logo .mark { width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(135deg, var(--green), var(--green-dark)); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 4px 12px rgba(1,157,118,.3); color: #fff; font-weight: 900; font-size: 16px; }
.logo-text b { font-size: 15px; font-weight: 800; line-height: 1.1; display: block; }
.logo-text span { font-size: 11px; color: var(--muted); font-weight: 500; }
.nav-group { font-size: 10.5px; font-weight: 700; color: var(--muted-2); letter-spacing: .5px; padding: 14px 10px 8px; }
.nav-item { display: flex; align-items: center; gap: 11px; padding: 10px 12px; border-radius: 11px; font-size: 14px; font-weight: 600; color: var(--muted); margin-bottom: 2px; transition: .18s; width: 100%; text-align: right; cursor: pointer; }
.nav-item svg { width: 19px; height: 19px; flex-shrink: 0; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.nav-item:hover { background: var(--bg); color: var(--ink); }
.nav-item.active { background: var(--green-soft); color: var(--green-dark); font-weight: 700; }
.side-foot { margin-top: auto; padding-top: 16px; border-top: 1px solid var(--border); }
.side-foot a { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 11px; font-size: 13px; font-weight: 600; color: var(--muted); transition: .18s; }
.side-foot a:hover { background: var(--bg); color: var(--ink); }

/* Main area */
.main { padding: 0 0 50px; overflow: hidden; }
.topbar { position: sticky; top: 0; z-index: 20; background: rgba(244,246,242,.85); backdrop-filter: blur(10px); padding: 18px 30px; display: flex; align-items: center; gap: 18px; border-bottom: 1px solid var(--border); }
.topbar h1 { font-size: 21px; font-weight: 800; }
.topbar h1 small { display: block; font-size: 12px; font-weight: 500; color: var(--muted); margin-top: 1px; }
.search { margin-inline-start: auto; position: relative; }
.search input { background: var(--card); border: 1px solid var(--border); border-radius: 11px; padding: 10px 38px 10px 14px; font-size: 13px; width: 230px; font-family: inherit; color: var(--ink); }
.search input:focus { outline: none; border-color: var(--green); }
.search svg { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); width: 16px; height: 16px; stroke: var(--muted); fill: none; }

/* Views */
.view { padding: 26px 30px; display: none; animation: fade .4s ease; }
.view.active { display: block; }
@keyframes fade { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.hidden { display: none !important; }

/* Login */
.login-overlay { position: fixed; inset: 0; background: linear-gradient(135deg, rgba(1,157,118,.92), rgba(1,122,92,.95)); display: flex; align-items: center; justify-content: center; z-index: 999; }
.login-box { background: #fff; padding: 2.5rem; border-radius: var(--radius); text-align: center; width: 340px; box-shadow: var(--shadow-lg); }
.login-box h2 { color: var(--green-dark); margin-bottom: .5rem; font-size: 1.5rem; font-weight: 800; }
.login-box p { color: var(--muted); font-size: .85rem; margin-bottom: 1.5rem; }
.login-box .pass-wrapper { position: relative; margin-bottom: .5rem; direction: ltr; }
.login-box .pass-wrapper input { width: 100%; padding: .8rem 2.5rem .8rem .8rem; border: 1px solid var(--border); border-radius: 12px; text-align: center; font-size: 1rem; outline: none; transition: var(--transition); font-family: inherit; }
.login-box .pass-wrapper input:focus { border-color: var(--green); }
.login-box .eye-toggle { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: var(--bg); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 1rem; color: var(--muted); padding: 4px 6px; line-height: 1; z-index: 2; }
.login-box .eye-toggle:hover { background: var(--border); }
.login-box .login-error { color: var(--hot); font-size: .85rem; margin-bottom: .5rem; min-height: 1.3em; font-weight: 600; }
.login-box .login-btn { background: linear-gradient(135deg, var(--green), var(--green-dark)); color: #fff; border: none; padding: .8rem 2rem; border-radius: 12px; cursor: pointer; font-size: 1rem; font-weight: 700; width: 100%; transition: var(--transition); font-family: inherit; }
.login-box .login-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(1,157,118,.4); }

/* KPI Cards */
.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 20px; }
@media(max-width:1150px) { .kpis { grid-template-columns: repeat(3, 1fr); } }
@media(max-width:560px) { .kpis { grid-template-columns: 1fr 1fr; } }
.kpi { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); cursor: pointer; transition: .18s; position: relative; overflow: hidden; }
.kpi:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }
.kpi .ic { width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 14px; font-size: 1.3rem; }
.kpi .lbl { font-size: 13px; color: var(--muted); font-weight: 600; }
.kpi .val { font-size: 28px; font-weight: 900; letter-spacing: -1px; margin-top: 3px; color: var(--ink); }
.kpi:nth-child(1) .ic { background: var(--green-soft); }
.kpi:nth-child(2) .ic { background: var(--gold-soft); }
.kpi:nth-child(3) .ic { background: var(--orange-soft); }
.kpi:nth-child(4) .ic { background: var(--cold-soft); }
.kpi:nth-child(5) .ic { background: var(--hot-soft); }

/* Panels grid */
.row { display: grid; gap: 16px; margin-top: 16px; }
.row.r-2 { grid-template-columns: 1.4fr 1fr; }
@media(max-width:1000px) { .row.r-2 { grid-template-columns: 1fr; } }
.panel { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); }
.panel-h { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.panel-h h3 { font-size: 16px; font-weight: 800; }

/* Funnel */
.funnel { display: flex; flex-direction: column; gap: 9px; }
.fn { position: relative; border-radius: 11px; padding: 13px 16px; color: #fff; display: flex; align-items: center; justify-content: space-between; font-weight: 700; cursor: pointer; transition: .18s; }
.fn:hover { filter: brightness(1.08); }
.fn small { font-size: 12px; opacity: .85; font-weight: 600; }
.fn b { font-size: 18px; font-weight: 900; }

/* Course rows */
.course-row { display: flex; justify-content: space-between; align-items: center; padding: 13px 0; border-bottom: 1px solid var(--border-2); }
.course-row:last-child { border: none; }
.course-row .c-name { font-size: 13.5px; font-weight: 600; flex: 1; }
.course-row .c-amount { font-weight: 800; color: var(--green-dark); font-size: 14px; }

/* List items (followups/attention) */
.list-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 4px; border-bottom: 1px solid var(--border-2); cursor: pointer; border-radius: 8px; transition: .18s; }
.list-item:hover { background: var(--green-soft); }
.list-item .name { font-weight: 600; font-size: 13.5px; }
.list-item .meta { font-size: 12px; color: var(--muted); font-weight: 600; }
.attention-badge { background: var(--warm-soft); color: #b97a06; padding: 3px 9px; border-radius: 20px; font-size: 11px; font-weight: 800; }

/* Leads */
.filters { display: flex; gap: 8px; margin-bottom: 18px; flex-wrap: wrap; align-items: center; }
.filters input, .filters select { padding: 10px 14px; border: 1px solid var(--border); border-radius: 11px; font-size: 13px; outline: none; transition: .18s; font-family: inherit; background: var(--card); color: var(--ink); }
.filters input:focus, .filters select:focus { border-color: var(--green); }
.filters input { flex: 1; min-width: 150px; }

.btn { padding: 8px 16px; border: none; border-radius: 11px; cursor: pointer; font-size: 13px; font-weight: 700; transition: .18s; display: inline-flex; align-items: center; gap: 6px; font-family: inherit; }
.btn:hover { transform: translateY(-1px); }
.btn-pink { background: var(--green); color: #fff; box-shadow: 0 2px 8px rgba(1,157,118,.3); }
.btn-green { background: var(--green); color: #fff; }
.btn-blue { background: var(--cold); color: #fff; }
.btn-outline { background: var(--card); border: 1px solid var(--border); color: var(--muted); }
.btn-outline:hover { border-color: var(--green); color: var(--green); }
.btn-small { padding: 5px 11px; font-size: 12px; }
.btn-icon { width: 36px; height: 36px; padding: 0; display: flex; align-items: center; justify-content: center; border-radius: 10px; }

/* Leads Table */
.leads-table { width: 100%; background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; border: 1px solid var(--border); }
.leads-table table { width: 100%; border-collapse: collapse; }
.leads-table th { padding: 10px 12px; text-align: right; font-size: 11px; color: var(--muted); font-weight: 800; text-transform: uppercase; letter-spacing: .4px; border-bottom: 1px solid var(--border); }
.leads-table td { padding: 13px 12px; border-bottom: 1px solid var(--border-2); font-size: 13.5px; font-weight: 600; }
.leads-table tr { transition: .18s; cursor: pointer; }
.leads-table tr:hover { background: var(--bg); }
.leads-table tr:last-child td { border-bottom: none; }

.lead-row-avatar { width: 32px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 13px; flex-shrink: 0; }
.lead-name-cell { display: flex; align-items: center; gap: 9px; }

.status-badge { padding: 3px 9px; border-radius: 20px; font-size: 11px; font-weight: 800; white-space: nowrap; }
.tag { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 800; padding: 3px 9px; border-radius: 20px; margin-left: 2px; }
.activity-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.activity-dot.hot { background: var(--green); box-shadow: 0 0 6px rgba(1,157,118,.5); animation: pulse 2s infinite; }
.activity-dot.warm { background: var(--warm); }
.activity-dot.cold { background: var(--muted); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }

.bulk-bar { display: none; align-items: center; gap: 8px; padding: 10px 16px; background: var(--green-soft); border: 1px solid var(--green); border-radius: 12px; margin-bottom: 12px; font-size: 13px; font-weight: 700; }
.bulk-bar.visible { display: flex; }

/* Drawer modal (replaces old center modal) */
.overlay { position: fixed; inset: 0; background: rgba(30,43,38,.4); backdrop-filter: blur(2px); opacity: 0; visibility: hidden; transition: .25s; z-index: 90; }
.overlay.open { opacity: 1; visibility: visible; }
.drawer { position: fixed; top: 0; right: 0; bottom: 0; width: 480px; max-width: 94vw; background: var(--bg); z-index: 100; transform: translateX(100%); transition: .32s cubic-bezier(.3,.7,.3,1); overflow-y: auto; box-shadow: -12px 0 40px rgba(30,43,38,.18); }
.drawer.open { transform: none; }
.dr-head { background: linear-gradient(135deg, var(--green), var(--green-dark)); padding: 24px; color: #fff; position: relative; }
.dr-close { position: absolute; top: 18px; left: 18px; width: 34px; height: 34px; border-radius: 10px; background: rgba(255,255,255,.18); display: flex; align-items: center; justify-content: center; cursor: pointer; color: #fff; font-size: 18px; font-weight: 700; }
.dr-close:hover { background: rgba(255,255,255,.3); }
.dr-head .dav { width: 56px; height: 56px; border-radius: 16px; background: rgba(255,255,255,.2); display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 900; margin-bottom: 12px; }
.dr-head h2 { font-size: 20px; font-weight: 900; }
.dr-head .meta { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.dr-head .mchip { background: rgba(255,255,255,.18); font-size: 11.5px; font-weight: 700; padding: 5px 11px; border-radius: 20px; display: inline-flex; align-items: center; gap: 5px; }
.dr-body { padding: 20px; }
.dr-tabs { display: flex; gap: 4px; padding: 0 20px; background: var(--card); border-bottom: 1px solid var(--border); }
.dr-tabs button { padding: 12px 16px; font-size: 13px; font-weight: 700; color: var(--muted); border-bottom: 2px solid transparent; transition: .18s; }
.dr-tabs button.active { color: var(--green-dark); border-bottom-color: var(--green); }
.dr-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px; margin-bottom: 14px; box-shadow: var(--shadow); }
.dr-card h4 { font-size: 11px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 12px; }

/* Legacy modal compat */
.modal-overlay { position: fixed; inset: 0; background: rgba(30,43,38,.4); display: flex; align-items: center; justify-content: center; z-index: 100; backdrop-filter: blur(3px); animation: fadeIn .2s; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal { background: var(--card); border-radius: var(--radius); width: 95%; max-width: 420px; max-height: 90vh; overflow-y: auto; animation: slideUp .3s; border: 1px solid var(--border); }
@keyframes slideUp { from { transform: translateY(30px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.modal-header { padding: 20px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; background: var(--card); z-index: 1; border-radius: var(--radius) var(--radius) 0 0; }
.modal-header h2 { color: var(--green-dark); font-size: 18px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
.modal-header .close-btn { font-size: 1.5rem; color: var(--muted); transition: .18s; width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.modal-header .close-btn:hover { background: var(--bg); color: var(--ink); }
.modal-body { padding: 20px 24px; }

.field-group { margin-bottom: 12px; }
.field-group label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 700; }
.field-group input, .field-group select, .field-group textarea { width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 11px; font-size: 13px; outline: none; transition: .18s; font-family: inherit; color: var(--ink); }
.field-group input:focus, .field-group select:focus, .field-group textarea:focus { border-color: var(--green); }
.field-group textarea { min-height: 80px; resize: vertical; }

.tags-container { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-toggle { padding: 5px 11px; border: 2px solid var(--border); border-radius: 20px; cursor: pointer; font-size: 12px; background: var(--card); transition: .18s; font-weight: 700; }
.tag-toggle:hover { border-color: var(--muted); }
.tag-toggle.active { border-color: var(--green); background: var(--green-soft); color: var(--green-dark); }

/* Timeline */
.timeline { margin-top: 8px; }
.timeline-item { display: flex; gap: 12px; padding: 11px 0; border-bottom: 1px solid var(--border-2); font-size: 13px; }
.timeline-dot { width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 15px; flex-shrink: 0; }
.timeline-dot.handoff { background: var(--orange-soft); }
.timeline-dot.purchase { background: var(--green-soft); }
.timeline-dot.status_change { background: var(--cold-soft); }
.timeline-dot.note { background: var(--gold-soft); }
.timeline-dot.message { background: var(--bg); }
.timeline-content { flex: 1; font-weight: 600; }
.timeline-content .time { color: var(--muted-2); font-size: 11px; font-weight: 600; }

/* Chat */
.chat-view { background: #ECE5DD; background-image: radial-gradient(rgba(0,0,0,.018) 1px, transparent 1px); background-size: 18px 18px; border-radius: 14px; padding: 18px; max-height: 500px; overflow-y: auto; }
.chat-msg { margin-bottom: 8px; padding: 9px 13px; border-radius: 12px; max-width: 74%; font-size: 13px; line-height: 1.45; position: relative; box-shadow: 0 1px 1px rgba(0,0,0,.06); }
.chat-msg.user { background: #DCF8C6; margin-left: auto; border-top-left-radius: 3px; }
.chat-msg.assistant { background: #fff; border-top-right-radius: 3px; }
.chat-msg .time { font-size: 9.5px; color: rgba(0,0,0,.35); display: block; text-align: left; margin-top: 3px; }
.session-block { margin-bottom: 8px; }
.session-header { display: flex; align-items: center; gap: .6rem; margin: 8px 0; cursor: pointer; user-select: none; }
.session-header::before, .session-header::after { content: ''; flex: 1; height: 1px; background: rgba(0,0,0,.15); }
.session-header span { background: rgba(0,0,0,.1); color: #555; font-size: 11px; padding: 4px 12px; border-radius: 20px; white-space: nowrap; font-weight: 700; display: flex; align-items: center; gap: 4px; }
.session-header .arrow { transition: transform .2s; font-size: .6rem; }
.session-header.collapsed .arrow { transform: rotate(-90deg); }
.session-messages { transition: max-height .3s ease; overflow: hidden; }
.session-messages.collapsed { max-height: 0 !important; }

/* Settings */
.settings-section { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); margin-bottom: 16px; }
.settings-section h3 { color: var(--ink); margin-bottom: 16px; font-size: 16px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
.setting-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border-2); }
.setting-item:last-child { border: none; }
.setting-item input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 9px; font-size: 13px; font-family: inherit; }
.setting-item .color-dot { width: 28px; height: 28px; border-radius: 8px; cursor: pointer; border: 2px solid var(--card); box-shadow: 0 0 0 1px var(--border); }
.setting-item .remove-btn { color: var(--muted); cursor: pointer; font-size: 1.2rem; transition: .18s; }
.setting-item .remove-btn:hover { color: var(--hot); }

/* Purchases table */
.purchases-table { width: 100%; background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; border: 1px solid var(--border); }
.purchases-table table { width: 100%; border-collapse: collapse; }
.purchases-table th { padding: 10px 12px; text-align: right; font-size: 11px; color: var(--muted); font-weight: 800; text-transform: uppercase; letter-spacing: .4px; border-bottom: 1px solid var(--border); }
.purchases-table td { padding: 13px 12px; border-bottom: 1px solid var(--border-2); font-size: 13.5px; font-weight: 600; }

/* Highlights section */
.row.r-1 { display: grid; grid-template-columns: 1fr; gap: 20px; margin-top: 20px; }
.highlight-icon { font-size: 18px; margin-inline-end: 10px; }
.highlight-text { flex: 1; font-size: 13px; line-height: 1.5; }
.highlight-text b { font-weight: 700; }

/* Toast */
.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(100px); background: var(--ink); color: #fff; padding: 10px 24px; border-radius: 14px; z-index: 200; font-size: 13px; font-weight: 700; box-shadow: var(--shadow-lg); transition: transform .3s cubic-bezier(.4,0,.2,1); }
.toast.visible { transform: translateX(-50%) translateY(0); }

/* Empty state */
.empty-state { text-align: center; padding: 40px 16px; color: var(--muted); }
.empty-state .icon { font-size: 2.5rem; margin-bottom: 8px; }
.empty-state p { font-size: 13px; font-weight: 600; }

/* Mobile bottom tab bar */
.tabbar { display: none; }
@media(max-width:980px) {
  .tabbar { display: flex; position: fixed; bottom: 0; left: 0; right: 0; z-index: 60; background: rgba(255,255,255,.97); backdrop-filter: blur(12px); border-top: 1px solid var(--border); padding: 7px 6px calc(7px + env(safe-area-inset-bottom)); box-shadow: 0 -4px 22px rgba(30,43,38,.07); }
  .tab { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 6px 2px; border-radius: 12px; color: var(--muted); font-size: 10.5px; font-weight: 700; cursor: pointer; }
  .tab svg { width: 21px; height: 21px; stroke: currentColor; fill: none; }
  .tab.active { color: var(--green); }
  .main { padding-bottom: 80px; }
  .topbar { padding: 14px 16px; }
  .view { padding: 18px 14px; }
  .search input { width: 140px; }
}
@media(max-width:768px) {
  .row.r-2 { grid-template-columns: 1fr; }
  .kpis { grid-template-columns: repeat(2, 1fr); }
}
@media(max-width:600px) {
  .leads-table th:nth-child(n+5), .leads-table td:nth-child(n+5) { display: none; }
  .drawer { width: 100%; max-width: 100vw; }
  .filters { flex-direction: column; }
}
@media(max-width:420px) { .search input { width: 108px; } }
</style>
</head>
<body>

<!-- Login -->
<div id="loginOverlay" class="login-overlay">
<div class="login-box">
  <h2>CRM שיטת שרמן</h2>
  <p>ניהול לידים ומעקב לקוחות</p>
  <div class="pass-wrapper">
    <input type="password" id="loginPass" placeholder="סיסמה" onkeydown="if(event.key==='Enter')doLogin()">
    <button type="button" class="eye-toggle" id="eyeBtn" onclick="togglePassView()">&#x1F441;</button>
  </div>
  <div class="login-error" id="loginError"></div>
  <button class="login-btn" onclick="doLogin()">כניסה</button>
</div>
</div>

<div class="app">
<!-- Main content -->
<div class="main">
  <div class="topbar">
    <h1>CRM שיטת שרמן<small>ניהול לידים ומעקב לקוחות</small></h1>
    <div class="search"></div>
  </div>

  <!-- Dashboard -->
  <div id="tab-dashboard" class="view active">
    <div class="kpis" id="statsGrid"></div>
    <div class="row r-2">
      <div class="panel"><div class="panel-h"><h3>משפך שיווקי</h3></div><div id="funnelBars"></div></div>
      <div class="panel"><div class="panel-h"><h3>קורסים מובילים</h3></div><div id="topCourses"></div></div>
    </div>
    <div class="row r-2">
      <div class="panel"><div class="panel-h"><h3>פולואפים קרובים</h3></div><div id="followupsList"></div></div>
      <div class="panel"><div class="panel-h"><h3>דורשות תשומת לב</h3></div><div id="attentionList"></div></div>
    </div>
    <div class="row r-1">
      <div class="panel"><div class="panel-h"><h3>פעולות אחרונות</h3></div><div id="highlightsList"></div></div>
    </div>
  </div>

  <!-- Leads -->
  <div id="tab-leads" class="view">
    <div class="filters">
      <input type="text" id="searchInput" placeholder="חיפוש שם או טלפון..." oninput="loadLeads()">
      <select id="statusFilter" onchange="loadLeads()"><option value="">כל הסטטוסים</option></select>
      <select id="tagFilter" onchange="loadLeads()"><option value="">כל התגיות</option></select>
      <button class="btn btn-pink" onclick="showNewLeadModal()">+ ליד חדש</button>
      <button class="btn btn-outline btn-small" onclick="exportCSV()">CSV יצוא</button>
    </div>
    <div class="bulk-bar" id="bulkBar">
      <span id="bulkCount">0</span> נבחרו
      <select id="bulkStatus" style="padding:5px 10px;border:1px solid var(--border);border-radius:9px;font-family:inherit"></select>
      <button class="btn btn-blue btn-small" onclick="applyBulkStatus()">עדכן סטטוס</button>
      <button class="btn btn-outline btn-small" onclick="clearBulk()">ביטול</button>
    </div>
    <div class="leads-table" id="leadsTable"></div>
  </div>

  <!-- Purchases -->
  <div id="tab-purchases" class="view">
    <div style="margin-bottom:16px"><button class="btn btn-green" onclick="showNewPurchaseModal()">+ רכישה חדשה</button></div>
    <div class="purchases-table" id="purchasesTable"></div>
  </div>

  <!-- Settings -->
  <div id="tab-settings" class="view">
    <div class="settings-section">
      <h3>סטטוסים</h3>
      <div id="settingsStatuses"></div>
      <button class="btn btn-outline btn-small" style="margin-top:8px" onclick="addSettingItem('statuses')">+ הוסף סטטוס</button>
    </div>
    <div class="settings-section">
      <h3>תגיות</h3>
      <div id="settingsTags"></div>
      <button class="btn btn-outline btn-small" style="margin-top:8px" onclick="addSettingItem('tags')">+ הוסף תגית</button>
    </div>
    <div class="settings-section">
      <h3>מקורות לידים</h3>
      <div id="settingsSources"></div>
      <button class="btn btn-outline btn-small" style="margin-top:8px" onclick="addSettingItem('sources')">+ הוסף מקור</button>
    </div>
    <button class="btn btn-pink" style="margin-top:16px" onclick="saveSettings()">שמור הגדרות</button>
  </div>
</div>

<!-- Sidebar -->
<aside class="sidebar">
  <div class="logo">
    <div class="mark">S</div>
    <div class="logo-text"><b>שיטת שרמן</b><span>CRM ניהול לקוחות</span></div>
  </div>
  <div class="nav-group">ראשי</div>
  <button class="nav-item active" onclick="showTab('dashboard',this)">
    <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    דשבורד
  </button>
  <button class="nav-item" onclick="showTab('leads',this)">
    <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
    לידים
  </button>
  <button class="nav-item" onclick="showTab('purchases',this)">
    <svg viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>
    רכישות
  </button>
  <div class="nav-group">הגדרות</div>
  <button class="nav-item" onclick="showTab('settings',this)">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    הגדרות
  </button>
  <div class="side-foot">
    <a href="/admin">
      <svg viewBox="0 0 24 24" width="19" height="19" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
      ניהול תוכן
    </a>
  </div>
</aside>
</div>

<!-- Mobile bottom tabs -->
<div class="tabbar">
  <div class="tab active" onclick="showTabMobile('dashboard',this)">
    <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    דשבורד
  </div>
  <div class="tab" onclick="showTabMobile('leads',this)">
    <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
    לידים
  </div>
  <div class="tab" onclick="showTabMobile('purchases',this)">
    <svg viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>
    רכישות
  </div>
  <div class="tab" onclick="showTabMobile('settings',this)">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33"/></svg>
    הגדרות
  </div>
</div>

<!-- Drawer overlay -->
<div class="overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
<div class="drawer" id="leadDrawer"></div>

<div class="toast" id="toast"></div>

<script>
const API = '/crm/api';
let currentTab = 'dashboard';
let allCourses = [];
let settings = { statuses: [], tags: [], sources: [] };
let selectedLeads = new Set();

// XSS protection — escape HTML in all user-supplied data
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

// Auth
function togglePassView() {
  var inp = document.getElementById('loginPass');
  var btn = document.getElementById('eyeBtn');
  if (inp.type === 'password') {
    inp.type = 'text';
    btn.innerHTML = '&#x1F648;';
  } else {
    inp.type = 'password';
    btn.innerHTML = '&#x1F441;';
  }
  inp.focus();
}
async function doLogin() {
  var pass = document.getElementById('loginPass').value.trim();
  var errEl = document.getElementById('loginError');
  errEl.textContent = '';
  if (!pass) { errEl.textContent = 'הקלד סיסמה'; return; }
  try {
    var r = await fetch('/admin/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: pass}),
      credentials: 'same-origin'
    });
    if (r.ok) { document.getElementById('loginOverlay').style.display = 'none'; init(); }
    else { errEl.textContent = 'סיסמה שגויה'; }
  } catch(e) { errEl.textContent = 'שגיאת חיבור'; }
}
(async()=>{
  try { const r=await fetch(API+'/dashboard'); if(r.ok){document.getElementById('loginOverlay').style.display='none';init();} } catch(e){}
})();

async function init() {
  const [courses, s] = await Promise.all([apiFetch('/courses-list'), apiFetch('/settings')]);
  allCourses = courses || [];
  if (s) {
    settings.statuses = s.statuses || [];
    settings.tags = s.tags || [];
    settings.sources = s.sources || [];
  }
  populateFilters();
  loadDashboard();
}

async function apiFetch(path, opts={}) {
  const r = await fetch(API+path, opts);
  if (r.status===401) { document.getElementById('loginOverlay').style.display='flex'; return null; }
  if (!r.ok) return null;
  return r.json();
}

function showTab(tab, navBtn) {
  document.querySelectorAll('.sidebar .nav-item').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.view').forEach(d=>{d.classList.remove('active');d.style.display='none';});
  if (navBtn) navBtn.classList.add('active');
  else document.querySelectorAll('.sidebar .nav-item').forEach(b=>{if(b.textContent.trim()&&b.onclick&&b.onclick.toString().includes("'"+tab+"'"))b.classList.add('active');});
  var el = document.getElementById('tab-'+tab);
  if (el) { el.style.display='block'; el.classList.add('active'); }
  currentTab = tab;
  if (tab==='dashboard') loadDashboard();
  if (tab==='leads') loadLeads();
  if (tab==='purchases') loadPurchases();
  if (tab==='settings') renderSettings();
}

function showTabMobile(tab, el) {
  document.querySelectorAll('.tabbar .tab').forEach(t=>t.classList.remove('active'));
  if (el) el.classList.add('active');
  showTab(tab);
}

function goToLeads(statusFilter) {
  document.querySelectorAll('.view').forEach(d=>{d.classList.remove('active');d.style.display='none';});
  var el = document.getElementById('tab-leads');
  el.style.display='block'; el.classList.add('active');
  document.querySelectorAll('.sidebar .nav-item').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.sidebar .nav-item')[1]?.classList.add('active');
  currentTab = 'leads';
  if (statusFilter) document.getElementById('statusFilter').value = statusFilter;
  else document.getElementById('statusFilter').value = '';
  loadLeads();
}

function goToPurchases() {
  document.querySelectorAll('.view').forEach(d=>{d.classList.remove('active');d.style.display='none';});
  var el = document.getElementById('tab-purchases');
  el.style.display='block'; el.classList.add('active');
  document.querySelectorAll('.sidebar .nav-item').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.sidebar .nav-item')[2]?.classList.add('active');
  currentTab = 'purchases';
  loadPurchases();
}

function toast(msg) {
  const t=document.getElementById('toast');t.textContent=msg;t.classList.add('visible');
  setTimeout(()=>t.classList.remove('visible'),2500);
}

function fmtDate(iso) { if(!iso)return'—'; const d=new Date(iso); return d.toLocaleDateString('he-IL')+' '+d.toLocaleTimeString('he-IL',{hour:'2-digit',minute:'2-digit'}); }
function fmtShortDate(iso) { if(!iso)return'—'; return new Date(iso).toLocaleDateString('he-IL'); }

function buildChatWithSessions(msgs) {
  if (!msgs.length) return '';
  const SESSION_GAP_MS = 2 * 60 * 60 * 1000; // 2 hours
  // Split into sessions
  const sessions = [];
  let cur = { msgs: [msgs[0]], start: msgs[0].created_at };
  for (let i = 1; i < msgs.length; i++) {
    if (new Date(msgs[i].created_at) - new Date(msgs[i-1].created_at) > SESSION_GAP_MS) {
      sessions.push(cur);
      cur = { msgs: [msgs[i]], start: msgs[i].created_at };
    } else {
      cur.msgs.push(msgs[i]);
    }
  }
  sessions.push(cur);
  // Reverse: newest first
  sessions.reverse();
  // Number sessions: 1 = newest
  let html = '';
  for (let si = 0; si < sessions.length; si++) {
    const s = sessions[si];
    const num = sessions.length - si;
    const isLatest = si === 0;
    const collapsed = !isLatest;
    const id = 'session_' + num;
    html += '<div class="session-block">';
    html += '<div class="session-header' + (collapsed ? ' collapsed' : '') + '" onclick="toggleSession(' + "'" + id + "'" + ', this)">';
    html += '<span><span class="arrow">' + (collapsed ? '◀' : '▼') + '</span> שיחה ' + num + ' — ' + fmtDate(s.start) + ' (' + s.msgs.length + ' הודעות)</span></div>';
    html += '<div id="' + id + '" class="session-messages' + (collapsed ? ' collapsed' : '') + '">';
    for (const m of s.msgs) {
      html += '<div class="chat-msg ' + m.role + '"><div>' + escapeHtml(m.content) + '</div><div class="time">' + fmtDate(m.created_at) + '</div></div>';
    }
    html += '</div></div>';
  }
  return html;
}

function toggleSession(id, header) {
  var el = document.getElementById(id);
  el.classList.toggle('collapsed');
  header.classList.toggle('collapsed');
  var arrow = header.querySelector('.arrow');
  if (arrow) arrow.textContent = el.classList.contains('collapsed') ? '\u25C0' : '\u25BC';
}

function getStatusColor(key) {
  const s = settings.statuses.find(s=>s.key===key);
  return s ? s.color : '#95a5a6';
}
function getStatusLabel(key) {
  const s = settings.statuses.find(s=>s.key===key);
  return s ? (s.label || s.key) : key;
}
function getTagColor(key) {
  const t = settings.tags.find(t=>t.key===key);
  return t ? t.color : '#95a5a6';
}
function getSourceLabel(key) {
  const s = settings.sources.find(s=>s.key===key);
  return s ? s.label : key;
}
function getAvatarColor(name) {
  const colors = ['#019D76','#F38120','#4F94C4','#EF5B3C','#F3A712','#8B5CF6','#14B8A6','#017a5c'];
  let h = 0; for(let i=0;i<(name||'').length;i++) h = name.charCodeAt(i) + ((h<<5)-h);
  return colors[Math.abs(h) % colors.length];
}
function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\\s+/);
  return parts.length > 1 ? (parts[0][0]+parts[1][0]) : name.slice(0,2);
}

function populateFilters() {
  const sf = document.getElementById('statusFilter');
  sf.innerHTML = '<option value="">כל הסטטוסים</option>' + settings.statuses.map(s=>`<option value="${s.key}">${s.label||s.key}</option>`).join('');
  const tf = document.getElementById('tagFilter');
  tf.innerHTML = '<option value="">כל התגיות</option>' + settings.tags.map(t=>`<option value="${t.key}">${t.key}</option>`).join('');
  const bs = document.getElementById('bulkStatus');
  bs.innerHTML = settings.statuses.map(s=>`<option value="${s.key}">${s.label||s.key}</option>`).join('');
}

// Dashboard
async function loadDashboard() {
  const d = await apiFetch('/dashboard');
  if(!d) return;
  document.getElementById('statsGrid').innerHTML = `
    <div class="kpi" onclick="goToLeads()"><div class="ic">👥</div><div class="lbl">סה"כ לידים</div><div class="val">${d.total_leads}</div></div>
    <div class="kpi" onclick="goToLeads('חדש')"><div class="ic">✨</div><div class="lbl">חדשים החודש</div><div class="val">${d.new_this_month}</div></div>
    <div class="kpi" onclick="goToPurchases()"><div class="ic">💰</div><div class="lbl">הכנסות החודש</div><div class="val">${d.month_revenue.toLocaleString()}₪</div></div>
    <div class="kpi" onclick="goToLeads('נרשמה')"><div class="ic">📊</div><div class="lbl">שיעור המרה</div><div class="val">${d.conversion_rate}%</div></div>
    <div class="kpi" onclick="goToPurchases()"><div class="ic">🏦</div><div class="lbl">הכנסות סה"כ</div><div class="val">${d.total_revenue.toLocaleString()}₪</div></div>
  `;

  // Funnel from settings
  const orderedStatuses = settings.statuses.sort((a,b)=>(a.order||0)-(b.order||0));
  const maxCount = Math.max(...orderedStatuses.map(s=>d.funnel[s.key]||0), 1);
  const funnelColors = ['linear-gradient(90deg,var(--green),var(--green-dark))','linear-gradient(90deg,#1aa885,#0c8a6a)','linear-gradient(90deg,var(--warm),#e08e0a)','linear-gradient(90deg,var(--orange),#dd6f12)','linear-gradient(90deg,var(--hot),#d44429)'];
  document.getElementById('funnelBars').innerHTML = '<div class="funnel">'+orderedStatuses.map((s,i)=>{
    const count = d.funnel[s.key]||0;
    const pct = Math.max(count/maxCount*100, 25);
    return `<div class="fn" style="width:${pct}%;background:${s.color?s.color:''};background:${funnelColors[i%funnelColors.length]};cursor:pointer" onclick="goToLeads('${s.key}')">
      <small>${s.label||s.key}</small><b>${count}</b>
    </div>`;
  }).join('')+'</div>';

  // Top courses
  const tc = d.top_courses || [];
  document.getElementById('topCourses').innerHTML = tc.length ? tc.map(c=>
    `<div class="course-row"><span class="c-name">${c.name}</span><span class="c-amount">${c.revenue.toLocaleString()}₪</span></div>`
  ).join('') : '<div class="empty-state"><div class="icon">📚</div><p>אין רכישות עדיין</p></div>';

  // Followups
  document.getElementById('followupsList').innerHTML = (d.upcoming_followups||[]).map(l=>
    `<div class="list-item" onclick="openLead('${escapeHtml(l.phone)}')"><span class="name">${escapeHtml(l.name||l.phone)}</span><span class="meta">${fmtShortDate(l.next_followup)}</span></div>`
  ).join('') || '<div class="empty-state"><div class="icon">📅</div><p>אין פולואפים מתוכננים</p></div>';

  // Needs attention
  document.getElementById('attentionList').innerHTML = (d.needs_attention||[]).map(l=>
    `<div class="list-item" onclick="openLead('${escapeHtml(l.phone)}')"><span class="name">${escapeHtml(l.name||l.phone)}</span><span class="attention-badge">לא פעילה 7+ ימים</span></div>`
  ).join('') || '<div class="empty-state"><div class="icon">✅</div><p>הכל מעודכן</p></div>';

  // Highlights
  const highlights = await apiFetch('/highlights');
  if (highlights) {
    document.getElementById('highlightsList').innerHTML = highlights.length ? highlights.map(e => {
      let data = {};
      try { data = typeof e.event_data === 'string' ? JSON.parse(e.event_data || '{}') : (e.event_data || {}); } catch(x) {}
      const name = escapeHtml(e.lead_name || e.lead_phone_display || '');
      const phone = escapeHtml(e.lead_phone_display || '');
      let icon = '', text = '';
      if (e.event_type === 'purchase') {
        icon = '💰';
        text = '<b>' + name + '</b> רכשה "' + escapeHtml(data.course || '') + '" — ' + escapeHtml(String(data.amount || '')) + '₪';
      } else if (e.event_type === 'new_lead') {
        icon = '👤';
        text = 'ליד חדש: <b>' + name + '</b> (' + phone + ')';
      } else if (e.event_type === 'handoff') {
        icon = '🔄';
        text = 'העברה למירב: <b>' + name + '</b>' + (data.reason ? ' — "' + escapeHtml(data.reason) + '"' : '');
      }
      return '<div class="list-item" style="cursor:pointer" onclick="openLead(' + "'" + phone + "'" + ')"><span class="highlight-icon">' + icon + '</span><span class="highlight-text">' + text + '</span><span class="meta">' + fmtDate(e.created_at) + '</span></div>';
    }).join('') : '<div class="empty-state"><div class="icon">📌</div><p>אין פעולות אחרונות</p></div>';
  }
}

// Activity indicator based on last_contact
function activityDot(lastContact) {
  if (!lastContact) return '<span class="activity-dot cold"></span>';
  const days = (Date.now() - new Date(lastContact).getTime()) / 86400000;
  if (days < 3) return '<span class="activity-dot hot" title="פעילה"></span>';
  if (days < 7) return '<span class="activity-dot warm" title="חמה"></span>';
  return '<span class="activity-dot cold" title="קרה"></span>';
}

// Leads
async function loadLeads() {
  const search = document.getElementById('searchInput')?.value||'';
  const status = document.getElementById('statusFilter')?.value||'';
  const tag = document.getElementById('tagFilter')?.value||'';
  const leads = await apiFetch(`/leads?search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}&tag=${encodeURIComponent(tag)}`);
  if(!leads) return;
  selectedLeads.clear();
  updateBulkBar();

  document.getElementById('leadsTable').innerHTML = leads.length ? `<table>
    <tr>
      <th style="width:30px"><input type="checkbox" onchange="toggleAllLeads(this,${JSON.stringify(leads.map(l=>l.phone)).replace(/"/g,'&quot;')})"></th>
      <th>שם</th><th>טלפון</th><th>סטטוס</th><th>דיוור</th><th>תגיות</th><th>פעילות</th><th>אחרון</th><th>פולואפ</th>
    </tr>
    ${leads.map(l=>`<tr onclick="openLead('${escapeHtml(l.phone)}')">
      <td onclick="event.stopPropagation()"><input type="checkbox" value="${escapeHtml(l.phone)}" onchange="toggleLeadSelect(this)"></td>
      <td><div class="lead-name-cell"><div class="lead-row-avatar" style="background:${getAvatarColor(l.name)}">${escapeHtml(getInitials(l.name))}</div>${escapeHtml(l.name||'—')}</div></td>
      <td dir="ltr">${escapeHtml(l.phone)}</td>
      <td><span class="status-badge" style="background:${getStatusColor(l.status)}20;color:${getStatusColor(l.status)}">${escapeHtml(getStatusLabel(l.status))}</span></td>
      <td><span style="font-size:.75rem;padding:2px 8px;border-radius:12px;${l.opt_in_marketing?'background:#e8f5e9;color:#2e7d32':(l.opt_in_date||l.opt_out_date?'background:#fce4ec;color:#c62828':'background:#fff3e0;color:#e65100')}">${l.opt_in_marketing?'V':(l.opt_in_date||l.opt_out_date?'X':'?')}</span></td>
      <td>${(l.tags||[]).map(t=>`<span class="tag" style="background:${getTagColor(t)}20;color:${getTagColor(t)}">${escapeHtml(t)}</span>`).join('')}</td>
      <td>${activityDot(l.last_contact)}</td>
      <td>${fmtShortDate(l.last_contact)}</td>
      <td>${fmtShortDate(l.next_followup)}</td>
    </tr>`).join('')}
  </table>` : '<div class="empty-state"><div class="icon">👥</div><p>אין לידים</p></div>';
}

function toggleLeadSelect(cb) {
  if(cb.checked) selectedLeads.add(cb.value); else selectedLeads.delete(cb.value);
  updateBulkBar();
}
function toggleAllLeads(cb, phones) {
  document.querySelectorAll('#leadsTable input[type=checkbox][value]').forEach(c=>{c.checked=cb.checked;});
  if(cb.checked) phones.forEach(p=>selectedLeads.add(p)); else selectedLeads.clear();
  updateBulkBar();
}
function updateBulkBar() {
  const bar = document.getElementById('bulkBar');
  if(selectedLeads.size>0) { bar.classList.add('visible'); document.getElementById('bulkCount').textContent=selectedLeads.size; }
  else bar.classList.remove('visible');
}
function clearBulk() { selectedLeads.clear(); document.querySelectorAll('#leadsTable input[type=checkbox]').forEach(c=>c.checked=false); updateBulkBar(); }
async function applyBulkStatus() {
  const status = document.getElementById('bulkStatus').value;
  await apiFetch('/leads/bulk-status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phones:[...selectedLeads],status})});
  toast(`עודכנו ${selectedLeads.size} לידים`);
  loadLeads();
}
function exportCSV() { window.open(API+'/leads-export','_blank'); }

// Lead detail drawer
function closeDrawer() {
  document.getElementById('drawerOverlay').classList.remove('open');
  document.getElementById('leadDrawer').classList.remove('open');
}

async function openLead(phone) {
  const [lead, timeline, convos, purchases] = await Promise.all([
    apiFetch(`/leads/${phone}`),
    apiFetch(`/leads/${phone}/timeline`),
    apiFetch(`/leads/${phone}/conversations?limit=1000`),
    apiFetch(`/purchases?lead_phone=${phone}`),
  ]);
  if(!lead) return;

  const leadTags = lead.tags||[];
  const drawer = document.getElementById('leadDrawer');

  drawer.innerHTML = `
    <div class="dr-head">
      <div class="dr-close" onclick="closeDrawer()">&times;</div>
      <div class="dav" style="background:rgba(255,255,255,.2)">${escapeHtml(getInitials(lead.name))}</div>
      <h2>${escapeHtml(lead.name||lead.phone)}</h2>
      <div class="meta">
        <span class="mchip" style="direction:ltr">${escapeHtml(lead.phone)}</span>
        <span class="mchip" style="background:${getStatusColor(lead.status)}40">${escapeHtml(getStatusLabel(lead.status))}</span>
        ${lead.lead_score ? '<span class="mchip">ניקוד: '+lead.lead_score+'</span>' : ''}
      </div>
    </div>
    <div class="dr-tabs">
      <button class="active" onclick="showDrawerTab(this,'dtab-details')">פרטים</button>
      <button onclick="showDrawerTab(this,'dtab-timeline')">ציר זמן (${timeline?.length||0})</button>
      <button onclick="showDrawerTab(this,'dtab-chat')">שיחה (${convos?.length||0})</button>
      <button onclick="showDrawerTab(this,'dtab-purchases')">רכישות (${purchases?.length||0})</button>
    </div>
    <div class="dr-body">
      <!-- Details tab -->
      <div id="dtab-details">
        <div class="dr-card">
          <h4>פרטי ליד</h4>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div class="field-group">
              <label>סטטוס</label>
              <select onchange="updateField('${phone}','status',this.value)">
                ${settings.statuses.map(s=>`<option value="${s.key}" ${s.key===lead.status?'selected':''}>${s.label||s.key}</option>`).join('')}
              </select>
            </div>
            <div class="field-group">
              <label>מקור</label>
              <select onchange="updateField('${phone}','source',this.value)">
                ${settings.sources.map(s=>`<option value="${s.key}" ${s.key===lead.source?'selected':''}>${s.label||s.key}</option>`).join('')}
              </select>
            </div>
            <div class="field-group">
              <label>שם</label>
              <input value="${lead.name||''}" onblur="updateField('${phone}','name',this.value)">
            </div>
            <div class="field-group">
              <label>פולואפ הבא</label>
              <input type="datetime-local" value="${lead.next_followup?lead.next_followup.slice(0,16):''}" onchange="updateField('${phone}','next_followup',this.value?new Date(this.value).toISOString():null)">
            </div>
          </div>
        </div>
        <div class="dr-card">
          <h4>תגיות</h4>
          <div class="tags-container">
            ${settings.tags.map(t=>`<span class="tag-toggle ${leadTags.includes(t.key)?'active':''}" style="${leadTags.includes(t.key)?'border-color:'+t.color+';background:'+t.color+'20;color:'+t.color:''}" onclick="toggleTag(this,'${phone}','${t.key}','${t.color}')">${t.key}</span>`).join('')}
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">
          <div style="padding:8px;border-radius:11px;font-size:12px;text-align:center;font-weight:700;${lead.opt_in_marketing?'background:var(--green-soft);border:1px solid var(--green);color:var(--green-dark)':(lead.opt_in_date||lead.opt_out_date?'background:var(--hot-soft);border:1px solid var(--hot);color:var(--hot)':'background:var(--warm-soft);border:1px solid var(--warm);color:#b97a06')}">${lead.opt_in_marketing?'דיוור: מאושר':(lead.opt_in_date||lead.opt_out_date?'דיוור: לא מאושר':'דיוור: לא נשאלה')}</div>
          <div style="padding:8px;border-radius:11px;font-size:12px;text-align:center;font-weight:700;background:var(--cold-soft);border:1px solid var(--cold);color:#2f6f9e">ניקוד: ${lead.lead_score||0}</div>
          <div style="padding:8px;border-radius:11px;font-size:12px;text-align:center;font-weight:700;cursor:pointer;${lead.followup_stopped?'background:var(--warm-soft);border:1px solid var(--warm);color:#b97a06':'background:var(--bg);border:1px solid var(--border);color:var(--muted)'}" onclick="toggleFollowupStop('${phone}',${!lead.followup_stopped})" title="לחצי כדי ${lead.followup_stopped?'להפעיל':'לעצור'} הודעות מעקב">${lead.followup_stopped?'מעקב: מושהה':'מעקב: פעיל'}</div>
        </div>
        <div class="dr-card">
          <h4>הערות</h4>
          <div class="field-group" style="margin-bottom:0">
            <textarea onblur="updateField('${phone}','notes',this.value)" style="min-height:60px">${lead.notes||''}</textarea>
          </div>
        </div>
        ${lead.ai_summary ? '<div class="dr-card" style="border-right:3px solid var(--cold)"><h4>סיכום AI</h4><p style="font-size:13px;line-height:1.5;font-weight:600">'+escapeHtml(lead.ai_summary)+'</p></div>' : ''}
        ${lead.conversation_summary ? '<div class="dr-card" style="border-right:3px solid var(--green)"><h4>הערות מירב</h4><p style="font-size:13px;line-height:1.5;font-weight:600">'+escapeHtml(lead.conversation_summary)+'</p></div>' : ''}
        <div style="text-align:center;color:var(--muted-2);font-size:12px;margin-top:16px;font-weight:600">
          קשר ראשון: ${fmtDate(lead.first_contact)} &bull; סה"כ שולם: ${lead.total_paid||0}₪
        </div>
      </div>

      <!-- Timeline tab -->
      <div id="dtab-timeline" style="display:none">
        <div class="timeline">
          ${(timeline||[]).map(e=>{
            const cls = e.event_type;
            let icon='📝', text='';
            const data = typeof e.event_data === 'string' ? JSON.parse(e.event_data||'{}') : (e.event_data||{});
            if(cls==='handoff'){icon='🔄';text='העברה למירב: '+(data.reason||'')}
            else if(cls==='purchase'){icon='💰';text='רכישה: '+(data.course||'')+' — '+(data.amount||'')+'₪'}
            else if(cls==='status_change'){icon='📊';text=(data.from||'—')+' → '+(data.to||'—')}
            else if(cls==='note'){icon='📝';text=data.text||''}
            else{text=JSON.stringify(data)}
            return '<div class="timeline-item"><div class="timeline-dot '+cls+'">'+icon+'</div><div class="timeline-content"><div class="time">'+fmtDate(e.created_at)+'</div>'+text+'</div></div>';
          }).join('')}
        </div>
        ${!timeline?.length ? '<div class="empty-state"><div class="icon">📋</div><p>אין אירועים</p></div>' : ''}
      </div>

      <!-- Chat tab -->
      <div id="dtab-chat" style="display:none">
        ${lead.ai_summary ? '<div class="dr-card" style="border-right:3px solid var(--cold);margin-bottom:12px"><h4>סיכום AI (אוטומטי)</h4><p style="font-size:13px;line-height:1.5;font-weight:600">'+escapeHtml(lead.ai_summary)+'</p></div>' : ''}
        <div class="field-group" style="margin-bottom:14px">
          <label style="font-weight:700;color:var(--green-dark)">הערות שלי על השיחה</label>
          <textarea style="min-height:60px;background:var(--green-soft);border-color:var(--green)" placeholder="מה יצא מהשיחה? למה מחכים? מה הצעד הבא?" onblur="updateField('${phone}','conversation_summary',this.value)">${lead.conversation_summary||''}</textarea>
        </div>
        <div class="chat-view">
          ${buildChatWithSessions(convos||[])}
        </div>
        ${!convos?.length ? '<div class="empty-state"><div class="icon">💬</div><p>אין שיחות</p></div>' : ''}
      </div>

      <!-- Purchases tab -->
      <div id="dtab-purchases" style="display:none">
        ${(purchases||[]).map(p=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid var(--border-2)">
          <span style="font-weight:700;font-size:13.5px">${p.course_name}</span><span style="font-weight:800;color:var(--green-dark)">${p.amount}₪</span><span style="color:var(--muted);font-size:12px;font-weight:600">${fmtShortDate(p.purchased_at)}</span>
        </div>`).join('')}
        <button class="btn btn-green btn-small" style="margin-top:12px" onclick="showPurchaseForLead('${phone}')">+ הוסף רכישה</button>
        ${!purchases?.length ? '<div class="empty-state"><div class="icon">🛒</div><p>אין רכישות</p></div>' : ''}
      </div>
    </div>
  `;

  // Open drawer
  document.getElementById('drawerOverlay').classList.add('open');
  drawer.classList.add('open');
}

function showDrawerTab(btn, tabId) {
  btn.closest('.drawer').querySelectorAll('.dr-tabs button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const body = btn.closest('.drawer').querySelector('.dr-body');
  body.querySelectorAll(':scope > div').forEach(d=>d.style.display='none');
  body.querySelector('#'+tabId).style.display='block';
}

async function updateField(phone, field, value) {
  const body = {};
  if (field==='tags') body.tags = value;
  else body[field] = value;
  await apiFetch(`/leads/${phone}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  toast('עודכן!');
}

async function toggleTag(el, phone, tag, color) {
  el.classList.toggle('active');
  if(el.classList.contains('active')) { el.style.borderColor=color; el.style.background=color+'20'; el.style.color=color; }
  else { el.style.borderColor=''; el.style.background=''; el.style.color=''; }
  const tags = [...el.parentElement.querySelectorAll('.tag-toggle.active')].map(t=>t.textContent);
  await updateField(phone, 'tags', tags);
}

async function toggleFollowupStop(phone, stopped) {
  await apiFetch(`/leads/${phone}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({followup_stopped:stopped})});
  toast(stopped ? 'הודעות מעקב הושהו' : 'הודעות מעקב הופעלו');
  closeDrawer();
  setTimeout(()=>openLead(phone), 350);
}

// New lead modal
function showNewLeadModal() {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal" style="max-width:420px">
    <div class="modal-header"><h2>ליד חדש</h2><button class="close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button></div>
    <div class="modal-body">
      <div class="field-group"><label>טלפון</label><input id="nl-phone" dir="ltr" placeholder="972501234567"></div>
      <div class="field-group"><label>שם</label><input id="nl-name"></div>
      <div class="field-group"><label>מקור</label>
        <select id="nl-source">${settings.sources.map(s=>`<option value="${s.key}">${s.label||s.key}</option>`).join('')}</select>
      </div>
      <button class="btn btn-pink" style="width:100%;margin-top:1rem" onclick="createLead()">צור ליד</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', e=>{ if(e.target===modal) modal.remove(); });
}

async function createLead() {
  const phone=document.getElementById('nl-phone').value.trim();
  const name=document.getElementById('nl-name').value.trim();
  const source=document.getElementById('nl-source').value;
  if(!phone){alert('חסר טלפון');return;}
  await apiFetch('/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone,name,source})});
  document.querySelector('.modal-overlay').remove();
  toast('ליד נוצר!');
  loadLeads();
}

// Purchases
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

function showNewPurchaseModal(prefillPhone='') {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal" style="max-width:420px">
    <div class="modal-header"><h2>רכישה חדשה</h2><button class="close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button></div>
    <div class="modal-body">
      <div class="field-group"><label>טלפון</label><input id="np-phone" dir="ltr" value="${prefillPhone}"></div>
      <div class="field-group"><label>קורס</label>
        <select id="np-course" onchange="npCourseChanged()">
          <option value="">בחרי קורס...</option>
          ${allCourses.map(c=>`<option value="${c.id}" data-name="${c.name}" data-price="${c.price}">${c.name} (${c.price})</option>`).join('')}
          <option value="custom">אחר</option>
        </select>
      </div>
      <div class="field-group"><label>שם קורס (אם אחר)</label><input id="np-cname"></div>
      <div class="field-group"><label>סכום (₪)</label><input id="np-amount" type="number"></div>
      <div class="field-group"><label>אמצעי תשלום</label>
        <select id="np-method">
          <option value="cardcom">Cardcom</option>
          <option value="transfer">העברה בנקאית</option>
          <option value="bit">ביט</option>
          <option value="cash">מזומן</option>
        </select>
      </div>
      <div class="field-group"><label>הערות</label><input id="np-notes"></div>
      <button class="btn btn-green" style="width:100%;margin-top:1rem" onclick="createPurchase()">שמור רכישה</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', e=>{ if(e.target===modal) modal.remove(); });
}

function showPurchaseForLead(phone) { showNewPurchaseModal(phone); }

function npCourseChanged() {
  const sel = document.getElementById('np-course');
  const opt = sel.options[sel.selectedIndex];
  if(opt.value && opt.value!=='custom') {
    document.getElementById('np-cname').value = opt.dataset.name||'';
    document.getElementById('np-amount').value = parseInt((opt.dataset.price||'0').replace(/[^0-9]/g,''))||'';
  }
}

async function createPurchase() {
  const phone=document.getElementById('np-phone').value.trim();
  const courseId=document.getElementById('np-course').value;
  const cname=document.getElementById('np-cname').value.trim();
  const amount=parseFloat(document.getElementById('np-amount').value);
  const notes=document.getElementById('np-notes').value;
  if(!phone||!amount){alert('חסר טלפון או סכום');return;}
  const method=document.getElementById('np-method').value;
  const body={lead_phone:phone, course_name:cname, amount, notes, payment_method:method};
  if(courseId&&courseId!=='custom') body.course_id=parseInt(courseId);
  await apiFetch('/purchases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  document.querySelector('.modal-overlay').remove();
  toast('רכישה נשמרה!');
  if(currentTab==='purchases') loadPurchases();
}

// Settings
function renderSettings() {
  renderSettingGroup('settingsStatuses', settings.statuses, 'statuses');
  renderSettingGroup('settingsTags', settings.tags, 'tags');
  renderSettingGroup('settingsSources', settings.sources, 'sources');
}

function renderSettingGroup(containerId, items, type) {
  const container = document.getElementById(containerId);
  container.innerHTML = items.map((item, i) => {
    if (type === 'statuses') {
      return `<div class="setting-item">
        <input type="color" class="color-dot" value="${item.color||'#95a5a6'}" onchange="settings.statuses[${i}].color=this.value" style="width:30px;height:30px;border:none;padding:0;cursor:pointer">
        <input value="${item.key}" onchange="settings.statuses[${i}].key=this.value;settings.statuses[${i}].label=this.value" placeholder="שם סטטוס">
        <input value="${item.order||i+1}" type="number" style="width:50px" onchange="settings.statuses[${i}].order=parseInt(this.value)">
        <span class="remove-btn" onclick="settings.statuses.splice(${i},1);renderSettings()">&times;</span>
      </div>`;
    } else if (type === 'tags') {
      return `<div class="setting-item">
        <input type="color" class="color-dot" value="${item.color||'#95a5a6'}" onchange="settings.tags[${i}].color=this.value" style="width:30px;height:30px;border:none;padding:0;cursor:pointer">
        <input value="${item.key}" onchange="settings.tags[${i}].key=this.value" placeholder="שם תגית">
        <span class="remove-btn" onclick="settings.tags.splice(${i},1);renderSettings()">&times;</span>
      </div>`;
    } else {
      return `<div class="setting-item">
        <input value="${item.key}" onchange="settings.sources[${i}].key=this.value" placeholder="מפתח" style="max-width:120px">
        <input value="${item.label||''}" onchange="settings.sources[${i}].label=this.value" placeholder="תווית תצוגה">
        <span class="remove-btn" onclick="settings.sources.splice(${i},1);renderSettings()">&times;</span>
      </div>`;
    }
  }).join('');
}

function addSettingItem(type) {
  if (type==='statuses') settings.statuses.push({key:'', label:'', color:'#95a5a6', order:settings.statuses.length+1});
  else if (type==='tags') settings.tags.push({key:'', color:'#95a5a6'});
  else settings.sources.push({key:'', label:''});
  renderSettings();
}

async function saveSettings() {
  // Filter out empty items
  settings.statuses = settings.statuses.filter(s=>s.key);
  settings.tags = settings.tags.filter(t=>t.key);
  settings.sources = settings.sources.filter(s=>s.key);

  await Promise.all([
    apiFetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({setting_key:'statuses',setting_value:settings.statuses})}),
    apiFetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({setting_key:'tags',setting_value:settings.tags})}),
    apiFetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({setting_key:'sources',setting_value:settings.sources})}),
  ]);
  populateFilters();
  toast('הגדרות נשמרו!');
}
</script>
</body>
</html>"""
