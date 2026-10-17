"""Regression checks for TIOM machine Source/RL correction versus actual transfer."""
import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / 'app' / 'routers' / 'webapp.py'
UI = ROOT / 'app' / 'static' / 'tiom_phase1.js'


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def check_source_correction(existing, new_source, payload):
    root = ast.parse(API.read_text(encoding='utf-8'))
    node = next(x for x in root.body if isinstance(x, ast.FunctionDef)
                and x.name == '_tiom_source_correction_reason')
    env = {'HTTPException': HttpError, 'short': lambda s: s[:300]}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(API), 'exec'), env)
    return env['_tiom_source_correction_reason'](existing, new_source, payload)


def test_audited_source_correction_accepts_same_deployment_with_reason():
    row = SimpleNamespace(source_location_id='WRONG-SOURCE')
    data = {'previousSourceLocationId': 'WRONG-SOURCE',
            'newSourceLocationId': 'CORRECT-SOURCE',
            'reason': 'Incorrect source selected during entry'}
    assert check_source_correction(row, 'CORRECT-SOURCE', data) == data['reason']


def test_source_correction_rejects_silent_and_stale_changes():
    row = SimpleNamespace(source_location_id='ORIGINAL')
    valid = {'previousSourceLocationId': 'ORIGINAL',
             'newSourceLocationId': 'CORRECT',
             'reason': 'Original field entry was wrong'}
    for payload, status in [
        (None, 409),
        ({**valid, 'previousSourceLocationId': 'STALE'}, 409),
        ({**valid, 'newSourceLocationId': 'OTHER'}, 409),
        ({**valid, 'reason': 'bad'}, 422),
        ({**valid, 'reason': 'x' * 251}, 422),
    ]:
        try:
            check_source_correction(row, 'CORRECT', payload)
        except HttpError as exc:
            assert exc.status_code == status
        else:
            raise AssertionError('An unauthorized source rewrite was accepted')


def test_correction_is_explicit_audited_and_does_not_rewrite_saved_trips():
    api = API.read_text(encoding='utf-8')
    ui = UI.read_text(encoding='utf-8')
    for term in (
        '_tiom_source_correction_reason(existing,source.location_id',
        "entry.source_location_id=source.location_id",
        "'TIOM_SOURCE_CORRECTION'",
        "'linkedSubmittedTrips':linked_submitted",
        'submitted trip(s) still reference the original source',
        "existing.machine_id!=machine.machine_id",
        'if _tiom_deployment_overlap(',
    ):
        assert term in api, term
    for term in (
        'window.saveDeployments=function()',
        'previousSourceLocationId:x.old.sourceLocationId',
        'sourceCorrections',
        'Wrong source? Select the correct Source and Save',
        'use Transfer Equipment',
    ):
        assert term in ui, term
