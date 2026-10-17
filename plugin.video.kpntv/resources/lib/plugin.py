"""Kodi navigation, metadata and InputStream Adaptive integration."""
import datetime as dt
import json
import os
import sys
from urllib.parse import parse_qs, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from .api import Client, KPNError, AuthError, content_id, flatten
from .storage import SavedLists, write_json

STRINGS = {
    'live': 30001, 'replay': 30002, 'movies': 30003, 'series': 30004,
    'search': 30005, 'favorites': 30006, 'later': 30007, 'login': 30008,
    'logout': 30009, 'settings': 30010, 'diagnostics': 30011, 'empty': 30012,
    'username': 30013, 'password': 30014, 'number': 30015, 'pin': 30016,
    'login_ok': 30017, 'login_needed': 30018, 'error': 30019, 'failed': 30020,
    'add_favorites': 30021, 'add_later': 30022, 'remove': 30023, 'saved': 30024,
    'today': 30025, 'drm_missing': 30026, 'expired': 30027, 'signed_out': 30028,
    'no_profile': 30029, 'saved_diag': 30030, 'guide': 30031, 'not_yet': 30032,
    'now': 30033, 'next': 30034, 'partial_guide': 30035,
}


class Plugin:
    def __init__(self, argv):
        self.base, self.handle = argv[0], int(argv[1])
        self.params = {key: value[0] for key, value in parse_qs(argv[2].lstrip('?')).items()}
        self.addon = xbmcaddon.Addon()
        self.profile = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        self.client = Client(self.profile, int(self.addon.getSetting('endpoint') or 0))
        self.lists = SavedLists(self.profile)
        self.dialog = xbmcgui.Dialog()

    def tr(self, key):
        return self.addon.getLocalizedString(STRINGS[key])

    def url(self, action, **params):
        return self.base + '?' + urlencode(dict(action=action, **params))

    def notify(self, key):
        self.dialog.notification('KPN TV', self.tr(key), xbmcgui.NOTIFICATION_INFO)

    def finish(self, succeeded=True):
        xbmcplugin.endOfDirectory(self.handle, succeeded=succeeded, cacheToDisc=False)

    def entry(self, label, action, folder=True, record=None, **params):
        item = xbmcgui.ListItem(label=label)
        if record:
            info = item.getVideoInfoTag()
            info.setTitle(record['title'])
            info.setPlot(record.get('plot', ''))
            info.setMediaType('video' if record['kind'] in ('channel', 'program') else
                              'tvshow' if record['kind'] in ('series', 'season') else 'movie')
            if record.get('duration'):
                info.setDuration(int(record['duration']))
            item.setArt({'thumb': record.get('image', ''), 'fanart': record.get('image', '')})
            encoded = json.dumps(record, ensure_ascii=False)
            contexts = [(self.tr('add_favorites'), 'RunPlugin(%s)' % self.url(
                'save', list='favorites', record=encoded))]
            if record['kind'] != 'channel':
                contexts.append((self.tr('add_later'), 'RunPlugin(%s)' % self.url(
                    'save', list='later', record=encoded)))
            if self.params.get('action') == 'saved':
                contexts.append((self.tr('remove'), 'RunPlugin(%s)' % self.url(
                    'remove', list=self.params['list'], record=encoded)))
            item.addContextMenuItems(contexts)
        if not folder:
            item.setProperty('IsPlayable', 'true' if action == 'play' else 'false')
        xbmcplugin.addDirectoryItem(self.handle, self.url(action, **params), item, isFolder=folder)

    def root(self):
        for key in ('live', 'replay', 'movies', 'series', 'search'):
            self.entry(self.tr(key), key)
        for key in ('favorites', 'later'):
            self.entry(self.tr(key), 'saved', list=key)
        for key in (('logout',) if self.client.logged_in else ('login',)) + ('settings', 'diagnostics'):
            self.entry(self.tr(key), key, folder=False)
        self.finish()

    def login(self):
        mode = 'subscription' if self.addon.getSetting('login_mode') == '1' else 'kpnid'
        username = self.dialog.input(self.tr('number' if mode == 'subscription' else 'username')).strip()
        if not username:
            return False
        password = self.dialog.input(self.tr('pin' if mode == 'subscription' else 'password'),
                                     type=xbmcgui.INPUT_ALPHANUM, option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not password:
            return False
        # Password is used only in memory for this request and is never logged or saved.
        self.client.login(username, password, mode)
        self.notify('login_ok')
        return True

    def require_login(self):
        if self.client.logged_in:
            return True
        self.dialog.ok('KPN TV', self.tr('login_needed'))
        return self.login()

    @staticmethod
    def channel_id(row):
        return str(row.get('metadata', {}).get('channelId', row.get('id', '')))

    @staticmethod
    def record(row, kind=None):
        meta = row.get('metadata', {})
        subtype = str(meta.get('contentSubtype', '')).upper()
        kind = kind or ('series' if subtype == 'SERIES' else 'season' if subtype == 'SEASON' else 'vod')
        identifier = Plugin.channel_id(row) if kind == 'channel' else content_id(row)
        title = meta.get('channelName') if kind == 'channel' else meta.get('episodeTitle') or meta.get('title')
        title = title or meta.get('channelName') or identifier
        picture = meta.get('pictureUrl', '')
        image = ''
        if picture and kind != 'channel':
            if str(picture).startswith('https://'):
                image = picture
            else:
                from urllib.parse import quote
                image = 'https://images.tv.kpn.com/%s/%s/1920x1080.jpg?blurred=false' % (
                    'epg' if kind == 'program' else 'vod', quote(str(picture), safe=''))
        return {'kind': kind, 'id': identifier, 'title': str(title), 'image': image,
                'plot': meta.get('longDescription') or meta.get('shortDescription', ''),
                'duration': meta.get('duration', 0)}

    def content_entry(self, record, label=None):
        if record['kind'] in ('series', 'season'):
            self.entry(label or record['title'], 'children', record=record,
                       kind=record['kind'], id=record['id'])
        else:
            self.entry(label or record['title'], 'play', folder=False, record=record,
                       kind=record['kind'], id=record['id'], title=record['title'])

    def live(self):
        rows = self.client.channels()
        current = {}
        try:
            for program in self.client.now([self.channel_id(row) for row in rows]):
                current[str(program.get('channel', {}).get('channelId'))] = program
        except KPNError:
            self.notify('partial_guide')
        for row in rows:
            record = self.record(row, 'channel')
            now = current.get(record['id'], {}).get('metadata', {})
            label = record['title']
            if now.get('title'):
                label += ' — ' + now['title']
                record['plot'] = now.get('shortDescription', '')
            self.content_entry(record, label)
        if not rows:
            self.notify('empty')
        xbmcplugin.setContent(self.handle, 'videos')
        self.finish()

    def replay(self):
        for row in self.client.channels():
            self.entry(self.record(row, 'channel')['title'], 'days', channel=self.channel_id(row))
        self.finish()

    def days(self):
        for offset in range(7):
            date = dt.date.today() - dt.timedelta(days=offset)
            self.entry(self.tr('today') if offset == 0 else date.strftime('%a %d-%m-%Y'),
                       'guide', channel=self.params['channel'], day=date.strftime('%Y%m%d'))
        self.finish()

    def guide(self):
        rows = self.client.epg(self.params['channel'], self.params['day'])
        rows.sort(key=lambda row: int(row['metadata']['airingStartTime']))
        now = dt.datetime.now().timestamp() * 1000
        for row in rows:
            record = self.record(row, 'program')
            start = int(row['metadata']['airingStartTime'])
            label = dt.datetime.fromtimestamp(start / 1000).strftime('%H:%M') + ' — ' + record['title']
            if start > now:
                # Upcoming listings are information only; no false playback promises.
                self.entry(label + ' (' + self.tr('not_yet') + ')', 'unavailable', folder=False)
            else:
                self.content_entry(record, label)
        if not rows:
            self.notify('empty')
        xbmcplugin.setContent(self.handle, 'episodes')
        self.finish()

    def catalogue(self, category=None):
        query = None
        if category is None:
            query = self.dialog.input(self.tr('search')).strip()
            if not query:
                self.finish()
                return
        rows = self.client.catalogue(category, query)
        for row in rows:
            self.content_entry(self.record(row))
        if not rows:
            self.notify('empty')
        xbmcplugin.setContent(self.handle, 'tvshows' if category == 'series' else 'videos')
        self.finish()

    def children(self):
        kind = 'GROUP_OF_BUNDLES' if self.params['kind'] == 'series' else 'BUNDLE'
        rows = self.client.detail(kind, self.params['id'])
        count = 0
        for row in flatten(rows):
            subtype = str(row.get('metadata', {}).get('contentSubtype', '')).upper()
            if subtype not in ('SEASON', 'EPISODE', 'VOD'):
                continue
            if content_id(row) == self.params['id']:
                continue
            self.content_entry(self.record(row))
            count += 1
        if not count:
            self.notify('empty')
        xbmcplugin.setContent(self.handle, 'seasons' if kind == 'GROUP_OF_BUNDLES' else 'episodes')
        self.finish()

    def saved(self):
        rows = self.lists.items(self.params['list'])
        for record in rows:
            self.content_entry(record)
        if not rows:
            self.notify('empty')
        self.finish()

    def play(self):
        import inputstreamhelper
        if not inputstreamhelper.Helper('mpd', drm='com.widevine.alpha').check_inputstream():
            self.dialog.ok('KPN TV', self.tr('drm_missing'))
            xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
            return
        stream = self.client.stream(self.params['kind'], self.params['id'])
        item = xbmcgui.ListItem(path=stream['url'])
        item.setContentLookup(False)
        item.setMimeType('application/dash+xml')
        item.getVideoInfoTag().setTitle(self.params.get('title', 'KPN TV'))
        item.setProperty('inputstream', 'inputstream.adaptive')
        item.setProperty('inputstream.adaptive.manifest_type', 'mpd')
        media_headers = urlencode(self.client.media_headers(stream['url']))
        item.setProperty('inputstream.adaptive.stream_headers', media_headers)
        item.setProperty('inputstream.adaptive.manifest_headers', media_headers)
        license_headers = urlencode(dict(self.client.media_headers(stream['license']),
                                         **{'Content-Type': 'application/octet-stream'}))
        item.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
        item.setProperty('inputstream.adaptive.license_key', stream['license'] + '|' + license_headers + '|R{SSM}|')
        xbmcplugin.setResolvedUrl(self.handle, True, item)

    def dispatch(self):
        action = self.params.get('action', 'root')
        if action in ('live', 'replay', 'guide', 'movies', 'series', 'search', 'children', 'play'):
            if not self.require_login():
                if action == 'play':
                    xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
                else:
                    self.finish(False)
                return
        if action == 'root':
            self.root()
        elif action == 'login':
            self.login()
            xbmc.executebuiltin('Container.Refresh')
        elif action == 'logout':
            self.client.logout()
            self.notify('signed_out')
            xbmc.executebuiltin('Container.Refresh')
        elif action in ('live', 'replay', 'days', 'guide', 'children', 'saved', 'play'):
            getattr(self, action)()
        elif action in ('movies', 'series', 'search'):
            self.catalogue(None if action == 'search' else action)
        elif action in ('save', 'remove'):
            record = json.loads(self.params['record'])
            if record.get('kind') not in ('channel', 'program', 'vod', 'series', 'season'):
                raise KPNError('INVALID_SAVED_ITEM')
            self.lists.update(self.params['list'], record, remove=action == 'remove')
            self.notify('saved')
            xbmc.executebuiltin('Container.Refresh')
        elif action == 'settings':
            self.addon.openSettings()
        elif action == 'diagnostics':
            # Deliberately exclude device ID, titles, URLs, cookies and account data.
            path = os.path.join(self.profile, 'diagnostics.json')
            write_json(path, {'addon_version': self.addon.getAddonInfo('version'),
                             'kodi_version': xbmc.getInfoLabel('System.BuildVersion'),
                             'endpoint_index': self.addon.getSetting('endpoint'),
                             'session_saved': self.client.logged_in})
            self.dialog.ok('KPN TV', self.tr('saved_diag') + '\n' + path)
        elif action == 'unavailable':
            self.notify('not_yet')
        else:
            raise KPNError('UNKNOWN_ACTION')


def run():
    plugin = None
    try:
        plugin = Plugin(sys.argv)
        plugin.dispatch()
    except Exception as error:
        # No tracebacks or raw provider bodies: they can include signed URLs.
        auth = isinstance(error, AuthError)
        code = str(error) if isinstance(error, KPNError) else type(error).__name__
        xbmc.log('[plugin.video.kpntv] ' + code, xbmc.LOGERROR)
        if plugin:
            plugin.dialog.ok('KPN TV', plugin.tr('expired' if auth else 'failed') + '\n' + code)
            if plugin.params.get('action') == 'play':
                xbmcplugin.setResolvedUrl(plugin.handle, False, xbmcgui.ListItem())
            elif plugin.params.get('action', 'root') in (
                    'root', 'live', 'replay', 'days', 'guide', 'movies', 'series', 'search', 'children', 'saved'):
                plugin.finish(False)
