# Changelog

## [11.13.0](https://github.com/WhispersOfJ/media-stack/compare/v11.12.1...v11.13.0) (2026-08-02)


### Features

* add loop remediation toolkit for manual unmonitor/exclude ([9b9a697](https://github.com/WhispersOfJ/media-stack/commit/9b9a697ac8781f238c5503bafe5ddcb4663f7b37))
* promote queue-monitoring loop to stack-queue-autofix endpoint ([a6359f4](https://github.com/WhispersOfJ/media-stack/commit/a6359f4cf46e4151488b03ec46ddde1a2e26fc85))


### Bug Fixes

* add rclone timeout tuning to nzbdav_rclone mount, adopt larger cache ([9d6e93d](https://github.com/WhispersOfJ/media-stack/commit/9d6e93dea7349b1b2419f0d05c3553c5cc8aedc2))
* cap usenet provider connections at 25 each ([a05e09c](https://github.com/WhispersOfJ/media-stack/commit/a05e09c6a493c7a4eaeae5a0c215a8e63d5e284d))
* confirm Plex stalled_suspected over multiple polls before flagging ([ad12ad1](https://github.com/WhispersOfJ/media-stack/commit/ad12ad1c630c023196d86a4f76a3f936dc68aa50))
* docker-compose-manager cascade uses force-recreate, verifies mount ([77a95c2](https://github.com/WhispersOfJ/media-stack/commit/77a95c2a87e37fdd7ff8ca2149b99570c194bb29))
* fall back to direct API lookup when queue item's embedded monitored status is null ([1b05e3c](https://github.com/WhispersOfJ/media-stack/commit/1b05e3cbfa839944b0fc0af8aa59a7e09218e611))
* remove stale/phantom service references from control panel ([e1fc188](https://github.com/WhispersOfJ/media-stack/commit/e1fc188a6b189e94e1eb3fd45afdd8038368f650))
* skip re-search for unmonitored items in queue-autofix ([f959f3f](https://github.com/WhispersOfJ/media-stack/commit/f959f3fe61e35225a9324bce08699b9686adfe49))
* tolerate benign 404/timeout on queue-autofix blocklist delete ([0be5cb3](https://github.com/WhispersOfJ/media-stack/commit/0be5cb35b5204c6935762788dd656356e7614c51))

## [11.12.1](https://github.com/WhispersOfJ/media-stack/compare/v11.12.0...v11.12.1) (2026-07-31)


### Bug Fixes

* enable NzbDAV usenet cascade with explicit provider priority ([ae07f4e](https://github.com/WhispersOfJ/media-stack/commit/ae07f4e160a8e4428257ef7c5d7487872f70b066))
