"""Probe: does setlist.fm return PAST concerts with the fields we need?

Looks up one venue (TD Garden), counts its setlists in 2024, and prints
schema coverage for one sample concert.

Usage: python events/setlistfm_probe.py
"""
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = "https://api.setlist.fm/rest/1.0"
VENUE_NAME = "TD Garden"
CITY = "Boston"
YEAR = 2024
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"


def get(endpoint, api_key, **params):
    time.sleep(0.6)  # stay under 2 requests/second
    resp = requests.get(f"{BASE}/{endpoint}", params=params, timeout=30,
                        headers={"x-api-key": api_key, "Accept": "application/json"})
    if resp.status_code == 404:  # setlist.fm returns 404 for "no results"
        return {}
    resp.raise_for_status()
    return resp.json()


def find_venue(api_key):
    data = get("search/venues", api_key, name=VENUE_NAME, cityName=CITY, country="US")
    venues = data.get("venue", [])
    print(f"Venue search '{VENUE_NAME}' in {CITY}: {data.get('total', 0)} match(es)")
    for v in venues:
        city = v.get("city", {})
        print(f"  {v['id']}  {v.get('name')}  ({city.get('name')}, {city.get('stateCode')})")
    exact = [v for v in venues if v.get("name", "").lower() == VENUE_NAME.lower()]
    if not (exact or venues):
        sys.exit("No venue found.")
    return (exact or venues)[0]


def coverage_report(s):
    venue = s.get("venue", {})
    coords = venue.get("city", {}).get("coords", {})
    songs = sum(len(st.get("song", [])) for st in s.get("sets", {}).get("set", []))
    fields = {
        "event_name": s.get("artist", {}).get("name"),
        "category": None,  # setlist.fm only covers concerts -> category = "concert"
        "venue_name": venue.get("name"),
        "venue_lat (CITY centroid)": coords.get("lat"),
        "venue_lon (CITY centroid)": coords.get("long"),
        "date_start": s.get("eventDate"),
        "date_end": None,
        "time_start": None,
        "time_end_or_duration": None,
        "description (tour name)": s.get("tour", {}).get("name"),
        "source_url": s.get("url"),
        "artist mbid (nice-to-have)": s.get("artist", {}).get("mbid"),
        "songs in setlist": songs,
        "info": s.get("info"),
    }
    print("\nSchema coverage for sample concert:")
    for name, value in fields.items():
        print(f"  {name:28s} {'MISSING' if value is None else value}")


def main():
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("SETLISTFM_API_KEY")
    if not api_key:
        sys.exit("SETLISTFM_API_KEY not set in .env")

    venue = find_venue(api_key)
    data = get("search/setlists", api_key, venueId=venue["id"], year=YEAR)
    setlists = data.get("setlist", [])
    print(f"\nSetlists at {venue['name']} in {YEAR}: {data.get('total', 0)} "
          f"({data.get('itemsPerPage')} per page)")
    for s in setlists[:5]:
        print(f"  {s.get('eventDate')}  {s.get('artist', {}).get('name')}  "
              f"| tour: {s.get('tour', {}).get('name')}")
    if not setlists:
        sys.exit("No setlists returned.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "setlistfm_sample.json"
    out.write_text(json.dumps(setlists[0], indent=2))
    print(f"Raw JSON saved to {out}")

    coverage_report(setlists[0])


if __name__ == "__main__":
    main()
