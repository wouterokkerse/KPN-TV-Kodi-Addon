# KPN TV for Kodi — experimental 0.1.0

A standalone, unofficial KPN TV addon targeting **Kodi 21.2** (Python 3;
Kodi 20 APIs are also used). Inspired by the navigation and feature set of
[Nigel1992's NLZIET addon](https://github.com/Nigel1992/NLZiet-Kodi-Addon).
This is a new provider implementation, not a renamed NLZIET addon.

**Status:** installable development build, not a verified working KPN release.
32 automated tests pass using synthetic API responses and Kodi API doubles.
No KPN subscriber login, real catalogue response, Widevine licence request,
or video playback has been tested. The build environment's network proxy was
unreachable; public source research used connected GitHub/browser tools.
The API references were last checked on 17 October 2026; the newest referenced
client was last pushed in September 2025 and is archived. KPN may have changed
its endpoints, login requirements or response formats since then.

## Install on Kodi 21.2

1. Download `plugin.video.kpntv-0.1.0.zip` from the supplied files.
2. In Kodi, open **Settings → System → Add-ons → Unknown sources** and enable it.
3. Open **Add-ons → Install from zip file** and select the addon ZIP. Use the
   addon ZIP, not the separate source-code archive.
4. Allow Kodi to install **InputStream Adaptive** and **InputStream Helper**
   from its official repository. On some platforms InputStream Adaptive must
   first be enabled under **My add-ons → VideoPlayer InputStream**.
5. Open **Video add-ons → KPN TV (unofficial)**. Choose **Sign in** and enter
   your KPN ID email and password on your Kodi device.
6. On first playback, follow InputStream Helper's Widevine setup if prompted.

For subscription-number/PIN login, first choose that method in addon settings.
This older KPN authentication flow may no longer work for every account.
Passwords and PINs are never saved. Session cookies are saved in Kodi's addon
profile so that login can survive restarts. Protect that profile as you would
other signed-in application data. Sign out removes this addon's local session;
it does not unregister the device or revoke the session on KPN's servers.

## Implemented paths and limits

All provider-dependent paths below still require testing with your subscription.

| Feature | Implementation |
| --- | --- |
| Sign in | KPN ID or legacy TV number/PIN; stable device ID; saved cookies |
| Live TV | Subscribed channel discovery, current programme labels, DASH/Widevine |
| Replay / TV guide | Direct KPN EPG for today and six previous days; replay entitlement checked at play time |
| Films / series | Subscription-filtered catalogue, series → seasons → episodes |
| Search | Film/series title search through KPN VOD search; no EPG search |
| My list / Watch later | Stored on this Kodi device; context-menu add/remove |
| Languages | Dutch and English, selected by Kodi's interface language |
| Diagnostics | Version, selected API index and local session status; no account details or media URLs |

KPN's subscription, location, device, simultaneous-stream and content restrictions
still apply. A programme appearing in the guide does not guarantee replay rights.
Expired saved items may remain listed and fail when played. Paid rental/purchase
assets are rejected; the addon never makes purchases. Picture quality depends on
what the web-client API and your Widevine/device combination permit.

This build does **not** implement recordings, KPN profile switching, cloud list
sync, recommendations/homepage rows, Trakt matching/scrobbling, library export,
PVR integration or a session heartbeat. These are not claimed as feature parity
with NLZIET. Long-running streams and stream-limit cleanup need live testing.
Kodi 22 is not a declared target; its DRM configuration must be checked separately.

## First subscriber test

1. Confirm the same account can watch at `https://tv.kpn.com`.
2. Test sign-in, one subscribed live channel, then a second channel.
3. Stop playback, reopen the addon, and check the session survives a Kodi restart.
4. Test a replay that is available in the official KPN app.
5. Browse a film, series, season and episode. Test title search and a local list.
6. Check subtitles/audio, seek in replay and watch live for at least 15 minutes.

The default API is **AVS67**, from the newer public KPN client. If it returns a
network/HTTP error while the official website works, settings also offer the
documented **AWS** and **Legacy** hosts. Changing the endpoint requires signing
in again. There is no automatic retry of your password across different hosts.

An error dialog shows a bounded error code. `HTTP_401` / `HTTP_403` can mean an
expired session or access refusal; `API_…` is KPN's result code;
`NO_PLAYABLE_ASSET` means the response did not contain an eligible asset;
`NETWORK_ERROR` means the request could not reach the selected API;
`PAGINATION_STALLED` means the API ignored paging, so results were not silently
reported as complete. MFA/browser-only sign-in, if required by KPN, is not
implemented in this build.

If a test fails, report the exact error code, Kodi version, operating system and
which screen/action failed. The diagnostics menu writes `diagnostics.json` in
`special://profile/addon_data/plugin.video.kpntv/`. Never share `cookies.txt`,
`session.json`, passwords, PINs or signed playback URLs. Kodi/InputStream's own
debug logs can contain signed URLs even though this addon avoids logging them.

## Development

No pip dependencies are needed for the provider client, tests or packaging.
Kodi supplies its own modules and installs the two declared playback dependencies.

```sh
python -m unittest discover -s tests -v
python scripts/localize.py
python scripts/build.py
```

`scripts/build.py` validates XML, Python syntax, referenced translations and addon
structure, then creates an installable ZIP and SHA-256 checksum in `dist/`.
Tests use synthetic contracts, not recordings of KPN's current production API.
They verify credential storage, cookie scoping, paging, subscription asset
selection, signed URLs, login cancellation, Kodi playable flags and DRM setup.
They do not establish service compatibility or successful video playback.

See [SOURCES.md](SOURCES.md) for provider references. Source is licensed under
GPL-3.0-or-later; the original geometric icon is included under the same licence.
This project is not affiliated with or endorsed by KPN or NLZIET.
