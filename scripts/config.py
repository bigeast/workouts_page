import os
from collections import namedtuple
from re import M

import yaml

GET_DIR = "activities"
OUTPUT_DIR = "activities"
GPX_FOLDER = os.path.join(os.getcwd(), "GPX_OUT")
SQL_FILE = "scripts/data.db"
JSON_FILE = "src/static/activities.json"

# TODO: Move into nike_sync
BASE_URL = "https://api.nike.com/sport/v3/me"
TOKEN_REFRESH_URL = "https://unite.nike.com/tokenRefresh"
NIKE_CLIENT_ID = "HlHa2Cje3ctlaOqnxvgZXNaAs7T9nAuH"
BASE_TIMEZONE = "Asia/Shanghai"

ENDOMONDO_FILE_DIR = "Workouts"

start_point = namedtuple("start_point", "lat lon")
run_map = namedtuple("polyline", "summary_polyline")

TYPE_DICT = {
    "running": "Run",
    "RUN": "Run",
    "Run": "Run",
    "street_running": "Run",
    "trail_running": "TrailRun",
    "cycling": "Ride",
    "CYCLING": "Ride",
    "road_biking": "Ride",
    "Ride": "Ride",
    "VirtualRide": "VirtualRide",
    "indoor_cycling": "IndoorRide",
    "indoor_cardio": "HIIT",
    "hiit": "HIIT",
    "walking": "Walk",
    "Walk": "Walk",
    "hiking": "Hike",
    "Hike": "Hike",
    "mountaineering": "Climb",
    "Swim": "Swim",
    "lap_swimming": "Swim",
    "open_water_swimming": "Swim",
    "rowing": "Rowing",
    "boating": "Rowing",
    "RoadTrip": "RoadTrip",
    "flight": "Flight",
}

MAPPING_TYPE = [
    "Run",
    "TrailRun",
    "Ride",
    "HIIT",
    "Walk",
    "Hike",
    "Climb",
    "Swim",
    "Rowing",
]


try:
    with open("config.yaml") as f:
        _config = yaml.safe_load(f)
except:
    _config = {}


def config(*keys):
    def safeget(dct, *keys):
        for key in keys:
            try:
                dct = dct[key]
            except KeyError:
                return None
        return dct

    return safeget(_config, *keys)


# add more type here
STRAVA_GARMIN_TYPE_DICT = {
    "Hike": "hiking",
    "Run": "running",
    "EBikeRide": "cycling",
    "VirtualRide": "VirtualRide",
    "Walk": "walking",
    "Swim": "swimming",
}
