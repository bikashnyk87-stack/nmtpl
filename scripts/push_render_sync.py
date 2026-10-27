from __future__ import annotations
import json
import urllib.request
from pathlib import Path
from sqlalchemy import text
from app.db import engine
from app.services.cloud_sync import init_sync_source

ROOT = Path(__file__).resolve().parents[1]
PUSH_STATE = ROOT / 'data' / 'render_push_state.json'


def _save(state):
    temp = PUSH_STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2), encoding='utf-8')
    temp.replace(PUSH_STATE)


def enable_tracking():
    if PUSH_STATE.exists():
        return
    init_sync_source(engine, force_local=True)
    with engine.connect() as conn:
        cursor = int(conn.execute(text('SELECT COALESCE(MAX(change_id),0) FROM sync_change_log')).scalar())
    _save({'initialLocalId': cursor, 'lastLocalId': cursor})


def push_pending(base_url, token, render_watermark):
    if not PUSH_STATE.exists():
        return 0
    state = json.loads(PUSH_STATE.read_text(encoding='utf-8'))
    count = 0
    while True:
        with engine.connect() as conn:
            rows = conn.execute(text('''SELECT change_id,table_name,operation,row_data
                FROM sync_change_log WHERE change_id > :cursor ORDER BY change_id LIMIT 100'''),
                {'cursor': state['lastLocalId']}).mappings().all()
        if not rows:
            return count
        changes = [{'changeId': int(r['change_id']), 'table': r['table_name'],
                    'operation': r['operation'], 'row': r['row_data']} for r in rows]
        payload = {'baseChangeId': render_watermark, 'initialLocalId': state['initialLocalId'],
                   'changes': changes}
        request = urllib.request.Request(base_url.rstrip('/') + '/api/sync/upload',
            data=json.dumps(payload, default=str).encode('utf-8'), method='POST',
            headers={'Content-Type': 'application/json', 'X-NMTPL-Sync-Token': token})
        with urllib.request.urlopen(request, timeout=120) as response:
            ack = json.loads(response.read().decode('utf-8'))
        if not ack.get('ok') or int(ack.get('lastLocalId', -1)) != changes[-1]['changeId']:
            raise RuntimeError('Render did not acknowledge the complete upload batch.')
        state['lastLocalId'] = changes[-1]['changeId']
        _save(state)
        count += int(ack['applied'])
