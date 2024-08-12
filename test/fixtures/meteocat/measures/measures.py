#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import csv
import _csv
import os

from pathlib import Path

from typing import TextIO
from typing import Union


@pytest.fixture(scope='function')
def meteocat_measures_csv_reader(request: pytest.FixtureRequest) -> Union[_csv.reader, None]:
    """
    TODO:
    """
    if hasattr(request, 'param'):
        year = str(request.param['year']) if 'year' in request.param else None
        if year is None or year not in ['2009', '2013', '2017']:
            yield None
        else:
            current_dir: Path = Path(__file__).parent
            csv_file: str = os.path.join(str(current_dir), os.path.join("csvs", "xema-{0:}-short.csv".format(year)))
            try:
                csv_file: TextIO = open(csv_file)
                reader: _csv.reader = csv.reader(csv_file, delimiter=',')
                yield reader
                csv_file.close()
            except Exception as ex:
                yield None

