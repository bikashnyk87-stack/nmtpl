"""Effective-dated TIOM shifts and uninterrupted Gmail scheduler regression tests."""
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace

from app.services.time_context import TZ, operating_context
from app.services.tiom_shift_schedule import context_at, definition_for_day, times_for_day
from scripts.wb_gmail_worker import wb_weigh_at
from app.routers import automation

ROOT = Path(__file__).resolve().parents[1]


def _dt(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_october_shift_changeover_and_overnight_ownership():
    expected = [
        (_dt(2026,9,30,20,59), (date(2026,9,30),"B")),
        (_dt(2026,9,30,21), (date(2026,9,30),"C")),
        (_dt(2026,10,1,4,59), (date(2026,9,30),"C")),
        (_dt(2026,10,1,5,30), None),  # policy-transition gap; do not guess
        (_dt(2026,10,1,6), (date(2026,10,1),"A")),
        (_dt(2026,10,1,13,59), (date(2026,10,1),"A")),
        (_dt(2026,10,1,14), (date(2026,10,1),"B")),
        (_dt(2026,10,1,21,30), (date(2026,10,1),"B")),
        (_dt(2026,10,1,22), (date(2026,10,1),"C")),
        (_dt(2026,10,2,5,59), (date(2026,10,1),"C")),
        (_dt(2026,10,2,6), (date(2026,10,2),"A")),
    ]
    for when, result in expected:
        assert context_at(when) == result
        if result is not None:
            assert operating_context(when)[:2] == result


def test_historical_shift_definitions_are_date_scoped_and_nonmutating():
    master=SimpleNamespace(shift="C",start_time=time(22),end_time=time(6),
                           active=True,scheduled_hours=8)
    old=definition_for_day(date(2026,9,30),master)
    new=definition_for_day(date(2026,10,1),master)
    assert (old.start_time,old.end_time)==(time(21),time(5))
    assert (new.start_time,new.end_time)==(time(22),time(6))
    assert (master.start_time,master.end_time)==(time(22),time(6))
    assert wb_weigh_at(date(2026,9,30),old,time(21,30)) is not None
    assert wb_weigh_at(date(2026,10,1),new,time(21,30)) is None
    assert wb_weigh_at(date(2026,10,1),new,time(23,30)) is not None
    stamp=wb_weigh_at(date(2026,10,1),new,time(2,15))
    assert stamp.date()==date(2026,10,2)


def test_render_wb_polling_does_not_stop_when_shift_confirmed():
    source=(ROOT/"app/routers/automation.py").read_text("utf-8")
    assert automation.WB_POLL_SECONDS == 180
    assert "wb_due = monotonic + WB_POLL_SECONDS" in source
    assert "await asyncio.to_thread(gmail_once)" in source
    assert "wb_done.add(" not in source
    assert "wb_checked" not in source


def test_auto_gmail_revision_guard_precedes_new_batch():
    worker=(ROOT/"scripts/wb_gmail_worker.py").read_text("utf-8")
    protected=worker[worker.index("def _ingest_single_shift_xlsx("):
                     worker.index("# NMTPL_WB_TIME_FIRST_SHIFT_ROUTING_V4")]
    assert protected.index("prior_confirmed =") < protected.index("batch = WbImportBatch(")
    assert "WB_EMAIL_REVISION_HELD" in protected
    assert "Manual source review required" in protected
