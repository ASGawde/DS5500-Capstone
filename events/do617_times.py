"""Show start times from Do617 (Boston events listings) for events whose venue page has none.

TD Garden pages carry an exact start in JSON-LD, but MGM (Live Nation) and Wang (Boch Center)
pages do not. Do617 keeps past-event pages for these venues with the listed start time
("8:00PM"). A start time is announced in advance, so it is available at forecast time.

robots.txt (checked 2026-10-22) allows /venues and /events. Requests are paced at ~1/sec and
every page is cached under data/raw/do617/.

Usage: python events/do617_times.py
Output: data/interim/times_do617.csv  (event_id, do617_time, do617_url, match_type)
"""
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wayback_text import alnum  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "interim" / "events_setlistfm.csv"
CACHE = ROOT / "data" / "raw" / "do617"
OUT = ROOT / "data" / "interim" / "times_do617.csv"
BASE = "https://do617.com"

# Do617 sometimes keeps one venue under two records.
VENUE_SLUGS = {
    "td_garden": ["td-garden"],
    "wang_theatre": ["wang-theatre", "boch-center-wang-theatre"],
    "mgm_music_hall": ["mgm-music-hall-at-fenway"],
}
LINK_RE = re.compile(r'href="/events/(20\d{2})/(\d{1,2})/(\d{1,2})/([^"]+)"')


def get(url, cache_file):
    """Cached GET with retries on transient server errors; returns "" if the page stays down."""
    if cache_file.exists():
        return cache_file.read_text()
    for attempt in range(3):
        time.sleep(1.2 + 5 * attempt)
        try:
            resp = requests.get(url, timeout=60, headers={"User-Agent": "DS5500-capstone-research"})
        except requests.RequestException:
            continue
        if resp.status_code >= 500:
            continue
        resp.raise_for_status()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(resp.text)
        return resp.text
    print(f"  skipped (server error): {url}", flush=True)
    return ""


def list_past_events(venue_slug, oldest):
    """(date, slug) for every past event at a venue, paging back until before `oldest`."""
    found = []
    for page in range(1, 60):
        html = get(f"{BASE}/venues/{venue_slug}/past_events?page={page}",
                   CACHE / "venues" / f"{venue_slug}_p{page}.html")
        links = {(date(int(y), int(m), int(d)), slug) for y, m, d, slug in LINK_RE.findall(html)}
        if not links:
            break
        found += links
        if min(d for d, _ in links) < oldest:
            break
    return sorted(set(found))


def page_time(slug_path):
    html = get(f"{BASE}/events/{slug_path}", CACHE / "events" / (slug_path.replace("/", "_") + ".html"))
    el = BeautifulSoup(html, "html.parser").select_one(".ds-event-time")
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AP])M", el.get_text(" ", strip=True), re.I) if el else None
    if not m:
        return None
    hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "P" else 0)
    return f"{hour:02d}:{m.group(2)}"


def main():
    events = pd.read_csv(EVENTS)
    events = events[~events.likely_non_concert]
    oldest = date.fromisoformat(events.date_start.min())
    rows = []
    for venue_key, slugs in VENUE_SLUGS.items():
        listing = [x for s in slugs for x in list_past_events(s, oldest)]
        by_date = {}
        for d, slug in listing:
            by_date.setdefault(d.isoformat(), []).append(f"{d.year}/{d.month}/{d.day}/{slug}")
        venue_events = events[events.venue_key == venue_key]
        print(f"{venue_key}: {len(listing)} Do617 listings, {len(venue_events)} events to time", flush=True)
        for ev in venue_events.itertuples():
            cands = by_date.get(ev.date_start, [])
            if not cands:
                rows.append({"event_id": ev.event_id, "match_type": "no_listing"})
                continue
            names = [ev.headliner] + (ev.supporting_artists.split("; ") if isinstance(ev.supporting_artists, str) else [])
            keys = [alnum(n) for n in names if len(alnum(n)) >= 4]
            named = [c for c in cands if any(k in alnum(c) for k in keys)]
            # One listing that day at the venue is unambiguous; otherwise require the artist name.
            pick = named[0] if named else (cands[0] if len(cands) == 1 else None)
            if pick is None:
                rows.append({"event_id": ev.event_id, "match_type": "ambiguous"})
                continue
            rows.append({"event_id": ev.event_id, "do617_time": page_time(pick),
                         "do617_url": f"{BASE}/events/{pick}",
                         "match_type": "artist+date" if named else "date_only"})
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    df["venue_key"] = df.event_id.str.rsplit("_", n=1).str[0]
    print("\nTime found by venue:", df.groupby("venue_key").do617_time.apply(lambda s: f"{s.notna().mean():.0%}").to_dict())
    print("Match types:", df.match_type.value_counts().to_dict())
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
