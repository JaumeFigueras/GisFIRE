#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NFDB agency fire point import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral) PostgreSQL
and a real shapefile, so the whole path is exercised — the subprocess, the ``.prj``,
the reprojection, the staging table and the SQL mapping.

The fixture is built the way the service publishes:

* points in NAD83 / Canada Atlas Lambert metres, with a ``.prj`` that **does** name
  ``EPSG:3978`` — unlike NBAC's, and worth reproducing because it is the difference
  between the two sources;
* ``LATITUDE`` and ``LONGITUDE`` as separate attribute columns, which is where the
  dirt lives: one row carries a projected easting in the degrees column and one is
  ``(0, 0)``;
* ``YEAR`` as a **Real** field carrying the ``-999`` sentinel on one row;
* ``PRESCRIBED`` in four of its published spellings, ``PB`` among them.
"""

import datetime
import json
import logging
import shutil
import subprocess

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports import common
from src.apps.imports.wildfires.canada_nfdb import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.geography.time_zone import TimeZone
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import canada_nbac
from src.providers import canada_nfdb
from src.providers import ocha
from src.providers.canada_nbac.wildfire import MATCH_INSIDE
from src.providers.canada_nbac.wildfire import NbacWildfire
from src.providers.canada_nfdb.ignition import NfdbIgnition
from src.providers.canada_nfdb.wildfire import NfdbWildfire

UTC = datetime.timezone.utc

CANADA = "MULTIPOLYGON(((-141 41, -52 41, -52 84, -141 84, -141 41)))"

#: The published ``.prj``, which names its EPSG code — unlike NBAC's.
PUBLISHED_PRJ = (
    'PROJCS["NAD83_Canada_Atlas_Lambert",GEOGCS["GCS_North_American_1983",'
    'DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",0.0],'
    'PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-95.0],'
    'PARAMETER["Standard_Parallel_1",49.0],PARAMETER["Standard_Parallel_2",77.0],'
    'PARAMETER["Latitude_Of_Origin",49.0],UNIT["Meter",1.0],AUTHORITY["EPSG","3978"]]'
)

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-nfdb-import")


def point(x: float, y: float, latitude: float, longitude: float, *, fire_id,
          year=2023, agency="AB", cause="N", cause2=None, size=12.5,
          rep_date="2023-05-03", out_date="2023-07-01", attk_date=None,
          prescribed=None, fire_type="IFR", name=None, park=None) -> tuple:
    """One published row, named exactly as the service names its fields.

    ``x``/``y`` are the geometry, in Lambert metres; ``latitude``/``longitude`` are
    the published attribute columns, which can and do disagree with it.
    """
    values = {
        "NFDBFIREID": fire_id, "SRC_AGENCY": agency, "NAT_PARK": park,
        "FIRE_ID": f"LWF-{fire_id}", "FIRENAME": name,
        "LATITUDE": latitude, "LONGITUDE": longitude, "YEAR": float(year),
        "MONTH": 5.0, "DAY": 3.0,
        "REP_DATE": rep_date, "ATTK_DATE": attk_date, "OUT_DATE": out_date,
        "SIZE_HA": size, "FIRE_TYPE": fire_type, "RESPONSE": "Full",
        "PROTZONE": "Forest Protection Area", "PRESCRIBED": prescribed,
        "MORE_INFO": None, "CFS_NOTE1": None, "CFS_NOTE2": None,
        "ACQ_DATE": "2026-05-27", "CAUSE": cause, "CAUSE2": cause2 or cause,
    }
    return values, [x, y]


#: Everything the mapping has to deal with. The Lambert coordinates and the published
#: degrees agree except where the comment says otherwise.
FEATURES = [
    # Ordinary natural-cause fires, in two years.
    point(-1200000, 1500000, 55.0, -114.0, fire_id="AB-1", cause="N"),
    point(-1150000, 1520000, 55.2, -113.5, fire_id="AB-2", cause="H",
          name="Sturgeon Lake"),
    point(-1100000, 1540000, 55.4, -113.0, fire_id="AB-3", cause="U",
          year=1990, rep_date="1990-06-01", out_date=None),
    # The same NFDBFIREID twice: 1,684 of the published values are used more than once.
    point(-1050000, 1560000, 55.6, -112.5, fire_id="AB-1", cause="N", year=1985,
          rep_date="1985-07-02"),
    # Before the import's year cut.
    point(-1000000, 1580000, 55.8, -112.0, fire_id="AB-old", cause="N", year=1960,
          rep_date="1960-05-01"),
    # The -999 year sentinel.
    point(-980000, 1590000, 55.9, -111.8, fire_id="AB-noyear", cause="N", year=-999,
          rep_date="2001-05-01"),
    # No report date: refused, because there is no second date to fall back on.
    point(-960000, 1600000, 56.0, -111.5, fire_id="AB-nodate", cause="N",
          rep_date=None),
    # A projected easting leaked into the degrees column: the point is dropped, the
    # fire is kept.
    point(-940000, 1610000, 56.1, -5617700.0, fire_id="AB-badlon", cause="N"),
    # (0, 0): 154 published rows are null or exactly this.
    point(-920000, 1620000, 0.0, 0.0, fire_id="AB-zero", cause="N"),
    # The four published spellings of PRESCRIBED.
    point(-900000, 1630000, 56.3, -111.0, fire_id="AB-pb", cause="H",
          cause2="H-PB", prescribed="PB"),
    point(-880000, 1640000, 56.4, -110.8, fire_id="AB-one", cause="H", prescribed="1"),
    point(-860000, 1650000, 56.5, -110.5, fire_id="AB-no", cause="N", prescribed="No"),
    point(-840000, 1660000, 56.6, -110.2, fire_id="AB-zeroflag", cause="N",
          prescribed="0"),
    # A Parks Canada row, and a re-burn.
    point(-820000, 1670000, 56.7, -110.0, fire_id="PC-1", cause="U", agency="PC",
          park="Wood Buffalo", cause2="RE"),
]


def write_layer(directory: Path, layer: str, features: list) -> Path:
    """Build the archive's shapefile, the way the service publishes it."""
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": values,
             "geometry": {"type": "Point", "coordinates": coordinates}}
            for values, coordinates in features
        ],
    }
    source = directory / f"source_{layer}.geojson"
    source.write_text(json.dumps(collection), encoding="utf-8")

    target = directory / f"{layer}.shp"
    subprocess.run(
        ["ogr2ogr", "-f", "ESRI Shapefile", str(target), str(source),
         "-a_srs", "EPSG:3978", "-nln", layer],
        check=True, capture_output=True,
    )
    (directory / f"{layer}.prj").write_text(PUBLISHED_PRJ, encoding="utf-8")
    source.unlink()
    return target


@pytest.fixture
def archive(tmp_path) -> Path:
    directory = tmp_path / "nfdb"
    directory.mkdir()
    return write_layer(directory, "NFDB_point_20260527", FEATURES)


@pytest.fixture
def database(postgresql):
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine, url
    engine.dispose()


@pytest.fixture
def with_boundaries(database):
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(data_provider=provider, source_id="CAN",
                                  name="Canada", name_en="Canada", level=0,
                                  geometry=f"SRID=4326;{CANADA}"))
        session.add(TimeZone(name="America/Edmonton", geometry=f"SRID=4326;{CANADA}"))
        session.commit()
    return database


def argv_for(url: str, path: Path, extra: list[str] | None = None) -> list[str]:
    """The command line reaching the ephemeral database the fixtures built."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", str(path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return argv + (extra or [])


def run(url: str, path: Path, extra: list[str] | None = None) -> int:
    return app.main(argv_for(url, path, extra))


def stored(engine, model=NfdbWildfire):
    with Session(engine) as session:
        return session.scalars(select(model).order_by(model.id)).all()


def by_agency_id(engine) -> dict:
    return {row.agency_fire_id: row for row in stored(engine)}


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# A fire and its point
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_fire_and_its_point_are_both_stored(archive, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archive) == 0

    fire = by_agency_id(engine)["LWF-AB-2"]
    assert fire.fire_name == "Sturgeon Lake"
    assert fire.src_agency == "AB"
    assert fire.fire_cause == "H"
    assert fire.size_ha == pytest.approx(12.5)
    assert fire.ignition_id is not None


@needs_ogr2ogr
def test_the_point_is_stored_in_both_crss(archive, with_boundaries):
    """EPSG:3978 as published on the provider row, EPSG:4326 on the generic one."""
    engine, url = with_boundaries
    run(url, archive)

    with Session(engine) as session:
        srids = session.execute(select(
            func.ST_SRID(NfdbIgnition.geometry_lambert),
            func.ST_SRID(NfdbIgnition.geometry),
        )).first()
    assert tuple(srids) == (3978, 4326)


@needs_ogr2ogr
def test_the_published_coordinates_are_not_moved(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)

    with Session(engine) as session:
        fire = session.scalar(select(NfdbWildfire)
                              .where(NfdbWildfire.agency_fire_id == "LWF-AB-1",
                                     NfdbWildfire.year == 2023))
        x = session.scalar(select(func.ST_X(NfdbIgnition.geometry_lambert))
                           .where(NfdbIgnition.id == fire.ignition_id))
    assert x == pytest.approx(-1200000.0)


@needs_ogr2ogr
def test_the_point_and_the_fire_share_an_instant(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)

    with Session(engine) as session:
        fire = session.scalar(select(NfdbWildfire)
                              .where(NfdbWildfire.agency_fire_id == "LWF-AB-2"))
        ignition = session.get(Ignition, fire.ignition_id)
        parent = session.get(Wildfire, fire.id)
        assert ignition.date_time == parent.start_date_time


@needs_ogr2ogr
def test_the_country_and_the_zone_are_resolved_from_the_point(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)

    with Session(engine) as session:
        fire = session.scalar(select(NfdbWildfire)
                              .where(NfdbWildfire.agency_fire_id == "LWF-AB-2"))
        parent = session.get(Wildfire, fire.id)
        assert parent.admin_boundary is not None
        assert parent.time_zone == "America/Edmonton"


@needs_ogr2ogr
def test_a_fire_is_never_given_a_perimeter(archive, with_boundaries):
    """The agencies publish a location, not a shape. NBAC has the shapes."""
    engine, url = with_boundaries
    run(url, archive)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Wildfire)
                              .where(Wildfire.perimeter.is_not(None))) == 0


# --------------------------------------------------------------------------
# What is refused, and what is only degraded
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_fire_before_the_year_cut_is_not_imported(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)

    assert "LWF-AB-old" not in by_agency_id(engine)


@needs_ogr2ogr
def test_the_year_cut_can_be_moved(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive, extra=["--from-year", "1930"])

    assert "LWF-AB-old" in by_agency_id(engine)


@needs_ogr2ogr
def test_the_year_sentinel_is_not_a_year(archive, with_boundaries):
    """``-999`` would otherwise import as a fire in the year minus 999."""
    engine, url = with_boundaries
    run(url, archive, extra=["--from-year", "1930"])

    assert "LWF-AB-noyear" not in by_agency_id(engine)
    assert all(row.year >= 1930 for row in stored(engine))


@needs_ogr2ogr
def test_a_fire_with_no_report_date_is_refused(archive, with_boundaries):
    """No second date to fall back on, so a date would be an invention."""
    engine, url = with_boundaries
    run(url, archive)

    assert "LWF-AB-nodate" not in by_agency_id(engine)


@needs_ogr2ogr
def test_a_bad_coordinate_drops_the_point_and_keeps_the_fire(archive, with_boundaries):
    """A report whose location is unusable is still a report."""
    engine, url = with_boundaries
    run(url, archive)

    fires = by_agency_id(engine)
    for agency_id in ("LWF-AB-badlon", "LWF-AB-zero"):
        assert agency_id in fires, "the fire is kept"
        assert fires[agency_id].ignition_id is None, "and the point is not"


@needs_ogr2ogr
def test_a_fire_with_no_point_has_no_country(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)

    fire = by_agency_id(engine)["LWF-AB-zero"]
    with Session(engine) as session:
        assert session.get(Wildfire, fire.id).admin_boundary_id is None


@needs_ogr2ogr
def test_a_duplicated_published_identifier_is_stored_twice(archive, with_boundaries):
    """1,684 of the published NFDBFIREIDs are used by more than one row."""
    engine, url = with_boundaries
    run(url, archive)

    with Session(engine) as session:
        same = session.scalars(select(NfdbWildfire)
                               .where(NfdbWildfire.nfdb_fire_id == "AB-1")).all()
    assert len(same) == 2
    assert {row.year for row in same} == {2023, 1985}


# --------------------------------------------------------------------------
# PRESCRIBED
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_published_affirmative_is_read_as_prescribed(archive, with_boundaries):
    """``PB`` above all: 437 published rows against a single ``1``."""
    engine, url = with_boundaries
    run(url, archive)

    fires = by_agency_id(engine)
    assert fires["LWF-AB-pb"].prescribed is True
    assert fires["LWF-AB-one"].prescribed is True


@needs_ogr2ogr
def test_a_negative_or_absent_flag_is_not_prescribed(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)

    fires = by_agency_id(engine)
    assert fires["LWF-AB-no"].prescribed is False
    assert fires["LWF-AB-zeroflag"].prescribed is False
    assert fires["LWF-AB-1"].prescribed is False, "unpublished is false, conservatively"


def test_the_sql_and_the_python_rule_agree():
    """The import resolves the flag in SQL; the model's helper resolves it in Python.

    Two implementations of one rule is exactly where they drift, so the vocabulary is
    shared rather than restated — this asserts that it is.
    """
    assert "pb" in canada_nfdb.PRESCRIBED_TRUE
    assert all(canada_nfdb.is_prescribed(value)
               for value in canada_nfdb.PRESCRIBED_TRUE)
    assert not any(canada_nfdb.is_prescribed(value)
                   for value in canada_nfdb.PRESCRIBED_FALSE)


# --------------------------------------------------------------------------
# A year at a time
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_staged_year_is_imported_by_a_statement_of_its_own(archive,
                                                                 with_boundaries,
                                                                 caplog):
    """The whole point of the loop: one step per year, and a line saying which.

    The archive is transformed year by year rather than in one pass, because six
    materialised CTEs over 380,000 rows is what took the real import to the OOM
    killer. What can be asserted here is the shape that makes that true: a step per
    year, reported as it happens.
    """
    engine, url = with_boundaries
    with caplog.at_level(logging.INFO):
        assert run(url, archive) == 0

    steps = [record.getMessage() for record in caplog.records
             if record.getMessage().startswith("NFDB_point_20260527.shp: [")]
    assert len(steps) == 3, "1985, 1990 and 2023 — one step each"
    assert "[1/3] 1985" in steps[0]
    assert "[3/3] 2023" in steps[2]
    assert count(engine, "nfdb_wildfire") == len(stored(engine))


@needs_ogr2ogr
def test_a_year_is_committed_before_the_next_one_starts(archive, with_boundaries):
    """Which is what makes an interrupted run leave the years it finished behind.

    Asserted through the door the loop itself uses: importing one year writes that year
    and commits it, with no other year in the transaction.
    """
    engine, url = with_boundaries
    args = app.parse_arguments(argv_for(url, archive))

    with Session(engine) as session:
        provider = DataProvider(name=canada_nfdb.PROVIDER_NAME,
                                product=canada_nfdb.PROVIDER_PRODUCT,
                                full_name=canada_nfdb.PROVIDER_FULL_NAME,
                                url=canada_nfdb.PROVIDER_URL)
        session.add(provider)
        session.commit()
        provider_id = provider.id

    common.create_staging_schema(engine, args.staging_schema)
    staging = f"{args.staging_schema}.{args.staging_table}"
    log = logging.LoggerAdapter(logger, {"archive": archive.name})
    app.load_archive(archive, staging, args, log)
    with Session(engine) as session:
        app.prepare_staging(session, staging, args, log)
        session.commit()

    audit = app.import_year(engine, args, provider_id, None, staging, 1990)

    assert audit.written == 1
    # Committed by import_year itself: a session opened afterwards sees it.
    assert {row.year for row in stored(engine)} == {1990}


@needs_ogr2ogr
def test_a_second_run_is_refused_while_one_holds_the_staging_table(archive,
                                                                  with_boundaries):
    """Two runs share one staged table and destroy each other's.

    ``ogr2ogr -overwrite`` drops and recreates the staged table outside any transaction
    this application controls, so a second load replaces the table the first run is
    walking year by year — which leaves the first importing nothing into years it has
    already deleted, and then dropping the table out from under the second one's COPY.
    That is not hypothetical; it happened. The second run is refused outright.
    """
    engine, url = with_boundaries
    args = app.parse_arguments(argv_for(url, archive))
    staging = f"{args.staging_schema}.{args.staging_table}"
    log = logging.LoggerAdapter(logger, {"archive": archive.name})

    with app.exclusive_run(engine, staging, log):
        assert run(url, archive) == 1, "the second run is refused, not queued"
        assert count(engine, "nfdb_wildfire") == 0, "and it wrote nothing"


@needs_ogr2ogr
def test_the_lock_is_released_when_the_run_ends(archive, with_boundaries):
    """An advisory lock and not a row in a table: a killed run leaves nothing behind."""
    engine, url = with_boundaries
    args = app.parse_arguments(argv_for(url, archive))
    staging = f"{args.staging_schema}.{args.staging_table}"
    log = logging.LoggerAdapter(logger, {"archive": archive.name})

    with pytest.raises(RuntimeError):
        with app.exclusive_run(engine, staging, log):
            raise RuntimeError("the run died here")

    assert run(url, archive) == 0, "the next run can take the lock"


def test_a_year_that_lost_its_staged_rows_is_not_committed():
    """The check that turns a silent emptying into a refusal.

    ``staged_years`` listed the year by reading the staged table and the transform
    applies the same condition to it, so ``in_scope`` of zero is impossible unless the
    table changed underneath the run. Raising before the commit takes the delete down
    with it, so the year keeps the fires it had.
    """
    with pytest.raises(RuntimeError, match="changed while this run was reading it"):
        app.assert_year_survived(2016, app.Audit(in_scope=0), "staging.nfdb_points")

    app.assert_year_survived(2016, app.Audit(in_scope=1), "staging.nfdb_points")


@needs_ogr2ogr
def test_a_staged_table_emptied_mid_run_keeps_the_years_it_had(archive,
                                                              with_boundaries):
    """The whole failure, reproduced: the years already imported survive intact.

    What must not happen is what did happen — the year is deleted, nothing replaces it,
    and the run reports success.
    """
    engine, url = with_boundaries
    run(url, archive, extra=["--keep-staging"])
    before = {row.id: row.year for row in stored(engine)}
    assert before, "the fixture imported something to lose"

    args = app.parse_arguments(argv_for(url, archive))
    staging = f"{args.staging_schema}.{args.staging_table}"
    with Session(engine) as session:
        session.execute(text(f"DELETE FROM {staging}"))
        session.commit()

    with pytest.raises(RuntimeError, match="changed while this run was reading it"):
        app.import_year(engine, args, 1, None, staging, 1990)

    assert {row.id: row.year for row in stored(engine)} == before


def test_the_audits_of_the_years_add_up():
    """No row is in two years, so the total is what one pass would have reported."""
    first = app.Audit(in_scope=10, usable=8, no_report_date=1, with_point=7,
                      without_point=1, disagreeing=1, natural_cause=4, written=8)
    second = app.Audit(in_scope=5, usable=5, no_report_date=0, with_point=5,
                       written=2)

    total = first + second

    assert total.in_scope == 15
    assert total.usable == 13
    assert total.written == 10
    assert total.natural_cause == 4
    assert app.Audit() + first == first, "an empty audit is the identity"


def test_a_year_whose_rows_are_all_unusable_is_still_a_step():
    """Otherwise its rows never reach the counts that say why they were dropped.

    The years drive the loop, so the condition that picks them has to be the one the
    transform applies and no stricter. Asking for a report date here would hide a year
    made up entirely of rows that publish none — and would leave such a year populated
    from a previous import rather than replacing it with nothing.
    """
    assert "rep_date" not in app.STAGED_YEARS_SQL
    assert "report_date IS NOT NULL" in app.TRANSFORM_SQL


@needs_ogr2ogr
def test_a_perimeter_bound_to_a_year_stops_the_run_before_anything_is_replaced(
        archive, with_boundaries):
    """The check is up front, because the years commit one by one.

    A refusal discovered halfway through would leave the earlier years replaced and the
    later ones not — the half-done state that a single transaction used to rule out and
    that only an up-front check can rule out now.
    """
    engine, url = with_boundaries
    run(url, archive)
    before = {row.id: row.year for row in stored(engine)}

    with Session(engine) as session:
        fire = session.scalars(select(NfdbWildfire)).first()
        provider = session.scalars(
            select(DataProvider).where(
                DataProvider.product == canada_nfdb.PROVIDER_PRODUCT)).one()
        session.add(NbacWildfire(
            data_provider_id=provider.id, gid="1990_1", nfireid=1, year=1990,
            start_date_time=datetime.datetime(1990, 6, 1, tzinfo=UTC),
            part_count=1, crosses_admin=False, date_source=canada_nbac.SOURCE_AGENCY,
            date_time_precision=canada_nbac.PRECISION_DAY, area_adjusted=False,
            prescribed=False, nfdb_wildfire_id=fire.id, match_method=MATCH_INSIDE,
        ))
        session.commit()

    assert run(url, archive) == 1, "the run is refused rather than half-applied"
    assert {row.id: row.year for row in stored(engine)} == before


# --------------------------------------------------------------------------
# Replacing a year
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_re_importing_replaces_the_years(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)
    fires, points = count(engine, "nfdb_wildfire"), count(engine, "nfdb_ignition")

    assert run(url, archive) == 0
    assert count(engine, "nfdb_wildfire") == fires
    assert count(engine, "nfdb_ignition") == points
    assert count(engine, "wildfire") == fires
    assert count(engine, "ignition") == points


@needs_ogr2ogr
def test_only_the_year_asked_for_is_replaced(archive, with_boundaries):
    engine, url = with_boundaries
    run(url, archive)
    before = {row.id for row in stored(engine) if row.year != 2023}

    run(url, archive, extra=["--year", "2023"])
    after = {row.id for row in stored(engine) if row.year != 2023}
    assert before == after, "the other years' rows were not touched"


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(archive, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archive, extra=["--dry-run"]) == 0

    assert count(engine, "nfdb_wildfire") == 0
    assert count(engine, "ignition") == 0


@needs_ogr2ogr
def test_the_import_works_without_any_boundaries(archive, database):
    engine, url = database
    assert run(url, archive) == 0

    with Session(engine) as session:
        parent = session.scalar(select(Wildfire))
        assert parent.admin_boundary_id is None
        assert parent.start_date_time is not None


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_a_missing_path_is_reported_rather_than_raised(tmp_path):
    assert app.main(["-s", str(tmp_path / "nowhere.zip"),
                     "--db-name", "x", "--db-user", "y"]) == 1


def test_the_year_cut_defaults_to_where_the_perimeters_start():
    arguments = app.parse_arguments(["-s", "x.zip", "--db-name", "x", "--db-user", "y"])
    assert arguments.from_year == canada_nfdb.FIRST_YEAR == 1973


def test_the_year_column_is_converted_rather_than_accepted():
    """``YEAR`` is published as Real and carries a sentinel compared against an int."""
    assert "double precision" not in app.COMPATIBLE_TYPES["integer"]
    assert app.STAGING_COLUMNS["year"] == "integer"


def test_the_year_summary_compresses_to_ranges():
    assert app.summarise_years([1973, 1974, 1975, 1980]) == "1973-1975, 1980"
    assert app.summarise_years([]) == "no year"
