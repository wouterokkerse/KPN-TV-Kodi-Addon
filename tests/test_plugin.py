"""Kodi API doubles exercise routing and playback resolution on Kodi 21 APIs."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.kpntv'))


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.items = []
        self.xbmc = Mock()
        self.xbmcplugin = Mock()
        self.xbmcgui = Mock()
        self.xbmcgui.ListItem.side_effect = self.new_item
        addon = Mock()
        addon.getAddonInfo.side_effect = lambda key: self.directory.name if key == 'profile' else '0.1.0'
        addon.getSetting.return_value = '0'
        addon.getLocalizedString.side_effect = lambda number: str(number)
        modules = {'xbmc': self.xbmc, 'xbmcplugin': self.xbmcplugin, 'xbmcgui': self.xbmcgui,
                   'xbmcaddon': types.SimpleNamespace(Addon=lambda: addon),
                   'xbmcvfs': types.SimpleNamespace(translatePath=lambda path: path),
                   'inputstreamhelper': Mock()}
        self.helper = modules['inputstreamhelper']
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        sys.modules.pop('resources.lib.plugin', None)
        from resources.lib.plugin import Plugin
        self.Plugin = Plugin

    def new_item(self, **kwargs):
        item = Mock()
        item.kwargs = kwargs
        self.items.append(item)
        return item

    def plugin(self, query):
        plugin = self.Plugin(['plugin://plugin.video.kpntv', '1', query])
        plugin.client = Mock()
        plugin.client.logged_in = True
        return plugin

    def test_live_items_are_playable_not_folders(self):
        plugin = self.plugin('?action=live')
        plugin.client.channels.return_value = [{'id': '18', 'metadata': {'channelId': 18, 'channelName': 'Test'}}]
        plugin.client.now.return_value = []
        plugin.dispatch()
        call = self.xbmcplugin.addDirectoryItem.call_args
        self.assertFalse(call.kwargs['isFolder'])
        self.assertIn('action=play', call.args[1])
        self.items[0].setProperty.assert_any_call('IsPlayable', 'true')

    def test_playback_sets_widevine_challenge_and_resolves_once(self):
        plugin = self.plugin('?action=play&kind=channel&id=18')
        plugin.client.stream.return_value = {'url': 'https://cdn.example/a.mpd?token=a%2Bb',
                                             'license': 'https://license.example/wv'}
        plugin.client.media_headers.return_value = {'User-Agent': 'test'}
        plugin.dispatch()
        self.xbmcplugin.setResolvedUrl.assert_called_once()
        args = self.xbmcplugin.setResolvedUrl.call_args.args
        self.assertTrue(args[1])
        item = args[2]
        self.assertEqual(item.kwargs['path'], 'https://cdn.example/a.mpd?token=a%2Bb')
        item.setProperty.assert_any_call('inputstream.adaptive.license_type', 'com.widevine.alpha')
        values = dict(call.args for call in item.setProperty.call_args_list)
        self.assertTrue(values['inputstream.adaptive.license_key'].endswith('|R{SSM}|'))
        self.xbmcplugin.endOfDirectory.assert_not_called()

    def test_missing_widevine_reports_failed_playback(self):
        plugin = self.plugin('?action=play&kind=channel&id=18')
        self.helper.Helper.return_value.check_inputstream.return_value = False
        plugin.dispatch()
        plugin.client.stream.assert_not_called()
        self.assertFalse(self.xbmcplugin.setResolvedUrl.call_args.args[1])

    def test_cancel_login_finishes_listing_as_failed(self):
        plugin = self.plugin('?action=live')
        plugin.client.logged_in = False
        plugin.dialog.input.return_value = ''
        plugin.dispatch()
        plugin.client.channels.assert_not_called()
        self.assertFalse(self.xbmcplugin.endOfDirectory.call_args.kwargs['succeeded'])

    def test_password_input_is_masked_and_not_trimmed(self):
        plugin = self.plugin('?action=login')
        plugin.dialog.input.side_effect = ['user@example.test', ' spaces ']
        plugin.dispatch()
        plugin.client.login.assert_called_once_with('user@example.test', ' spaces ', 'kpnid')
        self.assertEqual(plugin.dialog.input.call_args.kwargs['option'], self.xbmcgui.ALPHANUM_HIDE_INPUT)

    def test_season_navigation_uses_bundle_endpoint(self):
        plugin = self.plugin('?action=children&kind=season&id=42')
        plugin.client.detail.return_value = [{'id': '42', 'containers': [
            {'id': '43', 'metadata': {'contentSubtype': 'EPISODE', 'episodeTitle': 'Episode'}}]}]
        plugin.dispatch()
        plugin.client.detail.assert_called_once_with('BUNDLE', '42')
        call = self.xbmcplugin.addDirectoryItem.call_args
        self.assertFalse(call.kwargs['isFolder'])
        self.assertIn('kind=vod', call.args[1])

    def test_future_guide_items_are_not_playable(self):
        plugin = self.plugin('?action=guide&channel=18&day=20261017')
        plugin.client.epg.return_value = [{'id': '1', 'metadata': {
            'airingStartTime': 9999999999999, 'title': 'Future'}}]
        plugin.dispatch()
        self.items[0].setProperty.assert_any_call('IsPlayable', 'false')


if __name__ == '__main__':
    unittest.main()
