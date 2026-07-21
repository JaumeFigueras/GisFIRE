#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the GWIS burnt-area statistics application.

The fires here are inserted through the ORM rather than imported from a
shapefile: what has to be asserted is arithmetic over known areas in known
years, and building that by hand is both quicker and clearer than arranging for
an importer to produce it.

The absolute areas are checked against :mod:`pyproj`, which computes the same
geodesic area through PROJ rather than through PostGIS. Two independent
implementations agreeing is worth considerably more than a magic number copied
out of whatever the code returned the first time it ran.
"""

import csv
import datetime
import logging

from pathlib import Path

import pytest

from pyproj import Geod
from shapely.geometry import MultiPolygon
from shapely.geometry import box
from sqlalchemy import select

from src.apps.statistics.wildfires.gwis import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import ocha
from src.providers.gwis.wildfire import GwisWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

logger = logging.getLogger("test-gwis-statistics")

GEOD = Geod(ellps="WGS84")

#: Two countries wide enough to hold every fixture fire, plus a third with no
#: fires at all, which must simply not appear in the report.
COUNTRIES = [
    ("ESP", "Spain", box(-9, 36, 3, 44)),
    ("FRA", "France", box(3, 42, 8, 51)),
    ("AND", "Andorra", box(1.4, 42.4, 1.8, 42.7)),
]

#: (gwis_id, country, local start date, perimeter). Sizes are deliberately
#: unequal within a country and a year, so a minimum and a maximum are
#: distinguishable from each other and from the total.
FIRES = [
    # Spain, 2021: three fires of clearly different sizes.
    ("1", "Spain", datetime.date(2021, 7, 1), box(0.0, 41.0, 0.1, 41.1)),
    ("2", "Spain", datetime.date(2021, 8, 1), box(0.5, 41.0, 0.9, 41.4)),
    ("3", "Spain", datetime.date(2021, 9, 1), box(1.0, 41.0, 1.2, 41.2)),
    # Spain, 2020: one fire, smaller than every 2021 one.
    ("4", "Spain", datetime.date(2020, 6, 1), box(0.0, 40.0, 0.05, 40.05)),
    # Spain, 2019: one fire, larger than every other Spanish one.
    ("5", "Spain", datetime.date(2019, 6, 1), box(-2.0, 39.0, -1.0, 40.0)),
    # France, 2021: one fire.
    ("6", "France", datetime.date(2021, 7, 15), box(4.0, 44.0, 4.2, 44.2)),
]

#: The fire that must never appear: attributable to no country.
ORPHAN_FIRE = ("7", None, datetime.date(2021, 5, 5), box(-30.0, 10.0, -29.9, 10.1))


def hectares(geometry) -> float:
    """Geodesic area of a shapely polygon in hectares, computed by PROJ."""
    area, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / app.SQUARE_METRES_PER_HECTARE


def expected(gwis_id: str) -> float:
    """The area PROJ computes for one fixture fire."""
    for identifier, _, _, geometry in [*FIRES, ORPHAN_FIRE]:
        if identifier == gwis_id:
            return hectares(geometry)
    raise KeyError(gwis_id)


@pytest.fixture
def populated(db_session):
    """The fixture world: three countries, six attributable fires and one orphan."""
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    gwis_provider = DataProvider(name="GWIS", product="Global Wildfire Database v3",
                                 full_name="Global Wildfire Information System",
                                 url="https://doi.pangaea.de/10.1594/PANGAEA.943975")
    db_session.add_all([ocha_provider, gwis_provider])
    db_session.flush()

    boundaries = {}
    for code, name, geometry in COUNTRIES:
        boundary = OchaAdminBoundary(
            data_provider_id=ocha_provider.id, source_id=code, level=0, name=name,
            geometry=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            source=code, iso_code=1, iso_2=code[:2], iso_3=code, iso_name=name,
            iso_3_group=code, region1_code=1, region1_name="r1", region2_code=2,
            region2_name="r2", region3_code=3, region3_name="r3", status_code=1,
            status_name="State", valid_date=datetime.date(2025, 1, 1),
            update_date=datetime.date(2025, 1, 1), land_source="osm", view="intl",
        )
        db_session.add(boundary)
        db_session.flush()
        boundaries[name] = boundary

    for gwis_id, country, start, geometry in [*FIRES, ORPHAN_FIRE]:
        db_session.add(GwisWildfire(
            gwis_id=gwis_id,
            data_provider_id=gwis_provider.id,
            # Stored the way the importer stores it: local midnight, in a zone
            # whose name is kept alongside.
            start_date_time=datetime.datetime.combine(
                start, datetime.time(0, 0), tzinfo=datetime.timezone.utc),
            time_zone="UTC",
            perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            admin_boundary_id=boundaries[country].id if country else None,
        ))
    db_session.commit()
    return db_session


def rows_for(session, country=None, year=None) -> list[app.Row]:
    return app.compute(session, country, year, logger)


def find(rows: list[app.Row], country: str, year: int | None) -> app.Row:
    matches = [row for row in rows if row.country == country and row.year == year]
    assert len(matches) == 1, f"expected one row for {country}/{year}, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------

def test_an_output_is_required():
    """Computing a report and then printing nothing would be a strange thing to allow."""
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_either_output_alone_is_enough():
    assert app.parse_arguments(["--csv", "out.csv"]).docx is None
    assert app.parse_arguments(["--docx", "out.docx"]).csv is None


def test_the_scope_defaults_to_everything():
    parsed = app.parse_arguments(["--csv", "out.csv"])
    assert parsed.country is None
    assert parsed.year is None


# --------------------------------------------------------------------------
# The statistics themselves
# --------------------------------------------------------------------------

def test_the_area_matches_an_independent_geodesic_computation(populated):
    """PostGIS on the ellipsoid against PROJ on the ellipsoid: two implementations."""
    rows = rows_for(populated)
    spain_2021 = find(rows, "Spain", 2021)

    # Fire 2 is the largest of Spain's 2021 fires, fire 1 the smallest.
    assert spain_2021.maximum == pytest.approx(expected("2"), rel=1e-6)
    assert spain_2021.minimum == pytest.approx(expected("1"), rel=1e-6)
    assert spain_2021.total == pytest.approx(
        expected("1") + expected("2") + expected("3"), rel=1e-6)


def test_the_areas_are_in_hectares(populated):
    """An order-of-magnitude check, to catch a missing or doubled unit conversion.

    Fire 5 is a one-degree square at 39-40°N. A degree of latitude is about
    111 km; a degree of longitude there is 111 km x cos(39.5°), about 86 km. So
    roughly 111 x 86 = 9,500 km², which is ~950,000 ha — not 95 (m² mistaken for
    ha) and not 9.5e9 (m² left unconverted).
    """
    rows = rows_for(populated)
    biggest = find(rows, "Spain", 2019)
    assert 900_000 < biggest.maximum < 1_000_000


def test_each_country_and_year_gets_a_row(populated):
    rows = rows_for(populated)
    assert [(row.country, row.year_label) for row in rows] == [
        ("France", "2021"), ("France", "Total"),
        ("Spain", "2021"), ("Spain", "2020"), ("Spain", "2019"), ("Spain", "Total"),
    ]


def test_the_years_run_newest_first_with_the_total_last(populated):
    """The shape the report was asked for: years descending, then the summary."""
    spain = [row for row in rows_for(populated) if row.country == "Spain"]
    assert [row.year for row in spain] == [2021, 2020, 2019, None]
    assert spain[-1].is_total


def test_a_countrys_total_row_summarises_all_of_its_years(populated):
    """Minimum and maximum over every year, and the sum — not a total of the column."""
    rows = rows_for(populated)
    spain_total = find(rows, "Spain", None)
    years = [find(rows, "Spain", year) for year in (2021, 2020, 2019)]

    assert spain_total.minimum == pytest.approx(min(row.minimum for row in years))
    assert spain_total.maximum == pytest.approx(max(row.maximum for row in years))
    assert spain_total.total == pytest.approx(sum(row.total for row in years))
    assert spain_total.fires == 5

    # The smallest fire is 2020's and the largest is 2019's, so the total row
    # takes its two ends from different years — which a per-year total could not.
    assert spain_total.minimum == pytest.approx(expected("4"), rel=1e-6)
    assert spain_total.maximum == pytest.approx(expected("5"), rel=1e-6)


def test_a_single_fire_is_its_own_minimum_maximum_and_total(populated):
    rows = rows_for(populated)
    france = find(rows, "France", 2021)
    assert france.minimum == france.maximum == pytest.approx(france.total)
    assert france.fires == 1


def test_a_fire_with_no_country_is_excluded(populated):
    """The orphan mid-Atlantic fire must appear in no row and no total."""
    rows = rows_for(populated)
    assert sum(row.fires for row in rows if row.is_total) == len(FIRES)

    orphan_area = expected("7")
    assert all(row.maximum != pytest.approx(orphan_area, rel=1e-9) for row in rows)


def test_a_country_with_no_fires_is_absent(populated):
    """Andorra is a boundary with nothing in it; an empty row would be noise."""
    assert "Andorra" not in {row.country for row in rows_for(populated)}


# --------------------------------------------------------------------------
# Narrowing the scope
# --------------------------------------------------------------------------

def test_a_single_country_can_be_selected_by_name(populated):
    rows = rows_for(populated, country="Spain")
    assert {row.country for row in rows} == {"Spain"}


def test_a_country_can_be_selected_by_iso_3_code(populated):
    """``ESP`` is what someone reaches for before the full name."""
    by_code = rows_for(populated, country="ESP")
    by_name = rows_for(populated, country="Spain")
    assert [row.year for row in by_code] == [row.year for row in by_name]
    assert by_code[0].total == pytest.approx(by_name[0].total)


def test_the_country_is_matched_case_insensitively(populated):
    assert {row.country for row in rows_for(populated, country="spain")} == {"Spain"}
    assert {row.country for row in rows_for(populated, country="esp")} == {"Spain"}


def test_a_single_year_can_be_selected(populated):
    rows = rows_for(populated, year=2021)
    assert {row.year for row in rows} == {2021, None}
    assert {row.country for row in rows} == {"Spain", "France"}


def test_a_country_and_a_year_can_be_combined(populated):
    rows = rows_for(populated, country="Spain", year=2020)
    # One year row and its total row, identical because there is one year in scope.
    assert [row.year_label for row in rows] == ["2020", "Total"]
    assert rows[0].total == pytest.approx(rows[1].total)


def test_a_year_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    """Almost always a mistyped country; writing an empty file would hide it."""
    args = app.parse_arguments(["--country", "Atlantis", "--csv", str(tmp_path / "out.csv")])
    engine = populated.get_bind()

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, engine, logger)
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_asked_for_columns(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == ["Country", "Year", "Minimum (ha)", "Maximum (ha)", "Total (ha)"]
    assert table[1][:2] == ["France", "2021"]
    assert [line[1] for line in table if line[0] == "Spain"] == ["2021", "2020", "2019", "Total"]


def test_the_csv_numbers_are_machine_readable(populated, tmp_path):
    """No thousands separators: a CSV is read by a program more often than by a person."""
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        for column in ("Minimum (ha)", "Maximum (ha)", "Total (ha)"):
            assert "," not in row[column]
            float(row[column])  # parses without cleaning


def test_the_csv_totals_agree_with_the_computed_rows(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    computed = rows_for(populated)
    app.write_csv(computed, target, logger)

    with target.open(encoding="utf-8") as handle:
        written = {(row["Country"], row["Year"]): float(row["Total (ha)"])
                   for row in csv.DictReader(handle)}

    for row in computed:
        assert written[(row.country, row.year_label)] == pytest.approx(row.total, abs=0.01)


def test_the_docx_is_a_word_table_with_every_row(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, None, logger)

    document = docx.Document(str(target))
    table = document.tables[0]
    assert len(table.rows) == len(computed) + 1  # + the header
    assert [cell.text for cell in table.rows[0].cells] == [
        "Country", "Year", "Minimum (ha)", "Maximum (ha)", "Total (ha)"]
    assert [cell.text for cell in table.rows[1].cells][:2] == ["France", "2021"]


def test_the_docx_total_rows_are_bold(populated, tmp_path):
    """What separates the country blocks visually, in place of the ASCII rule."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, None, logger)

    table = docx.Document(str(target)).tables[0]
    for row, written in zip(computed, table.rows[1:]):
        bold = [run.bold for cell in written.cells for run in cell.paragraphs[0].runs]
        assert all(value is row.is_total for value in bold), f"{row.country}/{row.year_label}"


def test_the_docx_records_the_scope_it_was_run_with(populated, tmp_path):
    """A document detached from its command line should still say what it covers."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, "Spain", 2021), target, "Spain", 2021, logger)

    prose = "\n".join(paragraph.text for paragraph in docx.Document(str(target)).paragraphs)
    assert "Spain" in prose and "2021" in prose
    assert "hectares" in prose


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "b.csv"),
                                "--docx", str(tmp_path / "b.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "b.csv").exists()
    assert (tmp_path / "b.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2021" / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)
    assert target.exists()
