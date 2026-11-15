#!/usr/bin/env bash
# Downloads the public inputs for eda/02_concert_nights_demand.ipynb into data/raw/.
# (Bluebikes May–Oct 2024 trips, Red Sox / Bruins / Celtics home schedules.)
# The Do617 venue pages it also uses come from events/run_pipeline.sh.
#
# Usage: bash eda/fetch_concert_inputs.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw/bluebikes data/raw/mlb data/raw/nba

for m in 202405 202406 202407 202408 202409 202410; do
  f="data/raw/bluebikes/${m}-bluebikes-tripdata.zip"
  [ -f "$f" ] || curl -sS --fail -o "$f" "https://s3.amazonaws.com/hubway-data/${m}-bluebikes-tripdata.zip"
done

curl -sS --fail -o data/raw/mlb/redsox_2024.json \
  "https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=111&season=2024&gameType=R&hydrate=venue"
for s in 20232024 20242025; do
  curl -sS --fail -o "data/raw/nhl_bruins_${s}.json" "https://api-web.nhle.com/v1/club-schedule-season/BOS/${s}"
done
for season in 2024 2025; do
  for type in 2 3; do  # 2 = regular season, 3 = playoffs
    curl -sS --fail -o "data/raw/nba/celtics_${season}_type${type}.json" \
      "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/bos/schedule?season=${season}&seasontype=${type}"
  done
done
echo "Inputs for notebook 02 are in data/raw/."
