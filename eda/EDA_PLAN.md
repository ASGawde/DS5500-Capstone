# EDA plan: non-sports event data

**Owner:** Vignesh · **Data:** `data/processed/nonsports_events.csv` (555 events, Jan 2024 – Sep 2026) · **Notebook:** `eda/01_nonsports_events_eda.ipynb`

## Goal
Show that the non-sports event table is usable for the ablation study and describe what it contains. This feeds two slides in the progress update ("data collection done, EDA underway"):
- **Slide 1, "Recovering event text that no API keeps":** sources, pipeline, coverage, leakage check.
- **Slide 2, "What the event data looks like":** volume, timing and text coverage over time.

Demand analysis (Bluebikes near venues on concert nights) is a separate notebook (`02_...`), not covered here.

## Questions, analyses and outputs

| # | Question | Analysis | Figure / table | Slide |
|---|---|---|---|---|
| 1 | Is the table complete and clean? | Row counts, missing values in required fields, duplicate IDs, value ranges | Table: field completeness | 1 |
| 2 | Where does each field come from? | Counts of `description_source` and `time_start_source` | Table: provenance | 1 |
| 3 | How much real text do we have, by venue? | Real vs template events per venue | `fig_text_coverage_by_venue.png` (stacked horizontal bars) | 1 |
| 4 | Is the text really pre-event (no leakage)? | Days from text timestamp to event | `fig_text_lead_time.png` (histogram) | 1 |
| 5 | How are events spread over time? | Events per month, by venue | `fig_events_per_month.png` (small multiples) | 2 |
| 6 | Does text coverage change over time? | Real-text share per quarter, by venue | `fig_text_coverage_over_time.png` (lines, direct labels) | 2 |
| 7 | When do events happen? | Day of week and start hour, by venue | `fig_event_timing.png` | 2 (or backup) |
| 8 | What is the text like? | Length by source; demand-phrase share; most frequent content words per venue | `fig_text_length.png`, table of top terms | backup / appendix |

## Conventions
- **Venue colours** (validated for colour-blind safety with the dataviz palette check): TD Garden `#2a78d6`, Wang Theatre `#eb6834`, MGM Music Hall `#1baf7a`. Aqua is below 3:1 contrast, so lines and bars are labelled directly.
- **Text colour** is navy `#0B2240`, matching the deck. Grid and axes are light grey.
- **Figures** go to `eda/figures/` as PNG at 200 dpi, 16:9-friendly sizes.
- **No modelling** in this notebook, and no Bluebikes data.

## What to watch for (expected findings)
- MGM real-text coverage drops to about 0% by late 2025 (Vanyaland's last MGM On Sale roundup was Feb 2025), which constrains the time-based split.
- About 10% of real descriptions contain demand phrases (sold out, added dates), which is relevant for the robustness check.
- Most events start between 19:00 and 20:00, so the event window (−3 h to +2 h after the estimated end) mostly covers the evening.
