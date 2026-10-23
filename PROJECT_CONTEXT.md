# DS 5500 Capstone: Event-Driven Mobility Forecasting

## Project overview

**Title:** Does Adding Text Actually Improve Event-Driven Mobility Forecasting?

**Research question:** Does the text describing a public event (concert, festival, sports game) add predictive signal for transit/bike-share demand beyond what structured event facts (category, venue, start time) already provide?

**Course:** DS 5500 Capstone, Northeastern University, MS in Data Science, Fall 2026

**Team:**
- Anish Gawde
- Kishan Kumar Parida
- Vignesh Ramaswamy Balasundaram (me)

**Sponsor/stakeholder:** Professor Kylie Bemis (course instructor, serving as stakeholder per course guidelines; an external stakeholder may be confirmed later)

**GitHub:** github.com/ASGawde/DS5500-Capstone

**Data window:** January 2024 to September 2026

## What we're predicting

The target is **hourly trip counts** (arrivals and departures) for Bluebikes (and eventually MBTA) stations or zones in the Boston area. Every (station/zone, hour) combination gets a prediction, not just hours near an event, most hours have no nearby event at all and the model still needs to predict ordinary baseline demand for those.

Station identity matters (a downtown station near a venue behaves very differently from a quiet residential one), but we are not training separate models per station. Plan is to use **zone-level aggregation** (grouping nearby stations) rather than raw station IDs, plus each zone's own historical average demand as a feature. This also helps with a known limitation: event-window trip counts at individual stations can be small.

## Methodology: controlled ablation study

Same model and same time-based train/validation/test split across four progressively richer feature configurations:

1. **Baseline:** time, weather (NOAA), historical demand
2. **Structured events:** + event category, venue, start/end time
3. **TF-IDF:** + bag-of-words features from event text descriptions
4. **Embeddings:** + dense sentence embeddings of the same descriptions

Evaluation: MAE and RMSE on the full test set, and **separately on event windows and demand spikes** (since that's where any real benefit from text should show up). Paired bootstrap to test whether differences between configurations are statistically significant. All features must only use information that would have been available at forecast time (no leakage).

A null result (text adds little) is explicitly framed as a useful, legitimate finding, not a failure.

## Data sources (team-wide)

| Source | Provides | Role | Status |
|---|---|---|---|
| Bluebikes system data (bluebikes.com/system-data) | Trip histories, hourly counts per station/zone | Forecast target | Pilot done (Jun-Aug 2024) |
| NOAA Climate Data Online | Historical weather | Baseline covariates | To be joined |
| MLB Stats API (statsapi.mlb.com) | Red Sox home game times | Sports event source | Used in pilot (teammate's task) |
| Ticketmaster Discovery API | Event metadata/descriptions for concerts/festivals | Event text source | **See important caveat below** |
| U.S. DOT docked bikeshare (Data.gov) | Coarser ridership by system/year/month/hour | Fallback if station data too sparse | Not yet needed |

## Pilot findings so far (Jun-Aug 2024, Fenway Park area)

- Trip durations are right-skewed, most trips under 20 minutes; trips under 1 minute or over 24 hours are excluded as outliers
- Daily ridership is mostly 15,000-20,000 trips system-wide, with real day-to-day variation (hence baseline needs calendar + weather features)
- 6 Bluebikes stations fall within 500m of Fenway Park (includes Lansdowne T Stop, Kenmore Square, Boylston St at Jersey St, Burlington Ave at Brookline, Silber Way, Deerfield St at Commonwealth)
- Comparing weekday night-game days (n=25) vs. weekday non-game days (n=38) near Fenway: pre-game arrivals ~85/hour vs. ~50/hour on non-game days; post-game departures roughly 4x higher around 9 PM vs. non-game days. Morning peaks look nearly identical on both.
- Matching rule being tested: haversine distance from venue, comparing 250m / 500m / 800m radii

## MY TASK: collect non-sports event data

Team split: one teammate on sports events (MLB Stats API), one on Bluebikes/MBTA data pipeline, **I am responsible for non-sports events** (concerts, festivals, other public events) in the Boston area for Jan 2024-Sept 2026.

### Required schema (must match teammate's sports-event table structure so they stack cleanly)

Must-have fields:
- `event_name`
- `category` (concert, festival, comedy show, theater, etc.)
- `venue_name`
- `venue_lat`, `venue_lon` (geocode if not provided directly)
- `date_start`, `date_end` (multi-day festivals need both, not just one date)
- `time_start`
- `time_end_or_duration` (often missing from listings; if absent, use a documented fallback assumption, e.g. typical concert length, and flag it explicitly as an assumption)
- `description` (full text, the core input for TF-IDF/embedding features, must not be empty or boilerplate)
- `source_url`

Nice-to-have if easily available:
- `expected_attendance` or venue capacity
- `genre`/`subgenre`
- `indoor_or_outdoor`

### IMPORTANT CAVEAT: Ticketmaster Discovery API is likely NOT viable as the primary historical source

Since today's date is well past January 2024, and Ticketmaster's Discovery API is built around **currently on-sale / upcoming events** (not a historical archive), most of our Jan 2024-Sept 2026 window is already in the past and may not be returned by that API, even though its query parameters technically accept any date range.

Supporting evidence (not 100% definitive, but strong):
- Ticketmaster's own docs define event status `offsale` as "not yet reached (or **is past**) the timeframe of a public onsale," grouping already-happened events with not-yet-onsale ones
- Across venue/attraction/search response objects, the data model repeatedly exposes an `upcomingEvents` count field; there is no equivalent historical/past-events field anywhere in the schema

**Action item before building a full pipeline on Ticketmaster: empirically test it first.** Query the live API for a definitively past window (e.g., Boston events in March 2024) and see what actually comes back. If it returns real historical concerts, Ticketmaster is viable. If empty or sparse, fall back to the plan below.

### Recommended approach given the above

1. **Primary historical source: setlist.fm API** (free, API key required, genuinely built for historical concerts). Searchable by venue name, city, or year. Confirmed via official docs to return artist, venue, city, date, and tour name for past concerts. This is the right tool for "did a concert happen, where, when."
   - Limitation: setlist.fm gives facts, not marketing/descriptive text. No promotional blurb.

2. **For the required description text field, two complementary approaches:**
   - **Default/bulk approach:** build a simple synthetic description from structured fields already in hand, e.g. "{artist} performs as part of {tour_name}, a {genre} {category}." Defensible, fast, consistent across all events.
   - **For a handful of marquee/high-profile events only** (the equivalent of the sports team's biggest games): use the Wayback Machine (web.archive.org) to recover the actual original marketing text from an archived Ticketmaster or venue listing page close to its on-sale date. Richer and more authentic, but slow, worth doing selectively rather than at bulk scale.

3. Keep column names and structure identical to the sports-events table from the start so the two tables merge without reconciliation work later.

## Known Boston-area venues likely in scope

Fenway Park is the pilot anchor venue (used for the game-day vs. non-game-day comparison above). Other likely Boston venues to prioritize for concerts/festivals: TD Garden, MGM Music Hall at Fenway, House of Blues Boston, Leader Bank Pavilion, Rockland Trust Bank Pavilion (Xfinity Center), and any major festival sites, to be confirmed against what setlist.fm actually returns data for.

## Limitations already acknowledged in the proposal/deck (keep consistent with these)

- Pilot so far is descriptive only, one venue, one summer, no forecasting model yet, not weather-adjusted
- Event-window counts at single stations can be small (motivates zone-level aggregation)
- Text coverage for non-sports events may be thin or require assumptions (documented above)
- Matching radius (250/500/800m) and leakage control choices affect results and will be audited before freezing the dataset

## References already in use

1. Bluebikes, System Data. https://bluebikes.com/system-data
2. NOAA National Centers for Environmental Information, Climate Data Online. https://www.ncei.noaa.gov/cdo-web/
3. U.S. Department of Transportation, Bureau of Transportation Statistics, Docked Bikeshare Ridership by System, Year, Month, and Hour. Data.gov.
4. Ticketmaster Discovery API, event metadata source; historical coverage to be verified empirically (see caveat above).
5. MLB Stats API, schedule endpoint. https://statsapi.mlb.com/api/v1/schedule
