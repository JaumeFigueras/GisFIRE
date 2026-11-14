#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write ``cellsearch_2020-07-13_expected.json`` from gisfire_db (read only).

The regression test of ``build_thunderstorms`` runs Cellsearch over
``meteocat_lightning_2020-07-13.csv`` once per value of C and compares the
result with what the same runs stored in the real database. This writes that
reference, with the test's own :func:`stored_result`, from complete experiments
on 2020-07-13 that differ only in C::

    python3 test/fixtures/data/export_cellsearch_2020-07-13.py 1 9 10 2 3 4 5

Regenerate it only after a deliberate change of output: bump
``gisfire_algorithms.__version__``, run the experiments again with
``build_thunderstorms``, check them, then export.

Both files are **git-ignored**: MeteoCat's data is not licensed for
redistribution, so the regression day lives only where gisfire_db does, and
the test skips elsewhere. The strokes were exported from gisfire_db with::

    PGTZ=UTC psql -h $GISFIRE_DB_HOST -p $GISFIRE_DB_PORT -U $GISFIRE_DB_USER -d $GISFIRE_DB_NAME -c "
        COPY (SELECT l.date_time, ST_X(m.geometry_etrs89) AS longitude,
                     ST_Y(m.geometry_etrs89) AS latitude, m.network_version, m.flash_id,
                     m.multiplicity, m.stroke_index, m.ellipse_major_axis,
                     m.ellipse_minor_axis, l.peak_current, l.cloud_to_ground
              FROM lightning l JOIN meteocat_lightning m ON m.id = l.id
              WHERE l.date_time >= '2020-07-13T00:00Z' AND l.date_time < '2020-07-14T00:00Z'
              ORDER BY l.id) TO STDOUT WITH (FORMAT csv, HEADER)" \\
        > test/fixtures/data/meteocat_lightning_2020-07-13.csv
"""

import datetime
import importlib.util
import json
import sys

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src import settings  # noqa: E402

# Loaded by path: ``test`` is also the name of a standard-library package.
_spec = importlib.util.spec_from_file_location(
    "test_build_thunderstorms", ROOT / "test" / "apps" / "thunderstorms" / "test_build_thunderstorms.py")
_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tests)
EXPECTED = _tests.EXPECTED
stored_result = _tests.stored_result

CHECK_SQL = """
SELECT e.id, e.status, e.date_time_start, e.date_time_end, e.parameters, e.software_version,
       dp.name
FROM thunderstorm_experiment AS e
JOIN data_provider AS dp ON dp.id = e.data_provider_id
WHERE e.id = :id
"""


def _dumps(document: dict) -> str:
    """Indented JSON, but each thunderstorm on one line, so a diff shows which changed."""
    storms = {}

    def placeholder(run: dict) -> dict:
        marks = []
        for storm in run["thunderstorms"]:
            mark = f"@@storm{len(storms)}@@"
            storms[mark] = json.dumps(storm, ensure_ascii=False)
            marks.append(mark)
        return {**run, "thunderstorms": marks}

    text_ = json.dumps({**document, "runs": {key: placeholder(run)
                                             for key, run in document["runs"].items()}},
                       indent=1, ensure_ascii=False)
    for mark, storm in storms.items():
        text_ = text_.replace(json.dumps(mark), storm)
    return text_


def main(experiment_ids: list[int]) -> None:
    engine = create_engine(settings.database_url())
    runs = {}
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        reference = None
        for experiment_id in experiment_ids:
            row = connection.execute(text(CHECK_SQL), {"id": experiment_id}).one()
            if row.status != "complete" or row.name != "MeteoCat":
                raise SystemExit(f"experiment {experiment_id} is not a complete MeteoCat run")
            parameters = dict(row.parameters)
            limit = parameters.pop("time_distance_limit_min_km")
            key = "None" if limit is None else f"{limit:g}"
            setting = (row.date_time_start, row.date_time_end, parameters, row.software_version)
            if reference is None:
                reference = setting
            elif setting != reference:
                raise SystemExit(f"experiment {experiment_id} differs in more than C")
            if key in runs:
                raise SystemExit(f"two experiments with C = {key}")
            runs[key] = {"experiment_id": experiment_id, **stored_result(connection, experiment_id)}
    start, end, parameters, version = reference
    document = {
        "_about": "What gisfire_db stored for Cellsearch on 2020-07-13 (UTC), one run per value "
                  "of C, checked in QGIS on 2026-11-13. Written by "
                  "export_cellsearch_2020-07-13.py; see test_build_thunderstorms.py.",
        "date_time_start": start.astimezone(datetime.timezone.utc).isoformat(),
        "date_time_end": end.astimezone(datetime.timezone.utc).isoformat(),
        "software_version": version,
        "parameters_but_c": parameters,
        "runs": runs,
    }
    EXPECTED.write_text(_dumps(document) + "\n")
    print(f"Wrote {EXPECTED} ({', '.join(f'C={key}' for key in runs)})")


if __name__ == "__main__":
    main([int(value) for value in sys.argv[1:]])
