# eda/: exploratory analysis of the non-sports event data

| File | What it is |
|---|---|
| `01_nonsports_events_eda.ipynb` | Data quality, provenance, text coverage, timing. Reads only `data/processed/nonsports_events.csv`. |
| `02_concert_nights_demand.ipynb` | *Exploratory:* Bluebikes departures near TD Garden and MGM on concert nights vs quiet nights (May–Oct 2024) |
| `EDA_PLAN.md` | Questions, analyses and the figure for each |
| `figures/` | PNGs used in the slides (200 dpi) |
| `build_notebook_01.py`, `build_notebook_02.py` | Write the notebooks. Edit these, not the `.ipynb` directly. |
| `fetch_concert_inputs.sh` | Downloads notebook 02's inputs (Bluebikes trips, game schedules) |

## Rerun

```bash
# notebook 01: needs only the committed event table
python3 eda/build_notebook_01.py
python3 -m nbconvert --to notebook --execute --inplace eda/01_nonsports_events_eda.ipynb

# notebook 02: also needs downloads and the pipeline's Do617 cache
bash eda/fetch_concert_inputs.sh
bash events/run_pipeline.sh
python3 eda/build_notebook_02.py
python3 -m nbconvert --to notebook --execute --inplace eda/02_concert_nights_demand.ipynb
```

## Main findings

**Notebook 01**
- **Data quality:** 555 events, all required fields complete, no duplicates, no text dated on or after its event.
- **Real pre-show text:** 287 events (52%): TD Garden 91%, Wang 89%, MGM 23%.
- **Coverage over time:** it holds at TD Garden and Wang (69–100% per quarter). At MGM it falls to about 0% by late 2025, after Vanyaland's last MGM roundup in Feb 2025. A 2026 test set will have almost no MGM real text.
- **Timing:** 95% of events start between 19:00 and 20:30, and 39–48% of each venue's events fall on Friday or Saturday.

**Notebook 02 (exploratory, not in the slides)**
- **TD Garden:** on clean nights (no game or nearby event), departures at 23:00 are about 11 vs 4 trips/h. The effect varies a lot by show: the biggest nights reach 5–6× normal, while many look ordinary.
- **MGM:** no clear effect.
- **Method lesson:** comparison nights must be matched on month and weekday type, and nights with other events at the same stations must be removed. Otherwise seasonal patterns and nearby shows look like concert effects.
