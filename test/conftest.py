#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile

from pytest_postgresql import factories
from pathlib import Path

test_folder: Path = Path(__file__).parent
socket_dir: tempfile.TemporaryDirectory = tempfile.TemporaryDirectory()
postgresql_session = factories.postgresql_proc(port=None, unixsocketdir=socket_dir.name)
postgresql_schema = factories.postgresql('postgresql_session', dbname='test', load=[
    str(test_folder) + '/database_init.sql',
    str(test_folder.parent) + '/src/data_model/database/data_provider.sql',
    str(test_folder.parent) + '/src/data_model/database/lightning.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/lightning.sql',
    str(test_folder.parent) + '/src/data_model/database/request.sql',
    str(test_folder.parent) + '/src/data_model/database/user.sql',
    str(test_folder.parent) + '/src/data_model/database/user_access.sql',
    str(test_folder.parent) + '/src/data_model/database/weather_station.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/weather_station.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/weather_station_state.sql',
    str(test_folder.parent) + '/src/data_model/database/variable.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/variable.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/variable_state.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/variable_time_base.sql',
    str(test_folder.parent) + '/src/data_model/database/measure.sql',
    str(test_folder.parent) + '/src/meteocat/data_model/database/measure.sql',
    str(test_folder.parent) + '/src/data_model/database/wildfire_ignition.sql',
    str(test_folder.parent) + '/src/bomberscat/data_model/database/wildfire_ignition.sql',
])

pytest_plugins = [
    'test.fixtures.database.database',
    'test.fixtures.data_model.data_provider',
    'test.fixtures.data_model.user',
    'test.fixtures.api.api',
    'test.fixtures.meteocat.lightnings.lightnings',
    'test.fixtures.meteocat.weather_stations',
    'test.fixtures.meteocat.variables',
    'test.fixtures.meteocat.measures.measures',
    'test.fixtures.meteocat.gisfire_api.api',
    'test.fixtures.meteocat.remote_api.api',
    'test.fixtures.bomberscat.wildfire_ignitions',
]
