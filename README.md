# Does Adding Text Actually Improve Event-Driven Mobility Forecasting?

**DS 5500 Capstone, Fall 2026, Northeastern University (MS in Data Science)**
Anish Gawde · Kishan Kumar Parida · Vignesh Ramaswamy Balasundaram
Sponsor: Professor Kylie Bemis

## Overview

Large public events such as ballgames, concerts, and festivals can cause sudden, localized surges in transportation demand that standard daily patterns miss. This project asks whether **the text describing an event** carries predictive signal for hourly mobility demand **beyond** historical demand, time, weather, and structured event attributes like category, venue, and start time.

We forecast hourly trip counts at bike share stations (or zones) around Boston. The data starts with [Bluebikes](https://bluebikes.com/system-data) and expands to other mobility sources where comparable public data exists. It is joined with historical event schedules and NOAA weather. A finding that text adds little value is treated as a valid and useful result.

## Experimental design

The experiment is a controlled feature ablation. All four configurations use the same time-based train, validation, and test split and the same tuning budget.

| Configuration | Features |
|---|---|
| **Baseline** | Historical demand, calendar/time, weather |
| **Structured events** | Baseline + event category, venue, timing, distance to venue |
| **TF-IDF** | Structured events + TF-IDF features from event descriptions |
| **Sentence embeddings** | Structured events + dense sentence embeddings of event descriptions |

**Evaluation**
- **Metrics:** MAE and RMSE on the full test set, and separately on event windows and demand spikes.
- **Breakdowns:** by event type, venue, and mobility source.
- **Uncertainty:** paired bootstrap confidence intervals for differences between configurations.
- **Leakage control:** every feature must be available at forecast time. Model selection uses only the validation set, and the test set is evaluated once.

## Data sources

| Source | Use | Access |
|---|---|---|
| [Bluebikes System Data](https://bluebikes.com/system-data) | Trip histories (timestamps, stations, coordinates) | Public monthly zips on S3 |
| [NOAA Climate Data Online](https://www.ncei.noaa.gov/cdo-web/) | Hourly weather | Public |
| [MLB Stats API](https://statsapi.mlb.com/api/v1/schedule) | Red Sox home game times (pilot) | Public, non-commercial use |
| U.S. DOT BTS Docked Bikeshare Ridership | Coarser fallback / additional source | Data.gov |
| Ticketmaster Discovery API | Candidate source of event metadata and descriptions | Historical coverage to be verified |

Raw and processed data are **not committed** to this repository. The notebooks download everything from the original sources and cache it locally under `data/`.

## Repository structure

```
.
├── notebooks/
│   └── bluebikes_fenway_pilot_eda.ipynb   # Pilot: Bluebikes EDA + Fenway event matching
├── figs/                                  # Figures used in the proposal and reports
├── proposal/                              # LaTeX source for the project proposal
├── src/                                   # (planned) reusable pipeline and modeling code
├── data/                                  # (git-ignored) created on first run
│   ├── raw/                               # cached Bluebikes zips
│   └── processed/                         # station-hour panel, station table, event tables
├── requirements.txt
└── README.md
```

## Getting started

Requires Python 3.10+.

```bash
git clone https://github.com/<org>/<repo>.git
cd <repo>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/bluebikes_fenway_pilot_eda.ipynb
```

`requirements.txt`:

```
pandas>=2.0
numpy
matplotlib
requests
jupyterlab
pyarrow   # optional; enables parquet output
```

The first run of the pilot notebook downloads roughly 60 to 100 MB of Bluebikes data. To change the pilot window or matching settings, edit the configuration cell at the top of the notebook (`MONTHS`, `RADII_M`, `MATCH_RADIUS_M`, and so on).

Add this to `.gitignore`:

```
data/
.venv/
.ipynb_checkpoints/
```

## Pilot results

The pilot uses one mobility source (Bluebikes, June to August 2024) and one venue (Fenway Park, Red Sox home games).

- **Data quality:** Trip durations are right-skewed, and most trips are under 20 minutes. Trips shorter than 1 minute or longer than 24 hours are excluded.
- **Daily volume:** Ridership runs mostly between 15,000 and 20,000 trips per day.
- **Where demand is:** Trips concentrate in a dense core spanning Back Bay, Fenway, and Cambridge.
- **Event matching:**
  - Six stations lie within 500 m of Fenway Park.
  - We compared 25 weekday night-game days with 38 weekday non-game days.
  - Morning commute peaks are nearly identical on both kinds of day.
  - On game days, pre-game arrivals rise to about 85 trips per hour versus roughly 50.
  - Post-game departures at 9 PM reach about four times the non-game level.
- **Takeaway:** Distance-based event-to-station matching captures a real, localized event signal.

## Timeline

| Week | Milestone | Deliverable |
|---|---|---|
| 1 | Pilot | Pilot notebook and findings |
| 2 | Scope expansion | Final scope: event types, venues, mobility sources, date range |
| 3 | Event pipeline | Unified event table with descriptions |
| 4 | Data pipeline | Frozen dataset v1 and fixed splits |
| 5 | Baseline modeling | Baseline MAE/RMSE |
| 6 | Structured events | Structured-event results |
| 7 | Text experiments | TF-IDF results |
| 8 | Text experiments | Four-configuration ablation table |
| 9 | Evaluation | Test results with bootstrap confidence intervals |
| 10 | Final report | Report, presentation, cleaned repository |

## Known limitations

- **Missing Fenway events:** Concerts and other non-baseball events at Fenway are not in the MLB schedule. This contaminates the "non-game" baseline in the pilot.
- **Neighborhood confounders:** The Fenway/Kenmore area also includes universities, the Longwood Medical Area, and a major transit hub.
- **Patchy event text:** Historical event descriptions may be incomplete or uneven across event types.

## Acknowledgements

Bluebikes, NOAA NCEI, and MLB Advanced Media make the data used here publicly available. MLB data is used only for non-commercial academic purposes.
