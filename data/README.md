# data/

| Folder | Contents | In git? |
|---|---|---|
| `raw/` | Cached API responses and pages (setlist.fm, Wayback, Vanyaland, Do617), Bluebikes trip zips, game schedules | **No** (rebuilt by the scripts). Exception: `raw/nearby_venue_dates.json` |
| `interim/` | One CSV per source step of `events/run_pipeline.sh` | Yes |
| `processed/` | **`nonsports_events.csv`** (the final table) and `coverage_report.csv` | Yes |

`raw/nearby_venue_dates.json` lists setlist.fm dates for Fenway Park, House of Blues and Big Night Live. Notebook 02 uses it to drop nights with other events at the same stations.

## `processed/nonsports_events.csv`

**555 rows**, one per venue and date. TD Garden 159, Wang Theatre 80, MGM Music Hall 316. Window: Jan 2024 – Sep 2026. All times are local Boston time.

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
| `description_source` | `venue_archive` (215), `vanyaland` (72) or `template` (268). **Use as a feature in every model configuration.** |
| `has_real_text` | True for the 287 events with real text |
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
| `time_start_source` | `venue_page_schema` (190), `do617_listing` (355) or `venue_default` (10) |
| `time_assumed` | True when the start time is a venue default |
| `duration_hours`, `duration_assumed` | Assumed length: concerts 3 h (3.5 h at TD Garden), comedy 2 h, dance 2.5 h |
| `onsale_date`, `days_onsale_to_event` | From TD Garden pages (about 92% of TD Garden events) |

### Event and venue details

| Column | Meaning |
|---|---|
| `event_title` | Title on the venue page or article (e.g. "KISS 108 Jingle Ball") |
| `headliner`, `supporting_artists`, `tour_name`, `artist_mbid` | From setlist.fm (`artist_mbid` = MusicBrainz ID) |
| `ticket_price_min`, `ticket_price_max` | Where listed (mostly Wang) |
| `possibly_cancelled` | Venue page said "canceled" or "postponed" (1 event) |
| `venue_key`, `zone_id`, `venue_capacity`, `indoor_or_outdoor` | From `events/venues.py` |
| `do617_url` | Do617 listing used for the start time |
