"""Admin panel — API routes + HTML interface for Merav."""

import os
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from database import (
    get_all_faq, upsert_faq, delete_faq,
    get_all_courses, upsert_course, delete_course,
    get_all_sections, upsert_section,
    get_all_rules, upsert_rule,
)

router = APIRouter(prefix="/admin")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "sheri2024")


# ── Auth ───────────────────────────────────────────────────────────

def check_auth(request: Request):
    token = request.cookies.get("admin_token")
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


class LoginRequest(BaseModel):
    password: str


@router.post("/api/login")
async def login(req: LoginRequest):
    if req.password == ADMIN_PASSWORD:
        response = Response(content='{"ok":true}', media_type="application/json")
        response.set_cookie("admin_token", ADMIN_PASSWORD, httponly=True, max_age=86400 * 30)
        return response
    raise HTTPException(status_code=401, detail="סיסמה שגויה")


# ── FAQ API ────────────────────────────────────────────────────────

class FaqRequest(BaseModel):
    id: int | None = None
    question: str
    answer: str
    sort_order: int = 0


@router.get("/api/faq", dependencies=[Depends(check_auth)])
async def api_get_faq():
    return get_all_faq()


@router.post("/api/faq", dependencies=[Depends(check_auth)])
async def api_upsert_faq(req: FaqRequest):
    faq_id = upsert_faq(req.id, req.question, req.answer, req.sort_order)
    return {"id": faq_id}


@router.delete("/api/faq/{faq_id}", dependencies=[Depends(check_auth)])
async def api_delete_faq(faq_id: int):
    delete_faq(faq_id)
    return {"ok": True}


# ── Courses API ────────────────────────────────────────────────────

class CourseRequest(BaseModel):
    id: int | None = None
    name: str
    price: str
    audience: str = ""
    chapters: str = ""
    purchase_url: str = ""
    description: str = ""
    is_active: int = 1
    sort_order: int = 0


@router.get("/api/courses", dependencies=[Depends(check_auth)])
async def api_get_courses():
    return get_all_courses()


@router.post("/api/courses", dependencies=[Depends(check_auth)])
async def api_upsert_course(req: CourseRequest):
    fields = req.model_dump(exclude={"id"})
    course_id = upsert_course(req.id, **fields)
    return {"id": course_id}


@router.delete("/api/courses/{course_id}", dependencies=[Depends(check_auth)])
async def api_delete_course(course_id: int):
    delete_course(course_id)
    return {"ok": True}


# ── Content Sections API ──────────────────────────────────────────

class SectionRequest(BaseModel):
    section_key: str
    title: str
    body: str


@router.get("/api/sections", dependencies=[Depends(check_auth)])
async def api_get_sections():
    return get_all_sections()


@router.post("/api/sections", dependencies=[Depends(check_auth)])
async def api_upsert_section(req: SectionRequest):
    upsert_section(req.section_key, req.title, req.body)
    return {"ok": True}


# ── Rules API ─────────────────────────────────────────────────────

class RuleRequest(BaseModel):
    rule_key: str
    title: str
    body: str
    is_active: int = 1


@router.get("/api/rules", dependencies=[Depends(check_auth)])
async def api_get_rules():
    return get_all_rules()


@router.post("/api/rules", dependencies=[Depends(check_auth)])
async def api_upsert_rule(req: RuleRequest):
    upsert_rule(req.rule_key, req.title, req.body, req.is_active)
    return {"ok": True}


# ── Admin HTML page ───────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_page():
    return ADMIN_HTML


ADMIN_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ניהול שרי הבוטית</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f4f0; color: #333; line-height: 1.6; }

/* Login */
.login-overlay { position: fixed; inset: 0; background: #f8f4f0; display: flex; align-items: center; justify-content: center; z-index: 1000; }
.login-box { background: #fff; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; max-width: 360px; width: 90%; }
.login-box h1 { font-size: 24px; margin-bottom: 8px; color: #d4838f; }
.login-box p { color: #888; margin-bottom: 24px; font-size: 14px; }
.login-box input { width: 100%; padding: 12px 16px; border: 2px solid #e8ddd5; border-radius: 10px; font-size: 16px; text-align: center; outline: none; }
.login-box input:focus { border-color: #d4838f; }
.login-box button { width: 100%; padding: 12px; margin-top: 16px; background: #d4838f; color: #fff; border: none; border-radius: 10px; font-size: 16px; cursor: pointer; }
.login-box button:hover { background: #c07080; }
.login-error { color: #e74c3c; margin-top: 12px; font-size: 14px; display: none; }

/* Header */
header { background: linear-gradient(135deg, #d4838f, #e8a5b0); color: #fff; padding: 20px 24px; }
header h1 { font-size: 22px; font-weight: 600; }
header p { font-size: 13px; opacity: 0.9; }

/* Tabs */
.tabs { display: flex; background: #fff; border-bottom: 2px solid #e8ddd5; overflow-x: auto; }
.tab { padding: 14px 20px; cursor: pointer; font-size: 14px; font-weight: 500; color: #888; white-space: nowrap; border-bottom: 3px solid transparent; transition: all 0.2s; }
.tab:hover { color: #d4838f; }
.tab.active { color: #d4838f; border-bottom-color: #d4838f; }

/* Content */
main { max-width: 900px; margin: 0 auto; padding: 20px; }
.section { display: none; }
.section.active { display: block; }

/* Cards */
.card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { font-size: 16px; color: #555; }

/* Forms */
label { display: block; font-size: 13px; font-weight: 600; color: #666; margin-bottom: 4px; margin-top: 12px; }
input[type="text"], input[type="url"], input[type="number"], textarea, select {
    width: 100%; padding: 10px 14px; border: 2px solid #e8ddd5; border-radius: 8px;
    font-size: 14px; font-family: inherit; outline: none; transition: border 0.2s;
}
input:focus, textarea:focus, select:focus { border-color: #d4838f; }
textarea { min-height: 80px; resize: vertical; }

/* Buttons */
.btn { padding: 10px 20px; border: none; border-radius: 8px; font-size: 14px; font-family: inherit; cursor: pointer; transition: all 0.2s; }
.btn-primary { background: #d4838f; color: #fff; }
.btn-primary:hover { background: #c07080; }
.btn-add { background: #e8f5e9; color: #2e7d32; }
.btn-add:hover { background: #c8e6c9; }
.btn-danger { background: #fce4ec; color: #c62828; font-size: 12px; padding: 6px 12px; }
.btn-danger:hover { background: #ffcdd2; }
.btn-save { background: #e3f2fd; color: #1565c0; }
.btn-save:hover { background: #bbdefb; }

/* Toggle */
.toggle { display: flex; align-items: center; gap: 8px; }
.toggle input { width: auto; }

/* Status */
.status-bar { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 24px; border-radius: 20px; font-size: 14px; display: none; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.status-bar.success { background: #2e7d32; }
.status-bar.error { background: #c62828; }

/* Empty state */
.empty { text-align: center; padding: 40px; color: #aaa; }
.empty p { margin-bottom: 16px; }

/* Responsive */
@media (max-width: 600px) {
    .tab { padding: 12px 14px; font-size: 13px; }
    main { padding: 12px; }
    .card { padding: 16px; }
}
</style>
</head>
<body>

<!-- Login overlay -->
<div class="login-overlay" id="loginOverlay">
<div class="login-box">
    <h1>שרי הבוטית 🌸</h1>
    <p>פאנל ניהול</p>
    <input type="password" id="loginPassword" placeholder="סיסמה" onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">כניסה</button>
    <div class="login-error" id="loginError">סיסמה שגויה</div>
</div>
</div>

<!-- Header -->
<header>
    <h1>ניהול שרי הבוטית 🌸</h1>
    <p>עדכון תוכן, קורסים, שאלות ותשובות וכללי התנהגות</p>
</header>

<!-- Tabs -->
<div class="tabs">
    <div class="tab active" onclick="switchTab('courses')">קורסים ומחירים</div>
    <div class="tab" onclick="switchTab('faq')">שאלות ותשובות</div>
    <div class="tab" onclick="switchTab('content')">תוכן ומידע</div>
    <div class="tab" onclick="switchTab('rules')">כללי התנהגות</div>
</div>

<main>

<!-- ═══ Courses ═══ -->
<div class="section active" id="sec-courses">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h2>קורסים ומחירים</h2>
        <button class="btn btn-add" onclick="addCourse()">+ קורס חדש</button>
    </div>
    <div id="coursesList"></div>
</div>

<!-- ═══ FAQ ═══ -->
<div class="section" id="sec-faq">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h2>שאלות ותשובות</h2>
        <button class="btn btn-add" onclick="addFaq()">+ שאלה חדשה</button>
    </div>
    <div id="faqList"></div>
</div>

<!-- ═══ Content ═══ -->
<div class="section" id="sec-content">
    <h2 style="margin-bottom:16px;">תוכן ומידע כללי</h2>
    <div id="contentList"></div>
</div>

<!-- ═══ Rules ═══ -->
<div class="section" id="sec-rules">
    <h2 style="margin-bottom:16px;">כללי התנהגות הבוט</h2>
    <div id="rulesList"></div>
</div>

</main>

<div class="status-bar" id="statusBar"></div>

<script>
const API = '/admin/api';

// ── Auth ──
async function doLogin() {
    const pw = document.getElementById('loginPassword').value;
    try {
        const res = await fetch(API + '/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({password: pw})
        });
        if (res.ok) {
            document.getElementById('loginOverlay').style.display = 'none';
            loadAll();
        } else {
            document.getElementById('loginError').style.display = 'block';
        }
    } catch(e) {
        document.getElementById('loginError').style.display = 'block';
    }
}

// Check if already logged in
fetch(API + '/faq').then(r => {
    if (r.ok) {
        document.getElementById('loginOverlay').style.display = 'none';
        loadAll();
    }
});

// ── Tabs ──
function switchTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('sec-' + name).classList.add('active');
}

// ── Status ──
function showStatus(msg, type='success') {
    const bar = document.getElementById('statusBar');
    bar.textContent = msg;
    bar.className = 'status-bar ' + type;
    bar.style.display = 'block';
    setTimeout(() => bar.style.display = 'none', 2500);
}

// ── Load all ──
function loadAll() { loadCourses(); loadFaq(); loadContent(); loadRules(); }

// ── Courses ──
let coursesData = [];
async function loadCourses() {
    const res = await fetch(API + '/courses');
    coursesData = await res.json();
    const el = document.getElementById('coursesList');
    if (!coursesData.length) {
        el.innerHTML = '<div class="empty"><p>אין קורסים עדיין</p></div>';
        return;
    }
    el.innerHTML = coursesData.map(c => `
        <div class="card" id="course-${c.id}">
            <div class="card-header">
                <h3>${c.name}</h3>
                <div>
                    <button class="btn btn-save" onclick="saveCourse(${c.id})">שמור</button>
                    <button class="btn btn-danger" onclick="deleteCourse(${c.id})">מחק</button>
                </div>
            </div>
            <label>שם הקורס</label>
            <input type="text" id="cn-${c.id}" value="${esc(c.name)}">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div><label>מחיר</label><input type="text" id="cp-${c.id}" value="${esc(c.price)}"></div>
                <div><label>פרקים</label><input type="text" id="cc-${c.id}" value="${esc(c.chapters)}"></div>
            </div>
            <label>למי מתאים</label>
            <input type="text" id="ca-${c.id}" value="${esc(c.audience)}">
            <label>קישור רכישה</label>
            <input type="url" id="cu-${c.id}" value="${esc(c.purchase_url)}">
            <div class="toggle" style="margin-top:12px;">
                <input type="checkbox" id="ci-${c.id}" ${c.is_active ? 'checked' : ''}>
                <label for="ci-${c.id}" style="margin:0;font-weight:normal;">פעיל (מוצג ללקוחות)</label>
            </div>
        </div>
    `).join('');
}

async function saveCourse(id) {
    const data = {
        id, name: val('cn-'+id), price: val('cp-'+id), chapters: val('cc-'+id),
        audience: val('ca-'+id), purchase_url: val('cu-'+id),
        is_active: document.getElementById('ci-'+id).checked ? 1 : 0
    };
    await fetch(API + '/courses', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    showStatus('הקורס נשמר בהצלחה');
    loadCourses();
}

async function deleteCourse(id) {
    if (!confirm('למחוק את הקורס?')) return;
    await fetch(API + '/courses/' + id, {method:'DELETE'});
    showStatus('הקורס נמחק');
    loadCourses();
}

function addCourse() {
    const data = { name:'קורס חדש', price:'0₪', audience:'', chapters:'', purchase_url:'', is_active:1 };
    fetch(API + '/courses', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) })
        .then(() => { showStatus('קורס חדש נוצר'); loadCourses(); });
}

// ── FAQ ──
let faqData = [];
async function loadFaq() {
    const res = await fetch(API + '/faq');
    faqData = await res.json();
    const el = document.getElementById('faqList');
    if (!faqData.length) {
        el.innerHTML = '<div class="empty"><p>אין שאלות ותשובות עדיין</p><button class="btn btn-add" onclick="addFaq()">+ הוסיפי שאלה ראשונה</button></div>';
        return;
    }
    el.innerHTML = faqData.map(f => `
        <div class="card">
            <div class="card-header">
                <h3>שאלה #${f.id}</h3>
                <div>
                    <button class="btn btn-save" onclick="saveFaq(${f.id})">שמור</button>
                    <button class="btn btn-danger" onclick="deleteFaqItem(${f.id})">מחק</button>
                </div>
            </div>
            <label>שאלה</label>
            <input type="text" id="fq-${f.id}" value="${esc(f.question)}">
            <label>תשובה</label>
            <textarea id="fa-${f.id}">${esc(f.answer)}</textarea>
        </div>
    `).join('');
}

async function saveFaq(id) {
    const data = { id, question: val('fq-'+id), answer: val('fa-'+id) };
    await fetch(API + '/faq', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    showStatus('השאלה נשמרה');
}

async function deleteFaqItem(id) {
    if (!confirm('למחוק את השאלה?')) return;
    await fetch(API + '/faq/' + id, {method:'DELETE'});
    showStatus('השאלה נמחקה');
    loadFaq();
}

function addFaq() {
    const data = { question:'', answer:'' };
    fetch(API + '/faq', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) })
        .then(() => { showStatus('שאלה חדשה נוצרה - מלאי את התוכן'); loadFaq(); });
}

// ── Content Sections ──
async function loadContent() {
    const res = await fetch(API + '/sections');
    const data = await res.json();
    const el = document.getElementById('contentList');
    const sectionLabels = {
        about: 'על השיטה', syllabus: 'סילבוס', fam: 'מודעות לפוריות',
        mothers_daughters: 'קורס אמהות ונערות', frontal: 'קורסים פרונטליים',
        personal: 'שיחה אישית', policies: 'מדיניות', contact: 'פרטי קשר', coupon: 'הנחות וקופונים'
    };
    el.innerHTML = data.map(s => `
        <div class="card">
            <div class="card-header">
                <h3>${sectionLabels[s.section_key] || s.title}</h3>
                <button class="btn btn-save" onclick="saveSection('${s.section_key}')">שמור</button>
            </div>
            <label>כותרת</label>
            <input type="text" id="st-${s.section_key}" value="${esc(s.title)}">
            <label>תוכן</label>
            <textarea id="sb-${s.section_key}" rows="6">${esc(s.body)}</textarea>
        </div>
    `).join('');
}

async function saveSection(key) {
    const data = { section_key: key, title: val('st-'+key), body: val('sb-'+key) };
    await fetch(API + '/sections', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    showStatus('התוכן נשמר');
}

// ── Rules ──
async function loadRules() {
    const res = await fetch(API + '/rules');
    const data = await res.json();
    const el = document.getElementById('rulesList');
    el.innerHTML = data.map(r => `
        <div class="card">
            <div class="card-header">
                <h3>${esc(r.title)}</h3>
                <button class="btn btn-save" onclick="saveRule('${r.rule_key}')">שמור</button>
            </div>
            <label>שם הכלל</label>
            <input type="text" id="rt-${r.rule_key}" value="${esc(r.title)}">
            <label>תיאור</label>
            <textarea id="rb-${r.rule_key}">${esc(r.body)}</textarea>
            <div class="toggle" style="margin-top:12px;">
                <input type="checkbox" id="ra-${r.rule_key}" ${r.is_active ? 'checked' : ''}>
                <label for="ra-${r.rule_key}" style="margin:0;font-weight:normal;">כלל פעיל</label>
            </div>
        </div>
    `).join('');
}

async function saveRule(key) {
    const data = {
        rule_key: key, title: val('rt-'+key), body: val('rb-'+key),
        is_active: document.getElementById('ra-'+key).checked ? 1 : 0
    };
    await fetch(API + '/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    showStatus('הכלל נשמר');
}

// ── Helpers ──
function val(id) { return document.getElementById(id).value; }
function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>"""
