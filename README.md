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

## How everything is protected

Every app in this stack sits behind a real login screen with two-factor authentication (2FA) —
the kind where you type a password *and* a rotating 6-digit code from an app on your phone, the
same idea as logging into a bank. This is handled by a piece of the stack called **Authelia**,
and it's already set up for you.

- The first time you open any of the apps below, you'll be sent to a login page. Log in with
  the account you were given when this was set up.
- You'll be asked to set up two-factor authentication the first time — this means scanning a QR
  code with an authenticator app on your phone (Google Authenticator, Authy, or similar are all
  fine, free apps).
- After that, you stay logged in for a while — you won't have to do this on every visit.

Two things worth knowing:
- Everything is reached through **`https://` addresses** (the padlock-in-the-browser kind),
  not the plain `http://<ip>:<port>` addresses older setups use. This is safer.
- These addresses only work from devices on your home network, or connected to your
  [Tailscale](https://tailscale.com) network if you have one set up — nothing here is reachable
  from the public internet by default. That's intentional and is the safer default; see
  [TECHNICAL.md](TECHNICAL.md) if you ever want to change that.

## Opening everything in your browser

Each app has its own address, in the form `https://<name>.cave.internal`. For your browser to
find these addresses, add this line to your computer's **hosts file** once (a plain text file
your computer already checks before looking anything up on the internet):

```
<this computer's local network address>  traefik.cave.internal authelia.cave.internal prowlarr.cave.internal zilean.cave.internal decypharr.cave.internal decypharr-alldebrid.cave.internal zurg.cave.internal radarr.cave.internal sonarr.cave.internal nzbget.cave.internal seerr.cave.internal bazarr.cave.internal byparr.cave.internal tautulli.cave.internal control-panel.cave.internal debridmediamanager.cave.internal cleanuparr.cave.internal neutarr.cave.internal dozzle.cave.internal plex.cave.internal glances.cave.internal adminer.cave.internal
```

- On Linux/Mac, that file is `/etc/hosts`; on Windows it's
  `C:\Windows\System32\drivers\etc\hosts`. You'll need administrator/root access to edit it.
- Replace `<this computer's local network address>` with the actual local IP address of the
  computer running the stack (something like `192.168.x.x`).
- Do this on every device you want to use these addresses from (your laptop, your phone, etc).

| App | Address | What it's for, in plain English |
|---|---|---|
| **Seerr** | `https://seerr.cave.internal` | **Start here day to day.** Search for a movie or show and click Request — everything else happens automatically. |
| **Plex** | `https://plex.cave.internal` | Your actual streaming app — this is what you watch things on. |
| **Radarr** | `https://radarr.cave.internal` | Manages your movie library behind the scenes. |
| **Sonarr** | `https://sonarr.cave.internal` | Manages your TV show library behind the scenes. |
| **Bazarr** | `https://bazarr.cave.internal` | Automatically finds subtitles for what you watch. |
| **Tautulli** | `https://tautulli.cave.internal` | Shows stats on what's been watched, by whom. |
| **Control Panel** | `https://control-panel.cave.internal` | One dashboard with links to everything, plus quick buttons for common tasks. |
| **DebridMediaManager** | `https://debridmediamanager.cave.internal` | Browse your Real-Debrid/AllDebrid account directly. |
| Prowlarr | `https://prowlarr.cave.internal` | Behind-the-scenes indexer — you generally won't need to open this. |
| Zilean, Decypharr, Zurg | `https://zilean.cave.internal`, `https://decypharr.cave.internal`, `https://zurg.cave.internal` | Behind-the-scenes plumbing that connects Real-Debrid/AllDebrid to your library. Rarely need to be opened directly. |
| NZBGet | `https://nzbget.cave.internal` | A backup download method for the rare thing debrid doesn't have. |
| Byparr, Cleanuparr, NeutArr | — | Quiet background helpers with no reason to visit day to day. |
| Glances, Dozzle | `https://glances.cave.internal`, `https://dozzle.cave.internal` | Technical stats/logs — only useful if something's wrong. |
| Adminer | `https://adminer.cave.internal` | A database viewer — only needed for advanced troubleshooting. |

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

- **Check Control Panel first** (`https://control-panel.cave.internal`) — it shows every app's
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
