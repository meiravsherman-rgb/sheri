"""Admin panel — API routes + HTML interface for Merav."""

import os
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from database import (
    get_all_faq, upsert_faq, delete_faq,
    get_all_courses, upsert_course, delete_course,
    get_all_sections, upsert_section, delete_section,
    get_all_rules, upsert_rule, delete_rule,
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


@router.delete("/api/sections/{section_key}", dependencies=[Depends(check_auth)])
async def api_delete_section(section_key: str):
    delete_section(section_key)
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


@router.delete("/api/rules/{rule_key}", dependencies=[Depends(check_auth)])
async def api_delete_rule(rule_key: str):
    delete_rule(rule_key)
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

/* Area selector - two main areas */
.area-selector { display: flex; background: #fff; border-bottom: 2px solid #e8ddd5; }
.area-btn { flex: 1; padding: 16px; cursor: pointer; font-size: 16px; font-weight: 600; color: #888; text-align: center; border-bottom: 3px solid transparent; transition: all 0.2s; }
.area-btn:hover { color: #d4838f; background: #fef9f7; }
.area-btn.active { color: #d4838f; border-bottom-color: #d4838f; background: #fef9f7; }
.area-btn .area-icon { font-size: 24px; display: block; margin-bottom: 4px; }
.area-btn .area-desc { font-size: 12px; font-weight: 400; color: #aaa; }

/* Sub-tabs within each area */
.sub-tabs { display: flex; background: #fef9f7; border-bottom: 1px solid #e8ddd5; overflow-x: auto; }
.sub-tab { padding: 12px 20px; cursor: pointer; font-size: 14px; font-weight: 500; color: #888; white-space: nowrap; border-bottom: 2px solid transparent; transition: all 0.2s; }
.sub-tab:hover { color: #d4838f; }
.sub-tab.active { color: #d4838f; border-bottom-color: #d4838f; }

/* Content */
main { max-width: 900px; margin: 0 auto; padding: 20px; }
.area { display: none; }
.area.active { display: block; }
.section { display: none; }
.section.active { display: block; }

/* Cards */
.card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-header h3 { font-size: 16px; color: #555; }

/* Section header */
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-header h2 { font-size: 18px; color: #444; }
.section-desc { color: #999; font-size: 13px; margin-bottom: 16px; }

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
    .area-btn { padding: 12px 8px; font-size: 14px; }
    .area-btn .area-icon { font-size: 20px; }
    .sub-tab { padding: 10px 14px; font-size: 13px; }
    main { padding: 12px; }
    .card { padding: 16px; }
}
</style>
</head>
<body>

<!-- Login overlay -->
<div class="login-overlay" id="loginOverlay">
<div class="login-box">
    <h1>שרי הבוטית</h1>
    <p>פאנל ניהול</p>
    <input type="password" id="loginPassword" placeholder="סיסמה" onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">כניסה</button>
    <div class="login-error" id="loginError">סיסמה שגויה</div>
</div>
</div>

<!-- Header -->
<header>
    <h1>ניהול שרי הבוטית</h1>
    <p>ניהול מידע העסק וכללי ההתנהגות של הבוט</p>
</header>

<!-- Two main areas -->
<div class="area-selector">
    <div class="area-btn active" onclick="switchArea('info')">
        <span class="area-icon">&#128218;</span>
        מידע על העסק
        <span class="area-desc">תוכן, קורסים, שאלות ותשובות</span>
    </div>
    <div class="area-btn" onclick="switchArea('behavior')">
        <span class="area-icon">&#9881;</span>
        התנהגות הבוט
        <span class="area-desc">כללים, הנחיות ומשוב</span>
    </div>
</div>

<!-- Sub-tabs for INFO area -->
<div class="sub-tabs" id="tabs-info">
    <div class="sub-tab active" onclick="switchSubTab('info','content')">תוכן ומידע</div>
    <div class="sub-tab" onclick="switchSubTab('info','courses')">קורסים ומחירים</div>
    <div class="sub-tab" onclick="switchSubTab('info','faq')">שאלות ותשובות</div>
    <div class="sub-tab" onclick="switchSubTab('info','notes')">הערות חופשיות</div>
</div>

<!-- Sub-tabs for BEHAVIOR area -->
<div class="sub-tabs" id="tabs-behavior" style="display:none;">
    <div class="sub-tab active" onclick="switchSubTab('behavior','rules')">כללי התנהגות</div>
    <div class="sub-tab" onclick="switchSubTab('behavior','feedback')">משוב והערות</div>
</div>

<main>

<!-- ═══════════ INFO AREA ═══════════ -->
<div class="area active" id="area-info">

<!-- ── Content Sections ── -->
<div class="section active" id="sec-content">
    <div class="section-header">
        <h2>תוכן ומידע כללי</h2>
        <button class="btn btn-add" onclick="addSection()">+ נושא חדש</button>
    </div>
    <p class="section-desc">המידע שהבוט משתמש בו כדי לענות ללקוחות. ניתן לערוך, להוסיף ולמחוק כל נושא.</p>
    <div id="contentList"></div>
</div>

<!-- ── Courses ── -->
<div class="section" id="sec-courses">
    <div class="section-header">
        <h2>קורסים ומחירים</h2>
        <button class="btn btn-add" onclick="addCourse()">+ קורס חדש</button>
    </div>
    <div id="coursesList"></div>
</div>

<!-- ── FAQ ── -->
<div class="section" id="sec-faq">
    <div class="section-header">
        <h2>שאלות ותשובות</h2>
        <button class="btn btn-add" onclick="addFaq()">+ שאלה חדשה</button>
    </div>
    <p class="section-desc">שאלות שלקוחות שואלות לעיתים קרובות והתשובות שהבוט ייתן.</p>
    <div id="faqList"></div>
</div>

<!-- ── Free-form Notes ── -->
<div class="section" id="sec-notes">
    <div class="section-header">
        <h2>הערות חופשיות</h2>
        <button class="btn btn-add" onclick="addNote()">+ הערה חדשה</button>
    </div>
    <p class="section-desc">מקום חופשי להוסיף כל מידע שתרצי שהבוט ידע - טיפים, מידע על מוצרים, סיפורי לקוחות, תוכן ממסמכים, או כל דבר אחר. פשוט כתבי כותרת ותוכן.</p>
    <div id="notesList"></div>
</div>

</div><!-- /area-info -->

<!-- ═══════════ BEHAVIOR AREA ═══════════ -->
<div class="area" id="area-behavior">

<!-- ── Rules ── -->
<div class="section active" id="sec-rules">
    <div class="section-header">
        <h2>כללי התנהגות</h2>
        <button class="btn btn-add" onclick="addRule()">+ כלל חדש</button>
    </div>
    <p class="section-desc">כללים שמנחים את הבוט איך לענות. למשל: "לא להבטיח תוצאות", "להפנות למירב בשאלות רפואיות" וכו'. ניתן להפעיל ולכבות כל כלל.</p>
    <div id="rulesList"></div>
</div>

<!-- ── Feedback ── -->
<div class="section" id="sec-feedback">
    <div class="section-header">
        <h2>משוב והערות</h2>
    </div>
    <p class="section-desc">כתבי כאן דברים שאהבת בהתנהגות הבוט ודברים שלא אהבת. הוסיפי הנחיות ספציפיות כמו: "להיות יותר אישית", "לא לכתוב הודעות ארוכות" וכו'. כל מה שתכתבי כאן ישפיע על אופן התגובה של הבוט.</p>
    <div class="card">
        <div class="card-header">
            <h3>דברים שאהבתי</h3>
            <button class="btn btn-save" onclick="saveFeedbackRule('feedback_liked')">שמור</button>
        </div>
        <textarea id="rb-feedback_liked" rows="5" placeholder="למשל: אהבתי שהבוט עונה בצורה חמה ואישית..."></textarea>
    </div>
    <div class="card">
        <div class="card-header">
            <h3>דברים שצריך לשנות</h3>
            <button class="btn btn-save" onclick="saveFeedbackRule('feedback_disliked')">שמור</button>
        </div>
        <textarea id="rb-feedback_disliked" rows="5" placeholder="למשל: הבוט כותב הודעות ארוכות מדי, צריך לקצר..."></textarea>
    </div>
    <div class="card">
        <div class="card-header">
            <h3>הנחיות נוספות</h3>
            <button class="btn btn-save" onclick="saveFeedbackRule('feedback_instructions')">שמור</button>
        </div>
        <textarea id="rb-feedback_instructions" rows="5" placeholder="כל הנחיה אחרת שתרצי לתת לבוט..."></textarea>
    </div>
</div>

</div><!-- /area-behavior -->

</main>

<div class="status-bar" id="statusBar"></div>

<script>
const API = '/admin/api';
let currentArea = 'info';

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

// ── Area switching ──
function switchArea(area) {
    currentArea = area;
    document.querySelectorAll('.area-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.area').forEach(a => a.classList.remove('active'));
    event.currentTarget.classList.add('active');
    document.getElementById('area-' + area).classList.add('active');
    // Toggle sub-tabs
    document.getElementById('tabs-info').style.display = area === 'info' ? 'flex' : 'none';
    document.getElementById('tabs-behavior').style.display = area === 'behavior' ? 'flex' : 'none';
}

function switchSubTab(area, tab) {
    const areaEl = document.getElementById('area-' + area);
    const tabsEl = document.getElementById('tabs-' + area);
    tabsEl.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
    areaEl.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    event.currentTarget.classList.add('active');
    document.getElementById('sec-' + tab).classList.add('active');
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
function loadAll() { loadCourses(); loadFaq(); loadContent(); loadRules(); loadFeedback(); }

// ── Courses ──
async function loadCourses() {
    const res = await fetch(API + '/courses');
    const coursesData = await res.json();
    const el = document.getElementById('coursesList');
    if (!coursesData.length) {
        el.innerHTML = '<div class="empty"><p>אין קורסים עדיין</p></div>';
        return;
    }
    el.innerHTML = coursesData.map(c => `
        <div class="card">
            <div class="card-header">
                <h3>${esc(c.name)}</h3>
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
    const data = { name:'קורס חדש', price:'0', audience:'', chapters:'', purchase_url:'', is_active:1 };
    fetch(API + '/courses', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) })
        .then(() => { showStatus('קורס חדש נוצר'); loadCourses(); });
}

// ── FAQ ──
async function loadFaq() {
    const res = await fetch(API + '/faq');
    const faqData = await res.json();
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
let sectionsData = [];
async function loadContent() {
    const res = await fetch(API + '/sections');
    sectionsData = await res.json();
    renderSections();
}

function renderSections() {
    const el = document.getElementById('contentList');
    const notesEl = document.getElementById('notesList');
    // Separate regular sections from custom notes (notes have key starting with 'note_')
    const regular = sectionsData.filter(s => !s.section_key.startsWith('note_'));
    const notes = sectionsData.filter(s => s.section_key.startsWith('note_'));

    if (!regular.length) {
        el.innerHTML = '<div class="empty"><p>אין תוכן עדיין</p><button class="btn btn-add" onclick="addSection()">+ הוסיפי נושא ראשון</button></div>';
    } else {
        el.innerHTML = regular.map(s => sectionCard(s)).join('');
    }

    if (!notes.length) {
        notesEl.innerHTML = '<div class="empty"><p>אין הערות עדיין</p><button class="btn btn-add" onclick="addNote()">+ הוסיפי הערה ראשונה</button></div>';
    } else {
        notesEl.innerHTML = notes.map(s => sectionCard(s)).join('');
    }
}

function sectionCard(s) {
    const k = s.section_key;
    return `
        <div class="card">
            <div class="card-header">
                <h3>${esc(s.title) || '(ללא כותרת)'}</h3>
                <div>
                    <button class="btn btn-save" onclick="saveSection('${k}')">שמור</button>
                    <button class="btn btn-danger" onclick="deleteSection('${k}')">מחק</button>
                </div>
            </div>
            <label>כותרת</label>
            <input type="text" id="st-${k}" value="${esc(s.title)}">
            <label>תוכן</label>
            <textarea id="sb-${k}" rows="6">${esc(s.body)}</textarea>
        </div>`;
}

async function saveSection(key) {
    const data = { section_key: key, title: val('st-'+key), body: val('sb-'+key) };
    await fetch(API + '/sections', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    showStatus('התוכן נשמר');
}

async function deleteSection(key) {
    if (!confirm('למחוק את הנושא הזה?')) return;
    await fetch(API + '/sections/' + key, {method:'DELETE'});
    showStatus('הנושא נמחק');
    loadContent();
}

function addSection() {
    const key = 'sec_' + Date.now();
    const data = { section_key: key, title: '', body: '' };
    fetch(API + '/sections', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) })
        .then(() => { showStatus('נושא חדש נוצר - מלאי את התוכן'); loadContent(); });
}

function addNote() {
    const key = 'note_' + Date.now();
    const data = { section_key: key, title: '', body: '' };
    fetch(API + '/sections', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) })
        .then(() => { showStatus('הערה חדשה נוצרה - מלאי את התוכן'); loadContent(); });
}

// ── Rules ──
async function loadRules() {
    const res = await fetch(API + '/rules');
    const data = await res.json();
    const el = document.getElementById('rulesList');
    // Filter out feedback rules
    const realRules = data.filter(r => !r.rule_key.startsWith('feedback_'));
    if (!realRules.length) {
        el.innerHTML = '<div class="empty"><p>אין כללים עדיין</p><button class="btn btn-add" onclick="addRule()">+ הוסיפי כלל ראשון</button></div>';
        return;
    }
    el.innerHTML = realRules.map(r => `
        <div class="card">
            <div class="card-header">
                <h3>${esc(r.title) || '(ללא שם)'}</h3>
                <div>
                    <button class="btn btn-save" onclick="saveRule('${r.rule_key}')">שמור</button>
                    <button class="btn btn-danger" onclick="deleteRule('${r.rule_key}')">מחק</button>
                </div>
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

async function deleteRule(key) {
    if (!confirm('למחוק את הכלל הזה?')) return;
    await fetch(API + '/rules/' + key, {method:'DELETE'});
    showStatus('הכלל נמחק');
    loadRules();
}

function addRule() {
    const key = 'rule_' + Date.now();
    const data = { rule_key: key, title: '', body: '', is_active: 1 };
    fetch(API + '/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) })
        .then(() => { showStatus('כלל חדש נוצר - מלאי את הפרטים'); loadRules(); });
}

// ── Feedback (stored as rules with feedback_ prefix) ──
async function loadFeedback() {
    const res = await fetch(API + '/rules');
    const data = await res.json();
    const feedbackKeys = ['feedback_liked', 'feedback_disliked', 'feedback_instructions'];
    for (const key of feedbackKeys) {
        const rule = data.find(r => r.rule_key === key);
        const el = document.getElementById('rb-' + key);
        if (el && rule) {
            el.value = rule.body || '';
        }
    }
}

async function saveFeedbackRule(key) {
    const titles = {
        feedback_liked: 'דברים שמירב אוהבת',
        feedback_disliked: 'דברים שמירב רוצה לשנות',
        feedback_instructions: 'הנחיות נוספות ממירב'
    };
    const body = val('rb-' + key);
    const data = { rule_key: key, title: titles[key] || key, body: body, is_active: body.trim() ? 1 : 0 };
    await fetch(API + '/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    showStatus('המשוב נשמר');
}

// ── Helpers ──
function val(id) { return document.getElementById(id).value; }
function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>"""
