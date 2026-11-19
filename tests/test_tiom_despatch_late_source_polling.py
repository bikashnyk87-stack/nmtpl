"""Bounded Despatch Gmail follow-ups for late WB Time and Permit Qty.

A first successful E-Pass day is no longer the end of source scanning.
The 12:00/18:00 IST checks catch later approved mail while keeping polling
bounded and avoiding repeated sweeps in the same process.
"""
from datetime import datetime

from zoneinfo import ZoneInfo

from app.routers.automation import (
    DESPATCH_LATE_SOURCE_HOURS_IST, despatch_due_late_hours,
)


def at(hour, minute=0):
    return datetime(2026,11,20,hour,minute,tzinfo=ZoneInfo("Asia/Kolkata"))


def test_despatch_late_source_checks_are_bounded():
    assert DESPATCH_LATE_SOURCE_HOURS_IST==(12,18)
    assert despatch_due_late_hours(at(11,59),set())==[]
    assert despatch_due_late_hours(at(12),set())==[12]
    assert despatch_due_late_hours(at(18),set())==[12,18]


def test_despatch_completed_slots_not_queried_again():
    done={"2026-11-20:12"}
    assert despatch_due_late_hours(at(12,20),done)==[]
    assert despatch_due_late_hours(at(18,0),done)==[18]
    done.add("2026-11-20:18")
    assert despatch_due_late_hours(at(22,30),done)==[]


def test_late_restart_batches_due_windows_into_one_poll():
    # If the process starts at 20:00, it must make ONE consolidated Gmail
    # scan and mark both missed time slots done, not scan twice.
    pending=despatch_due_late_hours(at(20),set())
    assert pending==[12,18]
    complete={f"2026-11-20:{hour}" for hour in pending}
    assert despatch_due_late_hours(at(20,10),complete)==[]
