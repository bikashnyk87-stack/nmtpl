import asyncio
import os
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.db import engine, get_db, SessionLocal, Base
from app.auth import WebUser, WebSession, get_user, require, MODULES, hash_password
from app.config import settings
from app.models import MasterOption, WbHeaderAlias
from app.routers import health, masters, production, hsd, reconciliation, dashboard, shift_control, webapp, sites, site_ops, maintenance
from app.services.wb_mapping import ensure_wb_header_mapping
from app.services.attendance_automation import automation_loop
from app.site_models import create_multisite_tables
from app.maintenance_models import create_maintenance_tables
from app.services.site_context import seed_default_sites_and_shifts
from app.services.cloud_sync import init_sync_source
from app.services.tiom_reference_seed import seed_tiom_temp_reference_data
from app.services.tiom_location_erp import backfill_wb_canonical

@asynccontextmanager
async def lifespan(app):
    # Fresh database safety: create the complete registered core schema first so
    # all FK targets (persons/equipment/locations/products/etc.) exist before
    # multisite and maintenance extension tables are created.
    Base.metadata.create_all(engine, checkfirst=True)
    create_multisite_tables(engine)
    create_maintenance_tables(engine)
    init_sync_source(engine)
    # Pilot migration safety: if an older build left exactly one active account
    # with no management/modules, treat it as the original local administrator.
    # Never auto-promote when multiple accounts exist.
    with SessionLocal() as db:
        ensure_wb_header_mapping(db)
        seed_default_sites_and_shifts(db)
        if os.getenv("TIOM_TEMP_REFERENCE_SEED", "").strip().lower() in {"1","true","yes","on"}:
            seed_counts=seed_tiom_temp_reference_data(db)
            wb_map_counts=backfill_wb_canonical(db)
            print("TIOM_TEMP_REFERENCE_SEED_OK="+json.dumps(seed_counts,sort_keys=True),flush=True)
            print("TIOM_ERP_WB_CANONICAL="+json.dumps(wb_map_counts,sort_keys=True),flush=True)
        users = db.query(WebUser).all()
        # Cloud test bootstrap: create the first administrator only when the database
        # is empty and explicit Render environment variables are provided. No
        # credentials are stored in source control.
        if not users:
            bootstrap_login = os.getenv('NMTPL_BOOTSTRAP_ADMIN_LOGIN', '').strip().lower()
            bootstrap_password = os.getenv('NMTPL_BOOTSTRAP_ADMIN_PASSWORD', '')
            bootstrap_name = os.getenv('NMTPL_BOOTSTRAP_ADMIN_NAME', 'Administrator').strip() or 'Administrator'
            if bootstrap_login and bootstrap_password:
                db.add(WebUser(
                    login_id=bootstrap_login,
                    name=bootstrap_name,
                    password_hash=hash_password(bootstrap_password),
                    modules=','.join(sorted(MODULES)),
                    shifts='ALL',
                    admin=True,
                    active=True,
                ))
                db.flush()
                users = db.query(WebUser).all()
        if len(users) == 1:
            u = users[0]
            if u.active and not u.admin and not (u.modules or '').strip():
                u.admin = True
                u.modules = ','.join(sorted(MODULES))
                u.shifts = 'ALL'
        db.commit()
        if os.getenv("TIOM_TEMP_SELFTEST", "").strip().lower() in {"1","true","yes","on"}:
            admin_user=next((x for x in users if x.active and x.admin),None)
            if not admin_user:
                raise RuntimeError("TIOM temp self-test requires an active admin user.")
            mis_test=webapp.tiom_mis_desk(db,admin_user,{})
            dash_test=webapp.dashboard_desk(db,admin_user,{"mode":"TODAY","shift":"ALL"})
            expected_activities={"STACKING","DRILL FACE","TWIN HOPPER CLEANING","QDS","DISPATCH"}
            activity_ids={x.get("id") for x in mis_test.get("activities",[])}
            machine_ids={x.get("id") for x in mis_test.get("machines",[])}
            required_machines={"DOZER D8-1","DOZER D8-2","DOZER D6-3","DOZER D6-4","GRADER-01","GRADER-02","01.HITACHI-210 (DRILL)","02.HITACHI-210 (DRILL)-2"}
            kpis=dash_test.get("kpis",{})
            production_source_ids={x.get("id") for x in mis_test.get("sourceLocations",[])}
            production_destination_ids={x.get("id") for x in mis_test.get("destinationLocations",[])}
            dashboard_source_ids={x.get("id") for x in dash_test.get("availableSources",[])}
            dashboard_destination_ids={x.get("id") for x in dash_test.get("availableDestinations",[])}
            checks={
                "activitiesVisible":expected_activities.issubset(activity_ids),
                "machinesVisible":required_machines.issubset(machine_ids),
                "leadRulesVisible":len(mis_test.get("leadRules",[])),
                "leadDashboardKeys":all(x in kpis for x in ("leadResolvedTrips","leadMissingTrips","leadWithWbTrips","leadWithoutWbTrips","avgLeadKm","leadTonKm")),
                "sevenDayCumulative":all("cumulativeTonnes" in x and "cumulativeLeadTonKm" in x for x in dash_test.get("sevenDay",[])),
                "monthCumulative":all("cumulativeTonnes" in x for x in dash_test.get("monthTrend",[])),
                "sourceMasterConsistent":production_source_ids==dashboard_source_ids and len(production_source_ids)>=5,
                "destinationMasterConsistent":production_destination_ids==dashboard_destination_ids and len(production_destination_ids)>=29,
                "dashboardUsesCanonicalFilters":all(isinstance(x,dict) and x.get("id") and x.get("label") for x in dash_test.get("availableSources",[])+dash_test.get("availableDestinations",[])),
            }
            if not all(v is True or (k=="leadRulesVisible" and int(v)>=276) for k,v in checks.items()):
                raise RuntimeError("TIOM temp self-test failed: "+json.dumps(checks,sort_keys=True))
            print("TIOM_TEMP_SELFTEST_OK="+json.dumps(checks,sort_keys=True),flush=True)

    attendance_task = asyncio.create_task(automation_loop(), name="attendance-auto-close")
    cloud_automation_task = asyncio.create_task(automation.automation_loop(), name="cloud-integrations")
    try:
        yield
    finally:
        attendance_task.cancel()
        cloud_automation_task.cancel()
        with suppress(asyncio.CancelledError):
            await attendance_task
        with suppress(asyncio.CancelledError):
            await cloud_automation_task


app = FastAPI(title="NMTPL Central Operations Platform", version="1.0.0-tiom2.1.0-field-hardening", lifespan=lifespan)


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
        # Static URLs are versioned with ?v= in the HTML, so cache aggressively on field devices.
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable' if request.url.query else 'public, max-age=300, must-revalidate'
    return response

from app.routers import volvo, automation, sync
app.include_router(volvo.router)
app.include_router(automation.router)
app.include_router(sync.router)
app.include_router(health.router)
app.include_router(webapp.router)
app.include_router(sites.router)
app.include_router(site_ops.router)
app.include_router(maintenance.router)
for router in (masters.router, production.router, hsd.router, reconciliation.router, dashboard.router, shift_control.router):
    app.include_router(router, dependencies=[Depends(legacy_access)])

STATIC = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get("/")
def root():
    return FileResponse(STATIC / 'landing.html')


@app.get('/central-control')
def central_control():
    return FileResponse(STATIC / 'central.html')


@app.get("/tiom")
def tiom_app():
    return FileResponse(STATIC / 'index.html')


@app.get("/site/{site_id}")
def site_app(site_id: str):
    # The page resolves and authorizes the site through /api/sites/{site}/context.
    return FileResponse(STATIC / 'site.html')


@app.get("/tiom/mechanical")
def tiom_mechanical_app():
    # Compatibility only: Mechanical is now an integrated tab inside /tiom.
    return RedirectResponse('/tiom', status_code=307)


@app.get("/site/{site_id}/mechanical")
def mechanical_app(site_id: str):
    # Compatibility only: site modules stay inside their ERP workspace.
    return RedirectResponse(f'/site/{site_id}', status_code=307)
