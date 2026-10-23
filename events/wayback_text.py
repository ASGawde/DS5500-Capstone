"""Recover pre-event description text from archived venue event pages (Wayback Machine).

Works for venues whose site puts the description in the page HTML at
/events/detail/<slug> (TD Garden, Boch Center / Wang Theatre).

For each event in data/interim/events_setlistfm.csv:
  1. match the headliner (or an opener) to an archived page slug,
  2. take the latest snapshot dated strictly BEFORE the event day (no leakage),
  3. check the page's own date line mentions the event's month and year,
  4. extract the description, doors time and starting ticket price.

All CDX indexes and page snapshots are cached under data/raw/wayback/.

Usage: python events/wayback_text.py td_garden
Output: data/interim/text_wayback_<venue>.csv
"""
import gzip
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "interim" / "events_setlistfm.csv"
CACHE = ROOT / "data" / "raw" / "wayback"

SITES = {
    "td_garden": "www.tdgarden.com/events/detail/",
    "wang_theatre": "www.bochcenter.org/events/detail/",
}

# Ticketing logistics, not event description. Dropped sentence by sentence.
LOGISTICS = re.compile(
    r"lineup (is )?subject to change|pre-?sale|on[- ]sale|general public|ticketmaster|"
    r"tickets (will|go|are|can)|verizon|citi(bank)?\b|sign[- ]up|register (now|here|at)|"
    r"\bvip\b|ticket ?holders?|general admission|bag policy|clear bag|box office",
    re.I)
# Venue pages that use a different name than setlist.fm (checked by hand against the CDX index).
ARTIST_ALIASES = {
    "YoungBoy Never Broke Again": "NBA YoungBoy",
    "mgk": "Machine Gun Kelly",
    "Kurtis Connor": "Kurtis Conner",  # setlist.fm typo
    "Queens of the Stone Age": "QOTSA",
    "Gillian Welch & David Rawlings": "Welch and Rawlings",
}
# Multi-artist radio shows: setlist.fm has no tour name, the venue page is named after the event.
EVENT_ALIASES = {
    "td_garden_2024-12-15": "KISS 108 Jingle Ball 2024",
    "td_garden_2025-12-14": "KISS 108 Jingle Ball 2025",
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]


def alnum(s):
    """Lowercase letters/digits only, with accents folded (Reneé -> renee)."""
    folded = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def wayback_get(url, tries=5):
    """GET from the Wayback Machine, waiting out its frequent 'Temporarily Offline' pages."""
    for attempt in range(tries):
        time.sleep(1.0)
        try:
            resp = requests.get(url, timeout=120, headers={"User-Agent": "DS5500-capstone-research"})
        except requests.RequestException:
            resp = None
        body = resp.content if resp is not None else b""
        if body[:2] == b"\x1f\x8b":  # id_ snapshots are sometimes served still gzipped
            body = gzip.decompress(body)
        text = body.decode("utf-8", errors="ignore")
        if resp is not None and resp.ok and "Temporarily Offline" not in text[:2000]:
            return text
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Wayback unavailable after {tries} tries: {url}")


def load_index(venue_key):
    """slug -> sorted list of (timestamp, original_url), from a cached CDX query."""
    cache_file = CACHE / venue_key / "cdx_index.txt"
    if not cache_file.exists():
        url = ("http://web.archive.org/cdx/search/cdx?url=" + SITES[venue_key] +
               "&matchType=prefix&from=2023&to=2026&fl=timestamp,original"
               "&filter=statuscode:200&filter=mimetype:text/html")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(wayback_get(url))
    index = {}
    for line in cache_file.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2 or "/events/detail/" not in parts[1]:
            continue
        slug = alnum(parts[1].split("/events/detail/")[1].split("?")[0])
        if slug:
            index.setdefault(slug, []).append((parts[0], parts[1]))
    return {s: sorted(v) for s, v in index.items()}


def candidate_slugs(names, index):
    """Slugs that contain an artist name (or vice versa), best matches first."""
    found = []
    variants = [v for n in names for v in (n, ARTIST_ALIASES.get(n), n.replace("&", " and "))]
    for name in filter(None, variants):
        key = alnum(name)
        if len(key) < 3:
            continue
        for slug in index:
            # Short names only match exactly: "rain" must not match "nationalballetofukraine".
            if slug == key or (len(key) >= 6 and key in slug) or (len(slug) >= 6 and slug in key):
                found.append((abs(len(slug) - len(key)), slug))
    return [s for _, s in sorted(set(found))]


def fetch_snapshot(venue_key, ts, original):
    slug = alnum(original.split("/events/detail/")[1].split("?")[0])
    cache_file = CACHE / venue_key / "pages" / f"{slug}_{ts}.html"
    if not cache_file.exists():
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(wayback_get(f"http://web.archive.org/web/{ts}id_/{original}"))
    return cache_file.read_text()


def parse_page(page):
    soup = BeautifulSoup(page, "html.parser")
    text_of = lambda sel: soup.select_one(sel).get_text(" ", strip=True) if soup.select_one(sel) else ""
    items = " | ".join(x.get_text(" ", strip=True) for x in soup.select(".sidebar_event_doors, .item"))
    block = soup.select_one(".event_description")
    paras = [p.get_text(" ", strip=True) for p in block.find_all(["p", "li"])] if block else []
    paras = [p for p in paras if p]

    kept = []
    for para in paras:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        clean = " ".join(s for s in sentences if not LOGISTICS.search(s))
        if len(clean) > 20:
            kept.append(clean)

    doors = re.search(r"open at\s*(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M", items, re.I)
    doors_time = None
    if doors:
        hour = int(doors.group(1)) % 12 + (12 if doors.group(3).upper() == "P" else 0)
        doors_time = f"{hour:02d}:{doors.group(2) or '00'}"
    # "Ticket Prices Start at $39.50" (2024-25) / "Starting at $64 at the Box Office" (2026)
    price = re.search(r"Start(?:s|ing)? at \$\s*([\d,]+(?:\.\d{2})?)", items, re.I)
    # 2026 Boch Center pages: "Event Starts 8:00 PM" (used when there is no JSON-LD start)
    listed_start = re.search(r"Event Starts\s*(\d{1,2}):(\d{2})\s*([AP])\.?M", items, re.I)

    # schema.org Event JSON-LD: exact show start and on-sale date. Multi-date pages list only
    # the first date, so keep the clock time but not the date from startDate.
    show_start_time = onsale_date = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        event = next((x for x in (data if isinstance(data, list) else [data])
                      if isinstance(x, dict) and "Event" in str(x.get("@type"))), None)
        if event:
            start = str(event.get("startDate") or "")
            show_start_time = start[11:16] if len(start) >= 16 else None
            offers = event.get("offers")
            offers = offers[0] if isinstance(offers, list) and offers else offers
            if isinstance(offers, dict) and offers.get("availabilityStarts"):
                onsale_date = str(offers["availabilityStarts"])[:10]
            break
    if show_start_time is None and listed_start:
        hour = int(listed_start.group(1)) % 12 + (12 if listed_start.group(3).upper() == "P" else 0)
        show_start_time = f"{hour:02d}:{listed_start.group(2)}"

    return {
        "page_title": text_of(".event_heading.above_sidebar") or text_of("h1"),
        "page_date_text": text_of(".sidebar_event_date"),
        "description_raw": "\n".join(paras),
        "description": "\n".join(kept),
        "doors_time": doors_time,
        "show_start_time": show_start_time,
        "onsale_date": onsale_date,
        "ticket_price_min": float(price.group(1).replace(",", "")) if price else None,
        "page_says_cancelled": bool(re.search(r"cancel+ed|postponed", text_of(".sidebar_event_date"), re.I)),
    }


def date_matches(page_date_text, event_date):
    """Page's own date line must mention the event's month and year (guards against an
    artist's page from an earlier tour). Pages without a date line pass."""
    if not page_date_text:
        return True
    low = page_date_text.lower()
    # Boch Center abbreviates months ("Mar 23"); "mar" also matches "march".
    return str(event_date.year) in low and MONTHS[event_date.month - 1][:3] in low


def process_event(row, venue_key, index):
    # Tour name last: catches multi-artist shows whose page is named after the event (Jingle Ball).
    names = ([EVENT_ALIASES[row.event_id]] if row.event_id in EVENT_ALIASES else []) + ([row.headliner]
             + (row.supporting_artists.split("; ") if isinstance(row.supporting_artists, str) else [])
             + ([row.tour_name] if isinstance(row.tour_name, str) else []))
    event_day = date.fromisoformat(row.date_start)
    cutoff = row.date_start.replace("-", "")
    out = {"event_id": row.event_id, "status": "no_match"}

    for slug in candidate_slugs(names, index)[:3]:
        before = [(ts, url) for ts, url in index[slug] if ts[:8] < cutoff]
        if not before:
            out.update(status="no_pre_event_snapshot", match_slug=slug)
            continue
        ts, url = before[-1]
        parsed = parse_page(fetch_snapshot(venue_key, ts, url))
        out.update(match_slug=slug, description_timestamp=f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}Z",
                   description_url=f"https://web.archive.org/web/{ts}/{url}", **parsed)
        if not date_matches(parsed["page_date_text"], event_day):
            out["status"] = "date_mismatch"
            continue
        out["status"] = "ok" if parsed["description"] else "empty_description"
        if out["status"] == "ok":
            break
    return out


def main():
    venue_key = sys.argv[1] if len(sys.argv) > 1 else "td_garden"
    if venue_key not in SITES:
        sys.exit(f"Unknown venue '{venue_key}'. Options: {', '.join(SITES)}")

    events = pd.read_csv(EVENTS)
    events = events[(events.venue_key == venue_key) & ~events.likely_non_concert]
    index = load_index(venue_key)
    print(f"{venue_key}: {len(events)} events, {len(index)} archived page slugs")

    rows = []
    for i, row in enumerate(events.itertuples(), 1):
        rows.append(process_event(row, venue_key, index))
        if i % 10 == 0:
            print(f"  {i}/{len(events)} done", flush=True)

    df = pd.DataFrame(rows)
    df["description_source"] = df.status.map(lambda s: "venue_archive" if s == "ok" else None)
    df["description_length"] = df.description.str.len().where(df.status == "ok")
    out = ROOT / "data" / "interim" / f"text_wayback_{venue_key}.csv"
    df.to_csv(out, index=False)

    print("\nStatus counts:")
    print(df.status.value_counts().to_string())
    ok = df[df.status == "ok"]
    print(f"\nReal text: {len(ok)}/{len(df)} ({len(ok) / len(df):.0%}); "
          f"median length {ok.description_length.median():.0f} chars; "
          f"doors time {ok.doors_time.notna().mean():.0%}; show start {ok.show_start_time.notna().mean():.0%}; "
          f"on-sale date {ok.onsale_date.notna().mean():.0%}; price {ok.ticket_price_min.notna().mean():.0%}")
    if "page_says_cancelled" in df and df.page_says_cancelled.fillna(False).any():
        print("Pages marked cancelled/postponed:", ", ".join(df[df.page_says_cancelled.fillna(False)].event_id))
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
