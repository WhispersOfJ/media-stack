# Changelog

## [11.13.0](https://github.com/WhispersOfJ/media-stack/compare/v11.12.0...v11.13.0) (2026-07-31)


### Features

* add blocklist view/clear routes for Radarr and Sonarr ([8a07b85](https://github.com/WhispersOfJ/media-stack/commit/8a07b85d70d270e5dcfa2aa6d166bcaaa3802d51))
* add Plex Health monitor daemon (scan-lag/hang/SQLite-stall detection) ([5b99a0a](https://github.com/WhispersOfJ/media-stack/commit/5b99a0a5f9937bf51cc2c3efbc2c01242e02cabc))
* add Sonarr episode-monitor fix route ([bd80396](https://github.com/WhispersOfJ/media-stack/commit/bd80396ff62c5a41a530e163385cd841617e4dff))
* automate bearmount ffprobe-hang unstick, fix stale-mount cascade bug ([8affae0](https://github.com/WhispersOfJ/media-stack/commit/8affae064d4cfd7085c4222016d1d5fb97f094db))
* BearMount FUSE/health REST API integration, Plex Health analysis-awareness ([57655f3](https://github.com/WhispersOfJ/media-stack/commit/57655f373e7ef2935a15b0585da23bc881ecef8d))
* MDBList toplists import, BearMount-&gt;nzbdav docs/test cleanup ([c4a9c67](https://github.com/WhispersOfJ/media-stack/commit/c4a9c671ac0b63422640aab5806e654448105ec0))
* NzbDAV/AltMount-&gt;BearMount rebrand cleanup, poster sync sources, naming/scoring fixes ([682d0ce](https://github.com/WhispersOfJ/media-stack/commit/682d0ced1b8b3739778d125bd82bfa96da73a393))
* Plex Health monitor + mount-cascade mitigations in Control Panel ([2fc5e04](https://github.com/WhispersOfJ/media-stack/commit/2fc5e047da9762b9102d1dcce9a6093989e084a8))
* remove NeutArr entirely after blocklist-loop + Plex SQLite incident ([ca3a7dd](https://github.com/WhispersOfJ/media-stack/commit/ca3a7dd5e890cc9f37a1f8cb63eb78bb41c49ccb))
* switch versioning to release-please ([5de014c](https://github.com/WhispersOfJ/media-stack/commit/5de014c2f38f780ebe3c8a851b146742cb89adf3))
* wire tautulli/wrapperr/maintainerr/checkrr/prefetcharr/lingarr/kometa/notifiarr into Control Panel ([9549674](https://github.com/WhispersOfJ/media-stack/commit/954967418593b48830b7b49b1a26f4a2274d6f87))


### Bug Fixes

* add missing NOTIFIARR_API_KEY and backup usenet provider vars to .env.example ([755b35b](https://github.com/WhispersOfJ/media-stack/commit/755b35b3ff2735a9579cfa1f41e69bb9ed5e5676))
* automate bearmount mount-recovery lazy umount, harden recreate against orphaning ([91959cc](https://github.com/WhispersOfJ/media-stack/commit/91959cc7d7a09c6d62336e104c9fe573dd538ca8))
* bearmount cascade retry no longer re-inspects a container it already removed ([b32e967](https://github.com/WhispersOfJ/media-stack/commit/b32e967f4d6434283ebbb86dc7ca444445ddbf15))
* BearMount mount-table leak, missing stop_grace_period on bearmount/plex ([845b7ff](https://github.com/WhispersOfJ/media-stack/commit/845b7ff3918d16d47846a6b8ed84c952e4ab33ce))
* bearmount recreate now retries lazy-umount on the first-attempt failure too ([616c3e9](https://github.com/WhispersOfJ/media-stack/commit/616c3e9b43d8cbc36b3ca07d573bdfcb213ac898))
* bounded-exec deadlock and unbounded log read in Plex Health route ([9451362](https://github.com/WhispersOfJ/media-stack/commit/9451362141096f017ee70eecc02020cc56752a04))
* deploy confirmed root-cause fix for the ffprobe hang (asyncbuf-streaming-guard) ([293c3a9](https://github.com/WhispersOfJ/media-stack/commit/293c3a9b2dca8a57cefd4bfcde3c73a283a92492))
* rename ambiguous list-comprehension variable l to line (ruff E741) ([2528693](https://github.com/WhispersOfJ/media-stack/commit/2528693cdf2e9c4789707ff016c59e23696562db))
* test_post_discord_once_json_only_when_no_image needs a real webhook URL ([d9817bb](https://github.com/WhispersOfJ/media-stack/commit/d9817bb42c8cbae904135a1209d4974d79cf002c))
