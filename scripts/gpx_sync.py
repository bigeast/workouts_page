#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
If you do not want bind any account
Only the gpx files in GPX_OUT sync
"""

from config import GPX_FOLDER, JSON_FILE, SQL_FILE

from utils import make_activities_file, make_activities_file_only
import os
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpx-dir", dest="gpx_dir")
    options = parser.parse_args()
    gpx_dir = options.gpx_dir or "GPX_OUT"
    print(f"sync gpx files in {gpx_dir}")
    gpx_path = os.path.join(os.getcwd(), gpx_dir)
    make_activities_file(SQL_FILE, gpx_path, JSON_FILE)
