#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write ``cellsearch_2019-06-30_expected.json``, and a GeoPackage to check it in QGIS.

The Alaska regression test of ``build_thunderstorms`` imports
``alaska_uswfs_lightning_2019-06-30.txt`` with the Alaska importer, runs
Cellsearch over 2019-06-30 12:00 to 2019-07-01 12:00 UTC once per value of C, in
EPSG:3338, and compares each result with the frozen one in
``cellsearch_2019-06-30_expected.json``. This writes that file, with the test's
own loader and :func:`stored_result`, from the same seven runs made in an **empty
scratch database**::

    python3 test/fixtures/data/alaska_uswfs_regression/freeze_cellsearch_2019-06-30.py \\
        --db-url postgresql+psycopg://user@host:port/scratch \\
        --gpkg /tmp/cellsearch_2019-06-30.gpkg

The database must be migrated (``alembic upgrade head``, for the views) and hold
no stroke and no thunderstorm experiment: the script refuses any other, so it
cannot write into gisfire_db by mistake. ``--gpkg`` also exports, in EPSG:3338
(NAD83 / Alaska Albers), the strokes (with ``unknown_error`` for those published
with a semi-major axis of 0), the thunderstorms (concave hulls), the Cellsearch
centres and paths, and the experiments with their C, for a look in QGIS before
the file is committed.

The runs are the builder's default ones, over **cloud-to-ground strokes only**,
but with every storm (``zone=False``, ``--all-storms``: they were frozen before
the zone) and for N_min, which is the tests' ``MIN_FLASHES`` (5, the default when they
were frozen). The file records their ``lightning_filter``. The strokes layer of
``--gpkg`` holds the cloud strokes too, with ``cloud_to_ground`` to tell them
apart.

Regenerate it only after a deliberate change of output: an algorithm's (bump
``gisfire_algorithms.__version__``) or the builder's defaults', run this, check
the runs in QGIS, commit.

Source of the strokes: U.S. Wildland Fire Service (USWFS), Alaska Geographic
Area, Alaska Lightning Detection Network; public domain.
"""

import argparse
import datetime
import importlib.util
import json
import logging
import subprocess
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy import make_url  # noqa: E402
from sqlalchemy import text  # noqa: E402

import gisfire_algorithms  # noqa: E402

from gisfire_algorithms.thunderstorm import CellsearchParameters  # noqa: E402
from src.apps.imports import common  # noqa: E402
from src.apps.thunderstorms import build_thunderstorms as app  # noqa: E402
from src.providers import alaska_uswfs  # noqa: E402

# Loaded by path: ``test`` is also the name of a standard-library package.
_spec = importlib.util.spec_from_file_location(
    "test_build_thunderstorms", ROOT / "test" / "apps" / "thunderstorms" / "test_build_thunderstorms.py")
_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tests)

ALGORITHM = "cellsearch_tuomi_larjavaara"

#: The CRS the runs work in and the layers are exported in: NAD83 / Alaska Albers.
SRID = alaska_uswfs.PROJECTED_SRID

#: What makes a database not empty enough to be written into.
OCCUPIED_SQL = "SELECT (SELECT count(*) FROM lightning) + (SELECT count(*) FROM thunderstorm_experiment)"

_C = "CAST(e.parameters->>'time_distance_limit_min_km' AS double precision) AS c_min_km"

#: The layers of the GeoPackage, all in EPSG:3338: name, SQL.
LAYERS = {
    "strokes": """
        SELECT v.*, v.ellipse_semi_major_axis IS NULL AS unknown_error
        FROM v_alaska_uswfs_lightning_3338 v""",
    "thunderstorms": f"""
        SELECT v.*, {_C}
        FROM v_thunderstorm_3338 v JOIN thunderstorm_experiment e ON e.id = v.experiment_id""",
    "cellsearch_centres": f"""
        SELECT v.*, {_C}
        FROM v_thunderstorm_cellsearch_centre_3338 v
        JOIN thunderstorm_experiment e ON e.id = v.experiment_id""",
    "cellsearch_paths": f"""
        SELECT v.*, {_C}
        FROM v_thunderstorm_cellsearch_path_3338 v
        JOIN thunderstorm_experiment e ON e.id = v.experiment_id""",
    "experiments": """
        SELECT id, CAST(parameters->>'time_distance_limit_min_km' AS double precision) AS c_min_km,
               status, date_time_start, date_time_end, CAST(summary AS text) AS summary
        FROM thunderstorm_experiment""",
}


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


def export_geopackage(url: str, path: Path) -> None:
    """The layers of :data:`LAYERS` into a fresh GeoPackage, with ``ogr2ogr``."""
    target = make_url(url)
    connection = (f"PG:host={target.host} port={target.port or 5432} dbname={target.database} "
                  f"user={target.username}" + (f" password={target.password}" if target.password else ""))
    path.unlink(missing_ok=True)
    for index, (name, sql) in enumerate(LAYERS.items()):
        command = ["ogr2ogr", "-f", "GPKG", str(path), connection, "-sql", " ".join(sql.split()),
                   "-nln", name]
        if index:
            command.append("-update")
        subprocess.run(command, check=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-url", required=True, help="an empty, migrated scratch database")
    parser.add_argument("--gpkg", type=Path, help="also export the runs to this GeoPackage")
    args = parser.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("freeze-alaska-2019-06-30")

    engine = create_engine(args.db_url)
    common.require_tables(engine, ["lightning", "alaska_uswfs_lightning", "thunderstorm_experiment"],
                          logger)
    with engine.connect() as connection:
        if connection.execute(text(OCCUPIED_SQL)).scalar():
            raise SystemExit("the database holds strokes or experiments: use an empty scratch one")
    # The importer creates the provider's row, as a first import does.
    strokes = _tests.load_alaska_day(engine)
    logger.info("Imported %d strokes", strokes)

    runs = {}
    filters = []
    for limit in _tests.LIMITS:
        parameters = CellsearchParameters(
            time_distance_limit_min_km=None if limit == "None" else float(limit),
            min_flashes=_tests.MIN_FLASHES, srid=SRID)
        app.build_thunderstorms(engine, alaska_uswfs.PROVIDER_NAME, ALGORITHM, parameters,
                                _tests.ALASKA_DAY_START, _tests.ALASKA_DAY_END, logger, zone=False)
        with engine.connect() as connection:
            experiment_id = connection.execute(text(
                "SELECT max(id) FROM thunderstorm_experiment")).scalar_one()
            runs[limit] = {"experiment_id": experiment_id,
                           **_tests.stored_result(connection, experiment_id)}
            filters.append(connection.execute(text(
                "SELECT lightning_filter FROM thunderstorm_experiment WHERE id = :id"),
                {"id": experiment_id}).scalar_one())

    if any(stored != filters[0] for stored in filters):
        raise SystemExit(f"the runs stored different lightning filters: {filters}")
    parameters_but_c = CellsearchParameters(min_flashes=_tests.MIN_FLASHES, srid=SRID).to_dict()
    parameters_but_c.pop("time_distance_limit_min_km")
    document = {
        "_about": "Cellsearch on the Alaska Lightning Detection Network's cloud-to-ground "
                  "strokes of 2019-06-30 12:00 to 2019-07-01 12:00 UTC, one run per value of C, "
                  "in EPSG:3338, frozen on "
                  f"{datetime.date.today().isoformat()} from an empty scratch database by "
                  "freeze_cellsearch_2019-06-30.py. Awaiting Jaume's check in QGIS. Source of the "
                  f"strokes: {alaska_uswfs.ATTRIBUTION}.",
        "date_time_start": _tests.ALASKA_DAY_START.isoformat(),
        "date_time_end": _tests.ALASKA_DAY_END.isoformat(),
        "software_version": gisfire_algorithms.__version__,
        "parameters_but_c": parameters_but_c,
        "lightning_filter": filters[0],
        "runs": runs,
    }
    _tests.ALASKA_EXPECTED.write_text(_dumps(document) + "\n")
    logger.info("Wrote %s (%s)", _tests.ALASKA_EXPECTED, ", ".join(f"C={key}" for key in runs))
    if args.gpkg:
        export_geopackage(args.db_url, args.gpkg)
        logger.info("Wrote %s (%s)", args.gpkg, ", ".join(LAYERS))
    engine.dispose()


if __name__ == "__main__":
    main()
