import unittest
from datetime import date, time
from types import SimpleNamespace

from openpyxl import Workbook

from scripts.wb_gmail_worker import infer_file_context


class FakeDb:
    def __init__(self):
        self.definitions = {
            code: SimpleNamespace(shift=code, start_time=start, end_time=end,
                                  active=True, scheduled_hours=8)
            for code, (start, end) in {
                "A": (time(6, 0), time(14, 0)),
                "B": (time(14, 0), time(22, 0)),
                "C": (time(22, 0), time(6, 0)),
            }.items()
        }

    def get(self, _model, shift):
        return self.definitions.get(shift)


def sheet(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Movement Date", "Shift Code", "Vehicle Number", "GW Created Time"])
    for row in rows:
        ws.append(row)
    idx = {"date": 0, "shift": 1, "vehicle": 2, "time": 3}
    return ws, idx


class WbGmailShiftParityTests(unittest.TestCase):
    def test_c_shift_calendar_dates_resolve_to_previous_operating_date(self):
        ws, idx = sheet([
            [date(2026, 10, 3), "C", "T-1", time(22, 11)],
            [date(2026, 10, 3), "C", "T-2", time(23, 59)],
            [date(2026, 10, 4), "C", "T-3", time(0, 7)],
            [date(2026, 10, 4), "C", "T-4", time(4, 34)],
        ])
        operating_date, shift = infer_file_context(ws, 1, idx, FakeDb())
        self.assertEqual(shift, "C")
        self.assertEqual(operating_date, date(2026, 10, 3))

    def test_c_shift_single_operating_date_convention_is_accepted(self):
        ws, idx = sheet([
            [date(2026, 10, 3), "C", "T-1", time(22, 11)],
            [date(2026, 10, 3), "C", "T-2", time(0, 7)],
            [date(2026, 10, 3), "C", "T-3", time(4, 34)],
        ])
        operating_date, shift = infer_file_context(ws, 1, idx, FakeDb())
        self.assertEqual(shift, "C")
        self.assertEqual(operating_date, date(2026, 10, 3))


if __name__ == "__main__":
    unittest.main()
