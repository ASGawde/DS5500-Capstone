"""Hand-checked venue table shared by all event collectors.

Coordinates: Ticketmaster Discovery venue records (checked 2026-10-22).
Capacities: approximate public figures, used as an attendance proxy.
"""

VENUES = {
    "td_garden": {
        "venue_name": "TD Garden",
        "setlistfm_ids": ["3bd61414"],
        "venue_lat": 42.365841,
        "venue_lon": -71.060724,
        "venue_capacity": 19580,
        "indoor_or_outdoor": "indoor",
        "zone_id": "north_station",
    },
    "wang_theatre": {
        "venue_name": "Wang Theatre",
        "setlistfm_ids": ["63d62267"],
        "venue_lat": 42.35028,
        "venue_lon": -71.06496,
        "venue_capacity": 3500,
        "indoor_or_outdoor": "indoor",
        "zone_id": "theatre_district",
    },
    "mgm_music_hall": {
        "venue_name": "MGM Music Hall at Fenway",
        "setlistfm_ids": ["6bd0725e"],
        "venue_lat": 42.346806,
        "venue_lon": -71.097272,
        "venue_capacity": 5009,
        "indoor_or_outdoor": "indoor",
        "zone_id": "fenway",
    },
}

WINDOW_START = "2024-01-01"
WINDOW_END = "2026-09-30"
