#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import csv
import _csv
import os
import datetime
import pytz

from pathlib import Path

from src.meteocat.data_model.lightning import MeteocatLightning

from typing import TextIO
from typing import Union
from typing import List


@pytest.fixture(scope='function')
def meteocat_lightnings_csv_reader(request: pytest.FixtureRequest) -> Union[_csv.reader, None]:
    """
    TODO:
    """
    if hasattr(request, 'param'):
        year = str(request.param['year']) if 'year' in request.param else None
        if year is None or year not in ['2000', '2013', '2017']:
            yield None
        else:
            current_dir: Path = Path(__file__).parent
            csv_file: str = os.path.join(str(current_dir), os.path.join("csvs", "DATMET-12706_cg_cm_{0:}.csv".format(year)))
            try:
                csv_file: TextIO = open(csv_file)
                reader: _csv.reader = csv.reader(csv_file, delimiter=';')
                yield reader
                csv_file.close()
            except Exception as ex:
                yield None


@pytest.fixture(scope='function')
def meteocat_lightnings_list(request: pytest.FixtureRequest) -> Union[MeteocatLightning, None]:
    """
    TODO:
    """
    if hasattr(request, 'param'):
        year = str(request.param['year']) if 'year' in request.param else None
        if year is None or year not in ['2000', '2013', '2017']:
            yield None
        else:
            current_dir: Path = Path(__file__).parent
            csv_file: str = os.path.join(str(current_dir), os.path.join("csvs", "DATMET-12706_cg_cm_{0:}.csv".format(year)))
            try:
                csv_file: TextIO = open(csv_file)
                reader: _csv.reader = csv.reader(csv_file, delimiter=';')
                lightnings: List[MeteocatLightning] = list()
                next(reader)
                for row in reader:
                    lightning: MeteocatLightning = MeteocatLightning()
                    lightning.meteocat_id = int(row[0])
                    lightning.date_time = datetime.datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f').replace(
                        tzinfo=pytz.UTC)
                    year = lightning.date_time.year
                    lightning.peak_current = float(row[2])
                    lightning.chi_squared = float(row[3])
                    lightning.ellipse_major_axis = float(row[4])
                    lightning.ellipse_minor_axis = float(row[5])
                    lightning.ellipse_angle = 0.0
                    lightning.number_of_sensors = int(row[6])
                    lightning.hit_ground = row[7] == 't'
                    lightning.municipality_id = int(row[8]) if row[8] != '' else None
                    lightning.x_4258 = float(row[9])
                    lightning.y_4258 = float(row[10])
                    lightning.data_provider_name = 'Meteo.cat'
                    lightnings.append(lightning)
                yield lightnings
                csv_file.close()
            except Exception as xcpt:
                print(str(xcpt))
                yield None
