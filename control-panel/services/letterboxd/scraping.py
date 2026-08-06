"""Letterboxd page-fetch + regex primitives, split out of
services/radarr/router.py (which owned add-from-letterboxd* before this
package existed) - every Letterboxd-touching route in this package imports
from here instead of redeclaring these.
"""
import re

import httpx

from core.responses import fail

# Letterboxd doesn't expose TMDb ids directly, but every matched film page
# links to its TMDb entry in the sidebar - regex is simpler and more stable
# than parsing Letterboxd's HTML structure.
LETTERBOXD_TMDB_RE = re.compile(r"themoviedb\.org/movie/(\d+)")
# List/watchlist grid pages carry each poster's slug in this attribute.
LETTERBOXD_ITEM_SLUG_RE = re.compile(r'data-item-slug="([^"]+)"')
LETTERBOXD_LIST_PAGE_RE = re.compile(r"/page/(\d+)/")
# og:title is present on every Letterboxd film page (confirmed live,
# 2026-08-06, against https://letterboxd.com/film/oppenheimer/) as
# `<meta property="og:title" content="Title (Year)">` - used as the
# TV-crossover fallback title/year source when a film has no TMDb movie
# match (see services/letterboxd/cache.py's resolve_tv_crossovers).
LETTERBOXD_OG_TITLE_RE = re.compile(r'property="og:title" content="([^"(]+?)\s*\((\d{4})\)"')
# Own-ratings marker, confirmed live 2026-08-06 against
# https://letterboxd.com/<user>/films/ - each poster's <li> contains, only
# when the page owner rated that film,
# `<span class="rating -micro -darker rated-N">` where N is 1-10 (half-star
# granularity: N/2 = star count). Absent entirely for an unrated film, so
# this must be matched per-item-segment, not as a flat list zipped
# positionally against LETTERBOXD_ITEM_SLUG_RE's matches - see
# scrape_slugs_with_ratings() below.
LETTERBOXD_RATING_RE = re.compile(r'rated-(\d+)"')
# Tag chip pattern on a user's own logged/reviewed film page
# (https://letterboxd.com/<user>/film/<slug>/) - Letterboxd's documented
# public markup (community scrapers: letterboxdpy, judahpaul16/gruvbox-*).
# NOT independently confirmed live in this session (the specific user/film
# pages fetched during research had no tags set) - Task 5's Step 1 must
# re-verify this against a live page known to carry tags before relying on
# it, and adjust the pattern if Letterboxd's markup has since changed.
LETTERBOXD_TAG_RE = re.compile(r'href="/[^/]+/tag/([^/"]+)/"[^>]*class="tag"')

# robots.txt's "User-agent: *" section disallows these sort/filter path
# segments specifically.
LETTERBOXD_DISALLOWED_RE = re.compile(
    r"/(by|on|tag|genre|country|language|decade|friends)/"
    r"|/popular/this/"
    r"|/films/year/"
    r"|/films/[^/]+/year/"
    r"|/films/[^/]+/size/large/"
)
LETTERBOXD_GRID_RE = re.compile(
    r"^https://letterboxd\.com/(?:[^/]+/(?:list/[^/]+|watchlist|films)|[a-z-]+/[^/]+|films/in/[^/]+|films)/?$"
)

_LETTERBOXD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_page(url: str) -> str:
    try:
        page = httpx.get(url, headers=_LETTERBOXD_HEADERS, timeout=15, follow_redirects=True)
        page.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't fetch {url}: {e}")
    return page.text


def fetch_page_or_none(url: str) -> str | None:
    try:
        page = httpx.get(url, headers=_LETTERBOXD_HEADERS, timeout=15, follow_redirects=True)
        page.raise_for_status()
    except httpx.HTTPError:
        return None
    return page.text


def scrape_slugs_with_ratings(page_html: str) -> list[tuple[str, int | None]]:
    """Returns [(slug, rating_or_None), ...] in document order. Splits on
    each data-item-slug occurrence so a rating (when present) is matched
    only within its own <li>'s segment, not positionally zipped against a
    separate flat rating list - a film with no rating has no rated-N
    marker at all, so a flat zip would misalign every item after it."""
    slug_positions = [(m.group(1), m.start()) for m in re.finditer(r'data-item-slug="([^"]+)"', page_html)]
    results = []
    seen = set()
    for i, (slug, start) in enumerate(slug_positions):
        if slug in seen:
            continue
        seen.add(slug)
        end = slug_positions[i + 1][1] if i + 1 < len(slug_positions) else len(page_html)
        segment = page_html[start:end]
        rating_match = LETTERBOXD_RATING_RE.search(segment)
        results.append((slug, int(rating_match.group(1)) if rating_match else None))
    return results


def scrape_title_year(film_page_html: str) -> tuple[str, int] | None:
    match = LETTERBOXD_OG_TITLE_RE.search(film_page_html)
    if not match:
        return None
    return match.group(1).strip(), int(match.group(2))


def scrape_tags(user_film_page_html: str) -> list[str]:
    return list(dict.fromkeys(LETTERBOXD_TAG_RE.findall(user_film_page_html)))
