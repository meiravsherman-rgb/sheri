"""CRM panel — lead tracking, timeline, purchases, settings for Merav."""

import csv
import io
import json
import os
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
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
    phones: list[str]
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
    purchases = get_purchases(lead_phone)
    for p in purchases:
        p["lead_phone"] = display_phone(p.get("lead_phone", ""))
    return purchases


@router.post("/api/purchases", dependencies=[Depends(check_auth)])
async def api_create_purchase(req: NewPurchase):
    pid = create_purchase(req.lead_phone, req.course_name, req.amount,
                          req.course_id, req.payment_method, req.notes)
    log_lead_event(req.lead_phone, "purchase", {
        "course": req.course_name, "amount": req.amount
    })
    return {"id": pid}


@router.get("/api/courses-list", dependencies=[Depends(check_auth)])
async def api_courses_list():
    return [{"id": c["id"], "name": c["name"], "price": c["price"]}
            for c in get_all_courses() if c.get("is_active")]


@router.get("/api/settings", dependencies=[Depends(check_auth)])
async def api_get_settings():
    return get_crm_settings()


@router.post("/api/settings", dependencies=[Depends(check_auth)])
async def api_update_settings(req: SettingUpdate):
    update_crm_setting(req.setting_key, req.setting_value)
    return {"ok": True}


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
<style>
:root {
  --pink: #e91e8c; --pink-dark: #c2185b; --pink-light: #fce4f3; --pink-bg: #fff5fb;
  --green: #27ae60; --blue: #3498db; --orange: #f39c12; --red: #e74c3c;
  --gray: #95a5a6; --dark: #2c3e50; --bg: #f4f0f7;
  --purple: #9b59b6; --teal: #1abc9c;
  --shadow: 0 4px 15px rgba(0,0,0,.08);
  --shadow-hover: 0 8px 25px rgba(0,0,0,.12);
  --radius: 16px;
  --transition: all .3s cubic-bezier(.4,0,.2,1);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; background: var(--bg); color: var(--dark); direction: rtl; }

/* Login */
.login-overlay { position: fixed; inset: 0; background: linear-gradient(135deg, rgba(233,30,140,.9), rgba(194,24,91,.9)); display: flex; align-items: center; justify-content: center; z-index: 999; }
.login-box { background: #fff; padding: 2.5rem; border-radius: var(--radius); text-align: center; width: 340px; box-shadow: var(--shadow-hover); }
.login-box h2 { color: var(--pink); margin-bottom: .5rem; font-size: 1.5rem; }
.login-box p { color: #999; font-size: .85rem; margin-bottom: 1.5rem; }
.login-box .pass-wrapper { position: relative; margin-bottom: .5rem; direction: ltr; }
.login-box .pass-wrapper input { width: 100%; padding: .8rem 2.5rem .8rem .8rem; border: 2px solid #eee; border-radius: 12px; text-align: center; font-size: 1rem; outline: none; transition: var(--transition); }
.login-box .pass-wrapper input:focus { border-color: var(--pink); }
.login-box .eye-toggle { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: #f5f5f5; border: 1px solid #ddd; border-radius: 6px; cursor: pointer; font-size: 1rem; color: #666; padding: 4px 6px; line-height: 1; z-index: 2; }
.login-box .eye-toggle:hover { background: #eee; }
.login-box .login-error { color: var(--red); font-size: .85rem; margin-bottom: .5rem; min-height: 1.3em; font-weight: 600; }
.login-box .login-btn { background: linear-gradient(135deg, var(--pink), var(--pink-dark)); color: #fff; border: none; padding: .8rem 2rem; border-radius: 12px; cursor: pointer; font-size: 1rem; width: 100%; transition: var(--transition); }
.login-box .login-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(233,30,140,.4); }

/* Header */
header { background: linear-gradient(135deg, var(--pink), var(--pink-dark), #8e24aa); color: #fff; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 20px rgba(233,30,140,.3); }
header h1 { font-size: 1.4rem; font-weight: 700; }
header a { color: rgba(255,255,255,.85); text-decoration: none; font-size: .85rem; transition: var(--transition); }
header a:hover { color: #fff; }

/* Nav */
.nav { display: flex; gap: .3rem; background: #fff; padding: .6rem; border-bottom: 1px solid #eee; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.nav button { padding: .6rem 1.2rem; border: none; background: none; cursor: pointer; border-radius: 12px; font-size: .9rem; color: #888; font-weight: 500; transition: var(--transition); position: relative; }
.nav button:hover { color: var(--pink); background: var(--pink-bg); }
.nav button.active { background: linear-gradient(135deg, var(--pink), var(--pink-dark)); color: #fff; font-weight: 700; box-shadow: 0 2px 10px rgba(233,30,140,.3); }

.content { padding: 1.2rem; max-width: 1300px; margin: 0 auto; }
.hidden { display: none !important; }

/* Stat Cards */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.stat-card { background: #fff; border-radius: var(--radius); padding: 1.3rem; text-align: center; box-shadow: var(--shadow); position: relative; overflow: hidden; transition: var(--transition); }
.stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-hover); }
.stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px; }
.stat-card:nth-child(1)::before { background: linear-gradient(90deg, var(--pink), var(--purple)); }
.stat-card:nth-child(2)::before { background: linear-gradient(90deg, var(--blue), var(--teal)); }
.stat-card:nth-child(3)::before { background: linear-gradient(90deg, var(--green), var(--teal)); }
.stat-card:nth-child(4)::before { background: linear-gradient(90deg, var(--orange), var(--red)); }
.stat-card:nth-child(5)::before { background: linear-gradient(90deg, var(--purple), var(--pink)); }
.stat-card { cursor: pointer; }
.stat-card .icon { font-size: 1.8rem; margin-bottom: .3rem; }
.stat-card .number { font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, var(--pink), var(--purple)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.stat-card .label { color: #999; font-size: .82rem; margin-top: .3rem; }

/* Dashboard Grid */
.dash-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
.dash-card { background: #fff; border-radius: var(--radius); padding: 1.3rem; box-shadow: var(--shadow); }
.dash-card h3 { color: var(--dark); margin-bottom: 1rem; font-size: 1rem; display: flex; align-items: center; gap: .4rem; }

/* Funnel */
.funnel-step { display: flex; align-items: center; margin-bottom: .5rem; gap: .5rem; }
.funnel-step .f-label { min-width: 90px; font-size: .85rem; font-weight: 500; }
.funnel-step .f-bar-bg { flex: 1; height: 32px; background: #f0f0f0; border-radius: 8px; overflow: hidden; position: relative; }
.funnel-step .f-bar { height: 100%; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: .82rem; font-weight: 600; transition: width .8s cubic-bezier(.4,0,.2,1); min-width: 28px; }
.funnel-step .f-count { min-width: 30px; text-align: center; font-weight: 700; font-size: .9rem; }

/* Top Courses */
.course-row { display: flex; justify-content: space-between; align-items: center; padding: .5rem 0; border-bottom: 1px solid #f5f5f5; }
.course-row:last-child { border: none; }
.course-row .c-name { font-size: .85rem; flex: 1; }
.course-row .c-amount { font-weight: 700; color: var(--green); font-size: .9rem; }

/* Followups & Attention */
.list-item { display: flex; justify-content: space-between; align-items: center; padding: .6rem .4rem; border-bottom: 1px solid #f5f5f5; cursor: pointer; border-radius: 8px; transition: var(--transition); }
.list-item:hover { background: var(--pink-bg); }
.list-item .name { font-weight: 500; font-size: .88rem; }
.list-item .meta { font-size: .78rem; color: #999; }
.attention-badge { background: #fff3cd; color: #856404; padding: .15rem .5rem; border-radius: 6px; font-size: .72rem; font-weight: 600; }

/* Leads */
.filters { display: flex; gap: .5rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center; }
.filters input, .filters select { padding: .55rem .8rem; border: 2px solid #eee; border-radius: 12px; font-size: .9rem; outline: none; transition: var(--transition); }
.filters input:focus, .filters select:focus { border-color: var(--pink); }
.filters input { flex: 1; min-width: 150px; }

.btn { padding: .55rem 1.1rem; border: none; border-radius: 12px; cursor: pointer; font-size: .85rem; font-weight: 600; transition: var(--transition); display: inline-flex; align-items: center; gap: .3rem; }
.btn:hover { transform: translateY(-1px); }
.btn-pink { background: linear-gradient(135deg, var(--pink), var(--pink-dark)); color: #fff; box-shadow: 0 2px 8px rgba(233,30,140,.3); }
.btn-green { background: linear-gradient(135deg, var(--green), var(--teal)); color: #fff; }
.btn-blue { background: linear-gradient(135deg, var(--blue), #2471a3); color: #fff; }
.btn-outline { background: #fff; border: 2px solid #eee; color: #666; }
.btn-outline:hover { border-color: var(--pink); color: var(--pink); }
.btn-small { padding: .35rem .7rem; font-size: .78rem; }
.btn-icon { width: 36px; height: 36px; padding: 0; display: flex; align-items: center; justify-content: center; border-radius: 10px; }

/* Leads Table */
.leads-table { width: 100%; background: #fff; border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.leads-table table { width: 100%; border-collapse: collapse; }
.leads-table th { background: linear-gradient(180deg, #fafafa, #f5f5f5); padding: .8rem; text-align: right; font-size: .82rem; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; }
.leads-table td { padding: .75rem .8rem; border-top: 1px solid #f5f5f5; font-size: .88rem; }
.leads-table tr { transition: var(--transition); cursor: pointer; }
.leads-table tr:hover { background: var(--pink-bg); }

.lead-row-avatar { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: .85rem; flex-shrink: 0; }
.lead-name-cell { display: flex; align-items: center; gap: .5rem; }

.status-badge { padding: .25rem .7rem; border-radius: 20px; font-size: .75rem; font-weight: 700; white-space: nowrap; }
.tag { padding: .15rem .45rem; border-radius: 6px; font-size: .7rem; margin-left: .2rem; font-weight: 500; }
.activity-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.activity-dot.hot { background: var(--green); box-shadow: 0 0 6px rgba(39,174,96,.5); animation: pulse 2s infinite; }
.activity-dot.warm { background: var(--orange); }
.activity-dot.cold { background: var(--gray); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }

.bulk-bar { display: none; align-items: center; gap: .5rem; padding: .6rem 1rem; background: var(--pink-light); border-radius: 12px; margin-bottom: .8rem; }
.bulk-bar.visible { display: flex; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 100; backdrop-filter: blur(3px); animation: fadeIn .2s; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal { background: #fff; border-radius: var(--radius); width: 95%; max-width: 720px; max-height: 90vh; overflow-y: auto; animation: slideUp .3s; }
@keyframes slideUp { from { transform: translateY(30px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.modal-header { padding: 1.2rem 1.5rem; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; background: #fff; z-index: 1; border-radius: var(--radius) var(--radius) 0 0; }
.modal-header h2 { color: var(--pink); font-size: 1.2rem; display: flex; align-items: center; gap: .5rem; }
.modal-header .close-btn { background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #ccc; transition: var(--transition); width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.modal-header .close-btn:hover { background: #f5f5f5; color: #666; }
.modal-body { padding: 1.5rem; }
.modal-tabs { display: flex; gap: .2rem; padding: 0 1.5rem; background: #fafafa; border-bottom: 1px solid #f0f0f0; }
.modal-tabs button { padding: .6rem 1rem; border: none; background: none; cursor: pointer; font-size: .85rem; color: #888; border-bottom: 2px solid transparent; transition: var(--transition); }
.modal-tabs button.active { color: var(--pink); border-bottom-color: var(--pink); font-weight: 600; }

.field-group { margin-bottom: .8rem; }
.field-group label { display: block; font-size: .82rem; color: #888; margin-bottom: .3rem; font-weight: 500; }
.field-group input, .field-group select, .field-group textarea { width: 100%; padding: .55rem .8rem; border: 2px solid #eee; border-radius: 10px; font-size: .9rem; outline: none; transition: var(--transition); }
.field-group input:focus, .field-group select:focus, .field-group textarea:focus { border-color: var(--pink); }
.field-group textarea { min-height: 80px; resize: vertical; }

.tags-container { display: flex; flex-wrap: wrap; gap: .3rem; }
.tag-toggle { padding: .35rem .7rem; border: 2px solid #eee; border-radius: 20px; cursor: pointer; font-size: .8rem; background: #fff; transition: var(--transition); font-weight: 500; }
.tag-toggle:hover { border-color: #ccc; }
.tag-toggle.active { border-color: var(--pink); background: var(--pink-light); color: var(--pink); }

/* Timeline */
.timeline { margin-top: .5rem; }
.timeline-item { display: flex; gap: .6rem; padding: .6rem 0; border-bottom: 1px solid #f8f8f8; font-size: .85rem; }
.timeline-dot { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: .9rem; flex-shrink: 0; }
.timeline-dot.handoff { background: #fff3e0; }
.timeline-dot.purchase { background: #e8f5e9; }
.timeline-dot.status_change { background: #e3f2fd; }
.timeline-dot.note { background: #f3e5f5; }
.timeline-dot.message { background: #f5f5f5; }
.timeline-content { flex: 1; }
.timeline-content .time { color: #bbb; font-size: .72rem; }

/* Chat */
.chat-view { background: linear-gradient(180deg, #ece5dd, #d9d2c5); border-radius: 12px; padding: .8rem; max-height: 500px; overflow-y: auto; }
.chat-msg { margin-bottom: .4rem; padding: .5rem .8rem; border-radius: 8px; max-width: 78%; font-size: .85rem; position: relative; box-shadow: 0 1px 2px rgba(0,0,0,.1); }
.chat-msg.user { background: #dcf8c6; margin-left: auto; border-bottom-left-radius: 2px; }
.chat-msg.assistant { background: #fff; border-bottom-right-radius: 2px; }
.chat-msg .time { font-size: .68rem; color: #999; margin-top: .2rem; text-align: left; }
.session-block { margin-bottom: .5rem; }
.session-header { display: flex; align-items: center; gap: .6rem; margin: .6rem 0; cursor: pointer; user-select: none; }
.session-header::before, .session-header::after { content: ''; flex: 1; height: 1px; background: rgba(0,0,0,.2); }
.session-header span { background: rgba(0,0,0,.12); color: #555; font-size: .72rem; padding: .25rem .8rem; border-radius: 12px; white-space: nowrap; font-weight: 600; display: flex; align-items: center; gap: .3rem; }
.session-header .arrow { transition: transform .2s; font-size: .6rem; }
.session-header.collapsed .arrow { transform: rotate(-90deg); }
.session-messages { transition: max-height .3s ease; overflow: hidden; }
.session-messages.collapsed { max-height: 0 !important; }

/* Settings */
.settings-section { background: #fff; border-radius: var(--radius); padding: 1.3rem; box-shadow: var(--shadow); margin-bottom: 1rem; }
.settings-section h3 { color: var(--dark); margin-bottom: 1rem; font-size: 1rem; display: flex; align-items: center; gap: .4rem; }
.setting-item { display: flex; align-items: center; gap: .5rem; padding: .4rem 0; border-bottom: 1px solid #f8f8f8; }
.setting-item:last-child { border: none; }
.setting-item input { flex: 1; padding: .4rem .6rem; border: 1px solid #eee; border-radius: 8px; font-size: .85rem; }
.setting-item .color-dot { width: 24px; height: 24px; border-radius: 50%; cursor: pointer; border: 2px solid #fff; box-shadow: 0 0 0 1px #ddd; }
.setting-item .remove-btn { color: #ccc; cursor: pointer; font-size: 1.2rem; transition: var(--transition); }
.setting-item .remove-btn:hover { color: var(--red); }

/* Purchases table */
.purchases-table { width: 100%; background: #fff; border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.purchases-table table { width: 100%; border-collapse: collapse; }
.purchases-table th { background: linear-gradient(180deg, #fafafa, #f5f5f5); padding: .8rem; text-align: right; font-size: .82rem; color: #888; font-weight: 600; }
.purchases-table td { padding: .75rem .8rem; border-top: 1px solid #f5f5f5; font-size: .88rem; }

/* Toast */
.toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%) translateY(100px); background: linear-gradient(135deg, #333, #555); color: #fff; padding: .8rem 1.8rem; border-radius: 12px; z-index: 200; font-size: .9rem; box-shadow: 0 4px 15px rgba(0,0,0,.2); transition: transform .3s cubic-bezier(.4,0,.2,1); }
.toast.visible { transform: translateX(-50%) translateY(0); }

/* Empty state */
.empty-state { text-align: center; padding: 3rem 1rem; color: #ccc; }
.empty-state .icon { font-size: 3rem; margin-bottom: .5rem; }

/* Responsive */
@media (max-width: 768px) {
  .dash-grid { grid-template-columns: 1fr; }
  .stats-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 600px) {
  .leads-table th:nth-child(n+5), .leads-table td:nth-child(n+5) { display: none; }
  .stats-grid { grid-template-columns: 1fr 1fr; }
  .modal { width: 100%; border-radius: 0; max-height: 100vh; }
  .filters { flex-direction: column; }
  .nav { overflow-x: auto; }
  header h1 { font-size: 1.1rem; }
}
</style>
</head>
<body>

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

<header>
  <h1>CRM — שיטת שרמן</h1>
  <a href="/admin">ניהול תוכן &larr;</a>
</header>

<div class="nav">
  <button class="active" onclick="showTab('dashboard')">דשבורד</button>
  <button onclick="showTab('leads')">לידים</button>
  <button onclick="showTab('purchases')">רכישות</button>
  <button onclick="showTab('settings')">הגדרות</button>
</div>

<div class="content">
  <!-- Dashboard -->
  <div id="tab-dashboard">
    <div class="stats-grid" id="statsGrid"></div>
    <div class="dash-grid">
      <div class="dash-card"><h3>משפך שיווקי</h3><div id="funnelBars"></div></div>
      <div class="dash-card"><h3>קורסים מובילים</h3><div id="topCourses"></div></div>
    </div>
    <div class="dash-grid">
      <div class="dash-card"><h3>פולואפים קרובים</h3><div id="followupsList"></div></div>
      <div class="dash-card"><h3>דורשות תשומת לב</h3><div id="attentionList"></div></div>
    </div>
  </div>

  <!-- Leads -->
  <div id="tab-leads" class="hidden">
    <div class="filters">
      <input type="text" id="searchInput" placeholder="חיפוש שם או טלפון..." oninput="loadLeads()">
      <select id="statusFilter" onchange="loadLeads()"><option value="">כל הסטטוסים</option></select>
      <select id="tagFilter" onchange="loadLeads()"><option value="">כל התגיות</option></select>
      <button class="btn btn-pink" onclick="showNewLeadModal()">+ ליד חדש</button>
      <button class="btn btn-outline btn-small" onclick="exportCSV()">CSV יצוא</button>
    </div>
    <div class="bulk-bar" id="bulkBar">
      <span id="bulkCount">0</span> נבחרו
      <select id="bulkStatus"></select>
      <button class="btn btn-blue btn-small" onclick="applyBulkStatus()">עדכן סטטוס</button>
      <button class="btn btn-outline btn-small" onclick="clearBulk()">ביטול</button>
    </div>
    <div class="leads-table" id="leadsTable"></div>
  </div>

  <!-- Purchases -->
  <div id="tab-purchases" class="hidden">
    <div style="margin-bottom:1rem"><button class="btn btn-green" onclick="showNewPurchaseModal()">+ רכישה חדשה</button></div>
    <div class="purchases-table" id="purchasesTable"></div>
  </div>

  <!-- Settings -->
  <div id="tab-settings" class="hidden">
    <div class="settings-section">
      <h3>סטטוסים</h3>
      <div id="settingsStatuses"></div>
      <button class="btn btn-outline btn-small" style="margin-top:.5rem" onclick="addSettingItem('statuses')">+ הוסף סטטוס</button>
    </div>
    <div class="settings-section">
      <h3>תגיות</h3>
      <div id="settingsTags"></div>
      <button class="btn btn-outline btn-small" style="margin-top:.5rem" onclick="addSettingItem('tags')">+ הוסף תגית</button>
    </div>
    <div class="settings-section">
      <h3>מקורות לידים</h3>
      <div id="settingsSources"></div>
      <button class="btn btn-outline btn-small" style="margin-top:.5rem" onclick="addSettingItem('sources')">+ הוסף מקור</button>
    </div>
    <button class="btn btn-pink" style="margin-top:1rem" onclick="saveSettings()">שמור הגדרות</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API = '/crm/api';
let currentTab = 'dashboard';
let allCourses = [];
let settings = { statuses: [], tags: [], sources: [] };
let selectedLeads = new Set();

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

function showTab(tab) {
  document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(d=>d.classList.add('hidden'));
  event.target.classList.add('active');
  document.getElementById('tab-'+tab).classList.remove('hidden');
  currentTab = tab;
  if (tab==='dashboard') loadDashboard();
  if (tab==='leads') loadLeads();
  if (tab==='purchases') loadPurchases();
  if (tab==='settings') renderSettings();
}

function goToLeads(statusFilter) {
  // Switch to leads tab with optional status filter
  document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(d=>d.classList.add('hidden'));
  document.getElementById('tab-leads').classList.remove('hidden');
  document.querySelectorAll('.nav button')[1].classList.add('active');
  currentTab = 'leads';
  if (statusFilter) document.getElementById('statusFilter').value = statusFilter;
  else document.getElementById('statusFilter').value = '';
  loadLeads();
}

function goToPurchases() {
  document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(d=>d.classList.add('hidden'));
  document.getElementById('tab-purchases').classList.remove('hidden');
  document.querySelectorAll('.nav button')[2].classList.add('active');
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
      html += '<div class="chat-msg ' + m.role + '"><div>' + m.content + '</div><div class="time">' + fmtDate(m.created_at) + '</div></div>';
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
  const colors = ['#e91e8c','#9b59b6','#3498db','#1abc9c','#27ae60','#f39c12','#e74c3c','#2c3e50'];
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
    <div class="stat-card" onclick="goToLeads()"><div class="icon">👥</div><div class="number">${d.total_leads}</div><div class="label">סה"כ לידים</div></div>
    <div class="stat-card" onclick="goToLeads('חדש')"><div class="icon">✨</div><div class="number">${d.new_this_month}</div><div class="label">חדשים החודש</div></div>
    <div class="stat-card" onclick="goToPurchases()"><div class="icon">💰</div><div class="number">${d.month_revenue.toLocaleString()}₪</div><div class="label">הכנסות החודש</div></div>
    <div class="stat-card" onclick="goToLeads('נרשמה')"><div class="icon">📊</div><div class="number">${d.conversion_rate}%</div><div class="label">שיעור המרה</div></div>
    <div class="stat-card" onclick="goToPurchases()"><div class="icon">🏦</div><div class="number">${d.total_revenue.toLocaleString()}₪</div><div class="label">הכנסות סה"כ</div></div>
  `;

  // Funnel from settings
  const orderedStatuses = settings.statuses.sort((a,b)=>(a.order||0)-(b.order||0));
  const maxCount = Math.max(...orderedStatuses.map(s=>d.funnel[s.key]||0), 1);
  document.getElementById('funnelBars').innerHTML = orderedStatuses.map(s=>{
    const count = d.funnel[s.key]||0;
    const pct = Math.max(count/maxCount*100, 5);
    return `<div class="funnel-step" style="cursor:pointer" onclick="goToLeads('${s.key}')">
      <span class="f-label">${s.label||s.key}</span>
      <div class="f-bar-bg"><div class="f-bar" style="width:${pct}%;background:${s.color}">${count}</div></div>
    </div>`;
  }).join('');

  // Top courses
  const tc = d.top_courses || [];
  document.getElementById('topCourses').innerHTML = tc.length ? tc.map(c=>
    `<div class="course-row"><span class="c-name">${c.name}</span><span class="c-amount">${c.revenue.toLocaleString()}₪</span></div>`
  ).join('') : '<div class="empty-state"><div class="icon">📚</div><p>אין רכישות עדיין</p></div>';

  // Followups
  document.getElementById('followupsList').innerHTML = (d.upcoming_followups||[]).map(l=>
    `<div class="list-item" onclick="openLead('${l.phone}')"><span class="name">${l.name||l.phone}</span><span class="meta">${fmtShortDate(l.next_followup)}</span></div>`
  ).join('') || '<div class="empty-state"><div class="icon">📅</div><p>אין פולואפים מתוכננים</p></div>';

  // Needs attention
  document.getElementById('attentionList').innerHTML = (d.needs_attention||[]).map(l=>
    `<div class="list-item" onclick="openLead('${l.phone}')"><span class="name">${l.name||l.phone}</span><span class="attention-badge">לא פעילה 7+ ימים</span></div>`
  ).join('') || '<div class="empty-state"><div class="icon">✅</div><p>הכל מעודכן</p></div>';
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
      <th>שם</th><th>טלפון</th><th>סטטוס</th><th>תגיות</th><th>פעילות</th><th>אחרון</th><th>פולואפ</th>
    </tr>
    ${leads.map(l=>`<tr onclick="openLead('${l.phone}')">
      <td onclick="event.stopPropagation()"><input type="checkbox" value="${l.phone}" onchange="toggleLeadSelect(this)"></td>
      <td><div class="lead-name-cell"><div class="lead-row-avatar" style="background:${getAvatarColor(l.name)}">${getInitials(l.name)}</div>${l.name||'—'}</div></td>
      <td dir="ltr">${l.phone}</td>
      <td><span class="status-badge" style="background:${getStatusColor(l.status)}20;color:${getStatusColor(l.status)}">${getStatusLabel(l.status)}</span></td>
      <td>${(l.tags||[]).map(t=>`<span class="tag" style="background:${getTagColor(t)}20;color:${getTagColor(t)}">${t}</span>`).join('')}</td>
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

// Lead detail modal
async function openLead(phone) {
  const [lead, timeline, convos, purchases] = await Promise.all([
    apiFetch(`/leads/${phone}`),
    apiFetch(`/leads/${phone}/timeline`),
    apiFetch(`/leads/${phone}/conversations?limit=1000`),
    apiFetch(`/purchases?lead_phone=${phone}`),
  ]);
  if(!lead) return;

  const leadTags = lead.tags||[];

  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal">
    <div class="modal-header">
      <h2><div class="lead-row-avatar" style="background:${getAvatarColor(lead.name)}">${getInitials(lead.name)}</div> ${lead.name||lead.phone}</h2>
      <button class="close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button>
    </div>
    <div class="modal-tabs">
      <button class="active" onclick="showModalTab(this,'mtab-details')">פרטים</button>
      <button onclick="showModalTab(this,'mtab-timeline')">ציר זמן (${timeline?.length||0})</button>
      <button onclick="showModalTab(this,'mtab-chat')">שיחה (${convos?.length||0})</button>
      <button onclick="showModalTab(this,'mtab-purchases')">רכישות (${purchases?.length||0})</button>
    </div>
    <div class="modal-body">
      <!-- Details tab -->
      <div id="mtab-details">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem">
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
        <div class="field-group">
          <label>תגיות</label>
          <div class="tags-container">
            ${settings.tags.map(t=>`<span class="tag-toggle ${leadTags.includes(t.key)?'active':''}" style="${leadTags.includes(t.key)?'border-color:'+t.color+';background:'+t.color+'20;color:'+t.color:''}" onclick="toggleTag(this,'${phone}','${t.key}','${t.color}')">${t.key}</span>`).join('')}
          </div>
        </div>
        <div class="field-group">
          <label>הערות</label>
          <textarea onblur="updateField('${phone}','notes',this.value)">${lead.notes||''}</textarea>
        </div>
        ${lead.ai_summary ? '<div style="margin-top:.5rem;padding:.6rem .8rem;background:#e8f4fd;border-radius:10px;border-right:3px solid var(--blue);font-size:.85rem"><strong>סיכום AI:</strong> '+lead.ai_summary+'</div>' : ''}
        ${lead.conversation_summary ? '<div style="margin-top:.5rem;padding:.6rem .8rem;background:var(--pink-bg);border-radius:10px;border-right:3px solid var(--pink);font-size:.85rem"><strong>הערות מירב:</strong> '+lead.conversation_summary+'</div>' : ''}
        <div style="text-align:center;color:#bbb;font-size:.78rem;margin-top:.5rem;padding-top:.5rem;border-top:1px solid #f5f5f5">
          קשר ראשון: ${fmtDate(lead.first_contact)} &bull; סה"כ שולם: ${lead.total_paid||0}₪
        </div>
      </div>

      <!-- Timeline tab -->
      <div id="mtab-timeline" class="hidden">
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
      <div id="mtab-chat" class="hidden">
        ${lead.ai_summary ? '<div style="margin-bottom:.8rem;padding:.6rem .8rem;background:#e8f4fd;border-radius:10px;border-right:3px solid var(--blue);font-size:.85rem"><strong>סיכום AI (אוטומטי):</strong> '+lead.ai_summary+'</div>' : ''}
        <div class="field-group" style="margin-bottom:1rem">
          <label style="font-weight:600;color:var(--pink)">הערות שלי על השיחה</label>
          <textarea style="min-height:60px;background:var(--pink-bg);border-color:var(--pink-light)" placeholder="מה יצא מהשיחה? למה מחכים? מה הצעד הבא?" onblur="updateField('${phone}','conversation_summary',this.value)">${lead.conversation_summary||''}</textarea>
        </div>
        <div class="chat-view">
          ${buildChatWithSessions(convos||[])}
        </div>
        ${!convos?.length ? '<div class="empty-state"><div class="icon">💬</div><p>אין שיחות</p></div>' : ''}
      </div>

      <!-- Purchases tab -->
      <div id="mtab-purchases" class="hidden">
        ${(purchases||[]).map(p=>`<div style="display:flex;justify-content:space-between;padding:.5rem 0;border-bottom:1px solid #f5f5f5">
          <span>${p.course_name}</span><span style="font-weight:700;color:var(--green)">${p.amount}₪</span><span style="color:#999;font-size:.8rem">${fmtShortDate(p.purchased_at)}</span>
        </div>`).join('')}
        <button class="btn btn-green btn-small" style="margin-top:.8rem" onclick="showPurchaseForLead('${phone}')">+ הוסף רכישה</button>
        ${!purchases?.length ? '<div class="empty-state"><div class="icon">🛒</div><p>אין רכישות</p></div>' : ''}
      </div>
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', e=>{ if(e.target===modal) modal.remove(); });
}

function showModalTab(btn, tabId) {
  btn.closest('.modal').querySelectorAll('.modal-tabs button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const body = btn.closest('.modal').querySelector('.modal-body');
  body.querySelectorAll(':scope > div').forEach(d=>d.classList.add('hidden'));
  body.querySelector('#'+tabId).classList.remove('hidden');
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
    <div style="padding:.8rem 1rem;font-weight:700;font-size:1rem;border-bottom:1px solid #f0f0f0">סה"כ: ${total.toLocaleString()}₪ <span style="color:#999;font-weight:400">(${purchases.length} רכישות)</span></div>
    <table>
    <tr><th>טלפון</th><th>קורס</th><th>סכום</th><th>תאריך</th><th>אמצעי</th></tr>
    ${purchases.map(p=>`<tr>
      <td dir="ltr" style="cursor:pointer" onclick="openLead('${p.lead_phone}')">${p.lead_phone}</td>
      <td>${p.course_name}</td>
      <td style="font-weight:600;color:var(--green)">${p.amount}₪</td>
      <td>${fmtShortDate(p.purchased_at)}</td>
      <td>${p.payment_method}</td>
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
  const body={lead_phone:phone, course_name:cname, amount, notes, payment_method:'cardcom'};
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
