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
])

pytest_plugins = [
    'test.fixtures.database.database',
    'test.fixtures.data_model.data_provider',
]
