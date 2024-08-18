#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import csv
import _csv
import os
import json

from pathlib import Path

from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.json_decoders.no_none_in_list import NoNoneInList

from typing import TextIO
from typing import Union
from typing import List


@pytest.fixture(scope='function')
def meteocat_ignition_csv_reader() -> Union[_csv.reader, None]:
    """
    TODO:
    """
    current_dir: Path = Path(__file__).parent
    csv_file_name: str = os.path.join(str(current_dir), os.path.join("csvs", "llamps.csv"))
    csv_file: TextIO = open(csv_file_name)
    reader: _csv.reader = csv.reader(csv_file, delimiter=';')
    yield reader
    csv_file.close()


@pytest.fixture(scope='function')
def gisfire_api_bomberscat_wildfire_ignition() -> str:
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "bombers_ignitions.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def bomberscat_wildfire_ignitions_list() -> List[BomberscatWildfireIgnition]:
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "bombers_ignitions.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        ignitions = json.loads(data, cls=NoNoneInList, object_hook=BomberscatWildfireIgnition.object_hook_gisfire_api)
        for ignition in ignitions:
            ignition.id = None
            ignition.ts = None
        return ignitions
