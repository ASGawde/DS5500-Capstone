"""Collect past concerts from setlist.fm and group them to one row per venue-date.

setlist.fm returns one setlist per artist performance, so a night with a
headliner and two openers is three setlists. This script merges them.

Raw API pages are cached under data/raw/setlistfm/ so reruns cost no requests.

Usage: python events/setlistfm_collect.py
Output: data/interim/events_setlistfm.csv
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venues import VENUES, WINDOW_END, WINDOW_START  # noqa: E402

BASE = "https://api.setlist.fm/rest/1.0"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "raw" / "setlistfm"
OUT = ROOT / "data" / "interim" / "events_setlistfm.csv"


def get(endpoint, api_key, **params):
    """GET with ~1 req/sec pacing and backoff on 429 (setlist.fm throttles at 0.6 s)."""
    for attempt in range(5):
        time.sleep(1.1)
        resp = requests.get(f"{BASE}/{endpoint}", params=params, timeout=30,
                            headers={"x-api-key": api_key, "Accept": "application/json"})
        if resp.status_code == 429:
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code == 404:  # setlist.fm uses 404 for "no results"
            return {}
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Rate limited too many times on {endpoint} {params}")


def fetch_setlists(api_key, venue_id, year):
    """All setlists for one venue and year, using the page cache."""
    rows, page = [], 1
    while True:
        cache_file = CACHE / f"{venue_id}_{year}_p{page}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
        else:
            data = get("search/setlists", api_key, venueId=venue_id, year=year, p=page)
            CACHE.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data))
        rows += data.get("setlist", [])
        if not data or page * data["itemsPerPage"] >= data["total"]:
            return rows
        page += 1


def song_count(setlist):
    return sum(len(s.get("song", [])) for s in setlist.get("sets", {}).get("set", []))


def pick_headliner(setlists):
    """Headliner = a setlist with a tour name; ties broken by most songs."""
    return max(setlists, key=lambda s: ("tour" in s, song_count(s)))


def group_events(venue_key, setlists):
    venue = VENUES[venue_key]
    by_date = defaultdict(list)
    for s in setlists:
        by_date[datetime.strptime(s["eventDate"], "%d-%m-%Y").date().isoformat()].append(s)

    rows = []
    for date, group in sorted(by_date.items()):
        if not (WINDOW_START <= date <= WINDOW_END):
            continue
        head = pick_headliner(group)
        others = [s["artist"]["name"] for s in group if s is not head]
        tour = head.get("tour", {}).get("name") or next(
            (s["tour"]["name"] for s in group if "tour" in s), None)
        rows.append({
            "event_id": f"{venue_key}_{date}",
            "event_name": head["artist"]["name"],
            "category": "concert",
            "venue_key": venue_key,
            "venue_name": venue["venue_name"],
            "venue_lat": venue["venue_lat"],
            "venue_lon": venue["venue_lon"],
            "date_start": date,
            "date_end": date,
            "headliner": head["artist"]["name"],
            "supporting_artists": "; ".join(dict.fromkeys(others)) or None,
            "tour_name": tour,
            "artist_mbid": head["artist"].get("mbid"),
            "source_url": head.get("url"),
            "n_setlists": len(group),
            "headliner_songs": song_count(head),
            # Anthem singers at Celtics/Bruins games: TD Garden, one artist, no tour, exactly
            # one song. (0 songs just means nobody filled in the setlist for a real show.)
            "likely_non_concert": (venue_key == "td_garden" and len(group) == 1
                                   and tour is None and song_count(head) == 1),
            "venue_capacity": venue["venue_capacity"],
            "indoor_or_outdoor": venue["indoor_or_outdoor"],
            "zone_id": venue["zone_id"],
        })
    return rows


def main():
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("SETLISTFM_API_KEY")
    if not api_key:
        sys.exit("SETLISTFM_API_KEY not set in .env")

    years = range(int(WINDOW_START[:4]), int(WINDOW_END[:4]) + 1)
    all_rows = []
    for key, venue in VENUES.items():
        setlists = [s for vid in venue["setlistfm_ids"] for y in years
                    for s in fetch_setlists(api_key, vid, y)]
        rows = group_events(key, setlists)
        flagged = sum(r["likely_non_concert"] for r in rows)
        print(f"{venue['venue_name']:28s} setlists={len(setlists):4d}  "
              f"event_dates={len(rows):4d}  likely_non_concert={flagged}")
        all_rows += rows

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT, index=False)
    print(f"\nWrote {len(df)} rows to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
