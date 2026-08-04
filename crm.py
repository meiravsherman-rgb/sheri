"""CRM panel — lead tracking, timeline, purchases for Merav."""

import json
import os
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from database import (
    get_leads, get_lead, update_lead, create_lead_manual,
    log_lead_event, get_lead_timeline, get_lead_conversations,
    create_purchase, get_purchases, get_dashboard_stats,
    get_all_courses,
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


# ── API Routes ─────────────────────────────────────────────────────

@router.get("/api/dashboard", dependencies=[Depends(check_auth)])
async def api_dashboard():
    return get_dashboard_stats()


@router.get("/api/leads", dependencies=[Depends(check_auth)])
async def api_leads(status: str = "", search: str = "", tag: str = ""):
    return get_leads(status=status, search=search, tag=tag)


@router.get("/api/leads/{phone}", dependencies=[Depends(check_auth)])
async def api_lead_detail(phone: str):
    lead = get_lead(phone)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/api/leads/{phone}", dependencies=[Depends(check_auth)])
async def api_update_lead(phone: str, req: LeadUpdate):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    old = get_lead(phone)
    if not old:
        raise HTTPException(status_code=404, detail="Lead not found")
    # Log status change
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


@router.get("/api/leads/{phone}/timeline", dependencies=[Depends(check_auth)])
async def api_timeline(phone: str, limit: int = 50):
    return get_lead_timeline(phone, limit)


@router.get("/api/leads/{phone}/conversations", dependencies=[Depends(check_auth)])
async def api_conversations(phone: str, limit: int = 100):
    return get_lead_conversations(phone, limit)


@router.get("/api/purchases", dependencies=[Depends(check_auth)])
async def api_all_purchases(lead_phone: str = ""):
    return get_purchases(lead_phone)


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
:root{--pink:#e91e8c;--pink-light:#fce4f3;--green:#27ae60;--blue:#3498db;--orange:#f39c12;--gray:#95a5a6;--dark:#2c3e50;--bg:#f8f9fa}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Tahoma,sans-serif;background:var(--bg);color:var(--dark);direction:rtl}
.login-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:999}
.login-box{background:#fff;padding:2rem;border-radius:12px;text-align:center;width:300px}
.login-box h2{color:var(--pink);margin-bottom:1rem}
.login-box input{width:100%;padding:.7rem;border:1px solid #ddd;border-radius:8px;margin-bottom:1rem;text-align:center;font-size:1rem}
.login-box button{background:var(--pink);color:#fff;border:none;padding:.7rem 2rem;border-radius:8px;cursor:pointer;font-size:1rem;width:100%}
header{background:linear-gradient(135deg,var(--pink),#c2185b);color:#fff;padding:1rem;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:1.3rem}
.nav{display:flex;gap:.5rem;background:#fff;padding:.5rem;border-bottom:1px solid #eee}
.nav button{padding:.5rem 1rem;border:none;background:none;cursor:pointer;border-radius:8px;font-size:.9rem;color:#666}
.nav button.active{background:var(--pink-light);color:var(--pink);font-weight:bold}
.content{padding:1rem;max-width:1200px;margin:0 auto}
.hidden{display:none}
/* Dashboard */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin-bottom:1.5rem}
.stat-card{background:#fff;border-radius:12px;padding:1.2rem;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.stat-card .number{font-size:2rem;font-weight:bold;color:var(--pink)}
.stat-card .label{color:#888;font-size:.85rem;margin-top:.3rem}
.funnel{background:#fff;border-radius:12px;padding:1.2rem;box-shadow:0 2px 8px rgba(0,0,0,.06);margin-bottom:1.5rem}
.funnel h3{margin-bottom:1rem;color:var(--dark)}
.funnel-bar{display:flex;align-items:center;margin-bottom:.6rem;gap:.5rem}
.funnel-bar .label{min-width:100px;font-size:.85rem}
.funnel-bar .bar{height:28px;border-radius:6px;display:flex;align-items:center;padding:0 .5rem;color:#fff;font-size:.8rem;min-width:30px;transition:width .5s}
.followups-section{background:#fff;border-radius:12px;padding:1.2rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.followups-section h3{margin-bottom:1rem}
.followup-item{display:flex;justify-content:space-between;padding:.5rem 0;border-bottom:1px solid #f0f0f0;cursor:pointer}
.followup-item:hover{background:#fafafa}
/* Leads */
.filters{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
.filters input,.filters select{padding:.5rem;border:1px solid #ddd;border-radius:8px;font-size:.9rem}
.filters input{flex:1;min-width:150px}
.btn{padding:.5rem 1rem;border:none;border-radius:8px;cursor:pointer;font-size:.85rem}
.btn-pink{background:var(--pink);color:#fff}
.btn-green{background:var(--green);color:#fff}
.btn-blue{background:var(--blue);color:#fff}
.btn-small{padding:.3rem .6rem;font-size:.8rem}
.leads-table{width:100%;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden}
.leads-table table{width:100%;border-collapse:collapse}
.leads-table th{background:#f8f8f8;padding:.7rem;text-align:right;font-size:.85rem;color:#666}
.leads-table td{padding:.7rem;border-top:1px solid #f0f0f0;font-size:.9rem}
.leads-table tr:hover{background:#fefefe;cursor:pointer}
.status-badge{padding:.2rem .6rem;border-radius:12px;font-size:.75rem;font-weight:bold}
.status-חדש{background:#e8e8e8;color:#666}
.status-מתעניינת{background:#d4efff;color:#2980b9}
.status-בשיחה{background:#ffecd2;color:#e67e22}
.status-נרשמה{background:#d5f5e3;color:#27ae60}
.status-לקוחה{background:var(--pink-light);color:var(--pink)}
.tag{background:#e8e8e8;padding:.15rem .4rem;border-radius:4px;font-size:.7rem;margin-left:.2rem}
/* Lead Modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:100}
.modal{background:#fff;border-radius:12px;width:95%;max-width:700px;max-height:90vh;overflow-y:auto;padding:1.5rem}
.modal h2{color:var(--pink);margin-bottom:1rem;display:flex;justify-content:space-between;align-items:center}
.modal .close-btn{background:none;border:none;font-size:1.5rem;cursor:pointer;color:#999}
.field-group{margin-bottom:1rem}
.field-group label{display:block;font-size:.85rem;color:#666;margin-bottom:.3rem}
.field-group input,.field-group select,.field-group textarea{width:100%;padding:.5rem;border:1px solid #ddd;border-radius:8px;font-size:.9rem}
.field-group textarea{min-height:80px;resize:vertical}
.tags-container{display:flex;flex-wrap:wrap;gap:.3rem}
.tag-toggle{padding:.3rem .6rem;border:1px solid #ddd;border-radius:12px;cursor:pointer;font-size:.8rem;background:#fff}
.tag-toggle.active{background:var(--pink-light);border-color:var(--pink);color:var(--pink)}
.timeline{margin-top:1rem}
.timeline-item{padding:.6rem;border-right:3px solid var(--pink-light);margin-right:.5rem;margin-bottom:.5rem;font-size:.85rem}
.timeline-item .time{color:#999;font-size:.75rem}
.timeline-item.handoff{border-color:var(--orange)}
.timeline-item.purchase{border-color:var(--green)}
.timeline-item.status_change{border-color:var(--blue)}
.chat-view{background:#f0f0f0;border-radius:8px;padding:.8rem;max-height:400px;overflow-y:auto}
.chat-msg{margin-bottom:.5rem;padding:.5rem .8rem;border-radius:8px;max-width:80%;font-size:.85rem}
.chat-msg.user{background:#dcf8c6;margin-left:auto}
.chat-msg.assistant{background:#fff}
.chat-msg .time{font-size:.7rem;color:#999;margin-top:.2rem}
/* Purchases tab */
.purchases-table{width:100%;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden}
.purchases-table table{width:100%;border-collapse:collapse}
.purchases-table th{background:#f8f8f8;padding:.7rem;text-align:right;font-size:.85rem;color:#666}
.purchases-table td{padding:.7rem;border-top:1px solid #f0f0f0;font-size:.9rem}
.toast{position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:.7rem 1.5rem;border-radius:8px;z-index:200;display:none}
@media(max-width:600px){
  .leads-table{font-size:.8rem}
  .leads-table th:nth-child(n+4),.leads-table td:nth-child(n+4){display:none}
  .stats-grid{grid-template-columns:1fr 1fr}
  .modal{width:100%;border-radius:0;max-height:100vh}
}
</style>
</head>
<body>

<div id="loginOverlay" class="login-overlay">
<div class="login-box">
  <h2>CRM שיטת שרמן</h2>
  <input type="password" id="loginPass" placeholder="סיסמה">
  <button onclick="doLogin()">כניסה</button>
</div>
</div>

<header>
  <h1>CRM — שיטת שרמן</h1>
  <a href="/admin" style="color:#fff;text-decoration:none;font-size:.85rem">ניהול תוכן &larr;</a>
</header>

<div class="nav">
  <button class="active" onclick="showTab('dashboard')">דשבורד</button>
  <button onclick="showTab('leads')">לידים</button>
  <button onclick="showTab('purchases')">רכישות</button>
</div>

<div class="content">
  <!-- Dashboard -->
  <div id="tab-dashboard">
    <div class="stats-grid" id="statsGrid"></div>
    <div class="funnel" id="funnelSection"><h3>משפך שיווקי</h3><div id="funnelBars"></div></div>
    <div class="followups-section"><h3>פולואפים קרובים</h3><div id="followupsList"></div></div>
  </div>

  <!-- Leads -->
  <div id="tab-leads" class="hidden">
    <div class="filters">
      <input type="text" id="searchInput" placeholder="חיפוש שם או טלפון..." oninput="loadLeads()">
      <select id="statusFilter" onchange="loadLeads()">
        <option value="">כל הסטטוסים</option>
        <option value="חדש">חדש</option>
        <option value="מתעניינת">מתעניינת</option>
        <option value="בשיחה אישית">בשיחה אישית</option>
        <option value="נרשמה">נרשמה</option>
        <option value="לקוחה">לקוחה</option>
      </select>
      <button class="btn btn-pink" onclick="showNewLeadModal()">+ ליד חדש</button>
    </div>
    <div class="leads-table" id="leadsTable"></div>
  </div>

  <!-- Purchases -->
  <div id="tab-purchases" class="hidden">
    <div style="margin-bottom:1rem"><button class="btn btn-green" onclick="showNewPurchaseModal()">+ רכישה חדשה</button></div>
    <div class="purchases-table" id="purchasesTable"></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API = '/crm/api';
let currentTab = 'dashboard';
let allCourses = [];

// Auth
async function doLogin() {
  const pass = document.getElementById('loginPass').value;
  const r = await fetch('/admin/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:pass})});
  if (r.ok) { document.getElementById('loginOverlay').style.display='none'; init(); }
  else alert('סיסמה שגויה');
}
(async()=>{
  try { const r=await fetch(API+'/dashboard'); if(r.ok){document.getElementById('loginOverlay').style.display='none';init();} } catch(e){}
})();

async function init() {
  allCourses = await apiFetch('/courses-list');
  loadDashboard();
}

async function apiFetch(path, opts={}) {
  const r = await fetch(API+path, opts);
  if (r.status===401) { document.getElementById('loginOverlay').style.display='flex'; return null; }
  return r.json();
}

function showTab(tab) {
  document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(d=>d.classList.add('hidden'));
  document.querySelector(`.nav button[onclick="showTab('${tab}')"]`).classList.add('active');
  document.getElementById('tab-'+tab).classList.remove('hidden');
  currentTab = tab;
  if (tab==='dashboard') loadDashboard();
  if (tab==='leads') loadLeads();
  if (tab==='purchases') loadPurchases();
}

function toast(msg) {
  const t=document.getElementById('toast');t.textContent=msg;t.style.display='block';
  setTimeout(()=>t.style.display='none',2500);
}

function fmtDate(iso) { if(!iso)return'—'; const d=new Date(iso); return d.toLocaleDateString('he-IL')+' '+d.toLocaleTimeString('he-IL',{hour:'2-digit',minute:'2-digit'}); }
function fmtShortDate(iso) { if(!iso)return'—'; return new Date(iso).toLocaleDateString('he-IL'); }

// Dashboard
async function loadDashboard() {
  const d = await apiFetch('/dashboard');
  if(!d) return;
  document.getElementById('statsGrid').innerHTML = `
    <div class="stat-card"><div class="number">${d.total_leads}</div><div class="label">סה"כ לידים</div></div>
    <div class="stat-card"><div class="number">${d.new_this_month}</div><div class="label">חדשים החודש</div></div>
    <div class="stat-card"><div class="number">${d.month_revenue.toLocaleString()}₪</div><div class="label">הכנסות החודש</div></div>
    <div class="stat-card"><div class="number">${d.conversion_rate}%</div><div class="label">שיעור המרה</div></div>
  `;
  const statuses = ['חדש','מתעניינת','בשיחה אישית','נרשמה','לקוחה'];
  const colors = ['#95a5a6','#3498db','#f39c12','#27ae60','#e91e8c'];
  const maxCount = Math.max(...statuses.map(s=>d.funnel[s]||0), 1);
  document.getElementById('funnelBars').innerHTML = statuses.map((s,i)=>{
    const count = d.funnel[s]||0;
    const pct = Math.max(count/maxCount*100, 8);
    return `<div class="funnel-bar"><span class="label">${s}</span><div class="bar" style="width:${pct}%;background:${colors[i]}">${count}</div></div>`;
  }).join('');
  document.getElementById('followupsList').innerHTML = (d.upcoming_followups||[]).map(l=>
    `<div class="followup-item" onclick="openLead('${l.phone}')"><span>${l.name||l.phone}</span><span>${fmtShortDate(l.next_followup)}</span></div>`
  ).join('') || '<p style="color:#999;text-align:center">אין פולואפים מתוכננים</p>';
}

// Leads
async function loadLeads() {
  const search = document.getElementById('searchInput')?.value||'';
  const status = document.getElementById('statusFilter')?.value||'';
  const leads = await apiFetch(`/leads?search=${encodeURIComponent(search)}&status=${encodeURIComponent(status)}`);
  if(!leads) return;
  const statusClass = s => 'status-'+(s==='בשיחה אישית'?'בשיחה':s);
  document.getElementById('leadsTable').innerHTML = `<table>
    <tr><th>שם</th><th>טלפון</th><th>סטטוס</th><th>תגיות</th><th>אחרון</th><th>פולואפ</th></tr>
    ${leads.map(l=>`<tr onclick="openLead('${l.phone}')">
      <td>${l.name||'—'}</td>
      <td dir="ltr">${l.phone}</td>
      <td><span class="status-badge ${statusClass(l.status)}">${l.status}</span></td>
      <td>${(l.tags||[]).map(t=>`<span class="tag">${t}</span>`).join('')}</td>
      <td>${fmtShortDate(l.last_contact)}</td>
      <td>${fmtShortDate(l.next_followup)}</td>
    </tr>`).join('')}
  </table>`;
}

// Lead detail modal
async function openLead(phone) {
  const [lead, timeline, convos, purchases] = await Promise.all([
    apiFetch(`/leads/${phone}`),
    apiFetch(`/leads/${phone}/timeline`),
    apiFetch(`/leads/${phone}/conversations?limit=50`),
    apiFetch(`/purchases?lead_phone=${phone}`),
  ]);
  if(!lead) return;

  const availableTags = ['פוריות','כאבים','PMS','נערות','FAM','התרוקנות','אמהות ובנות','כללי'];
  const leadTags = lead.tags||[];

  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal">
    <h2>${lead.name||lead.phone} <button class="close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button></h2>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem">
      <div class="field-group">
        <label>סטטוס</label>
        <select id="m-status" onchange="updateField('${phone}','status',this.value)">
          ${['חדש','מתעניינת','בשיחה אישית','נרשמה','לקוחה'].map(s=>`<option ${s===lead.status?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>
      <div class="field-group">
        <label>מקור</label>
        <select id="m-source" onchange="updateField('${phone}','source',this.value)">
          ${['whatsapp_bot','manual','referral','frontal','other'].map(s=>`<option ${s===lead.source?'selected':''}>${s}</option>`).join('')}
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
        ${availableTags.map(t=>`<span class="tag-toggle ${leadTags.includes(t)?'active':''}" onclick="toggleTag(this,'${phone}','${t}')">${t}</span>`).join('')}
      </div>
    </div>

    <div class="field-group">
      <label>הערות</label>
      <textarea id="m-notes" onblur="updateField('${phone}','notes',this.value)">${lead.notes||''}</textarea>
    </div>

    <details style="margin-top:1rem">
      <summary style="cursor:pointer;font-weight:bold;color:var(--pink)">ציר זמן (${timeline?.length||0})</summary>
      <div class="timeline">
        ${(timeline||[]).map(e=>{
          const cls = e.event_type;
          let icon='📝', text='';
          const data = typeof e.event_data === 'string' ? JSON.parse(e.event_data||'{}') : (e.event_data||{});
          if(cls==='handoff'){icon='🔄';text=`העברה למירב: ${data.reason||''}`}
          else if(cls==='purchase'){icon='💰';text=`רכישה: ${data.course||''} — ${data.amount||''}₪`}
          else if(cls==='status_change'){icon='📊';text=`${data.from||'—'} → ${data.to||'—'}`}
          else if(cls==='note'){icon='📝';text=data.text||''}
          else{text=JSON.stringify(data)}
          return `<div class="timeline-item ${cls}"><span class="time">${fmtDate(e.created_at)}</span> ${icon} ${text}</div>`;
        }).join('')}
      </div>
    </details>

    <details style="margin-top:1rem">
      <summary style="cursor:pointer;font-weight:bold;color:var(--pink)">היסטוריית שיחה (${convos?.length||0})</summary>
      <div class="chat-view">
        ${(convos||[]).map(m=>`<div class="chat-msg ${m.role}"><div>${m.content}</div><div class="time">${fmtDate(m.created_at)}</div></div>`).join('')}
      </div>
    </details>

    <details style="margin-top:1rem">
      <summary style="cursor:pointer;font-weight:bold;color:var(--green)">רכישות (${purchases?.length||0})</summary>
      <div>
        ${(purchases||[]).map(p=>`<div style="padding:.4rem 0;border-bottom:1px solid #eee">${p.course_name} — ${p.amount}₪ — ${fmtShortDate(p.purchased_at)}</div>`).join('')}
        <button class="btn btn-green btn-small" style="margin-top:.5rem" onclick="showPurchaseForLead('${phone}')">+ הוסף רכישה</button>
      </div>
    </details>

    <div style="margin-top:1rem;text-align:center;color:#999;font-size:.8rem">
      קשר ראשון: ${fmtDate(lead.first_contact)} | סה"כ שולם: ${lead.total_paid||0}₪
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', e=>{ if(e.target===modal) modal.remove(); });
}

async function updateField(phone, field, value) {
  const body = {};
  if (field==='tags') body.tags = value;
  else body[field] = value;
  await apiFetch(`/leads/${phone}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  toast('עודכן!');
}

async function toggleTag(el, phone, tag) {
  el.classList.toggle('active');
  const tags = [...el.parentElement.querySelectorAll('.tag-toggle.active')].map(t=>t.textContent);
  await updateField(phone, 'tags', tags);
}

// New lead modal
function showNewLeadModal() {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal" style="max-width:400px">
    <h2>ליד חדש <button class="close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button></h2>
    <div class="field-group"><label>טלפון</label><input id="nl-phone" dir="ltr" placeholder="972501234567"></div>
    <div class="field-group"><label>שם</label><input id="nl-name"></div>
    <div class="field-group"><label>מקור</label>
      <select id="nl-source"><option value="manual">ידני</option><option value="referral">הפניה</option><option value="frontal">פרונטלי</option><option value="other">אחר</option></select>
    </div>
    <button class="btn btn-pink" style="width:100%;margin-top:1rem" onclick="createLead()">צור ליד</button>
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
  document.getElementById('purchasesTable').innerHTML = `
    <div style="padding:.7rem;font-weight:bold">סה"כ: ${total.toLocaleString()}₪ (${purchases.length} רכישות)</div>
    <table>
    <tr><th>טלפון</th><th>קורס</th><th>סכום</th><th>תאריך</th><th>אמצעי</th></tr>
    ${purchases.map(p=>`<tr>
      <td dir="ltr" style="cursor:pointer" onclick="openLead('${p.lead_phone}')">${p.lead_phone}</td>
      <td>${p.course_name}</td>
      <td>${p.amount}₪</td>
      <td>${fmtShortDate(p.purchased_at)}</td>
      <td>${p.payment_method}</td>
    </tr>`).join('')}
  </table>`;
}

function showNewPurchaseModal(prefillPhone='') {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal" style="max-width:400px">
    <h2>רכישה חדשה <button class="close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button></h2>
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
</script>
</body>
</html>"""
