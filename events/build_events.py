"""Merge the event list and recovered text into the final non-sports event table.

Inputs (data/interim/):
  events_setlistfm.csv                 event list (setlistfm_collect.py)
  text_wayback_td_garden.csv           venue-page text (wayback_text.py td_garden)
  text_wayback_wang_theatre.csv        venue-page text (wayback_text.py wang_theatre)
  text_vanyaland_mgm_music_hall.csv    press text (vanyaland_text.py)

Output:
  data/processed/nonsports_events.csv  one row per venue-date, shared schema first
  data/processed/coverage_report.csv   per-venue coverage of text and times

Text priority: real pre-event text (venue_archive or vanyaland), else a template built only
from structured fields (description_source = "template").

Times: all local Boston time (America/New_York). Start time comes from the best available
source, recorded in time_start_source; end time is always an assumption (duration_assumed).

Usage: python events/build_events.py
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venues import VENUES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

TEXT_FILES = {
    "td_garden": INTERIM / "text_wayback_td_garden.csv",
    "wang_theatre": INTERIM / "text_wayback_wang_theatre.csv",
    "mgm_music_hall": INTERIM / "text_vanyaland_mgm_music_hall.csv",
}

# Documented fallback assumptions (no source publishes end times).
DEFAULT_START = {"td_garden": "19:30", "wang_theatre": "19:30", "mgm_music_hall": "20:00"}
DOORS_TO_SHOW_MIN = 60
DURATION_HOURS = {"concert": 3.0, "comedy": 2.0, "dance_theater": 2.5}
ARENA_CONCERT_HOURS = 3.5  # TD Garden concerts usually run two openers before the headliner

# Phrases that reveal how popular an event is. Legitimate (public before the show), but flagged
# so the team can test whether text helps beyond them.
DEMAND = re.compile(
    r"sold[- ]out|overwhelming demand|(due to|by) (high|popular|fan) demand|"
    r"(second|third|fourth|additional|another|new|extra) (show|date|night|performance)s?\b|"
    r"added (a )?(second |third |new )?(show|date|night)|upgraded to", re.I)
# Matched against the title and opening lines only, where a page says what the event *is*;
# full bios mention "musical", "Broadway" or an opening comedian far too often.
COMEDY = re.compile(r"\bcomedian|stand[- ]?up|\bcomedy\b(?! rock)", re.I)
DANCE_THEATER = re.compile(r"\bballet\b|dance troupe|riverdance|irish dance", re.I)
LEAD_CHARS = 200

LISTED_TIME_SOURCES = ["venue_page_schema", "do617_listing", "press_listing"]

SHARED_SCHEMA = ["event_id", "event_name", "category", "venue_name", "venue_lat", "venue_lon",
                 "date_start", "date_end", "time_start", "time_end_or_duration", "description", "source_url"]


def load_text():
    frames = []
    for venue_key, path in TEXT_FILES.items():
        if not path.exists():
            sys.exit(f"Missing {path.relative_to(ROOT)}; run the text extractor for {venue_key} first.")
        df = pd.read_csv(path)
        frames.append(df.rename(columns={"status": "text_status", "header": "page_title_or_header"}))
    text = pd.concat(frames, ignore_index=True)
    if "page_title" in text:
        text["page_title_or_header"] = text.page_title.fillna(text.get("page_title_or_header"))
    return text


def template_description(r):
    """Built only from structured fields, so it carries no information beyond them."""
    text = f"{r.headliner} performs at {r.venue_name}."
    if isinstance(r.tour_name, str):  # tour names vary ("The ... Tour", "Mother Road"), so label, don't inline
        text += f" Tour: {r.tour_name}."
    if isinstance(r.supporting_artists, str):
        text += f" With {r.supporting_artists.replace('; ', ', ')}."
    return text


def classify(r):
    if r.description_source == "template":
        return "concert"  # setlist.fm only lists music
    body = r.description_raw if isinstance(r.description_raw, str) else r.description
    text = f"{r.page_title_or_header if isinstance(r.page_title_or_header, str) else ''} {body[:LEAD_CHARS]}"
    if COMEDY.search(text):
        return "comedy"
    if DANCE_THEATER.search(text):
        return "dance_theater"
    return "concert"


def add_minutes(hhmm, minutes):
    t = datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def pick_start(r):
    """(time, source). Priority: venue JSON-LD start > Do617 listing > press-listed time >
    doors + 1h > venue default."""
    if isinstance(r.show_start_time, str):
        return r.show_start_time, "venue_page_schema"
    if isinstance(getattr(r, "do617_time", None), str):
        return r.do617_time, "do617_listing"
    if isinstance(r.listed_time, str):
        return r.listed_time, "press_listing"
    if isinstance(r.doors_time, str):
        return add_minutes(r.doors_time, DOORS_TO_SHOW_MIN), "doors_plus_1h"
    return DEFAULT_START[r.venue_key], "venue_default"


def main():
    events = pd.read_csv(INTERIM / "events_setlistfm.csv")
    n_anthem = int(events.likely_non_concert.sum())
    events = events[~events.likely_non_concert].copy()

    text = load_text()
    df = events.merge(text, on="event_id", how="left", validate="one_to_one")
    times_file = INTERIM / "times_do617.csv"
    if times_file.exists():
        df = df.merge(pd.read_csv(times_file)[["event_id", "do617_time", "do617_url"]],
                      on="event_id", how="left", validate="one_to_one")
    else:
        print("Note: times_do617.csv not found; run do617_times.py for MGM/Wang start times.")

    real = df.text_status.eq("ok") & df.description.notna()
    df["description_source"] = df.description_source.where(real, "template")
    df.loc[~real, "description"] = df[~real].apply(template_description, axis=1)
    for col in ("description_timestamp", "description_url", "description_raw"):
        df.loc[~real, col] = None
    df["description_length"] = df.description.str.len()
    df["has_real_text"] = real

    df["category"] = df.apply(classify, axis=1)
    df["event_title"] = df.page_title_or_header.where(real, df.event_name)

    starts = df.apply(pick_start, axis=1, result_type="expand")
    df["time_start"], df["time_start_source"] = starts[0], starts[1]
    df["time_assumed"] = df.time_start_source.eq("venue_default")
    df["duration_hours"] = [ARENA_CONCERT_HOURS if (v == "td_garden" and c == "concert") else DURATION_HOURS[c]
                            for v, c in zip(df.venue_key, df.category)]
    df["duration_assumed"] = True
    start_dt = pd.to_datetime(df.date_start + " " + df.time_start)
    end_dt = start_dt + pd.to_timedelta(df.duration_hours, unit="h")
    df["start_datetime"] = start_dt.dt.strftime("%Y-%m-%dT%H:%M")
    df["end_datetime"] = end_dt.dt.strftime("%Y-%m-%dT%H:%M")
    df["time_end_or_duration"] = end_dt.dt.strftime("%H:%M")

    df["demand_language"] = real & df.description.str.contains(DEMAND, na=False)
    df["possibly_cancelled"] = df.page_says_cancelled.fillna(False).astype(bool) if "page_says_cancelled" in df else False
    df["onsale_date"] = df.get("onsale_date")
    df["days_onsale_to_event"] = (pd.to_datetime(df.date_start) - pd.to_datetime(df.onsale_date)).dt.days

    # ---- checks ----
    assert df.event_id.is_unique, "duplicate event_id"
    leak = df[real & (df.description_timestamp.str[:10] >= df.date_start)]
    assert leak.empty, f"text dated on/after the event: {leak.event_id.tolist()}"
    for col in ["time_start", "venue_lat", "venue_lon", "description", "date_start"]:
        assert df[col].notna().all(), f"missing {col}"
    assert set(df.venue_key) <= set(VENUES)

    columns = SHARED_SCHEMA + [
        "event_title", "headliner", "supporting_artists", "tour_name", "artist_mbid",
        "description_source", "has_real_text", "description_timestamp", "description_url", "description_length",
        "description_raw", "demand_language",
        "start_datetime", "end_datetime", "time_start_source", "time_assumed", "duration_hours", "duration_assumed",
        "do617_url",
        "onsale_date", "days_onsale_to_event", "ticket_price_min", "ticket_price_max", "possibly_cancelled",
        "venue_key", "zone_id", "venue_capacity", "indoor_or_outdoor", "text_status",
    ]
    out = df[[c for c in columns if c in df]].sort_values(["date_start", "venue_key"])
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED / "nonsports_events.csv", index=False)

    report = out.groupby("venue_name").agg(
        events=("event_id", "size"),
        real_text=("has_real_text", "sum"),
        real_text_pct=("has_real_text", "mean"),
        median_text_chars=("description_length", lambda s: s[out.loc[s.index, "has_real_text"]].median()),
        demand_language=("demand_language", "sum"),
        exact_or_listed_time_pct=("time_start_source", lambda s: s.isin(LISTED_TIME_SOURCES).mean()),
        time_assumed_pct=("time_assumed", "mean"),
        onsale_date_pct=("onsale_date", lambda s: s.notna().mean()),
        price_pct=("ticket_price_min", lambda s: s.notna().mean()),
        possibly_cancelled=("possibly_cancelled", "sum"),
    )
    report.loc["ALL"] = [len(out), out.has_real_text.sum(), out.has_real_text.mean(),
                         out[out.has_real_text].description_length.median(), out.demand_language.sum(),
                         out.time_start_source.isin(LISTED_TIME_SOURCES).mean(),
                         out.time_assumed.mean(), out.onsale_date.notna().mean(),
                         out.ticket_price_min.notna().mean(), out.possibly_cancelled.sum()]
    report.to_csv(PROCESSED / "coverage_report.csv")

    pd.set_option("display.width", 200)
    print(f"Dropped {n_anthem} likely anthem-singer rows. Final table: {len(out)} events.\n")
    print(report.round(2).to_string())
    print("\nCategories:", out.category.value_counts().to_dict())
    print("Start time sources:", out.time_start_source.value_counts().to_dict())
    print("Checks passed: unique event_id, no text dated on/after its event, no missing required fields.")
    print(f"Wrote {(PROCESSED / 'nonsports_events.csv').relative_to(ROOT)} and coverage_report.csv")


if __name__ == "__main__":
    main()
