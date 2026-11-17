"""Recover pre-event description text for Fenway Park concerts from archived Red Sox pages.

Every stadium concert gets a page at mlb.com/redsox/tickets/concerts/<artist> (one page per
artist, reused across tours). The Wayback Machine has snapshots of nearly all of them. A page
carries:
  - an "-intro" block: "<h4>Noah Kahan at Fenway Park / July 18 & 19, 2024</h4>" followed by
    the Live Nation / Red Sox announcement (tour, dates, special guests)
  - a banner image whose alt text names the tour and guests ("Noah Kahan. North America 2024.
    We'll All Be Here Forever Tour. ... With special guests Mt. Joy and James Bay.")
Everything else (VIP packages, suites, city licensing) is boilerplate and skipped. The pages
list no doors or show times.

Same rules as wayback_text.py: latest snapshot strictly BEFORE the event day, and the intro's
date line must mention the event's month and year (artist pages are reused across tours).

Fallback when there is no usable page (e.g. Lana Del Rey's page was first archived after the
show): Vanyaland posts with "Fenway Park" in the title, such as the season preview "Fenway Park
Concert Series: The starting lineup for Summer 2024", split one block per show ("June 20: Lana
Del Rey"). A block must name the event's date and artist and be published before the event day.
MGM roundups ("MGM Music Hall at Fenway") are skipped.

CDX index and snapshots are cached under data/raw/wayback/fenway_park/, Vanyaland posts under
data/raw/vanyaland/.

Usage: python events/fenway_text.py
Output: data/interim/text_fenway_park.csv
"""
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vanyaland_text import API as VANYALAND_API  # noqa: E402
from vanyaland_text import clean as clean_press  # noqa: E402
from vanyaland_text import show_dates, split_blocks  # noqa: E402
from venues import WINDOW_END, WINDOW_START  # noqa: E402
from wayback_text import LOGISTICS, alnum, candidate_slugs, date_matches, wayback_get  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "interim" / "events_setlistfm.csv"
CACHE = ROOT / "data" / "raw" / "wayback" / "fenway_park"
PRESS_CACHE = ROOT / "data" / "raw" / "vanyaland" / "posts_fenway_park.json"
OUT = ROOT / "data" / "interim" / "text_fenway_park.csv"
SITE = "www.mlb.com/redsox/tickets/concerts/"
VENUE_KEY = "fenway_park"

# Announcement filler that is not about the show itself.
FILLER = re.compile(r"^note:|non-?transferr?able|platinum seating|private suites|"
                    r"subject to final city licensing|^buy tickets", re.I)


def load_index():
    """slug -> sorted list of (timestamp, original_url), from a cached CDX query."""
    cache_file = CACHE / "cdx_index.txt"
    if not cache_file.exists():
        url = ("http://web.archive.org/cdx/search/cdx?url=" + SITE +
               "&matchType=prefix&from=2023&to=2026&fl=timestamp,original"
               "&filter=statuscode:200&filter=mimetype:text/html")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(wayback_get(url))
    index = {}
    for line in cache_file.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2 or "/tickets/concerts/" not in parts[1]:
            continue
        raw = parts[1].split("/tickets/concerts/")[1].split("?")[0].strip("/")
        if not raw or "/" in raw or "." in raw or "%" in raw:  # assets, junk URLs
            continue
        index.setdefault(alnum(raw), []).append((parts[0], parts[1]))
    return {s: sorted(v) for s, v in index.items()}


def fetch_snapshot(slug, ts, original):
    cache_file = CACHE / "pages" / f"{slug}_{ts}.html"
    if not cache_file.exists():
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(wayback_get(f"http://web.archive.org/web/{ts}id_/{original}"))
    return cache_file.read_text()


def parse_page(page):
    soup = BeautifulSoup(page, "html.parser")
    intro = next((w for w in soup.select(".p-wysiwyg") if str(w.get("data-slug", "")).endswith("-intro")),
                 None) or next((w for w in soup.select(".p-wysiwyg") if w.find("h4")), None)
    heading = intro.find("h4") if intro else None
    # "<h4>Pearl Jam at Fenway Park<br/>September 15 & 17, 2024</h4>": title, then date line.
    head_lines = list(heading.stripped_strings) if heading else []
    paras = [p.get_text(" ", strip=True) for p in intro.find_all(["p", "li"])] if intro else []
    paras = [p for p in paras if p]

    # The event banner, not the concert-series sponsor logo.
    banner = next((img["alt"] for img in soup.select(".p-image img[alt]")
                   if re.search(r"\b20\d\d\b|fenway park|special guest", img["alt"], re.I)
                   and "concert series" not in img["alt"].lower()), "")

    kept = [banner] if banner else []
    for para in paras:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        clean = " ".join(s for s in sentences if not LOGISTICS.search(s) and not FILLER.search(s.strip()))
        if len(clean) > 20:
            kept.append(clean)
    return {
        "page_title": head_lines[0] if head_lines else (soup.h1.get_text(" ", strip=True) if soup.h1 else ""),
        "page_date_text": " ".join(head_lines[1:]),
        "description_raw": "\n".join(([banner] if banner else []) + paras),
        "description": "\n".join(kept),
        "page_says_cancelled": bool(re.search(r"cancel+ed|postponed", " ".join(head_lines), re.I)),
    }


def fetch_press():
    """Vanyaland posts titled with "Fenway Park" (not MGM roundups) in the window (cached)."""
    if not PRESS_CACHE.exists():
        after = (date.fromisoformat(WINDOW_START) - timedelta(days=270)).isoformat()
        posts, page = [], 1
        while True:
            time.sleep(1.0)
            resp = requests.get(VANYALAND_API, timeout=60, headers={"User-Agent": "DS5500-capstone-research"}, params={
                "search": "Fenway Park", "per_page": 100, "page": page,
                "after": f"{after}T00:00:00", "before": f"{WINDOW_END}T23:59:59",
                "_fields": "id,date,link,title,content"})
            if resp.status_code == 400:  # past the last page
                break
            resp.raise_for_status()
            posts += resp.json()
            if page >= int(resp.headers.get("X-WP-TotalPages", 1)):
                break
            page += 1
        PRESS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PRESS_CACHE.write_text(json.dumps(posts))
    posts = json.loads(PRESS_CACHE.read_text())
    return [p for p in posts if "fenway park" in p["title"]["rendered"].lower()
            and "mgm" not in p["title"]["rendered"].lower()]


def press_text(row, posts):
    """Pre-event Vanyaland blocks naming this show's date and artist, earliest first."""
    names = [row.headliner] + (row.supporting_artists.split("; ") if isinstance(row.supporting_artists, str) else [])
    keys = [alnum(n.replace("&", " and ")) for n in names] + [alnum(n) for n in names]
    keys = [k for k in keys if len(k) >= 3]
    found = []
    for post in posts:
        published = date.fromisoformat(post["date"][:10])
        if post["date"][:10] >= row.date_start:
            continue
        for header, paras in split_blocks(post):
            text = clean_press(paras)
            if (text and date.fromisoformat(row.date_start) in show_dates(header, published)
                    and any(k in alnum(header) for k in keys)):
                found.append((post["date"], header, text, post["link"]))
    if not found:
        return None
    found.sort()
    return {"status": "ok", "page_title": found[0][1], "description": "\n".join(dict.fromkeys(f[2] for f in found)),
            "description_raw": None, "description_timestamp": found[-1][0],
            "description_url": " ".join(dict.fromkeys(f[3] for f in found)), "text_origin": "vanyaland"}


def process_event(row, index):
    names = ([row.headliner] + (row.supporting_artists.split("; ") if isinstance(row.supporting_artists, str) else [])
             + ([row.tour_name] if isinstance(row.tour_name, str) else []))
    event_day = date.fromisoformat(row.date_start)
    cutoff = row.date_start.replace("-", "")
    out = {"event_id": row.event_id, "status": "no_match"}

    for slug in candidate_slugs(names, index)[:3]:
        before = [(ts, url) for ts, url in index[slug] if ts[:8] < cutoff]
        if not before:
            out.update(status="no_pre_event_snapshot", match_slug=slug)
            continue
        # Latest pre-event snapshot whose date line is about this show (pages are reused
        # across tours, and an old snapshot can predate the announcement).
        for ts, url in reversed(before):
            parsed = parse_page(fetch_snapshot(slug, ts, url))
            if parsed["page_date_text"] and date_matches(parsed["page_date_text"], event_day):
                break
        out.update(match_slug=slug, description_timestamp=f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}Z",
                   description_url=f"https://web.archive.org/web/{ts}/{url}", **parsed)
        if not (parsed["page_date_text"] and date_matches(parsed["page_date_text"], event_day)):
            out["status"] = "date_mismatch"
            continue
        out["status"] = "ok" if parsed["description"] else "empty_description"
        if out["status"] == "ok":
            break
    return out


def main():
    events = pd.read_csv(EVENTS)
    events = events[(events.venue_key == VENUE_KEY) & ~events.likely_non_concert]
    index = load_index()
    posts = fetch_press()
    print(f"{VENUE_KEY}: {len(events)} events, {len(index)} archived page slugs, {len(posts)} Fenway Park press posts")

    rows = []
    for i, row in enumerate(events.itertuples(), 1):
        out = process_event(row, index)
        if out["status"] == "ok":
            out["text_origin"] = "venue_archive"
        else:
            press = press_text(row, posts)
            if press:
                out = {"event_id": row.event_id, "venue_page_status": out["status"], **press}
        rows.append(out)
        if i % 10 == 0:
            print(f"  {i}/{len(events)} done", flush=True)

    df = pd.DataFrame(rows)
    df["description_source"] = df.text_origin.where(df.status == "ok")
    df = df.drop(columns="text_origin")
    df["description_length"] = df.description.str.len().where(df.status == "ok")
    df.to_csv(OUT, index=False)

    print("\nStatus counts:")
    print(df.status.value_counts().to_string())
    ok = df[df.status == "ok"]
    print(f"\nReal text: {len(ok)}/{len(df)} ({len(ok) / len(df):.0%}); "
          f"median length {ok.description_length.median():.0f} chars")
    missing = df[df.status != "ok"]
    if len(missing):
        print("No text:", ", ".join(f"{r.event_id} ({r.status})" for r in missing.itertuples()))
    if df.page_says_cancelled.fillna(False).any():
        print("Pages marked cancelled/postponed:", ", ".join(df[df.page_says_cancelled.fillna(False)].event_id))
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
