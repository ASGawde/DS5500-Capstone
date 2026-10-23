"""Recover pre-event description text for MGM Music Hall shows from Vanyaland articles.

MGM's own pages (Crossroads Presents / Live Nation) carry only door times and bag policy,
so the descriptive text for MGM shows lives in Boston music press. Vanyaland runs weekly
"On Sale: MGM Music Hall at Fenway" roundups plus show previews, all with publish dates.

Posts are split into one block per show at each show heading:
  - "<h3>Kneecap, October 11</h3>"                        (On Sale roundups)
  - "ARTIST + OPENER :: Thursday, March 13 at MGM ... :: 6:30 p.m., all ages, $39.50 to $79.50"
Each block is matched to an event by date (one event per date at MGM) and confirmed by
artist name. Only posts published strictly before the event day are used (same rule as the
Wayback snapshots: forecasts are made the day before).

Posts come from the public WordPress API and are cached under data/raw/vanyaland/.

Usage: python events/vanyaland_text.py
Output: data/interim/text_vanyaland_mgm_music_hall.csv
"""
import html
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
from venues import WINDOW_END, WINDOW_START  # noqa: E402
from wayback_text import LOGISTICS, MONTHS, alnum  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "interim" / "events_setlistfm.csv"
CACHE = ROOT / "data" / "raw" / "vanyaland"
OUT = ROOT / "data" / "interim" / "text_vanyaland_mgm_music_hall.csv"
API = "https://vanyaland.com/wp-json/wp/v2/posts"
VENUE_KEY = "mgm_music_hall"

MONTH_RE = "|".join(m.capitalize() for m in MONTHS)
# "March 15", "March 15-17", "March 15 & 16", "February 15 to Saturday, February 18"
DATE_RE = re.compile(rf"({MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?"
                     rf"(?:\s*(?:-|–|&|and|to|through)\s*(?:[A-Z][a-z]+,\s*)?(?:({MONTH_RE})\s+)?(\d{{1,2}}))?")
PRICE_RE = re.compile(r"\$\s?([\d.]+)(?:\s*(?:to|-|–)\s*\$\s?([\d.]+))?")
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", re.I)


def fetch_posts():
    """All Vanyaland posts mentioning MGM Music Hall in the window (cached)."""
    cache_file = CACHE / "posts_mgm_music_hall.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    after = (date.fromisoformat(WINDOW_START) - timedelta(days=270)).isoformat()  # on-sale runs months ahead
    posts, page = [], 1
    while True:
        time.sleep(1.0)
        resp = requests.get(API, timeout=60, headers={"User-Agent": "DS5500-capstone-research"}, params={
            "search": "MGM Music Hall", "per_page": 100, "page": page,
            "after": f"{after}T00:00:00", "before": f"{WINDOW_END}T23:59:59",
            "_fields": "id,date,link,title,content"})
        if resp.status_code == 400:  # past the last page
            break
        resp.raise_for_status()
        batch = resp.json()
        posts += batch
        if page >= int(resp.headers.get("X-WP-TotalPages", 1)):
            break
        page += 1
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(posts))
    return posts


def show_dates(header, published):
    """Every date a header names, with the year inferred from the publish date."""
    out = []
    for m in DATE_RE.finditer(header):
        month = MONTHS.index(m.group(1).lower()) + 1
        start = int(m.group(2))
        end_month = MONTHS.index(m.group(3).lower()) + 1 if m.group(3) else month
        end = int(m.group(4)) if m.group(4) else start
        # Day lists: "September 2, 3, and 4" -> also the 3rd and 4th.
        tail = re.match(r"(?:\s*,?\s*(?:and\s+|&\s*)?\d{1,2}\b(?!:))+", header[m.end():])
        extra = [int(x) for x in re.findall(r"\d{1,2}", tail.group(0))] if tail and not m.group(4) else []
        if extra and all(1 <= x <= 31 for x in extra):
            end = max([start] + extra)
        for year in (published.year, published.year + 1):
            try:
                first, last = date(year, month, start), date(year if end_month >= month else year + 1, end_month, end)
            except ValueError:
                break
            if first >= published - timedelta(days=3):  # shows are previewed before they happen
                out += [first + timedelta(days=i) for i in range((last - first).days + 1) if i < 10]
                break
    return out


def split_blocks(post):
    """(header, paragraphs) per show in a post.

    Headings (<h2>-<h4>) start a block: "Kneecap, October 11" in roundups, "Music : Morrissey at
    MGM Music Hall at Fenway" in weekend picks. "ARTIST :: date at venue :: time, price" lines are
    footers carrying the date/venue/price of the block they close, so they are appended to that
    block's header. A preview post with no heading is one block whose footer is the :: line.
    """
    soup = BeautifulSoup(post["content"]["rendered"], "html.parser")
    blocks, header, paras = [], "", []
    for el in soup.find_all(["h2", "h3", "h4", "p"]):
        text = html.unescape(el.get_text(" ", strip=True))
        if not text:
            continue
        if el.name in ("h2", "h3", "h4"):
            if header or paras:
                blocks.append((header, paras))
            header, paras = text, []
        elif " :: " in text and DATE_RE.search(text):
            header = f"{header} || {text}" if header else text
        else:
            paras.append(text)
    if header:
        blocks.append((header, paras))
    return [(h, p) for h, p in blocks if h]


# Roundup filler left once the on-sale sentence is removed ("Performing live at MGM ... local time.")
FILLER = re.compile(r"^performing live at|local time\.?$|read our exclusive|^buy tickets|^editor", re.I)
MIN_TEXT = 100  # characters of real description; shorter blocks count as no text


def clean(paras):
    kept = []
    for para in paras:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        text = " ".join(s for s in sentences if not LOGISTICS.search(s) and not FILLER.search(s.strip()))
        if len(text) > 20:
            kept.append(text)
    text = "\n".join(kept)
    return text if len(text) >= MIN_TEXT else ""


def parse_header_extras(header):
    price = PRICE_RE.search(header)
    tm = TIME_RE.search(header.split("::")[-1]) if "::" in header else None
    listed_time = None
    if tm:
        hour = int(tm.group(1)) % 12 + (12 if tm.group(3).lower() == "p" else 0)
        listed_time = f"{hour:02d}:{tm.group(2) or '00'}"
    return {
        "ticket_price_min": float(price.group(1)) if price else None,
        "ticket_price_max": float(price.group(2)) if price and price.group(2) else None,
        "listed_time": listed_time,
    }


def collect_blocks(posts):
    """One row per (show block, date) that is about MGM."""
    rows = []
    for post in posts:
        published = date.fromisoformat(post["date"][:10])
        slug = post["link"].rstrip("/").split("/")[-1]
        mgm_roundup = slug.startswith("on-sale-mgm-music-hall")
        for header, paras in split_blocks(post):
            if not (mgm_roundup or "MGM" in header):
                continue  # block about another venue in a multi-venue post
            text = clean(paras)
            for d in show_dates(header, published):
                rows.append({"show_date": d.isoformat(), "published": post["date"], "header": header,
                             "text": text, "post_url": post["link"],
                             "post_type": "on_sale" if slug.startswith("on-sale") else
                                          "show_tonight" if "this-show-is-tonight" in slug else
                                          "weekend_picks" if "v3-weekend" in slug else "other",
                             **parse_header_extras(header)})
    return pd.DataFrame(rows)


def main():
    posts = fetch_posts()
    blocks = collect_blocks(posts)
    events = pd.read_csv(EVENTS)
    events = events[(events.venue_key == VENUE_KEY) & ~events.likely_non_concert]
    print(f"{len(posts)} posts -> {len(blocks)} MGM show blocks; {len(events)} MGM events")

    out, same_day_only = [], 0
    for ev in events.itertuples():
        names = [ev.headliner] + (ev.supporting_artists.split("; ") if isinstance(ev.supporting_artists, str) else [])
        keys = [alnum(n) for n in names if len(alnum(n)) >= 3]
        # Every block is already about MGM and MGM hosts one event per date, so the date is the key.
        # The artist check is recorded for auditing (festivals like "Totally Tubular" won't name
        # the setlist.fm headliner).
        cand = blocks[blocks.show_date == ev.date_start].copy()
        cand["artist_in_header"] = [any(k in alnum(h) for k in keys) for h in cand.header]
        # Date-only matches only for single-show headings; merged "||" headings can mix shows.
        cand = cand[cand.artist_in_header | ~cand.header.str.contains(r"\|\|", regex=True)]
        before = cand[cand.published.str[:10] < ev.date_start]
        with_text = before[before.text.str.len() > 0]
        row = {"event_id": ev.event_id}
        if with_text.empty:
            row["status"] = "no_pre_event_text" if not cand.empty else "no_match"
            same_day_only += int(not cand.empty and (cand.text.str.len() > 0).any() and before.empty)
        else:
            # Combine every pre-event block (roundup + previews), earliest first, no duplicates.
            with_text = with_text.sort_values("published")
            texts = list(dict.fromkeys(with_text.text))
            first = with_text.iloc[0]
            row.update(status="ok", description="\n".join(texts),
                       description_timestamp=with_text.published.max(),
                       description_url=" ".join(dict.fromkeys(with_text.post_url)),
                       n_articles=with_text.post_url.nunique(),
                       post_types="; ".join(sorted(set(with_text.post_type))),
                       ticket_price_min=with_text.ticket_price_min.min(),
                       ticket_price_max=with_text.ticket_price_max.max(),
                       listed_time=with_text.listed_time.dropna().iloc[0] if with_text.listed_time.notna().any() else None,
                       header=first.header,
                       match_type="artist+date" if with_text.artist_in_header.any() else "date_only")
        out.append(row)

    df = pd.DataFrame(out)
    df["description_source"] = df.status.map(lambda s: "vanyaland" if s == "ok" else None)
    df["description_length"] = df.description.str.len().where(df.status == "ok") if "description" in df else None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    print("\nStatus counts:")
    print(df.status.value_counts().to_string())
    ok = df[df.status == "ok"]
    print(f"\nReal text: {len(ok)}/{len(df)} ({len(ok) / len(df):.0%}); median length "
          f"{ok.description_length.median():.0f} chars; price found {ok.ticket_price_min.notna().mean():.0%}")
    print(f"Excluded same-day-only text (would add if same-day forecasts are allowed): {same_day_only}")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
