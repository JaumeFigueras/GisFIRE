#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The algorithms package must stay free of the data model, the database and QGIS.

It is imported in a fresh interpreter, so modules other tests have loaded do not
hide a forbidden import.
"""

import pathlib
import subprocess
import sys

FORBIDDEN = ("sqlalchemy", "geoalchemy2", "psycopg", "qgis", "shapely", "sklearn")

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_importing_the_algorithms_loads_no_adapter_library():
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import gisfire_algorithms\n"
        "import gisfire_algorithms.thunderstorm\n"
        f"print(','.join(m for m in {FORBIDDEN!r} if any(k == m or k.startswith(m + '.') for k in sys.modules)))\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ""
