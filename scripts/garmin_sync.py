#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 3 API wrapper for Garmin Connect to get your statistics.
Copy most code from https://github.com/cyberjunky/python-garminconnect
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import traceback
import zipfile
from io import BytesIO

import aiofiles
import cloudscraper
import httpx
from config import GPX_FOLDER, JSON_FILE, SQL_FILE, config

from utils import make_activities_file_only

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


TIME_OUT = httpx.Timeout(240.0, connect=360.0)
GARMIN_COM_URL_DICT = {
    "BASE_URL": "https://connect.garmin.com",
    "SSO_URL_ORIGIN": "https://sso.garmin.com",
    "SSO_URL": "https://sso.garmin.com/sso",
    # "MODERN_URL": "https://connect.garmin.com/modern",
    "MODERN_URL": "https://connect.garmin.com",
    "SIGNIN_URL": "https://sso.garmin.com/sso/signin",
    "CSS_URL": "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.2-min.css",
    "UPLOAD_URL": "https://connect.garmin.com/modern/proxy/upload-service/upload/.gpx",
    "ACTIVITY_URL": "https://connect.garmin.com/proxy/activity-service/activity/{activity_id}",
}

GARMIN_CN_URL_DICT = {
    "BASE_URL": "https://connect.garmin.cn",
    "SSO_URL_ORIGIN": "https://sso.garmin.com",
    "SSO_URL": "https://sso.garmin.cn/sso",
    # "MODERN_URL": "https://connect.garmin.cn/modern",
    "MODERN_URL": "https://connect.garmin.cn",
    "SIGNIN_URL": "https://sso.garmin.cn/sso/signin",
    "CSS_URL": "https://static.garmincdn.cn/cn.garmin.connect/ui/css/gauth-custom-v1.2-min.css",
    "UPLOAD_URL": "https://connect.garmin.cn/modern/proxy/upload-service/upload/.gpx",
    "ACTIVITY_URL": "https://connect.garmin.cn/proxy/activity-service/activity/{activity_id}",
}


class Garmin:
    def __init__(
        self,
        email,
        password,
        auth_domain,
        is_only_running=False,
        file_type="gpx",
        sync_type="recent",
        activity_types=["running"],
    ):
        """
        Init module
        """
        self.email = email
        self.password = password
        self.req = httpx.AsyncClient(timeout=TIME_OUT)
        self.cf_req = cloudscraper.CloudScraper()
        self.URL_DICT = (
            GARMIN_CN_URL_DICT
            if auth_domain and str(auth_domain).upper() == "CN"
            else GARMIN_COM_URL_DICT
        )
        self.modern_url = self.URL_DICT.get("MODERN_URL")

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36",
            "origin": self.URL_DICT.get("SSO_URL_ORIGIN"),
        }
        self.is_only_running = is_only_running
        self.file_type = file_type
        self.sync_type = sync_type
        self.activity_types = activity_types
        self.upload_url = self.URL_DICT.get("UPLOAD_URL")
        self.activity_url = self.URL_DICT.get("ACTIVITY_URL")
        self.is_login = False

    def login(self):
        """
        Login to portal
        """
        params = {
            "webhost": self.URL_DICT.get("BASE_URL"),
            "service": self.modern_url,
            "source": self.URL_DICT.get("SIGNIN_URL"),
            "redirectAfterAccountLoginUrl": self.modern_url,
            "redirectAfterAccountCreationUrl": self.modern_url,
            "gauthHost": self.URL_DICT.get("SSO_URL"),
            "locale": "en_US",
            "id": "gauth-widget",
            "cssUrl": self.URL_DICT.get("CSS_URL"),
            "clientId": "GarminConnect",
            "rememberMeShown": "true",
            "rememberMeChecked": "false",
            "createAccountShown": "true",
            "openCreateAccount": "false",
            "usernameShown": "false",
            "displayNameShown": "false",
            "consumeServiceTicket": "false",
            "initialFocus": "true",
            "embedWidget": "false",
            "generateExtraServiceTicket": "false",
        }

        data = {
            "username": self.email,
            "password": self.password,
            "embed": "true",
            "lt": "e1s1",
            "_eventId": "submit",
            "displayNameRequired": "false",
        }

        try:
            self.cf_req.get(
                self.URL_DICT.get("SIGNIN_URL"), headers=self.headers, params=params
            )
            response = self.cf_req.post(
                self.URL_DICT.get("SIGNIN_URL"),
                headers=self.headers,
                params=params,
                data=data,
            )
        except Exception as err:
            raise GarminConnectConnectionError("Error connecting") from err
        response_url = re.search(r'"(https:[^"]+?ticket=[^"]+)"', response.text)

        if not response_url:
            raise GarminConnectAuthenticationError("Authentication error")

        response_url = re.sub(r"\\", "", response_url.group(1))
        try:
            response = self.cf_req.get(response_url)
            self.req.cookies = self.cf_req.cookies
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Too many requests")
            response.raise_for_status()
            self.is_login = True
        except Exception as err:
            raise GarminConnectConnectionError("Error connecting") from err

    async def fetch_data(self, url, retrying=False):
        """
        Fetch and return data
        """
        try:
            response = await self.req.get(url, headers=self.headers)
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Too many requests")
            logger.debug(f"fetch_data got response code {response.status_code}")
            response.raise_for_status()
            return response.json()
        except Exception as err:
            if retrying:
                logger.debug(
                    "Exception occurred during data retrieval, relogin without effect: %s"
                    % err
                )
                raise GarminConnectConnectionError("Error connecting") from err
            else:
                logger.debug(
                    "Exception occurred during data retrieval - perhaps session expired - trying relogin: %s"
                    % err
                )
                self.login()
                return await self.fetch_data(url, retrying=True)

    async def get_activities(self, start, limit):
        """
        Fetch available activities
        """
        if not self.is_login:
            self.login()
        url = f"{self.modern_url}/proxy/activitylist-service/activities/search/activities?start={start}&limit={limit}"
        if self.is_only_running:
            url = url + "&activityType=running"
        activities = await self.fetch_data(url)
        print("activities_types: ", self.activity_types)
        if len(self.activity_types) == 0 or self.activity_types[0] == "":
            return activities
        else:
            return [
                x
                for x in activities
                if x["activityType"]["typeKey"] in self.activity_types
            ]

    async def download_activity(self, activity_id):
        if self.file_type == "fit":
            url = f"{self.modern_url}/modern/proxy/download-service/files/activity/{activity_id}"
        else:
            url = f"{self.modern_url}/proxy/download-service/export/{self.file_type}/activity/{activity_id}"
        logger.info(f"Download activity from {url}")
        response = await self.req.get(url, headers=self.headers)
        response.raise_for_status()
        return response.read()

    async def upload_activities(self, files):
        if not self.is_login:
            self.login()
        for file, garmin_type in files:
            files = {"data": ("file.gpx", file)}

            try:
                res = await self.req.post(
                    self.upload_url, files=files, headers={"nk": "NT"}
                )
            except Exception as e:
                print(str(e))
                # just pass for now
                continue
            try:
                resp = res.json()["detailedImportResult"]
            except Exception as e:
                print(e)
                raise Exception("failed to upload")
            # change the type
            if resp["successes"]:
                activity_id = resp["successes"][0]["internalId"]
                print(f"id {activity_id} uploaded...")
                data = {"activityTypeDTO": {"typeKey": garmin_type}}
                encoding_headers = {"Content-Type": "application/json; charset=UTF-8"}
                r = await self.req.put(
                    self.activity_url.format(activity_id=activity_id),
                    data=json.dumps(data),
                    headers=encoding_headers,
                )
                r.raise_for_status()
        await self.req.aclose()


class GarminConnectHttpError(Exception):
    def __init__(self, status):
        super(GarminConnectHttpError, self).__init__(status)
        self.status = status


class GarminConnectConnectionError(Exception):
    """Raised when communication ended in error."""

    def __init__(self, status):
        """Initialize."""
        super(GarminConnectConnectionError, self).__init__(status)
        self.status = status


class GarminConnectTooManyRequestsError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, status):
        """Initialize."""
        super(GarminConnectTooManyRequestsError, self).__init__(status)
        self.status = status


class GarminConnectAuthenticationError(Exception):
    """Raised when login returns wrong result."""

    def __init__(self, status):
        """Initialize."""
        super(GarminConnectAuthenticationError, self).__init__(status)
        self.status = status


async def save_garmin_activity(client, activity_id):
    try:
        file_data = await client.download_activity(activity_id)
        if client.file_type == "fit":
            zipfile.ZipFile(BytesIO(file_data)).extractall(GPX_FOLDER)
        else:
            file_path = os.path.join(GPX_FOLDER, f"{activity_id}." + client.file_type)
            async with aiofiles.open(file_path, "wb") as fb:
                await fb.write(file_data)
    except:
        print(f"Failed to download activity {activity_id}: ")
        traceback.print_exc()
        pass


async def get_activity_id_list(client, start=0):
    if client.sync_type == "all":
        activities = await client.get_activities(start, 100)
        if len(activities) > 0:
            ids = list(map(lambda a: str(a.get("activityId", "")), activities))
            print(f"{len(activities)} Syncing Activity {len(ids)} IDs: {ids}")
            return ids + await get_activity_id_list(client, start + 100)
        else:
            return []
    else:
        activities = await client.get_activities(start, 1)
        if len(activities) > 0:
            ids = list(map(lambda a: str(a.get("activityId", "")), activities))
            print(f"Syncing Activity IDs")
            return ids
        else:
            return []


async def gather_with_concurrency(n, tasks):
    semaphore = asyncio.Semaphore(n)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(task) for task in tasks))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email", nargs="?", help="email of garmin")
    parser.add_argument("password", nargs="?", help="password of garmin")
    parser.add_argument(
        "--is-cn",
        dest="is_cn",
        action="store_true",
        help="if garmin accout is cn",
    )
    parser.add_argument(
        "--only-run",
        dest="only_run",
        action="store_true",
        help="if is only for running",
    )
    parser.add_argument(
        "--sync-type",
        dest="sync_type",
        help="if sync for all records",
    )
    parser.add_argument(
        "--activity-types",
        dest="activity_types",
        help="from activityType.typeKey",
        nargs="+",
        choices=[
            "lap_swimming",
            "running",
            "hiking",
            "cycling",
            "street_running",
            "walking",
            "mountaineering",
            "indoor_cardio",
            "road_biking",
            "trail_running",
            "hiit",
            "boating",
            "open_water_swimming",
        ],
    )
    parser.add_argument(
        "--file-type",
        dest="file_type",
        help=".gpx, .tcx, .fit(zip)",
        choices=["gpx", "tcx", "fit"],
    )
    options = parser.parse_args()
    email = options.email or config("sync", "garmin", "email")
    password = options.password or config("sync", "garmin", "password")
    auth_domain = (
        "CN" if options.is_cn else config("sync", "garmin", "authentication_domain")
    )

    # all: sync all time activities, recent: recent 20 activities
    sync_type = options.sync_type or config("sync", "garmin", "sync-type") or "recent"
    activity_types = (
        options.activity_types
        or config("sync", "garmin", "activity-types")
        or "running"
    )
    file_type = options.file_type or config("sync", "garmin", "file-type") or "gpx"
    logger.debug(f"{sync_type}, {activity_types}")
    is_only_running = options.only_run
    if email == None or password == None:
        print("Missing argument nor valid configuration file")
        sys.exit(1)

    # make gpx dir
    if not os.path.exists(GPX_FOLDER):
        os.mkdir(GPX_FOLDER)

    async def download_new_activities():
        client = Garmin(
            email,
            password,
            auth_domain,
            is_only_running,
            file_type,
            sync_type,
            activity_types,
        )
        client.login()

        # because I don't find a para for after time, so I use garmin-id as filename
        # to find new run to generage
        downloaded_ids = [
            i.split(".")[0] for i in os.listdir(GPX_FOLDER) if not i.startswith(".")
        ]
        logger.debug(f"downloaded ids: {downloaded_ids}")
        activity_ids = await get_activity_id_list(client)
        logger.debug(f"activity ids: {downloaded_ids}")
        print(f"{len(activity_ids)} activities in total, {activity_ids}")
        to_generate_garmin_ids = list(set(activity_ids) - set(downloaded_ids))
        logger.debug(f"new ids: {to_generate_garmin_ids}")
        print(f"{len(to_generate_garmin_ids)} new activities to be downloaded")

        start_time = time.time()
        await gather_with_concurrency(
            10, [save_garmin_activity(client, id) for id in to_generate_garmin_ids]
        )
        print(f"Download finished. Elapsed {time.time()-start_time} seconds")
        make_activities_file_only(SQL_FILE, GPX_FOLDER, JSON_FILE)
        await client.req.aclose()

    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(download_new_activities())
    loop.run_until_complete(future)
