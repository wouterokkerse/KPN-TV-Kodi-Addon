"""Synthetic protocol fixtures, not captured subscriber traffic."""
import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.kpntv'))
from resources.lib.api import Client, KPNError, AuthError, asset_for, playback, ROOTS
from resources.lib.storage import SavedLists


def ok(result=None):
    return {'resultCode': 'OK', 'resultObj': result or {}}


def source():
    return {'src': {'sources': {'src': 'https://cdn.example/media.mpd?sig=a%2Bb&min_bitrate=1',
                               'contentProtection': {'widevine': {
                                   'licenseAcquisitionURL': 'https://license.example/wv?token=signed'}}}}}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.transport = Mock(return_value=ok())
        self.client = Client(self.directory.name, transport=self.transport)

    def test_login_does_not_persist_password_or_username(self):
        self.client.login('synthetic-user', 'synthetic-password')
        self.assertTrue(self.client.logged_in)
        method, path, params, body = self.transport.call_args.args
        self.assertEqual(method, 'POST')
        self.assertEqual(body['credentialsExtAuth']['credentials']['username'], 'synthetic-user')
        for path in Path(self.directory.name).iterdir():
            self.assertNotIn('synthetic-user', path.read_text())
            self.assertNotIn('synthetic-password', path.read_text())

    def test_subscription_login_keeps_leading_zero_pin(self):
        self.client.login('200001', '0012', 'subscription')
        body = self.transport.call_args.args[3]['credentialsStdAuth']
        self.assertEqual(body['password'], '0012')
        self.assertEqual(body['deviceRegistrationData']['deviceId'], self.client.state['device_id'])

    def test_device_id_survives_logout_and_restart(self):
        device_id = self.client.state['device_id']
        self.client.login('user', 'pass')
        self.client.logout()
        again = Client(self.directory.name)
        self.assertEqual(again.state['device_id'], device_id)
        self.assertFalse(again.logged_in)

    def test_endpoint_switch_invalidates_session(self):
        self.client.login('user', 'pass')
        again = Client(self.directory.name, endpoint=1)
        self.assertEqual(again.root, ROOTS[1])
        self.assertFalse(again.logged_in)

    def test_session_expiry_clears_local_state(self):
        self.client.login('user', 'pass')
        self.transport.return_value = {'resultCode': 'SESSION_EXPIRED'}
        with self.assertRaises(AuthError):
            self.client.channels()
        self.assertFalse(self.client.logged_in)

    def test_failed_login_clears_existing_session(self):
        self.client.login('user', 'pass')
        self.transport.return_value = {'resultCode': 'BAD_CREDENTIALS', 'message': 'private data'}
        with self.assertRaisesRegex(KPNError, '^API_BAD_CREDENTIALS$'):
            self.client.login('new', 'bad')
        self.assertFalse(self.client.logged_in)

    def test_api_errors_do_not_expose_server_text(self):
        self.transport.return_value = {'resultCode': 'URL https://secret', 'message': 'secret password'}
        with self.assertRaisesRegex(KPNError, '^API_UNKNOWN$'):
            self.client.channels()

    def test_pagination_retrieves_all_pages(self):
        self.transport.side_effect = [ok({'total': 3, 'containers': [{'id': 'a'}, {'id': 'b'}]}),
                                      ok({'total': 3, 'containers': [{'id': 'c'}]})]
        rows = self.client.paged('/test', size=2)
        self.assertEqual([r['id'] for r in rows], ['a', 'b', 'c'])
        self.assertEqual(self.transport.call_args.args[2], {'from': 2, 'to': 3})

    def test_repeated_page_is_reported_instead_of_truncated(self):
        self.transport.return_value = ok({'total': 10, 'containers': [{'id': 'a'}]})
        with self.assertRaisesRegex(KPNError, 'PAGINATION_STALLED'):
            self.client.paged('/test', size=1)

    def test_epg_flattens_channel_containers(self):
        self.transport.return_value = ok({'containers': [{'metadata': {'channelId': 18},
            'containers': [{'id': 'p', 'metadata': {'airingStartTime': 1000}}]}]})
        self.assertEqual(self.client.epg('18', '20261017')[0]['id'], 'p')

    def test_live_stream_refreshes_dsh_and_preserves_signed_url(self):
        self.client.state['logged_in'] = True
        self.transport.side_effect = [
            ok({'total': 1, 'containers': [{'id': '18', 'metadata': {'channelId': 18},
                'assets': [{'assetId': 22, 'videoType': 'SD_DASH_WV'}]}]}), ok(), ok(source())]
        stream = self.client.stream('channel', '18')
        self.assertEqual(stream['url'], source()['src']['sources']['src'])
        paths = [call.args[1] for call in self.transport.call_args_list]
        self.assertEqual(paths[1], '/USER/DSHTOKEN')
        self.assertEqual(paths[2], '/CONTENT/VIDEOURL/LIVE/18/22/')
        self.assertEqual(self.transport.call_args.args[2]['profile'], 'G03')

    def test_replay_requires_entitlement_before_playback(self):
        self.client.state['logged_in'] = True
        self.transport.return_value = ok({'containers': [{'entitlement': {'assets': [
            {'assetId': 1, 'videoType': 'SD_DASH_WV', 'programType': 'CUTV', 'rights': 'buy'}]}}]})
        with self.assertRaisesRegex(KPNError, 'NO_PLAYABLE_ASSET'):
            self.client.stream('program', 'p')
        self.assertEqual(self.transport.call_count, 1)

    def test_playback_requires_login(self):
        with self.assertRaises(AuthError):
            self.client.stream('channel', '18')
        self.transport.assert_not_called()

    def test_cookie_scope_is_respected_for_media(self):
        cookie = http.cookiejar.Cookie(0, 'session', 'synthetic', None, False,
                                      '.kpn.com', True, True, '/', True, True,
                                      None, True, None, None, {}, False)
        self.client.jar.set_cookie(cookie)
        self.assertIn('Cookie', self.client.media_headers('https://tv.kpn.com/test'))
        self.assertNotIn('Cookie', self.client.media_headers('https://cdn.example/test'))

    def test_http_errors_are_sanitized(self):
        self.client.opener.open = Mock(side_effect=HTTPError('https://secret', 500, 'private', {}, None))
        with self.assertRaisesRegex(KPNError, '^HTTP_500$'):
            self.client._http('GET', '/test', {}, None)

    def test_network_failure_is_sanitized(self):
        self.client.opener.open = Mock(side_effect=URLError('private URL'))
        with self.assertRaisesRegex(KPNError, '^NETWORK_ERROR$'):
            self.client._http('GET', '/test', {}, None)

    def test_http_unauthorized_clears_session(self):
        self.client.login('user', 'pass')
        self.client.transport = self.client._http
        self.client.opener.open = Mock(side_effect=HTTPError('https://secret', 401, '', {}, None))
        with self.assertRaises(AuthError):
            self.client.request('/test')
        self.assertFalse(self.client.logged_in)

    def test_saved_lists_deduplicate_and_remove(self):
        lists = SavedLists(self.directory.name)
        record = {'kind': 'vod', 'id': '1', 'title': 'Film'}
        lists.update('later', record)
        lists.update('later', dict(record, title='New title'))
        self.assertEqual(len(lists.items('later')), 1)
        self.assertEqual(lists.items('later')[0]['title'], 'New title')
        lists.update('later', record, remove=True)
        self.assertEqual(lists.items('later'), [])

    def test_logout_keeps_saved_lists(self):
        lists = SavedLists(self.directory.name)
        lists.update('favorites', {'kind': 'channel', 'id': '18'})
        self.client.logout()
        self.assertEqual(len(lists.items('favorites')), 1)


class AssetTests(unittest.TestCase):
    def test_widevine_preferred_then_ranking(self):
        row = {'assets': [{'assetId': 1, 'videoType': 'SD_DASH_PR', 'metadata': {'ranking': 99}},
                          {'assetId': 2, 'videoType': 'SD_DASH_WV', 'metadata': {'ranking': 1}},
                          {'assetId': 3, 'videoType': 'SD_DASH_WV', 'metadata': {'ranking': 2}}]}
        self.assertEqual(asset_for(row, 'channel'), '3')

    def test_replay_selects_only_catchup_watch_right(self):
        row = {'entitlement': {'assets': [
            {'assetId': 1, 'videoType': 'SD_DASH_WV', 'programType': 'LIVE', 'rights': 'watch'},
            {'assetId': 2, 'videoType': 'SD_DASH_WV', 'programType': 'CUTV', 'rights': 'watch'}]}}
        self.assertEqual(asset_for(row, 'program'), '2')

    def test_purchase_asset_rejected(self):
        row = {'entitlement': {'assets': [
            {'assetId': 1, 'assetType': 'MASTER', 'videoType': 'SD_DASH_WV', 'rights': 'buy'}]}}
        with self.assertRaises(KPNError):
            asset_for(row, 'vod')

    def test_license_required(self):
        with self.assertRaisesRegex(KPNError, 'NO_WIDEVINE_LICENSE'):
            playback({'src': {'sources': {'src': 'https://cdn.example/a.mpd'}}})

    def test_invalid_url_scheme_rejected(self):
        value = source()
        value['src']['sources']['src'] = 'plugin://untrusted'
        with self.assertRaisesRegex(KPNError, 'INVALID_MANIFEST_URL'):
            playback(value)

    def test_list_of_sources_supported(self):
        value = source()
        value['src']['sources'] = [dict(value['src']['sources'], type='application/dash+xml')]
        self.assertEqual(playback(value)['url'], source()['src']['sources']['src'])


if __name__ == '__main__':
    unittest.main()
