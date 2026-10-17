"""KPN AVS web-client adapter. Endpoint contracts need subscriber validation.

Protocol references and dates are recorded in SOURCES.md. This module never
decrypts media: Kodi's InputStream Adaptive handles licensed Widevine playback.
"""
import http.cookiejar
import json
import os
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .storage import read_json, write_json

ROOTS = (
    'https://api-avs67.tv.prod.itvavs.prod.aws.kpn.com/101/1.2.0/A/nld/pctv/kpn',
    'https://api.tv.prod.itvavs.prod.aws.kpn.com/101/1.2.0/A/nld/pctv/kpn',
    'https://api.tv.kpn.com/101/1.2.0/A/nld/pctv/kpn',
)
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/112.0.0.0 Safari/537.36')
HEADERS = {'User-Agent': USER_AGENT, 'Accept': 'application/json',
           'Accept-Language': 'nl-NL,nl;q=0.9',
           'AVSSite': 'http://www.itvonline.nl',
           'Origin': 'https://tv.kpn.com', 'Referer': 'https://tv.kpn.com/',
           'Cache-Control': 'no-cache', 'X-XSRF-TOKEN': 'null'}


class KPNError(Exception):
    """Safe error code only; never include response bodies, URLs or credentials."""


class AuthError(KPNError):
    pass


def containers(result):
    rows = result.get('containers', []) if isinstance(result, dict) else []
    if not isinstance(rows, list):
        raise KPNError('INVALID_CONTAINERS')
    return rows


def flatten(rows):
    for row in rows:
        yield row
        yield from flatten(row.get('containers', []))


def content_id(row):
    return str(row.get('metadata', {}).get('contentId', row.get('id', '')))


def asset_for(row, kind):
    assets = row.get('entitlement', {}).get('assets', row.get('assets', []))
    candidates = []
    for asset in assets:
        video = str(asset.get('videoType', ''))
        if video and 'DASH' not in video:
            continue
        if kind != 'channel':
            if asset.get('rights') not in ('watch', 'play'):
                continue
            if kind == 'program' and asset.get('programType') != 'CUTV':
                continue
            if kind == 'vod' and asset.get('assetType') != 'MASTER':
                continue
        if asset.get('assetId') is not None:
            candidates.append(asset)
    # Prefer explicit Widevine assets, then the provider's own quality ranking.
    candidates.sort(key=lambda a: ('WV' in str(a.get('videoType', '')),
                                  int(a.get('metadata', {}).get('ranking', 0))), reverse=True)
    if not candidates:
        raise KPNError('NO_PLAYABLE_ASSET')
    return str(candidates[0]['assetId'])


def playback(result):
    sources = result.get('src', {}).get('sources', {})
    if isinstance(sources, list):
        sources = next((s for s in sources if 'dash' in s.get('type', '').lower()),
                       sources[0] if sources else {})
    url = sources.get('src', '')
    license_url = sources.get('contentProtection', {}).get('widevine', {}).get('licenseAcquisitionURL', '')
    if not url:
        raise KPNError('NO_MANIFEST')
    # Preserve signed query strings exactly; stripping bitrate parameters can
    # invalidate a signature. Never interpret a returned URL as plugin code.
    if urlparse(url).scheme != 'https':
        raise KPNError('INVALID_MANIFEST_URL')
    if not license_url or urlparse(license_url).scheme != 'https':
        raise KPNError('NO_WIDEVINE_LICENSE')
    return {'url': url, 'license': license_url}


class Client:
    def __init__(self, profile, endpoint=0, transport=None):
        self.profile = profile
        self.root = ROOTS[int(endpoint)]
        os.makedirs(profile, exist_ok=True)
        self.cookie_path = os.path.join(profile, 'cookies.txt')
        self.state_path = os.path.join(profile, 'session.json')
        self.state = read_json(self.state_path, {})
        # Cookies belong to one endpoint. Switching hosts requires a new login.
        if self.state.get('endpoint') != self.root:
            self.state = {'device_id': self.state.get('device_id', secrets.token_hex(32)),
                          'endpoint': self.root, 'logged_in': False}
        self.jar = http.cookiejar.MozillaCookieJar(self.cookie_path)
        if self.state.get('logged_in'):
            try:
                self.jar.load(ignore_discard=True)
            except (OSError, http.cookiejar.LoadError):
                self.state['logged_in'] = False
        self.opener = build_opener(HTTPCookieProcessor(self.jar))
        self.transport = transport or self._http

    @property
    def logged_in(self):
        return bool(self.state.get('logged_in'))

    def _save(self):
        write_json(self.state_path, self.state)
        # Save cookie scope, expiration and secure flags, including session cookies.
        self.jar.save(ignore_discard=True)
        os.chmod(self.cookie_path, 0o600)

    def logout(self):
        self.jar.clear()
        self.state['logged_in'] = False
        self._save()

    def _http(self, method, path, params, body):
        url = self.root + path
        if params:
            url += '?' + urlencode(params)
        request = Request(url, method=method, headers=dict(HEADERS),
                          data=json.dumps(body).encode('utf-8') if body is not None else None)
        if body is not None:
            request.add_header('Content-Type', 'application/json')
        try:
            with self.opener.open(request, timeout=25) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise KPNError('RESPONSE_TOO_LARGE')
            self._save()
            value = json.loads(raw.decode('utf-8'))
            if isinstance(value, str):
                value = json.loads(value)
            return value
        except HTTPError as error:
            if error.code in (401, 403):
                raise AuthError('HTTP_%s' % error.code) from None
            raise KPNError('HTTP_%s' % error.code) from None
        except (URLError, OSError, TimeoutError):
            raise KPNError('NETWORK_ERROR') from None
        except (ValueError, UnicodeError):
            raise KPNError('INVALID_JSON') from None

    def request(self, path, params=None, body=None):
        try:
            value = self.transport('POST' if body is not None else 'GET', path, params or {}, body)
            if not isinstance(value, dict):
                raise KPNError('INVALID_RESPONSE')
            code = value.get('resultCode')
            if code != 'OK':
                # Return only a bounded identifier. Messages can contain PII.
                safe = str(code or 'UNKNOWN')
                safe = safe if safe.replace('_', '').isalnum() and len(safe) < 64 else 'UNKNOWN'
                if any(term in safe.upper() for term in ('AUTH', 'SESSION', 'LOGIN')):
                    raise AuthError(safe)
                raise KPNError('API_' + safe)
            result = value.get('resultObj', {})
            if not isinstance(result, dict):
                raise KPNError('INVALID_RESULT')
            return result
        except AuthError:
            self.logout()
            raise

    def login(self, username, password, mode='kpnid'):
        self.logout()
        device_id = self.state['device_id']
        if mode == 'kpnid':
            body = {'credentialsExtAuth': {
                'credentials': {'loginType': 'UsernamePassword', 'username': username,
                                'password': password, 'appId': 'KPN'},
                'remember': 'Y', 'deviceInfo': {
                    'deviceId': device_id, 'deviceIdType': 'DEVICEID', 'deviceType': 'PCTV',
                    'deviceVendor': 'CHROME', 'deviceModel': '112.0.0.0',
                    'deviceFirmVersion': 'Windows', 'appVersion': '10'}}}
        elif mode == 'subscription':
            body = {'credentialsStdAuth': {
                'username': username, 'password': password, 'remember': 'Y',
                'deviceRegistrationData': {
                    'deviceId': device_id, 'accountDeviceIdType': 'DEVICEID',
                    'deviceType': 'PCTV', 'vendor': 'CHROME', 'model': '112.0.0.0',
                    'deviceFirmVersion': 'Windows', 'appVersion': '10'}}}
        else:
            raise ValueError('Unknown login mode')
        try:
            self.request('/USER/SESSIONS/', body=body)
            self.state['logged_in'] = True
            self._save()
        except KPNError:
            self.logout()
            raise

    def paged(self, path, params=None, size=100):
        params = dict(params or {})
        found, seen = [], set()
        for page in range(100):
            offset = page * size
            result = self.request(path, dict(params, **{'from': offset, 'to': offset + size - 1}))
            rows = containers(result)
            if not rows:
                return found
            added = 0
            for row in rows:
                key = row.get('id', content_id(row))
                if not key:
                    raise KPNError('MISSING_CONTENT_ID')
                key = str(key)
                if key not in seen:
                    found.append(row)
                    seen.add(key)
                    added += 1
            total = result.get('total')
            if total is not None and len(found) >= int(total):
                return found
            if not added:
                raise KPNError('PAGINATION_STALLED')
            if total is None and len(rows) < size:
                return found
        raise KPNError('PAGINATION_LIMIT')

    def channels(self):
        return self.paged('/TRAY/LIVECHANNELS', {
            'orderBy': 'orderId', 'sortOrder': 'asc', 'dfilter_channels': 'subscription'})

    def now(self, channel_ids):
        if not channel_ids:
            return []
        return self.paged('/TRAY/SEARCH/PROGRAM', {
            'filter_airingTime': 'now', 'filter_channelIds': ','.join(map(str, channel_ids)),
            'dfilter_channels': 'subscription'})

    def epg(self, channel_id, day):
        result = self.request('/TRAY/EPG', {'filter_day': day,
                              'filter_channelIds': channel_id, 'extendedChannelMetadata': 'true'})
        return [row for row in flatten(containers(result))
                if row.get('metadata', {}).get('airingStartTime') is not None]

    def catalogue(self, category=None, query=None):
        params = {'dfilter_packages': 'matchSubscription', 'orderBy': 'title', 'sortOrder': 'asc'}
        if category == 'series':
            params['filter_contentType'] = 'GROUP_OF_BUNDLES'
            params['filter_contentSubtype'] = 'SERIES'
        elif category == 'movies':
            params['filter_contentType'] = 'VOD'
            params['filter_contentSubtype'] = 'VOD'
        if query:
            params['filter_title'] = query
        return self.paged('/TRAY/SEARCH/VOD', params)

    def detail(self, kind, identifier):
        if kind not in ('GROUP_OF_BUNDLES', 'BUNDLE', 'PROGRAM', 'VOD'):
            raise ValueError('Unknown content type')
        return containers(self.request('/CONTENT/DETAIL/%s/%s' % (kind, quote(str(identifier), safe=''))))

    def stream(self, kind, identifier):
        if not self.logged_in:
            raise AuthError('LOGIN_REQUIRED')
        if kind == 'channel':
            row = next((row for row in self.channels()
                        if str(row.get('metadata', {}).get('channelId', row.get('id'))) == str(identifier)), None)
            if row is None:
                raise KPNError('CHANNEL_UNAVAILABLE')
            asset = asset_for(row, kind)
            content_type = 'LIVE'
        elif kind in ('program', 'vod'):
            content_type = 'PROGRAM' if kind == 'program' else 'VOD'
            rows = containers(self.request('/CONTENT/USERDATA/%s/%s' %
                              (content_type, quote(str(identifier), safe=''))))
            if not rows:
                raise KPNError('CONTENT_UNAVAILABLE')
            asset = asset_for(rows[0], kind)
        else:
            raise ValueError('Unknown playback type')
        self.request('/USER/DSHTOKEN', {'deviceId': self.state['device_id']})
        result = self.request('/CONTENT/VIDEOURL/%s/%s/%s/' %
                              (content_type, quote(str(identifier), safe=''), quote(asset, safe='')),
                              {'deviceId': self.state['device_id'], 'profile': 'G03',
                               'time': int(time.time() * 1000)})
        return playback(result)

    def media_headers(self, url):
        # Only cookies applicable to this precise URL; never leak all API cookies
        # to an unrelated CDN or license host.
        request = Request(url, headers={'User-Agent': USER_AGENT,
                                      'Origin': HEADERS['Origin'], 'Referer': HEADERS['Referer']})
        self.jar.add_cookie_header(request)
        return dict(request.header_items())
