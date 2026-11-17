"""Collect pre-event Reddit chatter about each show (social "buzz" text, not a description).

Suggested in the midterm presentation for events with no recovered description. Reddit's own
API cannot search by date, so this uses the Arctic Shift archive of Reddit
(https://arctic-shift.photon-reddit.com, free, no key, no uptime guarantee). The archive's
full-text search times out under load, so nothing here depends on it: every post in the
subreddits below is downloaded month by month and matched locally.

For every event, within LOOKBACK_DAYS before the event day:
  - local subs (r/boston, r/bostonmusic): posts naming the headliner, kept only if they also
    mention a show/ticket/venue word (artist names like "Sting" or "Yes" are words)
  - r/concerts: posts naming the headliner and Boston or the venue
  - every comment in a local-sub thread whose title names the headliner ("anyone going tonight?")
  - the artist's own subreddit (guessed as the alphanumeric headliner name): posts mentioning
    Boston or the venue and a show/ticket word
Comments outside those threads are not searched (r/boston has millions).

Leakage: only items created strictly before midnight (Boston time) of the event day, the same
rule as the Wayback and Vanyaland text. Usernames are never stored.

Terms: Reddit content is used for non-commercial research only. reddit_ids are kept so the set
can be rebuilt (and deleted posts dropped) from the archive.

Raw responses are cached under data/raw/reddit/. Failed requests are not cached, so a rerun
retries only what is missing.

Usage: python events/reddit_text.py [--missing-only] [--limit N]
Output: data/interim/social_reddit.csv
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venues import WINDOW_END, WINDOW_START  # noqa: E402
from wayback_text import alnum  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "interim" / "events_setlistfm.csv"
PROCESSED = ROOT / "data" / "processed" / "nonsports_events.csv"
CACHE = ROOT / "data" / "raw" / "reddit"
OUT = ROOT / "data" / "interim" / "social_reddit.csv"
API = "https://arctic-shift.photon-reddit.com/api"
BOSTON = ZoneInfo("America/New_York")

LOOKBACK_DAYS = 90
LOCAL_SUBS = ["boston", "bostonmusic"]
GLOBAL_SUBS = ["concerts"]
POST_FIELDS = ["id", "created_utc", "subreddit", "title", "selftext", "num_comments"]
MAX_PAGES = 100         # x 100 items per request; a month of r/boston is ~15 pages
ARTIST_SUB_PAGES = 10   # big fandom subs (r/taylorswift) are capped, oldest posts first
MAX_TEXT_CHARS = 10000  # per event, earliest items kept first
MIN_ITEM_CHARS = 20
LONG_POST = 1500        # longer post bodies keep only the paragraphs about the show
RETRIES = 4             # waits 5, 10, 20, 40 s

VENUE_WORDS = {
    "td_garden": r"td garden|the garden|north station",
    "wang_theatre": r"wang|boch",
    # Fans call MGM "Fenway"; "music hall" alone would match Radio City / Brighton Music Hall.
    "mgm_music_hall": r"mgm|fenway(?! park)",
    "fenway_park": r"fenway park",
}
# Unambiguous names, used to spot a post about the artist's show at another of our venues.
VENUE_NAMES = {
    "td_garden": r"td garden",
    "wang_theatre": r"wang|boch",
    "mgm_music_hall": r"mgm|music hall at fenway",
    "fenway_park": r"fenway park",
}
# Posts naming one of these (and not the event's venue) are about another show by the artist.
OTHER_VENUES = (r"radio city|brighton music hall|house of blues|paradise rock|roadrunner|big night live|"
                r"leader bank|cisco|rockland trust|xfinity center|boston calling|agganis|royale|"
                r"the sinclair|orpheum|tanglewood|gillette")
SHOW_WORDS = r"concert|show|tour|ticket|gig|setlist|opener|opening act|tonight|perform|presale|on ?sale"
URL = re.compile(r"\[([^\]]*)\]\([^)]*\)|https?://\S+")
GONE = {"[deleted]", "[removed]", ""}


class ArchiveError(Exception):
    """A request still failing after RETRIES."""


def fetch(endpoint, params, max_pages=MAX_PAGES):
    """All pages of one Arctic Shift listing (oldest first), cached on success."""
    key = hashlib.sha1(json.dumps([endpoint, params, max_pages], sort_keys=True).encode()).hexdigest()
    cache_file = CACHE / "queries" / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    items, after = [], params["after"]
    for _ in range(max_pages):
        for attempt in range(RETRIES):
            time.sleep(1.0)
            try:
                resp = requests.get(f"{API}/{endpoint}", timeout=90,
                                    headers={"User-Agent": "DS5500-capstone-research"},
                                    params={**params, "after": after, "sort": "asc", "limit": 100})
                body = resp.json()
            except (requests.RequestException, ValueError):
                resp, body = None, {"error": "network"}
            if resp is not None and resp.status_code == 200 and not body.get("error"):
                break
            # 429 = rate limit; 422 "Timeout. Maybe slow down a bit" = the archive's query timed out.
            time.sleep(5 * 2 ** attempt)
        else:
            raise ArchiveError(f"{endpoint} {params}: {body.get('error')}")
        batch = body.get("data") or []
        items += batch
        if len(batch) < 100:
            break
        after = batch[-1]["created_utc"]  # same-second items reappear; deduped below
    items = list({i["id"]: i for i in items}.values())
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(items))
    return items


def slim(post):
    return {k: post.get(k) for k in POST_FIELDS}


def months():
    first = date.fromisoformat(WINDOW_START) - timedelta(days=LOOKBACK_DAYS)
    m, last = first.replace(day=1), date.fromisoformat(WINDOW_END)
    while m <= last:
        nxt = (m + timedelta(days=32)).replace(day=1)
        yield m, nxt
        m = nxt


def download_sub(sub):
    """Every post in a subreddit over the window, one cached file per month.

    Returns (posts DataFrame, list of months that failed).
    """
    posts, failed = [], []
    for start, end in months():
        cache_file = CACHE / "posts" / sub / f"{start:%Y-%m}.json"
        if cache_file.exists():
            posts += json.loads(cache_file.read_text())
            continue
        try:
            batch = [slim(p) for p in fetch("posts/search", {"subreddit": sub, "after": start.isoformat(),
                                                             "before": end.isoformat()})]
        except ArchiveError:
            failed.append(f"{start:%Y-%m}")
            continue
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(batch))
        posts += batch
        print(f"  r/{sub} {start:%Y-%m}: {len(batch)} posts", flush=True)
    df = pd.DataFrame(posts, columns=POST_FIELDS)
    df["text"] = [post_text(p) for p in df.itertuples()]
    return df.sort_values("created_utc").reset_index(drop=True), failed


def clean(text):
    text = URL.sub(lambda m: m.group(1) or "", str(text or "")).strip()
    return "" if text in GONE else re.sub(r"\s+", " ", text)


def post_text(p):
    return clean(f"{p.title or ''}. {clean(p.selftext)}")


def focus(title, selftext, pattern, venue=None):
    """Post text, cut to the paragraphs matching pattern (and venue) when the body is long.

    Long bodies are mostly r/boston's weekly "things to do" lists, where one line is the show
    and the rest is every other event in town ("James Taylor @ Koussevitzky Music Shed" is a
    different show, hence the venue check). Returns "" if no paragraph is about the show and
    the title is not either.
    """
    if len(str(selftext or "")) <= LONG_POST:
        return clean(f"{title or ''}. {clean(selftext)}")
    paras = [clean(p) for p in re.split(r"\n\s*\n", str(selftext))]
    kept = [p for p in paras if mentioned(pattern, p) and (venue is None or mentioned(venue, p))]
    if not kept and not mentioned(pattern, title):
        return ""
    return clean(f"{title or ''}. " + " ".join(dict.fromkeys(kept)))


def mentioned(pattern, text):
    return re.search(pattern, str(text), re.I) is not None


def name_pattern(name):
    """Any co-headliner ("Tina Fey & Amy Poehler"), safe for names like "A$AP Rocky" or "bbno$"."""
    parts = [p.strip() for p in re.split(r"\s+(?:&|and|with)\s+", str(name)) if len(p.strip()) >= 3]
    words = [r"\s*".join(re.escape(w) for w in p.split()) for p in parts or [str(name)]]
    return r"(?<!\w)(?:" + "|".join(words) + r")(?!\w)"


def window(ev):
    """(after, before) as Unix seconds: LOOKBACK_DAYS before the event day up to its midnight."""
    day = datetime.fromisoformat(ev.date_start).replace(tzinfo=BOSTON)
    return int((day - timedelta(days=LOOKBACK_DAYS)).timestamp()), int(day.timestamp())


def collect(ev, subs):
    after, before = window(ev)
    name, venue = name_pattern(ev.headliner), VENUE_WORDS[ev.venue_key]
    local_ok, global_ok = rf"{SHOW_WORDS}|{venue}", rf"\bboston\b|{venue}"
    found = []  # (created_utc, kind, id, subreddit, text)
    row = {"event_id": ev.event_id, "lookback_days": LOOKBACK_DAYS}

    for sub, df in subs.items():
        in_window = df[(df.created_utc >= after) & (df.created_utc < before)]
        named = in_window[in_window.text.str.contains(name, case=False, regex=True)]
        keep = named.text.str.contains(local_ok if sub in LOCAL_SUBS else global_ok, case=False, regex=True)
        for p in named[keep].itertuples():
            found.append((p.created_utc, "post", p.id, sub, focus(p.title, p.selftext, name, venue)))
            if sub in LOCAL_SUBS and p.num_comments and mentioned(name, p.title):
                # A thread about the show: take every comment made before the cutoff.
                try:
                    comments = fetch("comments/search", {"link_id": p.id, "after": after, "before": before})
                except ArchiveError:
                    row["missing"] = "thread_comments"
                    comments = []
                found += [(c["created_utc"], "comment", c["id"], sub, clean(c.get("body"))) for c in comments]

    artist_sub = alnum(ev.headliner)
    row["artist_sub"] = artist_sub if 3 <= len(artist_sub) <= 21 else None  # Reddit's name limits
    if row["artist_sub"] and artist_sub not in subs:
        try:
            for p in fetch("posts/search", {"subreddit": artist_sub, "after": after, "before": before},
                           max_pages=ARTIST_SUB_PAGES):
                text = clean(f"{p.get('title', '')}. {clean(p.get('selftext'))}")
                if mentioned(global_ok, text) and mentioned(SHOW_WORDS, text):
                    found.append((p["created_utc"], "post", p["id"], p.get("subreddit", artist_sub),
                                  focus(p.get("title"), p.get("selftext"), global_ok)))
        except ArchiveError:
            row["missing"] = "; ".join(filter(None, [row.get("missing"), "artist_sub"]))

    # Drop posts about the artist's show at another venue (comments are judged by their thread).
    elsewhere = "|".join([OTHER_VENUES] + [w for k, w in VENUE_NAMES.items() if k != ev.venue_key])
    found = [i for i in found if i[1] == "comment" or not mentioned(elsewhere, i[4]) or mentioned(venue, i[4])]
    # Same item can come from several routes; keep real text, earliest first.
    items = sorted({i[2]: i for i in found if len(i[4]) >= MIN_ITEM_CHARS and i[0] < before}.values())
    if not items:
        return {**row, "status": "no_reddit_text", "n_posts": 0, "n_comments": 0}
    text, kept = "", []
    for item in items:
        if len(text) + len(item[4]) > MAX_TEXT_CHARS and kept:
            break
        text += ("\n" if text else "") + item[4]
        kept.append(item)
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")
    return {**row, "status": "ok", "social_text": text, "social_text_length": len(text),
            "n_posts": sum(i[1] == "post" for i in items),
            "n_comments": sum(i[1] == "comment" for i in items),
            "subreddits": "; ".join(sorted({i[3].lower() for i in items})),
            "first_item_utc": iso(items[0][0]), "last_item_utc": iso(kept[-1][0]),
            "truncated": len(kept) < len(items),
            "reddit_ids": " ".join(("t3_" if i[1] == "post" else "t1_") + i[2] for i in items)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing-only", action="store_true",
                    help="only events with no real description in the processed table")
    ap.add_argument("--limit", type=int, help="first N events (for testing)")
    args = ap.parse_args()

    events = pd.read_csv(EVENTS)
    events = events[~events.likely_non_concert]
    if args.missing_only:
        has_text = pd.read_csv(PROCESSED).set_index("event_id").has_real_text
        events = events[~events.event_id.map(has_text).fillna(False).astype(bool)]
    if args.limit:
        events = events.head(args.limit)

    print("Downloading subreddit posts (cached per month)")
    subs, gaps = {}, {}
    for sub in LOCAL_SUBS + GLOBAL_SUBS:
        df, failed = download_sub(sub)
        subs[sub] = df
        if failed:
            gaps[sub] = failed
        print(f"r/{sub}: {len(df)} posts" + (f", {len(failed)} months failed" if failed else ""), flush=True)

    print(f"\nMatching {len(events)} events, lookback {LOOKBACK_DAYS} days")
    rows = []
    for i, ev in enumerate(events.itertuples(), 1):
        row = collect(ev, subs)
        after, before = window(ev)
        span = {f"{d:%Y-%m}" for d in pd.date_range(pd.Timestamp(after, unit="s"), pd.Timestamp(before, unit="s"))}
        lost = [f"r/{s}" for s, failed in gaps.items() if span & set(failed)]
        if lost:
            row["missing"] = "; ".join(filter(None, [row.get("missing"), *lost]))
        rows.append(row)
        if i % 25 == 0 or i == len(events):
            ok = sum(r["status"] == "ok" for r in rows)
            print(f"  {i}/{len(events)} done, {ok} with Reddit text", flush=True)

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    venue = df.event_id.map(events.set_index("event_id").venue_name)
    print("\nEvents with Reddit text, by venue:")
    print(df.assign(venue=venue, ok=df.status == "ok").groupby("venue").ok.agg(["sum", "count", "mean"])
          .rename(columns={"sum": "with_text", "count": "events", "mean": "share"}).to_string())
    ok = df[df.status == "ok"]
    if len(ok):
        print(f"\nMedian {ok.social_text_length.median():.0f} chars, {ok.n_posts.median():.0f} posts, "
              f"{ok.n_comments.median():.0f} comments per covered event")
    if "missing" in df and df.missing.notna().any():
        print(f"{df.missing.notna().sum()} events have gaps (column 'missing'); rerun to fill them in")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
