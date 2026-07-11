# The Stack

🤖 **Built entirely by [Claude AI](https://www.anthropic.com/claude)** — every part of this
project, including this guide, was set up and tested by Claude.

This project automatically finds movies and TV shows, adds them to your own private streaming
server (Plex), and gets them ready to watch — you just search for what you want and click
"Request." No manual downloading, no digging through websites.

If you want the deep technical details (why things are configured the way they are, exact
troubleshooting steps for advanced problems), see **[TECHNICAL.md](TECHNICAL.md)**. This guide
is just about getting it running and using it day to day.

## What you need before you start

1. **A computer or server that stays turned on** — a spare PC, a mini-PC, or a home server.
   This guide assumes Linux, but the ideas are the same on other systems.
2. **[Docker](https://docs.docker.com/get-docker/) installed** on that computer. Docker is the
   tool that runs everything in this project in neat, isolated little boxes called
   "containers," so you don't have to install two dozen separate programs by hand. Follow the
   link above and install it before continuing — that's the only real prerequisite.
3. **A Real-Debrid and/or AllDebrid account.** These are paid services (a few dollars a month)
   that give you instant access to a huge shared library of already-available content — this is
   what makes things "just show up" instead of downloading slowly. You don't strictly need
   both; one is enough to get started.
4. **A Plex account** (free) — this is the actual media server / streaming app you'll watch
   everything through, on your TV, phone, or laptop.

That's it. You don't need to know Linux commands beyond copy-pasting the ones below, and you
don't need to know what any of the individual programs in this stack are yet — that's covered
further down.

## Setting it up

Open a terminal on your computer and run these, one at a time:

```bash
mkdir -p ~/Stack && cd ~/Stack

# 1. Download this project's files
docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest

# 2. Open a setup form in your browser to fill in your details
docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest --setup
```

After step 2, open a web browser and go to `http://<this-computer's-address>:8090` — you'll see
a form asking for things like your timezone and your Plex/Real-Debrid details. Fill in what you
can (a few fields say "fill in after first boot" — that's expected, come back to those later,
see [After your first boot](#after-your-first-boot) below). Submit the form.

Then bring everything online:

```bash
# 3. Start the core apps
docker compose up -d

# 4. Start the optional extras too (recommended - subtitles, stats, automation, and more)
docker compose --profile extras up -d
```

Give it a minute or two to finish starting up, then jump to
[Opening everything in your browser](#opening-everything-in-your-browser) below.

### After your first boot

A few pieces of information don't exist until the apps have started for the first time (they
generate their own login keys on first boot), so the setup form couldn't have known them
earlier:

1. Open Radarr and Sonarr (see the table below for addresses) and find each app's own API key
   under **Settings → General → Security**.
2. Open Plex, click any movie or show, choose **Get Info → View XML**, and copy the `token=...`
   value from the address bar that opens.
3. Re-run the exact same setup command from step 2 above — it'll load your existing answers, so
   you only need to paste in these three new values.
4. Run `docker compose up -d --force-recreate control-panel` to pick up the change.

## Security note

There's no login screen in front of any of these apps — this stack trusts whoever can reach it,
same as a printer or a smart TV on your network. That's a deliberate, simple choice for a
home server used only on your own network, not an oversight.

- Everything is reached through plain **`http://<ip>:<port>`** addresses — no certificate to
  install, no account to create.
- These addresses only work from devices on your home network, or connected to your
  [Tailscale](https://tailscale.com) network if you have one set up — nothing here is reachable
  from the public internet unless you specifically set that up yourself.
- **Control Panel** and **Dozzle** are worth knowing about specifically — they can restart or
  inspect any container in this stack. Don't put this stack on a network you don't trust, and
  don't forward any of these ports to the public internet. See [TECHNICAL.md](TECHNICAL.md) if
  you ever want to add a login layer back in front of everything.

## Opening everything in your browser

Each app has its own address, in the form `http://<this computer's local network address>:<port>`
— find your computer's local address with `hostname -I` (Linux) or by checking your router's
connected-devices list, then just add `:` and the port number below. For example, if your
server's address is `192.168.1.50`, Seerr is at `http://192.168.1.50:5055`.

| App | Port | What it's for, in plain English |
|---|---|---|
| **Seerr** | `5055` | **Start here day to day.** Search for a movie or show and click Request — everything else happens automatically. |
| **Plex** | `32400/web` | Your actual streaming app — this is what you watch things on. |
| **Radarr** | `7878` | Manages your movie library behind the scenes. |
| **Sonarr** | `8989` | Manages your TV show library behind the scenes. |
| **Bazarr** | `6767` | Automatically finds subtitles for what you watch. |
| **Tautulli** | `8182` | Shows stats on what's been watched, by whom. |
| **Control Panel** | `8420` | One dashboard with links to everything, plus quick buttons for common tasks. |
| **DebridMediaManager** | `3000` | Browse your Real-Debrid/AllDebrid account directly. |
| Prowlarr | `9696` | Behind-the-scenes indexer — you generally won't need to open this. |
| Zilean, Decypharr, Zurg | `8181`, `8282`, `9999` | Behind-the-scenes plumbing that connects Real-Debrid/AllDebrid to your library. Rarely need to be opened directly. |
| NzbDAV | `3001` | A backup source for the rare thing debrid doesn't have - streams, doesn't download. |
| Byparr, Cleanuparr, NeutArr | — | Quiet background helpers with no reason to visit day to day. |
| Glances, Dozzle | `61208`, `8080` | Technical stats/logs — only useful if something's wrong. |
| Adminer | `8081` | A database viewer — only needed for advanced troubleshooting. |

You genuinely only need **Seerr** and **Plex** for everyday use. Everything else runs quietly in
the background.

## Using it day to day

1. Open Seerr, search for a movie or show, click **Request**.
2. Wait a bit — usually just a few minutes if it's already cached on Real-Debrid/AllDebrid,
   longer if it has to fall back to a regular download.
3. Open Plex — it'll show up in your library automatically once it's ready.

That's genuinely the whole workflow. Everything between "click Request" and "it's in Plex" — 
finding it, checking if it's already cached, adding subtitles, organizing the file — happens on
its own.

## If something goes wrong

- **Check Control Panel first** (`http://<your server's address>:8420`) — it shows every app's
  status at a glance and lets you restart anything with one click.
- **`docker compose up -d`** is always safe to run again — it only touches anything that's
  actually not running correctly, and won't disturb apps that are already fine.
- Still stuck? [TECHNICAL.md](TECHNICAL.md) has the deep detail on every part of this stack, and
  [CHANGELOG.md](CHANGELOG.md) documents every issue that's come up before and how it was
  fixed — there's a good chance whatever you're seeing has already been solved once.

---

🤖 **This stack — architecture, every app, every fix, every line of documentation — was built
by [Claude AI](https://www.anthropic.com/claude).** Full version history in
[CHANGELOG.md](CHANGELOG.md); the deep technical reference is in [TECHNICAL.md](TECHNICAL.md).
