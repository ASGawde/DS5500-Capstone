"""Probe: does the Ticketmaster Discovery API return PAST events?

Queries one venue (TD Garden) for a past window (March 2024) and a control
window (next 30 days), then prints schema coverage for one sample event.

Usage: python events/ticketmaster_probe.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = "https://app.ticketmaster.com/discovery/v2"
VENUE_KEYWORD = "TD Garden"
PAST_WINDOW = ("2024-03-01T00:00:00Z", "2024-03-31T23:59:59Z")
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def get(endpoint, api_key, **params):
    resp = requests.get(f"{BASE}/{endpoint}", params={"apikey": api_key, **params}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_venue(api_key):
    data = get("venues.json", api_key, keyword=VENUE_KEYWORD, stateCode="MA", countryCode="US")
    venues = data.get("_embedded", {}).get("venues", [])
    print(f"Venue search '{VENUE_KEYWORD}': {len(venues)} match(es)")
    for v in venues:
        loc = v.get("location", {})
        print(f"  {v['id']}  {v.get('name')}  ({loc.get('latitude')}, {loc.get('longitude')})  "
              f"{v.get('address', {}).get('line1')}")
    exact = [v for v in venues if v.get("name", "").lower() == VENUE_KEYWORD.lower()]
    if not (exact or venues):
        sys.exit("No venue found.")
    return (exact or venues)[0]["id"]


def query_events(api_key, venue_id, start, end):
    data = get("events.json", api_key, venueId=venue_id, startDateTime=start, endDateTime=end, size=1)
    total = data.get("page", {}).get("totalElements", 0)
    events = data.get("_embedded", {}).get("events", [])
    return total, events


def dig(obj, *path):
    for key in path:
        if isinstance(obj, list):
            obj = obj[key] if len(obj) > key else None
        elif isinstance(obj, dict):
            obj = obj.get(key)
        if obj is None:
            return None
    return obj


def coverage_report(ev):
    venue = dig(ev, "_embedded", "venues", 0) or {}
    description = ev.get("description") or ev.get("info") or ev.get("pleaseNote")
    fields = {
        "event_name": ev.get("name"),
        "category": " / ".join(filter(None, [
            dig(ev, "classifications", 0, "segment", "name"),
            dig(ev, "classifications", 0, "genre", "name"),
            dig(ev, "classifications", 0, "subGenre", "name"),
        ])) or None,
        "venue_name": venue.get("name"),
        "venue_lat": dig(venue, "location", "latitude"),
        "venue_lon": dig(venue, "location", "longitude"),
        "date_start": dig(ev, "dates", "start", "localDate"),
        "date_end": dig(ev, "dates", "end", "localDate"),
        "time_start": dig(ev, "dates", "start", "localTime"),
        "time_end_or_duration": dig(ev, "dates", "end", "localTime"),
        "description": description,
        "source_url": ev.get("url"),
        "status (nice-to-have)": dig(ev, "dates", "status", "code"),
        "attractions (nice-to-have)": ", ".join(
            a.get("name", "") for a in dig(ev, "_embedded", "attractions") or []) or None,
    }
    print("\nSchema coverage for sample event:")
    for name, value in fields.items():
        if value is None:
            print(f"  {name:28s} MISSING")
        elif name == "description":
            print(f"  {name:28s} ({len(value)} chars) {value[:150]!r}")
        else:
            print(f"  {name:28s} {value}")


def main():
    load_dotenv()
    api_key = os.getenv("TICKETMASTER_API_KEY")
    if not api_key:
        sys.exit("TICKETMASTER_API_KEY not set. Copy .env.example to .env and add your key.")

    venue_id = find_venue(api_key)

    past_total, past_events = query_events(api_key, venue_id, *PAST_WINDOW)
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    ctrl_window = (now.strftime(fmt), (now + timedelta(days=30)).strftime(fmt))
    ctrl_total, ctrl_events = query_events(api_key, venue_id, *ctrl_window)

    print(f"\nPast window    {PAST_WINDOW[0][:10]} -> {PAST_WINDOW[1][:10]}: {past_total} events")
    print(f"Control window {ctrl_window[0][:10]} -> {ctrl_window[1][:10]}: {ctrl_total} events")

    if past_events:
        label, ev = "past", past_events[0]
    elif ctrl_events:
        label, ev = "control", ctrl_events[0]
        print("\nNo past events returned; showing a control (upcoming) event instead.")
    else:
        sys.exit("\nBoth windows empty: check the API key and venue ID.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"ticketmaster_sample_{label}.json"
    out.write_text(json.dumps(ev, indent=2))
    print(f"Raw JSON saved to {out}")

    coverage_report(ev)


if __name__ == "__main__":
    main()
