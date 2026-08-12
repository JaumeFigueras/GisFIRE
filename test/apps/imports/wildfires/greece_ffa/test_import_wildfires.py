#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Greek Fire Service import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on workbooks built in the shapes the service publishes. What is
being tested is what this dataset makes hard: that a **year** is the unit replaced,
since nothing identifies a fire; that στρέμματα become hectares; that the three
quarters of the archive with no coordinate is stored without one rather than
dropped or placed at null island; and that the 2025 false alarms are kept.
"""

import datetime

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.wildfires.greece_ffa import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import greece_ffa
from src.providers import ocha
from src.providers.greece_ffa.ignition import GreeceFfaIgnition
from src.providers.greece_ffa.wildfire import GreeceFfaWildfire

from .conftest import HEADER_2000
from .conftest import HEADER_2022
from .conftest import HEADER_2025
from .conftest import PREAMBLE_2025
from .conftest import a_2005_fire
from .conftest import a_2022_fire
from .conftest import a_2025_fire
from .conftest import fire
from .conftest import write_workbook

#: A square around Greece, standing in for the OCHA country outline.
GREECE_OUTLINE = ("SRID=4326;MULTIPOLYGON(((19.0 34.0, 30.0 34.0, 30.0 42.0, "
                  "19.0 42.0, 19.0 34.0)))")


@pytest.fixture
def database(postgresql):
    """An empty GisFIRE schema on an ephemeral PostgreSQL, and its URL."""
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
    """The OCHA provider and a Greece-shaped level 0 boundary to attribute fires to."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(data_provider=provider, source_id="GRC",
                                  name="Greece", name_en="Greece",
                                  level=0, geometry=GREECE_OUTLINE))
        session.commit()
    return database


def run(url: str, *paths: Path, extra: list[str] | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", *[str(path) for path in paths],
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def stored(engine, model=GreeceFfaWildfire):
    """Every row of a model, ordered by id."""
    with Session(engine) as session:
        return session.scalars(select(model).order_by(model.id)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# A fire round trips
# --------------------------------------------------------------------------

def test_a_located_fire_is_stored_with_its_point(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})

    assert run(url, path) == 0

    fire_row, = stored(engine)
    assert fire_row.year == 2022
    assert fire_row.source_sheet == "2022"
    assert fire_row.record_number == 1799346
    assert fire_row.engage_id == 970757
    assert fire_row.prefecture_name == "ΑΤΤΙΚΗΣ"
    assert fire_row.municipality_name == "Δ. ΩΡΩΠΟΥ"
    assert fire_row.address == "ΘΕΣΗ ΧΙΛΙΟΠΟΤΑΜΟΣ"
    assert fire_row.personnel_fire_service == 28
    assert fire_row.aircraft_leased_helicopters == 2
    assert fire_row.ignition_id is not None

    point, = stored(engine, GreeceFfaIgnition)
    assert (point.year, point.record_number, point.engage_id) == (2022, 1799346, 970757)


def test_the_published_point_is_stored_unreprojected(tmp_path, with_boundaries):
    """WGS 84 in, WGS 84 out: the only wildfire import with no ``ST_Transform``."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    run(url, path)

    with Session(engine) as session:
        longitude, latitude, srid = session.execute(select(
            func.ST_X(Ignition.geometry), func.ST_Y(Ignition.geometry),
            func.ST_SRID(Ignition.geometry),
        )).one()
    assert (longitude, latitude) == pytest.approx((23.86, 38.28))
    assert srid == 4326


def test_the_naive_local_reading_becomes_an_instant(tmp_path, with_boundaries):
    """13:24 in Athens on 14 June is 10:24 UTC — EEST, three hours ahead."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    run(url, path)

    parent, = stored(engine, Wildfire)
    assert parent.start_date_time == datetime.datetime(
        2022, 6, 14, 10, 24, tzinfo=datetime.timezone.utc)
    assert parent.end_date_time == datetime.datetime(
        2022, 6, 16, 17, 59, tzinfo=datetime.timezone.utc)
    assert parent.time_zone == greece_ffa.DEFAULT_TIME_ZONE


def test_a_winter_fire_is_resolved_on_the_winter_offset(tmp_path, with_boundaries):
    """``AT TIME ZONE`` resolves daylight saving from the date, so March is +2."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2025.xlsx",
                          {"Sheet0": (HEADER_2025, [a_2025_fire()])},
                          preamble={"Sheet0": PREAMBLE_2025})
    run(url, path)

    parent, = stored(engine, Wildfire)
    assert parent.start_date_time == datetime.datetime(
        2025, 3, 12, 9, 23, tzinfo=datetime.timezone.utc)


def test_the_areas_are_converted_to_hectares(tmp_path, with_boundaries):
    """17 στρέμματα of agricultural land is 1.7 ha, and 0.9 is 0.09."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    run(url, path)

    fire_row, = stored(engine)
    assert fire_row.area_ha_agricultural == pytest.approx(1.7)
    assert fire_row.area_ha_crop_residue == pytest.approx(0.09)
    assert fire_row.area_ha_forest_land == pytest.approx(0.3)
    assert fire_row.area_ha_forest == 0.0, "a published zero is an answer"


def test_the_country_is_resolved_from_the_point(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    run(url, path)

    with Session(engine) as session:
        parent = session.scalar(select(Wildfire))
        assert parent.admin_boundary is not None
        assert parent.admin_boundary.name_en == "Greece"
        point = session.scalar(select(Ignition))
        assert point.admin_boundary_id == parent.admin_boundary_id


# --------------------------------------------------------------------------
# The years with no coordinate
# --------------------------------------------------------------------------

def test_a_fire_with_no_coordinate_is_stored_without_a_point(tmp_path, with_boundaries):
    """201,948 rows: every year before 2020 publishes no coordinate at all."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2005.xlsx",
                          {"2005": (HEADER_2000, [a_2005_fire()])})

    assert run(url, path) == 0

    fire_row, = stored(engine)
    assert fire_row.ignition_id is None
    assert fire_row.record_number is None
    assert count(engine, "ignition") == 0
    assert fire_row.station_name == "Π.Κ. ΑΧΑΡΝΩΝ"
    assert fire_row.locality_name == "ΚΡΥΟΝΕΡΙ"


def test_an_unlocated_row_is_not_placed_at_null_island(tmp_path, with_boundaries):
    """The ``0``/``0`` of 3,755 rows is an absence, not a point in the Gulf of Guinea."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(**{"X-ENGAGE": 0, "Y-ENGAGE": 0}), a_2022_fire()])})
    run(url, path)

    assert count(engine, "greece_ffa_wildfire") == 2
    assert count(engine, "greece_ffa_ignition") == 1, "one of the two has a point"
    unlocated = [row for row in stored(engine) if row.ignition_id is None]
    assert len(unlocated) == 1


def test_a_fire_with_no_point_has_no_country(tmp_path, with_boundaries):
    """Nothing to test against: no Greek boundaries below level 0 are imported."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2005.xlsx",
                          {"2005": (HEADER_2000, [a_2005_fire()])})
    run(url, path)

    parent, = stored(engine, Wildfire)
    assert parent.admin_boundary_id is None


def test_a_year_that_publishes_no_deployment_stores_nulls(tmp_path, with_boundaries):
    """NULL and not 0: 2000-2010 do not publish the block at all."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2005.xlsx",
                          {"2005": (HEADER_2000, [a_2005_fire()])})
    run(url, path)

    fire_row, = stored(engine)
    assert fire_row.personnel_fire_service is None
    assert fire_row.aircraft_cl415 is None
    assert fire_row.area_ha_landfill == 0.0, "which this year does publish, as zero"


# --------------------------------------------------------------------------
# A year is the unit
# --------------------------------------------------------------------------

def test_a_multi_year_workbook_imports_every_year(tmp_path, with_boundaries):
    """The 2000-2012 file is thirteen years; each is its own transaction."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "many.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire(), a_2005_fire()]),
        "2006": (HEADER_2000, [a_2005_fire(**{
            "Ημερ/νία Έναρξης": datetime.datetime(2006, 7, 1)})]),
    })
    run(url, path)

    years = sorted(row.year for row in stored(engine))
    assert years == [2005, 2005, 2006]


def test_re_importing_a_year_replaces_it(tmp_path, with_boundaries):
    """There is no key to upsert on, so the only idempotent operation is replace."""
    engine, url = with_boundaries
    first = write_workbook(tmp_path / "a.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(), a_2022_fire(**{"Υπηρεσία": "Π.Κ. ΩΡΩΠΟΥ"})])})
    run(url, first)
    assert count(engine, "greece_ffa_wildfire") == 2

    revised = write_workbook(tmp_path / "b.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(**{"Υπηρεσία": "Π.Κ. ΑΝΑΘΕΩΡΗΜΕΝΟ"})])})
    assert run(url, revised) == 0

    fire_row, = stored(engine)
    assert fire_row.station_name == "Π.Κ. ΑΝΑΘΕΩΡΗΜΕΝΟ"
    assert count(engine, "wildfire") == 1, "the parent row went with it"
    assert count(engine, "greece_ffa_ignition") == 1
    assert count(engine, "ignition") == 1, "and so did the orphaned point"


def test_replacing_a_year_leaves_the_others_alone(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "many.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire()]),
        "2022": (HEADER_2022, [a_2022_fire()]),
    })
    run(url, path)

    only_2022 = write_workbook(tmp_path / "2022.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(), a_2022_fire()])})
    run(url, only_2022)

    years = sorted(row.year for row in stored(engine))
    assert years == [2005, 2022, 2022]


def test_only_the_years_asked_for_are_imported(tmp_path, with_boundaries):
    """``--year`` skips the other sheets of a multi-year workbook."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "many.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire()]),
        "2006": (HEADER_2000, [a_2005_fire()]),
    })

    assert run(url, path, extra=["--year", "2006"]) == 0

    assert [row.year for row in stored(engine)] == [2006]


def test_a_year_is_committed_before_the_next_is_read(tmp_path, with_boundaries):
    """One transaction per year, so an interrupted run keeps the years it finished.

    The second sheet is made unimportable — no start column at all — so the import
    fails part way through and what is asserted is that the first year survived.
    """
    engine, url = with_boundaries
    broken = tuple(name for name in HEADER_2000 if name != "Ημερ/νία Έναρξης")
    path = write_workbook(tmp_path / "many.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire()]),
        "2006": (broken, [fire(broken, **{"Νομός": "ΑΤΤΙΚΗΣ"})]),
    })

    assert run(url, path) == 1, "the run reports failure"
    assert [row.year for row in stored(engine)] == [2005], "and 2005 is still there"


# --------------------------------------------------------------------------
# The 2025 file
# --------------------------------------------------------------------------

def test_a_false_alarm_is_imported_with_its_category(tmp_path, with_boundaries):
    """1,255 rows of 2025. A row that says "not a fire" can be filtered afterwards."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2025.xlsx", {"Sheet0": (HEADER_2025, [
        a_2025_fire(),
        a_2025_fire(**{"Κατηγορία Συμβάντος": greece_ffa.CATEGORY_FALSE_ALARM}),
    ])}, preamble={"Sheet0": PREAMBLE_2025})

    assert run(url, path) == 0

    categories = sorted(row.incident_category for row in stored(engine))
    assert categories == sorted([greece_ffa.CATEGORY_SMALL,
                                 greece_ffa.CATEGORY_FALSE_ALARM])


def test_an_engage_id_too_big_for_an_int32_is_stored(tmp_path, with_boundaries):
    """Two rows of the real 2023 sheet publish one, and both columns are bigint.

    ``911023000013`` and ``2310230025`` against a median around a million — a date
    and a sequence run together by whatever wrote them. They are what the service
    published, and an ``integer`` column would have failed the whole year on them.
    """
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2023.xlsx", {"2023": (HEADER_2022, [
        a_2022_fire(**{"Α/Α ENGAGE": 911023000013}),
        a_2022_fire(**{"Α/Α ENGAGE": 2310230025}),
    ])})

    assert run(url, path) == 0

    assert sorted(row.engage_id for row in stored(engine)) == [2310230025, 911023000013]
    assert sorted(row.engage_id for row in stored(engine, GreeceFfaIgnition)) == \
        [2310230025, 911023000013]


def test_the_2025_sheet_is_stored_under_its_own_name(tmp_path, with_boundaries):
    """``Sheet0``, with the year taken from the cell above the header."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2025.xlsx",
                          {"Sheet0": (HEADER_2025, [a_2025_fire()])},
                          preamble={"Sheet0": PREAMBLE_2025})
    run(url, path)

    fire_row, = stored(engine)
    assert (fire_row.year, fire_row.source_sheet) == (2025, "Sheet0")
    assert fire_row.aircraft_gru is None, "2025 stopped publishing the column"
    assert fire_row.aircraft_other_agencies == 0, "and started publishing this one"


# --------------------------------------------------------------------------
# Rows that cannot be stored
# --------------------------------------------------------------------------

def test_a_row_with_no_start_date_is_skipped_and_the_rest_committed(tmp_path,
                                                                    with_boundaries):
    """``wildfire.start_date_time`` is NOT NULL and nothing can stand in for it."""
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(**{"Ημερ/νία Έναρξης": None}),
        a_2022_fire(),
    ])})

    assert run(url, path) == 0
    assert count(engine, "greece_ffa_wildfire") == 1


def test_an_unparseable_date_does_not_lose_the_year(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(**{"Ημερ/νία Έναρξης": "the fourteenth"}),
        a_2022_fire(),
        a_2022_fire(),
    ])})
    run(url, path)

    assert count(engine, "greece_ffa_wildfire") == 2


def test_a_sheet_with_no_start_column_is_refused(tmp_path, with_boundaries):
    """Refused loudly rather than importing a year of fires with no instant."""
    engine, url = with_boundaries
    broken = tuple(name for name in HEADER_2022 if name != "Ημερ/νία Έναρξης")
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (broken, [fire(broken, **{"Νομός": "ΑΤΤΙΚΗΣ"})])})

    assert run(url, path) == 1
    assert count(engine, "greece_ffa_wildfire") == 0


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_a_directory_imports_every_workbook(tmp_path, with_boundaries):
    engine, url = with_boundaries
    write_workbook(tmp_path / "a.xlsx", {"2005": (HEADER_2000, [a_2005_fire()])})
    write_workbook(tmp_path / "b.xlsx", {"2022": (HEADER_2022, [a_2022_fire()])})

    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(tmp_path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]

    assert app.main(argv) == 0
    assert sorted(row.year for row in stored(engine)) == [2005, 2022]


def test_a_missing_path_is_reported_rather_than_raised(tmp_path, with_boundaries):
    _, url = with_boundaries
    assert run(url, tmp_path / "nowhere.xlsx") == 1


def test_a_file_that_is_not_a_workbook_is_refused(tmp_path, with_boundaries):
    _, url = with_boundaries
    path = tmp_path / "notes.txt"
    path.write_text("nothing here")

    assert run(url, path) == 1


def test_an_empty_directory_is_refused(tmp_path, with_boundaries):
    """More likely a wrong path than an empty download, and silence would hide it."""
    engine, url = with_boundaries
    empty = tmp_path / "empty"
    empty.mkdir()

    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(empty), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]

    assert app.main(argv) == 1


def test_the_provider_row_is_created_once(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    run(url, path)
    run(url, path)

    with Session(engine) as session:
        providers = session.scalars(
            select(DataProvider).where(DataProvider.name == greece_ffa.PROVIDER_NAME)
        ).all()
    assert len(providers) == 1
    assert providers[0].product == greece_ffa.PROVIDER_PRODUCT


def test_the_import_works_without_any_boundaries(tmp_path, database):
    """The fires and their dates are worth having; the boundaries can come later."""
    engine, url = database
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})

    assert run(url, path) == 0

    parent, = stored(engine, Wildfire)
    assert parent.admin_boundary_id is None
    assert parent.start_date_time is not None


def test_the_polymorphic_rows_are_written_on_both_tables(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_workbook(tmp_path / "2022.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    run(url, path)

    with Session(engine) as session:
        parent = session.scalar(select(Wildfire))
        assert parent.type == "greece_ffa_wildfire"
        assert isinstance(parent, GreeceFfaWildfire)
        point = session.scalar(select(Ignition))
        assert point.type == "greece_ffa_ignition"
        assert isinstance(point, GreeceFfaIgnition)
