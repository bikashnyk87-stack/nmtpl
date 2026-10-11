"""NMTPL HRMS staging workbench. Synthetic data ONLY. Do not use for payroll."""
from __future__ import annotations
import json, os, secrets, sqlite3, threading, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

DB = os.environ.get("HRMS_STAGING_DB", "/tmp/nmtpl_hrms_test.sqlite3")
PASSWORD = os.environ.get("HRMS_STAGING_PASSWORD", "")
if len(PASSWORD) < 16:
    raise RuntimeError("Set HRMS_STAGING_PASSWORD with at least 16 characters")
SESSIONS = {}
LOCK = threading.RLock()
ROOT = Path(__file__).resolve().parent
TEMPLATES = {
    "HR Entry Operator": {"employees": ["view","create","edit"], "masters":["view"],"attendance":["view","create"]},
    "HR Checker": {"employees":["view","approve"],"attendance":["view","approve"],"masters":["view"]},
    "Payroll Preparer": {"employees":["view"],"payroll":["view","create","edit"],"attendance":["view"]},
    "Site Supervisor": {"employees":["view"],"attendance":["view","create"],"operations":["view","create"]},
    "Banking Viewer": {"banking":["view"]},
    "Audit Viewer": {"audit":["view","export"]},
}

def connect():
    conn=sqlite3.connect(DB, timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def init():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    with LOCK, connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,permissions TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'active');
        CREATE TABLE IF NOT EXISTS sites(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assignments(user_id INTEGER,site_id INTEGER,role_id INTEGER,
            PRIMARY KEY(user_id,site_id,role_id));
        CREATE TABLE IF NOT EXISTS masters(id INTEGER PRIMARY KEY,category TEXT NOT NULL,value TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,UNIQUE(category,value));
        CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY,reference TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,prepared_by TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING');
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,action TEXT NOT NULL,detail TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if not c.execute("SELECT COUNT(*) FROM sites").fetchone()[0]:
            c.executemany("INSERT INTO sites(code,name) VALUES (?,?)",[
                ("TIOM","Thakurani Iron Ore Mine"),("SOCP","SOCP"),("KOCP","KOCP")])
        if not c.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            c.executemany("INSERT INTO users(username,status) VALUES (?,?)",[
                ("superadmin","active"),("hr.entry.demo","active"),("hr.checker.demo","active"),("site.supervisor.demo","active")])
        if not c.execute("SELECT COUNT(*) FROM roles").fetchone()[0]:
            c.executemany("INSERT INTO roles(code,permissions) VALUES (?,?)",
                [(k,json.dumps(v)) for k,v in TEMPLATES.items()])
        if not c.execute("SELECT COUNT(*) FROM masters").fetchone()[0]:
            c.executemany("INSERT INTO masters(category,value) VALUES (?,?)", [
                ("Department","HR"),("Department","Operations"),("Department","Mechanical"),
                ("Designation","Operator"),("Designation","Helper"),("Designation","Supervisor"),
                ("Shift","A"),("Shift","B"),("Shift","C"),
                ("Employment Type","Direct"),("Employment Type","Contract"),
                ("Leave Type","CL"),("Leave Type","SL")])
        if not c.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]:
            c.executemany("INSERT INTO approvals(reference,label,prepared_by) VALUES (?,?,?)",[
                ("DEMO-HR-001","3 synthetic employee records","hr.entry.demo"),
                ("DEMO-ATT-002","A-shift attendance correction","site.supervisor.demo"),
                ("DEMO-HR-003","1 synthetic verification case","hr.entry.demo")])

def audit(c,action,detail):
    c.execute("INSERT INTO audit(action,detail) VALUES (?,?)",(action,json.dumps(detail,sort_keys=True)))

@asynccontextmanager
async def lifespan(app):
    init()
    yield

app=FastAPI(title="NMTPL HRMS Staging - Synthetic Data",docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)

@app.middleware("http")
async def headers(request,call_next):
    resp=await call_next(request)
    resp.headers["Cache-Control"]="no-store"
    resp.headers["X-Frame-Options"]="DENY"
    resp.headers["X-Content-Type-Options"]="nosniff"
    resp.headers["Referrer-Policy"]="no-referrer"
    resp.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    return resp

def auth(req,mutation=False):
    token=req.cookies.get("hrms_staging","")
    session=SESSIONS.get(token)
    if not session or session["expires"]<time.time(): raise HTTPException(401,"Sign in")
    if mutation:
        if not secrets.compare_digest(req.headers.get("X-CSRF-Token",""),session["csrf"]):
            raise HTTPException(403,"Invalid CSRF token")
    return session

@app.get("/health")
def health():
    return {"status":"ok","environment":"synthetic-staging","persistent":False}

@app.get("/")
def home():
    return HTMLResponse((ROOT/"index.html").read_text(encoding="utf8"))

class Login(BaseModel):
    password:str

@app.post("/api/login")
def login(p:Login):
    if not secrets.compare_digest(p.password,PASSWORD):
        raise HTTPException(401,"Invalid test access password")
    token=secrets.token_urlsafe(40)
    csrf=secrets.token_urlsafe(32)
    SESSIONS[token]={"expires":time.time()+8*3600,"csrf":csrf}
    r=JSONResponse({"ok":True,"csrf":csrf})
    r.set_cookie("hrms_staging",token,httponly=True,secure=True,samesite="strict",max_age=8*3600)
    return r

@app.post("/api/logout")
def logout(req:Request):
    SESSIONS.pop(req.cookies.get("hrms_staging",""),None)
    r=JSONResponse({"ok":True})
    r.delete_cookie("hrms_staging",samesite="strict",secure=True)
    return r

def rows(c,query):
    return [dict(x) for x in c.execute(query).fetchall()]

@app.get("/api/state")
def state(req:Request):
    session=auth(req)
    with connect() as c:
        return {
            "csrf":session["csrf"],"sites":rows(c,"SELECT * FROM sites ORDER BY code"),
            "users":rows(c,"SELECT * FROM users ORDER BY username"),
            "roles":[dict(r)|{"permissions":json.loads(r["permissions"])} for r in c.execute("SELECT * FROM roles ORDER BY code")],
            "assignments":rows(c,"SELECT * FROM assignments"),
            "masters":rows(c,"SELECT * FROM masters ORDER BY category,value"),
            "approvals":rows(c,"SELECT * FROM approvals ORDER BY id"),
            "audit":rows(c,"SELECT action,detail,created_at FROM audit ORDER BY id DESC LIMIT 15"),
            "templates":TEMPLATES, "disclaimer":"SYNTHETIC TEST DATA ONLY — resets on redeploy"
        }

class MasterIn(BaseModel):
    category:str=Field(min_length=2,max_length=60)
    value:str=Field(min_length=1,max_length=100)

@app.post("/api/master")
def add_master(p:MasterIn,req:Request):
    auth(req,True)
    with LOCK,connect() as c:
        try:
            c.execute("INSERT INTO masters(category,value) VALUES (?,?)",(p.category.strip(),p.value.strip()))
        except sqlite3.IntegrityError: raise HTTPException(409,"This master value already exists")
        audit(c,"master_created",p.model_dump())
    return {"ok":True}

class RoleIn(BaseModel):
    code:str=Field(min_length=3,max_length=50)
    permissions:dict=Field(default_factory=dict)

@app.post("/api/role")
def add_role(p:RoleIn,req:Request):
    auth(req,True)
    allowed={"view","create","edit","approve","export"}
    modules={"employees","masters","attendance","payroll","banking","users","audit","operations"}
    if not p.permissions or any(m not in modules or not isinstance(v,list) or any(x not in allowed for x in v) for m,v in p.permissions.items()):
        raise HTTPException(422,"Select valid module permissions")
    with LOCK,connect() as c:
        try:c.execute("INSERT INTO roles(code,permissions) VALUES (?,?)",(p.code.strip(),json.dumps(p.permissions)))
        except sqlite3.IntegrityError:raise HTTPException(409,"Role already exists")
        audit(c,"role_created",{"role":p.code})
    return {"ok":True}

class GrantIn(BaseModel):
    user_id:int
    site_id:int
    role_ids:list[int]=Field(default_factory=list)

@app.post("/api/site-roles")
def set_roles(p:GrantIn,req:Request):
    auth(req,True)
    if len(set(p.role_ids))!=len(p.role_ids):raise HTTPException(422,"Duplicate role")
    with LOCK,connect() as c:
        if not c.execute("SELECT 1 FROM users WHERE id=?",(p.user_id,)).fetchone():raise HTTPException(404,"Unknown user")
        if not c.execute("SELECT 1 FROM sites WHERE id=?",(p.site_id,)).fetchone():raise HTTPException(404,"Unknown site")
        known={r[0] for r in c.execute("SELECT id FROM roles")}
        if not set(p.role_ids).issubset(known):raise HTTPException(422,"Unknown role")
        c.execute("DELETE FROM assignments WHERE user_id=? AND site_id=?",(p.user_id,p.site_id))
        c.executemany("INSERT INTO assignments VALUES (?,?,?)",[(p.user_id,p.site_id,r) for r in p.role_ids])
        audit(c,"site_roles_updated",p.model_dump())
    return {"ok":True}

class BatchIn(BaseModel):
    ids:list[int]=Field(min_length=1,max_length=100)

@app.post("/api/approvals/bulk")
def bulk(p:BatchIn,req:Request):
    auth(req,True)
    if len(set(p.ids))!=len(p.ids):raise HTTPException(422,"Duplicate cases")
    with LOCK,connect() as c:
        c.execute("BEGIN IMMEDIATE")
        selected=c.execute("SELECT * FROM approvals WHERE id IN ("+",".join("?" for _ in p.ids)+")",p.ids).fetchall()
        if len(selected)!=len(p.ids):raise HTTPException(422,"Invalid cases; no changes made")
        if any(r["status"]!="PENDING" or r["prepared_by"]=="superadmin" for r in selected):
            raise HTTPException(409,"Ineligible or self-prepared case; no changes made")
        c.executemany("UPDATE approvals SET status='APPROVED' WHERE id=?",[(i,) for i in p.ids])
        audit(c,"bulk_approved",{"ids":p.ids,"count":len(p.ids)})
    return {"approved":len(p.ids)}
