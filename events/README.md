# events/: non-sports event pipeline

Builds the table of concerts and shows at **TD Garden, Wang Theatre and MGM Music Hall at Fenway** (Jan 2024 – Sep 2026). Each event gets a **description that was public before the show**, where one exists.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your keys (see below)
bash events/run_pipeline.sh   # about 1 hour the first time, seconds once cached
```

Output: `data/processed/nonsports_events.csv` and `coverage_report.csv`. Every API response and page is cached under `data/raw/` (not committed). Reruns use the cache and make no new requests.

**Keys** go in `.env` at the repo root, which is never committed:
- `SETLISTFM_API_KEY`: free from <https://www.setlist.fm/settings/api>
- `TICKETMASTER_API_KEY`: free from <https://developer.ticketmaster.com>. Used only by the probe script.

## Scripts, in pipeline order

| Script | What it does | Output (`data/interim/`) |
|---|---|---|
| `venues.py` | Venue table (IDs, coordinates, capacity, zone) and the date window. **Change the window here.** | – |
| `setlistfm_collect.py` | Past concerts from setlist.fm, one row per venue-date (openers merged, anthem singers flagged) | `events_setlistfm.csv` |
| `wayback_text.py <venue>` | TD Garden / Wang descriptions from Internet Archive snapshots taken **before** each show, plus show time, on-sale date and price | `text_wayback_<venue>.csv` |
| `vanyaland_text.py` | MGM descriptions from Vanyaland articles published **before** each show | `text_vanyaland_mgm_music_hall.csv` |
| `do617_times.py` | Show start times from Do617 listings | `times_do617.csv` |
| `build_events.py` | Merges everything, fills templates and assumptions, runs the checks | `data/processed/*.csv` |
| `run_pipeline.sh` | Runs all of the above in order | – |
| `ticketmaster_probe.py`, `setlistfm_probe.py` | One-off API tests: Ticketmaster has **no past events**; setlist.fm does | – |

## Rules the pipeline enforces

- **No leakage:** text must be dated strictly before the event day. `build_events.py` fails if any is not.
- **Provenance:** every row records `description_source` (`venue_archive`, `vanyaland` or `template`) and `time_start_source`.
- **Assumptions are flagged:** `time_assumed` (2% of events) and `duration_assumed` (always; no source publishes end times).

## Why these sources

- Ticketmaster deletes events once they happen.
- MGM's own pages (Live Nation / Crossroads) show only door times and the bag policy.
- TD Garden and Boch Center pages keep full descriptions in the HTML, so the Wayback Machine has them.

The full source comparison is in `PROJECT_CONTEXT.md` and the EDA notebook.
