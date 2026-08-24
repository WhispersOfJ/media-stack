# StackOps Control Panel — Massive Redesign Plan

## Current State Audit

### What exists today
- **18 HTML templates**: 5 shell pages (Overview, Settings, Reference, Activity Log, Login), 7 app pages (Fleet, Host, Plex, Posters, Letterboxd, MDBList), 6 partials
- **17 service files** with 100+ functions — rich backend, thin frontend
- **Custom CSS** (735 lines): hand-written design system with variables, cards, badges, progress bars
- **htmx + hyperscript** for interactivity — no JS framework, no build step
- **7 overview cards** with 20s polling, sidebar navigation, command palette (copies fish commands to clipboard)

### What's broken or missing
| Area | Problem |
|------|---------|
| **Speed** | Overview calls 5 services sequentially on every 20s poll; no caching, no dedup |
| **Settings page** | Placeholder stub ("Task 8 coming soon") |
| **Reference page** | Placeholder stub |
| **Activity Log** | Empty static strip — never populated with real data |
| **Log viewer** | No way to view container logs in-browser |
| **Charts/graphs** | Zero data visualization — no sparklines, no history, no trends |
| **Toast/notifications** | No feedback when actions succeed or fail |
| **Loading states** | No skeleton screens, spinners, or disabled states during htmx requests |
| **Error handling** | Services fail silently (catch → return `{}`), user sees "…" forever |
| **Mobile** | Sidebar hidden on small screens with no hamburger toggle |
| **Keyboard** | Command palette only; no vim-like navigation, no focus management |
| **Accessibility** | No ARIA labels, no focus-visible styles, no screen reader support |
| **Real-time** | No SSE/WebSocket streaming for logs, queue changes, or Plex activity |
| **Direct access** | All actions require navigating to a page first; no quick-action toolbar |
| **Polish** | No animations, no transitions, no micro-interactions |

---

## Architecture Decisions

### Keep
- **htmx + hyperscript** — no build step, works with Django templates, fast to iterate
- **Custom CSS variables** — the design system foundation is solid
- **Service layer pattern** — `services.py` stays framework-agnostic, views call it directly
- **No JS framework** — htmx replaces React/Vue for this use case; the DOM is the API

### Add
- **Chart.js** (CDN, ~60KB) — lightweight charting for sparklines, gauges, history
- **htmx SSE extension** — real-time log streaming without WebSocket complexity
- **Skeleton CSS** — loading states for every card and table
- **Toast component** — htmx-driven success/error notifications
- **CSS transitions** — subtle animations for state changes (card updates, badge colors)
- **aria-live regions** — screen reader announcements for dynamic content

### Don't add
- No React, Vue, or Svelte — htmx handles all interactivity
- No Tailwind — the custom CSS variables are cleaner and lighter
- No WebSocket server — SSE via htmx is simpler and Django supports it natively
- No bundler (webpack, vite) — vanilla JS + CDN libraries only

---

## Phase 1: Design System + Component Library (Foundation)

**Goal**: Every page shares consistent, polished components that look and feel like a single product.

### 1A. CSS Architecture Overhaul
```
ui/static/css/
├── tokens.css          # Design tokens (colors, spacing, typography, shadows)
├── reset.css           # Minimal CSS reset
├── components.css      # All component styles
├── layout.css          # Sidebar, topbar, grid, responsive
├── pages.css           # Page-specific overrides
└── style.css           # Imports all of the above
```

**New components to build:**
- `btn` — primary, secondary, ghost, danger, icon-only, loading state
- `card` — elevation levels (flat, raised, floating), interactive hover
- `table` — sortable headers, zebra striping, row actions, empty state
- `badge` — success, warning, error, info, neutral with pulse animation
- `modal` — slide-in panels, confirmation dialogs, form modals
- `toast` — auto-dismiss, stacked, success/error/info variants
- `skeleton` — loading placeholders for cards, tables, text
- `tooltip` — hover and focus triggers, positioned via CSS
- `dropdown` — menu, select, filter
- `tabs` — horizontal and vertical variants
- `progress` — determinate, indeterminate, multi-step
- `stat` — large number + label + trend indicator
- `timeline` — activity feed with timestamps
- `sparkline` — inline Chart.js sparklines (CPU, RAM, queue over time)

### 1B. Responsive System
- **Sidebar**: Full-width on desktop (>1024px), collapsed to icons on tablet (768-1024px), off-screen drawer with hamburger on mobile (<768px)
- **Grid**: 4-column on desktop, 2 on tablet, 1 on mobile
- **Cards**: Stack vertically on mobile, side-by-side on desktop
- **Tables**: Horizontal scroll on mobile with sticky first column
- **Command palette**: Full-screen overlay on mobile

### 1C. Accessibility Foundation
- All interactive elements get `aria-label`, `role`, and `aria-live` attributes
- Focus-visible styles for keyboard navigation
- Skip-to-content link
- Color contrast ratios ≥ 4.5:1 for all text
- Reduced-motion media query to disable animations
- Semantic HTML: `<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>`

---

## Phase 2: Dashboard Revolution (Overview Page)

**Goal**: The overview becomes the command center — you see everything at a glance and can act on anything with one click.

### 2A. Live Metrics Grid
Replace the 4 static cards with a dynamic dashboard:

| Row 1 (4 cards) | Row 2 (full-width) |
|---|---|
| **Queue** — downloading/waiting/importing with mini sparkline (last 10 min) | **Activity Timeline** — real-time feed of all stack events |
| **Host** — CPU/RAM/Disk gauges with Chart.js doughnut charts | |
| **Plex** — active sessions with progress bars, scan % complete | |
| **Arr Fleet** — missing/cutoff/importing per app with trend arrows | |

### 2B. Quick Actions Bar
A persistent toolbar below the topbar with one-click actions:
- `[▶ Scan Plex]` `[🔄 RSS Sync]` `[🧹 Prune Docker]` `[📊 Queue Status]`
- Each button fires an htmx POST and shows a toast on completion
- Actions are configurable (settings page lets you pin/unpin actions)

### 2C. Real-Time Updates via SSE
- Replace 20s polling with Server-Sent Events for the overview
- `htmx-ext/sse` pushes updates when queue changes, Plex activity changes, or host metrics spike
- Fallback to polling if SSE connection drops
- Add a "last updated" timestamp and connection indicator

### 2D. History Sparklines
- CPU/RAM/Disk: Chart.js line charts showing last 30 minutes (stored in-session)
- Queue depth: line chart showing downloads over time
- Plex sessions: area chart of concurrent streams

---

## Phase 3: Page-by-Page Rebuild

### 3A. Host Page — Infrastructure Command Center
**Current**: 38 lines, basic vitals + container list
**Target**: Full infrastructure dashboard

**Layout:**
```
┌─────────────────────────────────────────────┐
│ [CPU gauge] [RAM gauge] [Disk gauge]        │  ← Chart.js doughnuts
├─────────────────────────────────────────────┤
│ Container Fleet                              │
│ ┌─────────┬─────────┬─────────┬──────────┐ │
│ │ Name    │ Status  │ CPU/Mem │ Actions  │ │  ← sortable table
│ │ plex    │ ● up    │ 5%/12%  │ [restart]│ │
│ │ radarr  │ ● up    │ 2%/8%   │ [restart]│ │
│ │ ...     │         │         │          │ │
│ └─────────┴─────────┴─────────┴──────────┘ │
├─────────────────────────────────────────────┤
│ [Mount Health] [OOM Check] [Disk Usage]     │  ← expandable panels
│ [Image Updates] [Resource Limits] [Perms]   │
├─────────────────────────────────────────────┤
│ Host Actions                                 │
│ [Restart All] [Prune Docker] [Reboot Host]  │  ← with confirmation modals
│ [Sync Packages] [Upgrade Packages]          │
├─────────────────────────────────────────────┤
│ Live Logs (streaming)                        │  ← SSE-powered log viewer
│ ┌─────────────────────────────────────────┐ │
│ │ 16:32:01 plex  Scanner started          │ │
│ │ 16:32:03 radarr Queue item added        │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

**New features:**
- Container table with sortable columns (name, status, CPU%, memory, uptime)
- One-click restart/stop/start per container with confirmation modal
- Expandable "Vitals" panels (mount health, OOM, disk, images, permissions) — click to expand, results cached for 60s
- Real-time container resource usage (top-like) with auto-refresh
- Live log streaming — select a container from dropdown, logs stream via SSE
- Disk usage bar chart per mount point
- Container resource limit compliance table

### 3B. Arr Fleet Page — Download Management Hub
**Current**: 28 lines, basic cards + queue table
**Target**: Full queue management with search, filter, and bulk actions

**Layout:**
```
┌─────────────────────────────────────────────┐
│ [RSS Sync] [Search Missing] [Auto-fix]      │  ← action buttons
├─────────────────────────────────────────────┤
│ Queue Table (sortable, filterable)           │
│ ┌────────┬─────────┬────────┬──────┬──────┐│
│ │ Title  │ Status  │ Size   │ ETA  │ Act  ││
│ │ Movie1 │ ↓ 45%   │ 2.1GB  │ 5m   │ [×]  ││
│ │ ShowS2 │ ⏳ wait │ 4.2GB  │ —    │ [×]  ││
│ └────────┴─────────┴────────┴──────┴──────┘│
├─────────────────────────────────────────────┤
│ Tabs: [Missing] [Cutoff Unmet] [Blocklist]  │
│         [Recently Added] [Import Lists]     │
│ ┌─────────────────────────────────────────┐ │
│ │ Tab content (htmx partial swap)         │ │
│ └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│ Per-App Panels (Radarr / Sonarr / Prowlarr) │
│ ┌──────────────┐ ┌──────────────┐           │
│ │ Radarr       │ │ Sonarr       │           │
│ │ Backlog: 42  │ │ Backlog: 89  │           │
│ │ Errors: 3    │ │ Errors: 1    │           │
│ │ [View Logs]  │ │ [View Logs]  │           │
│ └──────────────┘ └──────────────┘           │
└─────────────────────────────────────────────┘
```

**New features:**
- Sortable/filterable queue table with column sorting
- Bulk select + actions (blocklist selected, unmonitor selected)
- Tab-based views for Missing, Cutoff, Blocklist, Recently Added, Import Lists
- Per-app status panels with backlog counts and error indicators
- Command queue visualization (pending/running/completed commands)
- Search bar that filters queue items client-side
- Manual import candidates with drag-and-drop (or click-to-import)

### 3C. Plex Page — Media Server Health
**Current**: 44 lines, basic health + sessions
**Target**: Complete Plex operations center

**Layout:**
```
┌─────────────────────────────────────────────┐
│ [Scan] [Refresh] [Empty Trash] [Optimize]   │  ← quick actions
├─────────────────────────────────────────────┤
│ Health Status                                │
│ ┌──────────┬──────────┬──────────┬─────────┐│
│ │ State    │ Scans    │ D-state  │ Mounts  ││
│ │ ● Idle   │ 0 active │ 0 found  │ ● OK    ││
│ └──────────┴──────────┴──────────┴─────────┘│
├─────────────────────────────────────────────┤
│ Active Sessions                              │
│ ┌─────────────────────────────────────────┐ │
│ │ 🎬 The Matrix  John  Transcoding 72%   │ │  ← progress bars
│ │ 📺 Breaking Bad Mary Direct Play 45%   │ │
│ └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│ Libraries                                    │
│ Movies (20,286) ● Shows (1,204) ● Anime    │  ← clickable to posters
├─────────────────────────────────────────────┤
│ Recently Added                               │
│ [poster] [poster] [poster] [poster] ...      │  ← horizontal scroll
├─────────────────────────────────────────────┤
│ Scan History (last 15 min)                   │
│ ████████░░░░░░░░░░░░ 42%  ETA: 3m           │  ← timeline chart
├─────────────────────────────────────────────┤
│ Recent Plex Log (streaming)                  │
└─────────────────────────────────────────────┘
```

**New features:**
- Library cards with item counts and last scan time
- Session cards with poster thumbnails, user info, quality, progress
- Scan progress bar with ETA calculation
- Recently added horizontal scroll with poster art
- Plex log streaming (SSE)
- Duplicate detection results with side-by-side comparison
- TMDb missing metadata report

### 3D. Posters Page — Art Management
**Current**: 26 lines, library list + empty gallery
**Target**: Full poster browsing and sync management

**New features:**
- Library selector as horizontal tabs
- Gallery grid with poster thumbnails (lazy loading, masonry layout)
- Hover overlay with: title, rating, year, source (TMDb/Fanart/TVDB)
- Click to compare: current poster vs. candidate
- Bulk sync controls: Dry Run, Auto, Review modes
- Sync progress with item-by-item status
- Sync history with success/failure counts

### 3E. Settings Page — Stack Configuration
**Current**: Placeholder stub
**Target**: Full settings interface

**Sections:**
1. **Connection** — Radarr/Sonarr/Prowlarr URLs and API keys (test connection button)
2. **Plex** — URL, token, library selection
3. **Authentication** — Change password, session timeout, API keys management
4. **Display** — Theme (dark/light), sidebar position, card layout
5. **Notifications** — Webhook URLs, alert thresholds
6. **Advanced** — Log levels, cache TTL, debug mode
7. **Danger Zone** — Factory reset, data export/import

### 3F. Activity Log Page — Audit Trail
**Current**: Placeholder stub
**Target**: Searchable, filterable activity history

**Features:**
- Timeline view of all actions (who did what, when)
- Filter by: action type, app, user, time range
- Search by keyword
- Export to CSV
- Auto-scroll with "new events" indicator
- Correlate with Docker logs

### 3G. Log Viewer Page — Centralized Logging
**Current**: None
**Target**: Unified log viewer for all containers

**Features:**
- Container selector (multi-select to view multiple)
- Real-time streaming via SSE
- Search/filter by keyword, regex
- Log level filtering (ERROR, WARN, INFO, DEBUG)
- Timestamp range filtering
- Auto-scroll with pause/resume
- Download logs as text file
- Error highlighting and count badges

---

## Phase 4: Interactive Features

### 4A. Enhanced Command Palette
- **Fuzzy search** — not just substring match
- **Recent commands** — show last 5 executed commands
- **Favorites** — pin frequently used commands
- **Direct execution** — some commands run in-browser (API calls) instead of clipboard
- **Context-aware** — on the Fleet page, palette shows Fleet commands; on Host, Host commands
- **Keyboard shortcuts** — assign `Ctrl+1` through `Ctrl+9` to pinned commands

### 4B. Toast Notification System
```html
<div id="toasts" aria-live="polite" class="toast-container"></div>
```
- Triggered by htmx `afterRequest` events
- Variants: success (green), error (red), warning (amber), info (blue)
- Auto-dismiss after 5s, manual dismiss with × button
- Stack multiple toasts vertically
- Sound notification option (optional, off by default)

### 4C. Confirmation Dialogs
- Destructive actions (restart all, prune, reboot, blocklist clear) show a modal
- Modal has: title, description, danger level indicator, Cancel/Confirm buttons
- Some actions require typing confirmation ("REBOOT" to confirm reboot)
- Keyboard: Enter to confirm, Escape to cancel

### 4D. Inline Editing
- Settings values editable inline (click to edit, Enter to save)
- Quality profile names editable
- Root folder paths editable with validation

### 4E. Drag and Drop
- Poster reorder in gallery view
- Queue priority reordering
- Import list reordering

---

## Phase 5: Performance Optimization

### 5A. Overview Polling Optimization
**Current**: `_overview_context()` calls 5 services sequentially, every 20s
**Target**: Parallel execution + per-card independent polling

```python
# Current (sequential, ~5-8s total):
queue = aggregate_queue_status()  # hits Radarr + Sonarr + Plex
hr = host_resources()              # reads /proc
sh = scan_health()                  # hits Plex + Docker
bs = backlog_status()              # hits Radarr + Sonarr

# New (parallel, ~2s total):
import asyncio
results = await asyncio.gather(
    aggregate_queue_status(),
    host_resources(),
    scan_health(),
    backlog_status(),
)
```

- Each overview card polls independently at different intervals:
  - Queue: every 10s (fast-changing)
  - Host: every 5s (real-time)
  - Plex: every 15s (medium)
  - Arr: every 30s (slow-changing)
- Overview cards use `hx-trigger="every Xs"` with staggered offsets
- Add `If-Modified-Since` / ETag to partial responses to avoid full re-renders

### 5B. Caching Layer
- **View-level cache**: `cache_page(60)` for non-critical views (reference, docs)
- **Service-level cache**: `@lru_cache` for config reads, library lists
- **Partial cache**: ETags on htmx partials — browser sends `If-None-Match`, server returns 304
- **Static file cache**: Whitenoise already handles this with `CompressedManifestStaticFilesStorage`

### 5C. Lazy Loading
- Images: `loading="lazy"` on all poster thumbnails
- Below-fold sections: load on scroll (IntersectionObserver)
- Tab content: load on first tab click, not on page load
- Log viewer: virtual scrolling for large log volumes

### 5D. Frontend Bundle Optimization
- Chart.js: load only required chart types (tree-shaking via CDN)
- hyperscript: only load on pages that use it (conditional script tag)
- CSS: split into critical (above-fold) and non-critical (below-fold) with media queries

---

## Phase 6: Polish & Delight

### 6A. Animations & Transitions
- **Card updates**: subtle fade + slide when values change
- **Badge pulse**: error badges pulse red, success badges glow green
- **Page transitions**: crossfade between pages (htmx `hx-push-url` + CSS transitions)
- **Skeleton loading**: shimmer animation on placeholder content
- **Progress bars**: smooth CSS transitions, not instant jumps
- **Toast entrance**: slide in from top-right, fade out on dismiss
- **Modal entrance**: backdrop fade + modal slide up

### 6B. Micro-Interactions
- Button press: scale(0.98) on mousedown, return on mouseup
- Card hover: subtle elevation increase (shadow-md → shadow-lg)
- Nav item: left border slide-in on hover
- Toggle switch: smooth color transition
- Number changes: count-up animation for large numbers (like odometer)

### 6C. Dark/Light Theme
- CSS variables swap via `data-theme="light"` on `<html>`
- Persisted in `localStorage`
- Toggle in topbar (sun/moon icon)
- System preference detection (`prefers-color-scheme`)
- Light theme: white backgrounds, dark text, same accent colors

### 6D. Empty States
Every list/table/card gets a designed empty state:
- Queue empty: "All caught up! 🎉" with a subtle animation
- No sessions: "No one's watching right now" with a couch icon
- No logs: "No recent activity" with a fade-in prompt to check a container
- Library list empty: "Connect Plex to see your libraries" with setup instructions

### 6E. Error States
- Connection lost: banner at top with "Reconnecting..." and retry button
- Service unavailable: card shows error icon + retry button instead of "…"
- API error: toast with error details and "Copy to clipboard" button
- Full-page error: illustrated error page with "Go to Dashboard" button

---

## Implementation Order

| Phase | Effort | Impact | Dependencies |
|-------|--------|--------|--------------|
| **1A: CSS Architecture** | 2-3 days | ⭐⭐⭐⭐⭐ | None |
| **1B: Responsive** | 1-2 days | ⭐⭐⭐⭐ | 1A |
| **1C: Accessibility** | 1 day | ⭐⭐⭐ | 1A |
| **2A: Live Metrics** | 2-3 days | ⭐⭐⭐⭐⭐ | 1A |
| **2B: Quick Actions** | 1 day | ⭐⭐⭐⭐ | 1A |
| **2C: SSE Real-Time** | 2 days | ⭐⭐⭐⭐ | 2A |
| **2D: Sparklines** | 1 day | ⭐⭐⭐ | 2A, Chart.js |
| **3A: Host Page** | 3-4 days | ⭐⭐⭐⭐⭐ | 1A-1C |
| **3B: Fleet Page** | 3-4 days | ⭐⭐⭐⭐⭐ | 1A-1C |
| **3C: Plex Page** | 2-3 days | ⭐⭐⭐⭐ | 1A-1C |
| **3D: Posters Page** | 2 days | ⭐⭐⭐ | 1A-1C |
| **3E: Settings Page** | 2-3 days | ⭐⭐⭐⭐ | 1A-1C |
| **3F: Activity Log** | 1-2 days | ⭐⭐⭐ | 2C |
| **3G: Log Viewer** | 2-3 days | ⭐⭐⭐⭐⭐ | 2C |
| **4A: Command Palette** | 1-2 days | ⭐⭐⭐ | 1A |
| **4B: Toast System** | 1 day | ⭐⭐⭐⭐ | 1A |
| **4C: Confirmations** | 1 day | ⭐⭐⭐ | 1A |
| **5A: Polling Opt** | 1-2 days | ⭐⭐⭐⭐⭐ | 2A |
| **5B: Caching** | 1 day | ⭐⭐⭐⭐ | None |
| **6A: Animations** | 1-2 days | ⭐⭐⭐ | 1A |
| **6B: Micro-Interactions** | 1 day | ⭐⭐ | 6A |
| **6C: Dark/Light** | 1 day | ⭐⭐ | 1A |
| **6D/E: Empty/Error States** | 1-2 days | ⭐⭐⭐ | 1A |

**Total estimated effort: 35-50 days**

---

## Quick Wins (Do First)

If you want the panel to feel dramatically better in 1 day:

1. **Toast notifications** — instant feedback for every action (1 day)
2. **Loading skeletons** — no more "…" everywhere (half day)
3. **Mobile sidebar toggle** — hamburger menu for phones (half day)
4. **Container restart buttons** with confirmation (half day)
5. **Fix overview polling** — parallelize the 5 sequential service calls (half day)
6. **Error states** — show retry buttons instead of silent failures (half day)

That's 3 days of work that transforms the panel from "barely functional" to "feels real."
