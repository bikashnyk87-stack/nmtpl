import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.db import engine, get_db, SessionLocal, Base
from app.auth import WebUser, WebSession, get_user, require, MODULES
from app.config import settings
from app.models import MasterOption, WbHeaderAlias
from app.routers import health, masters, production, hsd, reconciliation, dashboard, shift_control, webapp, sites, site_ops, maintenance
from app.services.wb_mapping import ensure_wb_header_mapping
from app.services.attendance_automation import automation_loop
from app.site_models import create_multisite_tables
from app.maintenance_models import create_maintenance_tables
from app.services.site_context import seed_default_sites_and_shifts
from app.services.tiom_location_erp import ensure_location_master_schema, ensure_location_master_roles

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine, checkfirst=True)
    ensure_location_master_schema(engine)
    create_multisite_tables(engine)
    create_maintenance_tables(engine)
    with SessionLocal() as db:
        ensure_wb_header_mapping(db)
        ensure_location_master_roles(db)
        seed_default_sites_and_shifts(db)
        users = db.query(WebUser).all()
        if len(users) == 1:
            u = users[0]
            if u.active and not u.admin and not (u.modules or '').strip():
                u.admin = True
                u.modules = ','.join(sorted(MODULES))
                u.shifts = 'ALL'
        db.commit()
    attendance_task = asyncio.create_task(automation_loop(), name='attendance-auto-close')
    try:
        yield
    finally:
        attendance_task.cancel()
        with suppress(asyncio.CancelledError):
            await attendance_task

app = FastAPI(title='NMTPL Central Operations Platform', version='1.0.0-site-software-r1', lifespan=lifespan)

def legacy_access(request: Request, db=Depends(get_db)):
    user = get_user(db, request)
    require(user, admin=True)
    if request.method not in {'GET', 'HEAD'}:
        raise HTTPException(409, 'Legacy writes are disabled during the pilot. Use the migrated webapp.')

@app.middleware('http')
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://commons.wikimedia.org https://upload.wikimedia.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.scheme == 'https' or request.headers.get('x-forwarded-proto', '').split(',')[0].strip() == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if (request.url.path.startswith('/api/') and not request.url.path.startswith('/api/volvo/map-tile/')) or request.url.path in {'/','/tiom','/central-control'} or request.url.path.startswith('/site/'):
        response.headers['Cache-Control'] = 'no-store'
    elif request.url.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable' if request.url.query else 'public, max-age=300, must-revalidate'
    return response

from app.routers import volvo
app.include_router(volvo.router)
app.include_router(health.router)
app.include_router(webapp.router)
app.include_router(sites.router)
app.include_router(site_ops.router)
app.include_router(maintenance.router)
for router in (masters.router, production.router, hsd.router, reconciliation.router, dashboard.router, shift_control.router):
    app.include_router(router, dependencies=[Depends(legacy_access)])

STATIC = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
def root():
    return FileResponse(STATIC / 'landing.html')

@app.get('/central-control')
def central_control():
    return FileResponse(STATIC / 'central.html')

@app.get('/tiom')
def tiom_app():
    return FileResponse(STATIC / 'index.html')

@app.get('/site/{site_id}')
def site_app(site_id: str):
    site_id = str(site_id or '').upper().strip()
    if site_id == 'TIOM':
        return RedirectResponse('/tiom', status_code=307)
    if site_id not in {'SOCP', 'KOCP'}:
        return RedirectResponse('/', status_code=307)
    return FileResponse(STATIC / 'site.html')

@app.get('/tiom/mechanical')
def tiom_mechanical_app():
    return RedirectResponse('/tiom', status_code=307)

@app.get('/site/{site_id}/mechanical')
def mechanical_app(site_id: str):
    site_id = str(site_id or '').upper().strip()
    if site_id == 'TIOM':
        return RedirectResponse('/tiom', status_code=307)
    return RedirectResponse(f'/site/{site_id}', status_code=307)
