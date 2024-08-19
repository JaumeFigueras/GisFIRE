#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import dateutil.parser
import json
import argparse
import csv
from requests.auth import HTTPBasicAuth
from typing import Any
from typing import Dict
from typing import List
from typing import Union

import pytz
import requests
import math


def download_lightnings(requested_day: datetime.datetime, host: str, username: str, token: str) -> Union[List[Dict[str, Any]], None]:
    year: int = requested_day.year
    month: int = requested_day.month
    day: int = requested_day.day
    auth: HTTPBasicAuth = HTTPBasicAuth(username, token)
    url: str = "{}/meteocat/lightning/{}/{}/{}?srid=25831".format(host, year, month, day)
    response: requests.Response = requests.get(url, auth=auth)
    if response.status_code == 200:
        return json.loads(response.text)
    else:
        return None


def download_grouped_lightnings(requested_day: datetime.datetime, host: str, username: str, token: str) -> Union[List[Dict[str, Any]], None]:
    year: int = requested_day.year
    month: int = requested_day.month
    day: int = requested_day.day
    auth: HTTPBasicAuth = HTTPBasicAuth(username, token)
    url: str = "{}/meteocat/lightning/grouped_by_discharges/{}/{}/{}?srid=25831".format(host, year, month, day)
    response: requests.Response = requests.get(url, auth=auth)
    if response.status_code == 200:
        return json.loads(response.text)
    else:
        return None


def get_land_cover(identifier: int, host: str, username: str, token: str) -> Union[Dict[str, Any], None]:
    auth: HTTPBasicAuth = HTTPBasicAuth(username, token)
    url: str = "{}/meteocat/lightning/land_cover/{}".format(host, identifier)
    response: requests.Response = requests.get(url, auth=auth)
    if response.status_code == 200:
        print(json.loads(response.text), identifier)
        return json.loads(response.text)
    else:
        return None


def get_discharges(identifier: int, host: str, username: str, token: str) -> Union[Dict[str, Any], None]:
    auth: HTTPBasicAuth = HTTPBasicAuth(username, token)
    url: str = "{}/meteocat/lightning/discharge_count/{}".format(host, identifier)
    response: requests.Response = requests.get(url, auth=auth)
    if response.status_code == 200:
        print(json.loads(response.text), identifier)
        return json.loads(response.text)
    else:
        print(response.text)
        return None


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-file', help='Firefighter file')
    parser.add_argument('-o', '--output-file', help='Matched lightnings file')
    parser.add_argument('-H', '--host', help='Host name were the database cluster is located')
    parser.add_argument('-u', '--username', help='Database username')
    parser.add_argument('-t', '--token', help='Database password')
    parser.add_argument('-y', '--type', help='Type of matching algorithm: individual, combined', default='individual')
    parser.add_argument('-f', '--time-divider', help='Time divider on the time component cost: 1=seconds, 60=minutes', default=1, type=float)

    # noinspection DuplicatedCode
    args = parser.parse_args()

    # Load firefighters records
    csv_lightnings: List[List[str]] = list()
    with open(args.input_file) as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)  # Skip header
        for row in reader:
            csv_lightnings.append(row)
    filtered_lightnings: List[List[Any]] = list()
    for lightning in csv_lightnings:
        str_date = lightning[1] + ' ' + lightning[2]
        try:
            lightning_date = datetime.datetime.strptime(str_date, "%d/%m/%Y %H:%M:%S")
            lightning_date = lightning_date.replace(tzinfo=pytz.timezone('Europe/Paris'))
            x: float = float(lightning[3])
            y: float = float(lightning[4])
        except ValueError as _:
            continue
        new_row = [lightning_date, x, y]
        filtered_lightnings.append(new_row)
    filtered_lightnings.sort(key=lambda l: l[0])

    days_to_search: List[datetime.datetime] = list()
    matched_lightnings = list()
    matched_lightnings.append(['id', 'meteocat_id', 'discharges', 'date-UTC', 'x', 'y', 'land_cover', 'weight', 'date-UTC-ff', 'x-ff', 'y-ff'])
    for lightning in filtered_lightnings:
        days_to_search = [lightning[0] - datetime.timedelta(days=day) for day in range(6)]
        lightnings: List[Dict[str, Any]] = list()
        for day in days_to_search:
            if args.type == 'individual':
                lightnings += download_lightnings(datetime.datetime(day.year, day.month, day.day, 0, 0, 0), args.host,
                                                  args.username, args.token)
            elif args.type == 'combined':
                lightnings += download_grouped_lightnings(datetime.datetime(day.year, day.month, day.day, 0, 0, 0),
                                                          args.host, args.username, args.token)
        print(lightning[0], len(lightnings))
        computed_cost_lightnings = list()
        if lightnings is not None and len(lightnings) > 0:
            # print(len(lightnings))
            distance_max = 10000000000
            lightning_max = None
            for possible in lightnings:
                possible_date = dateutil.parser.isoparse(possible['date'])
                possible_x = possible['coordinates_x']
                possible_y = possible['coordinates_y']

                diff_time: datetime.timedelta = lightning[0] - possible_date

                if diff_time.total_seconds() > 0:
                    distance = math.sqrt((lightning[1] - possible_x)**2 + (lightning[2] - possible_y)**2 + (diff_time.total_seconds() / (args.time_divider))**2)  # / (1 + ((possible_discharges - 1) / 4))
                    if distance < 15000:
                        computed_cost_lightnings.append([distance, possible.copy()])

            if len(computed_cost_lightnings) > 0:
                computed_cost_lightnings.sort(key=lambda l: l[0])
                lightning_max = None
                distance_max = None
                land_cover = None
                discharges_max = None
                for computed_lightning in computed_cost_lightnings:
                    land = get_land_cover(computed_lightning[1]['id'], args.host, args.username, args.token)
                    if land is None:
                        print('Land cover not found!', computed_lightning[1]['id'])
                        break
                    land_cover = int(land['land_cover_type'])
                    if 0 < land_cover < 300:
                        discharges = get_discharges(computed_lightning[1]['id'], args.host, args.username, args.token)
                        if discharges is None:
                            print('discharges not found!', computed_lightning[1]['id'])
                            break
                        discharges_max = int(discharges['count'])
                        lightning_max = computed_lightning[1]
                        distance_max = computed_lightning[0]
                        break
                if lightning_max is not None:
                    date_in_utc: datetime.datetime = lightning[0].astimezone(pytz.utc)
                    new_row = [lightning_max['id'], lightning_max['meteocat_id'], discharges_max, lightning_max['date'],
                               lightning_max['coordinates_x'], lightning_max['coordinates_y'], land_cover, distance_max,
                               date_in_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), lightning[1], lightning[2]]
                    matched_lightnings.append(new_row)
            else:
                print('No match')

    with open(args.output_file, 'w') as file:
        writer = csv.writer(file)
        writer.writerows(matched_lightnings)