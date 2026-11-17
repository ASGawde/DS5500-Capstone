# data/

| Folder | Contents | In git? |
|---|---|---|
| `raw/` | Cached API responses and pages (setlist.fm, Wayback, Vanyaland, Do617), Bluebikes trip zips, game schedules | **No** (rebuilt by the scripts). Exception: `raw/nearby_venue_dates.json` |
| `interim/` | One CSV per source step of `events/run_pipeline.sh` | Yes |
| `processed/` | **`nonsports_events.csv`** (the final table) and `coverage_report.csv` | Yes |

`raw/nearby_venue_dates.json` lists setlist.fm dates for Fenway Park, House of Blues and Big Night Live. Notebook 02 uses it to drop nights with other events at the same stations.

**Fenway Park and MGM Music Hall share the `fenway` zone** (about 100 m apart). 13 of the 34 Fenway concerts fall on a night with an MGM show, so their demand effects overlap.

**Fenway Park coverage was audited** against every archived Red Sox concert page: no in-window show is missing. Two cancellations in the window: Shakira on 2025-05-29 (called off after fans had arrived; not in setlist.fm, so not in the table) and Jason Aldean / Brooks & Dunn on 2025-05-30 (in the table with `possibly_cancelled` = True). Drop or treat both as non-events when modeling.

## `processed/nonsports_events.csv`

**589 rows**, one per venue and date. TD Garden 159, Wang Theatre 80, MGM Music Hall 316, Fenway Park 34 (stadium concerts only; Red Sox games are in the sports table). Window: Jan 2024 – Sep 2026. All times are local Boston time.

### Shared schema (same columns as the sports table)

| Column | Meaning |
|---|---|
| `event_id` | `<venue_key>_<date>`, unique |
| `event_name` | Headliner |
| `category` | `concert`, `comedy` or `dance_theater` |
| `venue_name`, `venue_lat`, `venue_lon` | Venue and its coordinates |
| `date_start`, `date_end` | Event date (equal for single nights) |
| `time_start` | Show start, `HH:MM` |
| `time_end_or_duration` | Estimated end, `HH:MM` (**assumed**; see `duration_hours`) |
| `description` | Text for TF-IDF and embeddings: real pre-show text, or a template |
| `source_url` | setlist.fm page for the event |

### Text and provenance

| Column | Meaning |
|---|---|
| `description_source` | `venue_archive` (248), `vanyaland` (73) or `template` (268). **Use as a feature in every model configuration.** |
| `has_real_text` | True for the 321 events with real text (all 34 Fenway Park concerts) |
| `description_timestamp` | When the text was archived or published. Always before `date_start`. |
| `description_url` | The exact archived page or article |
| `description_raw` | Venue-page text before ticketing sentences were removed |
| `description_length` | Characters in `description` |
| `demand_language` | Text mentions sold-out or added shows (57 events). Legitimate pre-event information, flagged for a robustness check. |
| `text_status` | Why there is no real text (`no_match`, `no_pre_event_snapshot`, …) |

### Timing

| Column | Meaning |
|---|---|
| `start_datetime`, `end_datetime` | `YYYY-MM-DDTHH:MM` |
| `time_start_source` | `venue_page_schema` (190), `do617_listing` (355) or `venue_default` (44: every Fenway Park concert, since no source lists past stadium show times) |
| `time_assumed` | True when the start time is a venue default |
| `duration_hours`, `duration_assumed` | Assumed length: concerts 3 h (3.5 h at TD Garden), comedy 2 h, dance 2.5 h |
| `onsale_date`, `days_onsale_to_event` | From TD Garden pages (about 92% of TD Garden events) |

### Event and venue details

| Column | Meaning |
|---|---|
| `event_title` | Title on the venue page or article (e.g. "KISS 108 Jingle Ball") |
| `headliner`, `supporting_artists`, `tour_name`, `artist_mbid` | From setlist.fm (`artist_mbid` = MusicBrainz ID) |
| `ticket_price_min`, `ticket_price_max` | Where listed (mostly Wang) |
| `possibly_cancelled` | Venue page said "canceled" or "postponed", or the show is known to have been cancelled (2 events) |
| `venue_key`, `zone_id`, `venue_capacity`, `indoor_or_outdoor` | From `events/venues.py` |
| `do617_url` | Do617 listing used for the start time |

### Social media (Reddit)

Pre-event Reddit discussion: posts and comments from r/boston, r/bostonmusic, r/concerts and the artist's subreddit in the 90 days before the show. This is **not a description**. It is mostly ticket resale, logistics (lines, seats, the T) and hype (sold out, show added), with only about 12% about the music itself. Treat it as a separate feature set, not a fill-in for `description`.

| Column | Meaning |
|---|---|
| `social_text` | Reddit text, earliest first, one post or comment per line (capped at 10,000 characters). Empty when there is none. |
| `has_social_text` | True for the 489 events with Reddit text (216 of the 268 without a real description) |
| `social_n_posts`, `social_n_comments` | Matched posts and comments |
| `social_text_length` | Characters of Reddit text (capped at 10,000) |
| `social_subreddits` | Where the text came from |
| `social_last_item_utc` | Time of the latest post or comment used. Always before midnight (Boston time) of the event day; `build_events.py` checks this. |
| `social_reddit_ids` | Reddit IDs of every matched item (`t3_` = post, `t1_` = comment), for rebuilding the text |

To rebuild: `python3 events/reddit_text.py`, then `python3 events/build_events.py`. Without `social_reddit.csv`, the build drops these columns.
