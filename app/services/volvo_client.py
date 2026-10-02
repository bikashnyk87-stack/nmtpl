"""Read-only Volvo client. Credentials never enter telemetry payloads or logs."""
import base64
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ENDPOINTS = {
    'vehicles': ('vehicleResponse', 'vehicles'),
    'vehiclepositions': ('vehiclePositionResponse', 'vehiclePositions'),
    'vehiclestatuses': ('vehicleStatusResponse', 'vehicleStatuses'),
}
ROOT = Path(__file__).resolve().parents[2]


class VolvoError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise VolvoError('Unexpected redirect from Volvo; request stopped.')


def timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def report_time(row):
    return timestamp(row.get('receivedDateTime') or row.get('createdDateTime'))


def _env_file_values():
    path = ROOT / '.env'
    out = {}
    if not path.is_file():
        return out
    try:
        for raw in path.read_text(encoding='utf-8-sig').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            out[key] = value
    except OSError:
        return {}
    return out


def credential(name):
    return os.environ.get(name) or _env_file_values().get(name) or ''


def parse_page(payload, endpoint):
    wrapper, key = ENDPOINTS[endpoint]
    try:
        rows = payload[wrapper][key]
        more = payload['moreDataAvailable']
    except (KeyError, TypeError):
        raise VolvoError('Unexpected Volvo response structure; no data saved.') from None
    if not isinstance(rows, list) or type(more) is not bool:
        raise VolvoError('Invalid Volvo records or pagination flag.')
    if any(not isinstance(r, dict) or not isinstance(r.get('vin'), str) or len(r['vin']) != 17 for r in rows):
        raise VolvoError('Invalid vehicle identifier in Volvo response.')
    return rows, more


class VolvoClient:
    def __init__(self, username, password):
        if not username or not password or ':' in username:
            raise VolvoError('Volvo API username and password are required.')
        self._authorization = 'Basic ' + base64.b64encode((username + ':' + password).encode()).decode()
        self._base_url = (credential('VOLVO_API_BASE_URL') or 'https://api.volvotrucks.com/vehicle').rstrip('/')
        self._opener = urllib.request.build_opener(NoRedirect())

    def page(self, endpoint, params):
        url = self._base_url + '/' + endpoint
        if params:
            url += '?' + urllib.parse.urlencode(params, doseq=True)
        request = urllib.request.Request(url, headers={
            'Accept': 'application/x.volvogroup.com.' + endpoint + '.v1.0+json',
            'Authorization': self._authorization,
            'User-Agent': 'NMTPL-TIOM-Volvo-Integration/1.1',
        })
        try:
            with self._opener.open(request, timeout=45) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise VolvoError('Volvo response exceeds the size limit.')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise VolvoError('Volvo HTTP ' + str(exc.code) + '; check access or rate limits. No data saved.') from None
        except (urllib.error.URLError, OSError):
            raise VolvoError('Unable to connect securely to Volvo. No data saved.') from None
        except (ValueError, UnicodeError):
            raise VolvoError('Volvo returned invalid JSON. No data saved.') from None

    def fetch(self, endpoint):
        params = {} if endpoint == 'vehicles' else {'latestOnly': 'true', 'datetype': 'received'}
        records, cursors = [], set()
        for _ in range(1000):
            rows, more = parse_page(self.page(endpoint, params), endpoint)
            records.extend(rows)
            if not more:
                return records
            cursor = rows[-1]['vin'] if rows else None
            if not cursor or cursor in cursors:
                raise VolvoError('Volvo pagination did not advance; no data saved.')
            cursors.add(cursor)
            params['lastVin'] = cursor
        raise VolvoError('Volvo pagination exceeded the safety limit.')
