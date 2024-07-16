#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import csv
import _csv
import os

from pathlib import Path

from typing import TextIO
from typing import Union
from typing import Tuple


@pytest.fixture(scope='function')
def meteocat_lightnings_csv_reader(request: pytest.FixtureRequest) -> Union[_csv.reader, None]:
    """
    TODO:
    """
    if hasattr(request, 'param'):
        year = str(request.param['year']) if 'year' in request.param else None
        print(year)
        if year is None or year not in ['2013', '2017']:
            yield None
        current_dir: Path = Path(__file__).parent
        csv_file: str = os.path.join(str(current_dir), os.path.join("csvs", "DATMET-12706_cg_cm_{0:}.csv".format(year)))
        try:
            csv_file: TextIO = open(csv_file)
            reader: _csv.reader = csv.reader(csv_file, delimiter=';')
            yield reader
            csv_file.close()
        except Exception as ex:
            yield None

