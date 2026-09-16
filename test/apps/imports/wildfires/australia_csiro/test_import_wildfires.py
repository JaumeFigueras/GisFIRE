#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Australian bushfire extents import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral) PostgreSQL
and a real file geodatabase, so the whole path is exercised — the subprocess, the
``.gdb`` suffix GDAL insists on, ``-preserve_fid``, the staging table, the resolution
pass and the per-year SQL mapping.

The fixture geodatabase is **built rather than checked in**, and built the way the
Digital Atlas publishes it:

* two feature classes with the published names, one national and one for the
  Northern Territory, in EPSG:4283;
* the two classes' **different vocabularies** — ``VIC (Victoria)`` against ``NT`` —
  because normalising them is half of what the resolution pass does;
* ``capture_date`` as ``YYYYMMDD`` **text** in the national class and a real date in
  the Northern Territory one, which is the difference the published classes have;
* a directory **without** the ``.gdb`` suffix, which is how the archive arrives and
  the reason :func:`~src.apps.imports.wildfires.australia_csiro.import_wildfires.geodatabase`
  exists.

The features are chosen for what each one exercises: a burn published as three
patches sharing a fire number — which stay **three rows**, nothing being merged —
two features sharing the sentinel ``'999'``, the same fire number on another date, a
prescribed burn, a fire whose only date is its extinction, one with no date at all,
one dated in the year 2525, and one out in the Indian Ocean with no country.
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

from src.apps.imports.wildfires.australia_csiro import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import australia_csiro
from src.providers import ocha
from src.providers.australia_csiro.wildfire import CsiroWildfire

UTC = datetime.timezone.utc

#: Australia, near enough for a fixture: it contains every fire below except the one
#: in the Indian Ocean, which is the point of that one.
AUSTRALIA = "MULTIPOLYGON(((112 -44, 154 -44, 154 -9, 112 -9, 112 -44)))"

#: The mainland's zone here, and Darwin's for the Northern Territory rows — two
#: zones, because a fixture with one could not show that the lookup happens at all.
VICTORIA = "MULTIPOLYGON(((140 -39, 150 -39, 150 -33, 140 -33, 140 -39)))"
TOP_END = "MULTIPOLYGON(((129 -16, 138 -16, 138 -11, 129 -11, 129 -16)))"

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-csiro-import")


def square(x: float, y: float, side: float = 0.01) -> list:
    """A small square in EPSG:4283 degrees, as GeoJSON Polygon coordinates."""
    return [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]]


def feature(object_id, geometry, fire_id=None, fire_name=None, ignition=None,
            extinguish=None, capture=None, fire_type="Bushfire", cause=None,
            method="Landsat", area_ha=100.0, perim_km=8.0, state="VIC (Victoria)",
            agency="VIC DEECA") -> tuple:
    """One published feature, named exactly as the geodatabase names its fields."""
    values = {
        "fire_id": fire_id, "fire_name": fire_name, "ignition_date": ignition,
        "capture_date": capture, "extinguish_date": extinguish, "fire_type": fire_type,
        "ignition_cause": cause, "capt_method": method, "area_ha": area_ha,
        "perim_km": perim_km, "state": state, "agency": agency,
    }
    return object_id, values, geometry


#: The national class.
#:
#: * 11-13 are **one burn published as three patches**, all 2018-05-26, sharing fire
#:   number 705270 — the Victorian mosaic in miniature. They stay three rows.
#: * 14 has the **same fire number on another date**, and is a different fire.
#: * 20 and 21 publish the sentinel ``'999'`` on the same day in the same state.
#: * 30 is a prescribed burn, published in the lower-case spelling.
#: * 31 publishes **no ignition date**, only an extinction.
#: * 32 publishes **no date at all** and cannot be stored.
#: * 33 is extinguished in the year **2525**.
#: * 34 is in the Indian Ocean: no country, no zone.
#: * 40 is a 2019 fire, so that a year filter and a re-import have something to
#:   leave alone.
NATIONAL = [
    feature(11, square(141.50, -35.10), fire_id="705270", fire_name="Murray Sunset",
            ignition="2018-05-26", extinguish="2018-06-02", area_ha=100.0,
            perim_km=8.0, fire_type="Prescribed Burn", cause="Undetermined"),
    feature(12, square(141.55, -35.12), fire_id="705270", fire_name="Murray Sunset",
            ignition="2018-05-26", extinguish="2018-06-02", area_ha=8.0, perim_km=2.0,
            fire_type="Prescribed Burn", cause="Undetermined"),
    feature(13, square(141.60, -35.14), fire_id="705270", fire_name="Murray Sunset",
            ignition="2018-05-26", extinguish="2018-06-02", area_ha=100.0,
            perim_km=9.0, fire_type="Prescribed Burn", cause="NOT DETERMINED"),
    # The same fire number a year later. Named differently only so that the tests can
    # tell the two apart by name; the archive itself reuses the name as well.
    feature(14, square(141.70, -35.20), fire_id="705270",
            fire_name="Murray Sunset 2019", ignition="2019-04-29", area_ha=42.0),
    feature(20, square(142.00, -36.00), fire_id="999", fire_name="Big Desert",
            ignition="2018-12-15", state="WA (Western Australia)", agency="WA DFES",
            cause="Natural"),
    feature(21, square(142.10, -36.10), fire_id="999", fire_name="Big Desert South",
            ignition="2018-12-15", state="WA (Western Australia)", agency="WA DFES",
            cause="OTHER"),
    feature(30, square(143.00, -37.00), fire_id="838733", fire_name="Otway",
            ignition="2018-04-21", fire_type="Prescribed burn", method="Sentinel",
            capture="20180422"),
    feature(31, square(143.20, -37.20), fire_id="541342", fire_name="No ignition",
            extinguish="2018-03-15", cause="Accidental"),
    feature(32, square(143.40, -37.40), fire_id="600001", fire_name="No date at all"),
    feature(33, square(143.60, -37.60), fire_id="600002", fire_name="Extinguished in 2525",
            ignition="2018-11-01", extinguish="2525-05-15"),
    feature(34, square(100.00, -20.00), fire_id="600003", fire_name="Indian Ocean",
            ignition="2018-02-01", state="WA (Western Australia)", agency="WA DFES"),
    feature(40, square(141.50, -35.50), fire_id="700001", fire_name="Another year",
            ignition="2019-01-10", area_ha=55.0),
]

#: The Northern Territory class: the other vocabulary, the other spelling of
#: *prescribed burn*, a real date in ``capture_date``, and two patches sharing a fire
#: number that stay two rows.
NORTHERN_TERRITORY = [
    feature(1, square(131.00, -12.50), fire_id="14085", fire_name="Tipperary",
            ignition="2025-01-01", extinguish="2025-01-05", capture="2025-09-17",
            fire_type="Prescribed burn", cause="Incendiary", method="MODIS",
            state="NT", agency="NTFES", area_ha=1000.0),
    feature(2, square(131.10, -12.60), fire_id="14085", fire_name="Tipperary",
            ignition="2025-01-01", extinguish="2025-01-05", capture="2025-09-17",
            fire_type="Prescribed burn", cause="Incendiary", method="MODIS",
            state="NT", agency="NTFES", area_ha=500.0),
    feature(3, square(132.00, -13.00), fire_id="14958", fire_name="Kakadu",
            ignition="2025-06-01", capture="2025-09-17", fire_type="Bushfire",
            cause="Natural", method="Sentinel", state="NT", agency="Parks"),
]


def write_layer(target: Path, layer: str, features: list, capture_is_text: bool) -> None:
    """Add one feature class to the fixture geodatabase.

    ``capture_date`` is written as a string field for the national class and as a
    date for the Northern Territory one, which is the difference between the two
    published classes and the reason the import reads the column through a cast.
    """
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": object_id, "properties": values,
             "geometry": {"type": "Polygon", "coordinates": coordinates}}
            for object_id, values, coordinates in features
        ],
    }
    source = target.parent / f"source_{layer}.geojson"
    source.write_text(json.dumps(collection), encoding="utf-8")

    fields = ("fire_id=String(200),fire_name=String(255),ignition_date=DateTime,"
              f"capture_date={'String(200)' if capture_is_text else 'DateTime'},"
              "extinguish_date=DateTime,fire_type=String(50),"
              "ignition_cause=String(200),capt_method=String(200),area_ha=Real,"
              "perim_km=Real,state=String(200),agency=String(50)")
    subprocess.run(
        ["ogr2ogr", "-f", "OpenFileGDB", str(target), str(source),
         "-a_srs", "EPSG:4283", "-nln", layer, "-nlt", "MULTIPOLYGON",
         "-preserve_fid", "-lco", "FID=OBJECTID",
         "-oo", f"FIELD_TYPES={fields}", "-update" if target.exists() else "-overwrite"],
        check=True, capture_output=True,
    )
    source.unlink()


@pytest.fixture
def geodatabase(tmp_path) -> Path:
    """The fixture geodatabase, in a directory with **no** ``.gdb`` suffix."""
    target = tmp_path / "build.gdb"
    write_layer(target, app.layer_name(australia_csiro.LAYER_NATIONAL), NATIONAL,
                capture_is_text=True)
    write_layer(target, app.layer_name(australia_csiro.LAYER_NT), NORTHERN_TERRITORY,
                capture_is_text=False)
    # Delivered as the Digital Atlas delivers it: the suffix GDAL needs is not there.
    delivered = tmp_path / "perimetres-gdb"
    target.rename(delivered)
    return delivered


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
    """The OCHA provider, an Australia-shaped boundary and two zones."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(data_provider=provider, source_id="AUS",
                                  name="Australia", name_en="Australia", level=0,
                                  geometry=f"SRID=4326;{AUSTRALIA}"))
        session.add(TimeZone(name="Australia/Melbourne",
                             geometry=f"SRID=4326;{VICTORIA}"))
        session.add(TimeZone(name="Australia/Darwin", geometry=f"SRID=4326;{TOP_END}"))
        session.commit()
    return database


def run(url: str, path: Path, extra: list[str] | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-g", str(path),
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def stored(engine, model=CsiroWildfire):
    with Session(engine) as session:
        return session.scalars(select(model).order_by(model.id)).all()


def by_name(engine) -> dict:
    return {row.fire_name: row for row in stored(engine)}


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# Opening the geodatabase
# --------------------------------------------------------------------------

def test_a_directory_without_the_suffix_is_opened_through_a_link(tmp_path):
    """GDAL reads a geodatabase by its suffix, and the archive arrives without one."""
    delivered = tmp_path / "perimetres-gdb"
    delivered.mkdir()

    with app.geodatabase(delivered, logger) as source:
        assert source.endswith(".gdb")
        assert Path(source).resolve() == delivered.resolve()


def test_a_directory_that_is_already_a_gdb_is_used_as_it_is(tmp_path):
    named = tmp_path / "australia.gdb"
    named.mkdir()

    with app.geodatabase(named, logger) as source:
        assert Path(source) == named.resolve()


def test_the_temporary_link_does_not_outlive_the_run(tmp_path):
    delivered = tmp_path / "perimetres-gdb"
    delivered.mkdir()

    with app.geodatabase(delivered, logger) as source:
        link = Path(source)
    assert not link.exists()
    assert delivered.exists(), "the data itself is untouched"


# --------------------------------------------------------------------------
# The year loop
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_year_is_imported(geodatabase, with_boundaries):
    engine, url = with_boundaries
    assert run(url, geodatabase) == 0

    # Twelve national features and three Northern Territory ones, one row each,
    # except the national feature that publishes no date at all and is stored
    # nowhere. 2018 holds nine of them, 2019 two, 2025 three.
    assert count(engine, "csiro_wildfire") == 14
    assert count(engine, "wildfire") == 14
    assert {fire.year for fire in stored(engine)} == {2018, 2019, 2025}


@needs_ogr2ogr
def test_one_year_can_be_imported_alone(geodatabase, with_boundaries):
    """The unit of work is a year, and ``--year`` is how a run is restricted to one."""
    engine, url = with_boundaries
    assert run(url, geodatabase, extra=["--year", "2019"]) == 0

    assert {fire.year for fire in stored(engine)} == {2019}
    assert count(engine, "csiro_wildfire") == 2


@needs_ogr2ogr
def test_re_importing_a_year_replaces_only_that_year(geodatabase, with_boundaries):
    """The other years stay written, which is what makes the loop resumable."""
    engine, url = with_boundaries
    run(url, geodatabase)
    before = {fire.year: fire.id for fire in stored(engine) if fire.year == 2019}

    assert run(url, geodatabase, extra=["--year", "2018"]) == 0

    after = {fire.year: fire.id for fire in stored(engine) if fire.year == 2019}
    assert before == after, "2019 was not rewritten"
    assert count(engine, "csiro_wildfire") == 14, "and nothing was duplicated"


@needs_ogr2ogr
def test_each_year_is_committed_on_its_own(geodatabase, with_boundaries, monkeypatch):
    """A year that fails costs that year, and the years before it stay written.

    The point of the loop, so it is tested by making the third year fail rather than
    by trusting that the transactions are where they look.
    """
    engine, url = with_boundaries
    real_transform = app.transform_year
    seen: list[int] = []

    def failing(session, provider_id, parts, staging_table, source_layer, year):
        seen.append(year)
        if len(seen) == 3:
            raise RuntimeError("no more years for you")
        return real_transform(session, provider_id, parts, staging_table,
                              source_layer, year)

    monkeypatch.setattr(app, "transform_year", failing)
    assert run(url, geodatabase) == 1

    assert seen == [2018, 2019, 2025]
    assert {fire.year for fire in stored(engine)} == {2018, 2019}, "2025 rolled back"


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(geodatabase, with_boundaries):
    engine, url = with_boundaries
    assert run(url, geodatabase, extra=["--dry-run"]) == 0

    assert count(engine, "csiro_wildfire") == 0
    assert count(engine, "wildfire") == 0


@needs_ogr2ogr
def test_one_feature_class_can_be_imported_alone(geodatabase, with_boundaries):
    engine, url = with_boundaries
    assert run(url, geodatabase, extra=["--layer", "nt"]) == 0

    assert {fire.source_layer for fire in stored(engine)} == {"nt"}
    assert count(engine, "csiro_wildfire") == 3


# --------------------------------------------------------------------------
# Nothing is merged
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_patches_of_one_burn_stay_separate_rows(geodatabase, with_boundaries):
    """Three published patches, one fire number, one day — three rows.

    The import used to dissolve these. It does not, because the same rule merged
    Western Australian features 2,403 km apart: the numbers it keyed on are district
    sequences reused across the state. See the provider module.
    """
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        patches = session.scalars(
            select(CsiroWildfire).where(CsiroWildfire.fire_id == "705270",
                                        CsiroWildfire.year == 2018)
            .order_by(CsiroWildfire.object_id)
        ).all()
    assert [patch.object_id for patch in patches] == [11, 12, 13]
    assert [patch.area_ha for patch in patches] == [100.0, 8.0, 100.0], (
        "each row carries its own published area, unsummed")


@needs_ogr2ogr
def test_every_published_feature_becomes_exactly_one_row(geodatabase, with_boundaries):
    """Twelve national features, one undated, eleven rows — and no OBJECTID twice."""
    engine, url = with_boundaries
    run(url, geodatabase, extra=["--layer", "national"])

    stored_ids = [fire.object_id for fire in stored(engine)]
    assert sorted(stored_ids) == [11, 12, 13, 14, 20, 21, 30, 31, 33, 34, 40]
    assert len(stored_ids) == len(set(stored_ids))


@needs_ogr2ogr
def test_the_same_fire_number_on_another_day_is_another_row(geodatabase,
                                                            with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        fires = session.scalars(
            select(CsiroWildfire).where(CsiroWildfire.fire_id == "705270")
            .order_by(CsiroWildfire.object_id)
        ).all()
    assert [fire.year for fire in fires] == [2018, 2018, 2018, 2019]


@needs_ogr2ogr
def test_sentinel_fire_numbers_are_their_own_rows(geodatabase, with_boundaries):
    """Two WA features publishing '999' on one day are two rows."""
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        sentinels = session.scalars(
            select(CsiroWildfire).where(CsiroWildfire.fire_id_is_sentinel)
        ).all()
    assert {fire.object_id for fire in sentinels} == {20, 21}


# --------------------------------------------------------------------------
# What the published values become
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_two_state_vocabularies_are_normalised(geodatabase, with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    fires = by_name(engine)
    assert fires["Murray Sunset"].state_published == "VIC (Victoria)"
    assert fires["Murray Sunset"].state_code == "VIC"
    assert fires["Kakadu"].state_published == "NT"
    assert fires["Kakadu"].state_code == "NT"


@needs_ogr2ogr
def test_both_spellings_of_prescribed_burn_are_one_type(geodatabase, with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    fires = by_name(engine)
    assert fires["Murray Sunset"].fire_type_published == "Prescribed Burn"
    assert fires["Otway"].fire_type_published == "Prescribed burn"
    assert (fires["Murray Sunset"].fire_type == fires["Otway"].fire_type
            == australia_csiro.FIRE_TYPE_PRESCRIBED_BURN)


@needs_ogr2ogr
def test_a_prescribed_burn_is_imported_as_a_wildfire_row(geodatabase, with_boundaries):
    """Kept, not dropped: fire_type is what a wildfire count filters on."""
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        prescribed = session.scalar(
            select(func.count()).select_from(CsiroWildfire)
            .where(CsiroWildfire.fire_type == australia_csiro.FIRE_TYPE_PRESCRIBED_BURN)
        )
        generic = session.scalar(select(func.count()).select_from(Wildfire.__table__))
    assert prescribed == 6
    assert generic == 14, "and they are Wildfire rows like any other"


@needs_ogr2ogr
def test_a_cause_with_no_canonical_form_stays_unreconciled(geodatabase, with_boundaries):
    """OTHER is a fifth category: kept as published, and NULL in the normalised column."""
    engine, url = with_boundaries
    run(url, geodatabase)

    fire = by_name(engine)["Big Desert South"]
    assert fire.cause_published == "OTHER"
    assert fire.cause is None


@needs_ogr2ogr
def test_the_capture_date_is_read_from_either_published_type(geodatabase,
                                                             with_boundaries):
    """YYYYMMDD text in the national class, a real date in the Northern Territory one."""
    engine, url = with_boundaries
    run(url, geodatabase)

    fires = by_name(engine)
    assert fires["Otway"].capture_date == datetime.date(2018, 4, 22)
    assert fires["Tipperary"].capture_date == datetime.date(2025, 9, 17)


@needs_ogr2ogr
def test_the_object_id_is_the_published_one(geodatabase, with_boundaries):
    """``-preserve_fid``: the staged key is the geodatabase's OBJECTID, not a count."""
    engine, url = with_boundaries
    run(url, geodatabase)

    assert by_name(engine)["Otway"].object_id == 30
    assert by_name(engine)["Kakadu"].object_id == 3


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_fire_with_no_ignition_date_is_dated_from_its_extinction(geodatabase,
                                                                  with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    fire = by_name(engine)["No ignition"]
    assert fire.ignition_date is None
    assert fire.date_source == australia_csiro.SOURCE_EXTINGUISH
    assert fire.year == 2018


@needs_ogr2ogr
def test_a_fire_with_no_date_at_all_is_not_stored(geodatabase, with_boundaries):
    """start_date_time is NOT NULL and this dataset offers nothing else to put in it."""
    engine, url = with_boundaries
    run(url, geodatabase)

    assert "No date at all" not in by_name(engine)


@needs_ogr2ogr
def test_an_implausible_end_is_stored_but_not_believed(geodatabase, with_boundaries):
    """The year 2525 is kept on the provider row and kept out of the instant."""
    engine, url = with_boundaries
    run(url, geodatabase)

    fire = by_name(engine)["Extinguished in 2525"]
    assert fire.extinguish_date == datetime.date(2525, 5, 15)
    assert fire.dates_plausible is False

    with Session(engine) as session:
        parent = session.get(Wildfire, fire.id)
        assert parent.end_date_time is None


@needs_ogr2ogr
def test_the_start_is_local_midnight_in_the_fires_own_zone(geodatabase,
                                                           with_boundaries):
    """Every published date is a bare date; the zone decides which instant that is."""
    engine, url = with_boundaries
    run(url, geodatabase)

    fire = by_name(engine)["Murray Sunset"]
    with Session(engine) as session:
        parent = session.get(Wildfire, fire.id)
    assert parent.time_zone == "Australia/Melbourne"
    assert parent.start_date_time == datetime.datetime(2018, 5, 25, 14, 0, tzinfo=UTC)
    assert fire.date_time_precision == australia_csiro.PRECISION_DAY


@needs_ogr2ogr
def test_a_northern_territory_fire_is_dated_in_darwin(geodatabase, with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        parent = session.get(Wildfire, by_name(engine)["Kakadu"].id)
    assert parent.time_zone == "Australia/Darwin"


# --------------------------------------------------------------------------
# Place
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_fire_is_placed_in_its_country(geodatabase, with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        parent = session.get(Wildfire, by_name(engine)["Murray Sunset"].id)
    assert parent.admin_boundary_id is not None


@needs_ogr2ogr
def test_a_fire_outside_every_boundary_keeps_none(geodatabase, with_boundaries):
    """The Indian Ocean one: stored, with no country and no zone, and counted."""
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        parent = session.get(Wildfire, by_name(engine)["Indian Ocean"].id)
    assert parent.admin_boundary_id is None
    assert parent.time_zone is None


@needs_ogr2ogr
def test_the_import_runs_without_boundaries_at_all(geodatabase, database):
    """A country and a zone are an improvement, not a prerequisite."""
    engine, url = database
    assert run(url, geodatabase) == 0

    with Session(engine) as session:
        parent = session.get(Wildfire, by_name(engine)["Murray Sunset"].id)
    assert parent.admin_boundary_id is None
    assert parent.time_zone is None
    assert parent.start_date_time is not None, "dated against the state's zone instead"


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_staging_tables_are_dropped_when_the_run_ends(geodatabase, with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase)

    with Session(engine) as session:
        remaining = session.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'staging' AND table_name LIKE 'csiro_extents%'"))
    assert remaining == 0


@needs_ogr2ogr
def test_keeping_the_staging_table_keeps_the_lookups_too(geodatabase, with_boundaries):
    engine, url = with_boundaries
    run(url, geodatabase, extra=["--keep-staging"])

    assert count(engine, "staging.csiro_extents_boundary_parts") > 0
    assert count(engine, "staging.csiro_extents_time_zone_parts") > 0


@needs_ogr2ogr
def test_an_unknown_state_stops_the_run(geodatabase, with_boundaries, monkeypatch):
    """state_code is NOT NULL and constrained; a new spelling gets a sentence."""
    engine, url = with_boundaries
    monkeypatch.setattr(app, "STATE_NORMALISATIONS", {"nt": "NT"})

    assert run(url, geodatabase) == 1
    assert count(engine, "csiro_wildfire") == 0
