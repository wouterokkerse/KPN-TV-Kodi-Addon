# Implementation references

Inspected on 2026-10-17 through connected GitHub tools. No proprietary client
bundles, credentials, media, decryption keys or account traffic are included.

* [NLZIET addon README](https://github.com/Nigel1992/NLZiet-Kodi-Addon/blob/master/README.md),
  v1.4.1 dated 2026-10-16: feature/navigation reference only. NLZIET code, artwork
  and authentication are not copied into this addon.
* [bartoostveen/kpn-itv-client](https://github.com/bartoostveen/kpn-itv-client),
  GPL-3.0; repository archived, last pushed 2025-09-10. Inspected `KpnRoutes.kt`,
  `Constants.kt`, `Models.kt`, `requests/Login.kt`, `requests/Channels.kt`,
  `requests/Streams.kt` under `kpn/src/main/kotlin/me/huizengek/kpnclient/`.
  These describe the AVS67 root, KPN ID login body, live-channel schema, G03
  profile, device ID, DSH refresh and Widevine playback response. Our Python
  adapter implements these contracts; the Kotlin sources are not bundled.
* [dut-iptv KPN API](https://github.com/dut-iptv/dut-iptv/blob/master/plugin.video.kpn/resources/lib/api.py),
  latest KPN-specific commit found: 2022-01-26. Inspected for legacy subscription
  login, replay/VOD entitlement and asset selection, and bundle detail paths.
  `constants.py` supplies the legacy API root and origin headers.
* [wvthoog KPN EPG client](https://github.com/wvthoog/iptv-downloader/blob/master/kpn/epg.py):
  describes direct `/TRAY/EPG`, `filter_day`, channel IDs, `/TRAY/SEARCH/PROGRAM`,
  and `SD_DASH_WV` replay assets with `CUTV`/`watch` rights.
* [KPN TV request in Retrospect](https://github.com/retrospect-addon/plugin.video.retrospect/issues/1789):
  API AWS hostname recorded in April 2024; issue closed December 2024.
* [dut-iptv issue list](https://github.com/dut-iptv/dut-iptv/issues): reports that
  the external dut-epg feed stopped updating in January 2023. This implementation
  has no dependency on that feed, repository proxy, DNS overrides or patched audio.

The direct catalogue filters combine published KPN AVS search/detail contracts.
Series/film classifications, paging offsets, login cookie requirements, replay
availability and playback headers remain hypotheses until checked against a real
current subscriber session. The API hostname options are explicitly selectable
historical references, not a claim that every hostname is currently operational.
