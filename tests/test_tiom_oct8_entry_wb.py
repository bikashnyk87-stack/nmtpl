from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.site_models import ensure_tiom_entry_columns

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app' / 'static'


def test_nullable_entry_migrations_on_older_schema_are_repeatable():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE tiom_source_deployment (deployment_id VARCHAR(70) PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE tiom_drilling_shift (drilling_id VARCHAR(90) PRIMARY KEY)'))
    ensure_tiom_entry_columns(engine)
    ensure_tiom_entry_columns(engine)
    insp = inspect(engine)
    dep = {x['name'] for x in insp.get_columns('tiom_source_deployment')}
    drilling = {x['name'] for x in insp.get_columns('tiom_drilling_shift')}
    assert 'operator_id' in dep
    assert {'rom_ob_holes', 'bhj_bhq_holes'} <= drilling
    engine.dispose()


def test_entry_defaults_and_safe_wb_merge_are_present():
    js=(STATIC / 'tiom_phase1.js').read_text('utf-8')
    assert 'misRows:15,depRows:20' in js
    assert 'Math.max(20,(d.deployments||[]).length)' in js
    assert "q('tm_driver_panel')?.before(q('tm_dep_panel'))" in js
    assert "const used=new Set(current.map(x=>x.wbMovementKey)" in js
    assert 'copyPreviousMisRow(5)' in js
    assert 'copyPreviousMisRow(10)' in js
    assert 'operatorId:v(' in js
    assert 'romObHoles:v(' in js and 'bhjBhqHoles:v(' in js


def test_wb_history_and_excel_are_read_only_and_filterable():
    api=(ROOT / 'app' / 'routers' / 'webapp.py').read_text('utf-8')
    ui=(STATIC / 'tiom_wb_reporting.js').read_text('utf-8')
    index=(STATIC / 'index.html').read_text('utf-8')
    for term in ['get_tiom_wb_history','/wb/full-export',
                 'latestConfirmedOnly', 'Content-Disposition','getTiomWbHistory']:
        assert term in api
    assert 'All shifts' in ui
    assert 'Download Full XLSX' in ui
    assert 'tiom_wb_reporting.js' in index


def test_drill_holes_and_operator_are_additive_nullable():
    model=(ROOT / 'app' / 'site_models.py').read_text('utf-8')
    api=(ROOT / 'app' / 'routers' / 'webapp.py').read_text('utf-8')
    assert 'operator_id: Mapped[str | None]' in model
    assert 'rom_ob_holes: Mapped[int | None]' in model
    assert 'bhj_bhq_holes: Mapped[int | None]' in model
    assert 'unclassifiedHoles' in api
    assert 'Close the earlier time range before transferring' in api
