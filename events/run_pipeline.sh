#!/usr/bin/env bash
# Rebuild the non-sports event table from scratch, in dependency order.
# The window is set once in events/venues.py (WINDOW_START / WINDOW_END).
# Raw API responses and pages are cached in data/raw/, so reruns are fast and polite.
#
# Usage: bash events/run_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="python3 -W ignore"

echo "== 1/7 Event list (setlist.fm)";               $PY events/setlistfm_collect.py
echo "== 2/7 TD Garden text (Wayback)";              $PY events/wayback_text.py td_garden
echo "== 3/7 Wang Theatre text (Wayback)";           $PY events/wayback_text.py wang_theatre
echo "== 4/7 MGM Music Hall text (Vanyaland)";       $PY events/vanyaland_text.py
echo "== 5/7 Fenway Park text (Red Sox pages)";     $PY events/fenway_text.py
echo "== 6/7 Start times (Do617)";                   $PY events/do617_times.py
echo "== 7/7 Final table";                           $PY events/build_events.py
