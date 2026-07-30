#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ICNF burnt-area statistics application.

The fires here are inserted through the ORM rather than imported from a
shapefile: what has to be asserted is arithmetic over known areas in known years,
and building that by hand is both quicker and clearer than arranging for an
importer to produce it.

The absolute areas are checked against :mod:`pyproj`, which computes the same
geodesic area through PROJ rather than through PostGIS. Two independent
implementations agreeing is worth considerably more than a magic number copied out
of whatever the code returned the first time it ran.

The ICNF fixture carries two things the GWIS and GFA ones do not, because they are
the two facts this report has to get right: fires whose **published year and start
date disagree in kind** — 71% of the real dataset has a placeholder date — and a
fire digitised into the **sea** while still carrying a Portuguese boundary.
"""

import csv
import datetime
import logging

import pytest

from pyproj import Geod
from shapely.geometry import MultiPolygon
from shapely.geometry import box
from sqlalchemy import select

from src.apps.statistics.wildfires.portugal_icnf import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import icnf
from src.providers import ocha
from src.providers.icnf.wildfire import IcnfWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

logger = logging.getLogger("test-icnf-statistics")

GEOD = Geod(ellps="WGS84")

#: Portugal wide enough to hold the fixture fires, and Spain next door so that a
#: cross-border perimeter has somewhere to go.
COUNTRIES = [
    ("PRT", "Portugal", box(-9.6, 37.0, -6.2, 42.2)),
    ("ESP", "Spain", box(-6.2, 36.0, 3.0, 43.8)),
]

#: (sgif_code, year, precision, perimeter). Sizes are deliberately unequal within
#: a year so a minimum and a maximum are distinguishable from each other and from
#: the total.
#:
#: The 1985 fires carry :data:`~src.providers.icnf.PRECISION_YEAR`, which in the
#: real data means the layer published no date and the importer stored 1 January
#: as a placeholder. The report has to group them by 1985 all the same.
FIRES = [
    # 2024: three dated fires of clearly different sizes.
    ("2024-1", 2024, icnf.PRECISION_DAY, box(-8.0, 40.0, -7.9, 40.1)),
    ("2024-2", 2024, icnf.PRECISION_DAY, box(-8.5, 40.0, -8.1, 40.4)),
    ("2024-3", 2024, icnf.PRECISION_DAY, box(-7.5, 40.0, -7.3, 40.2)),
    # 2023: one dated fire, smaller than every 2024 one.
    ("2023-1", 2023, icnf.PRECISION_DAY, box(-8.0, 39.0, -7.95, 39.05)),
    # 1985: two undated fires, the larger one bigger than anything else.
    ("1985-1", 1985, icnf.PRECISION_YEAR, box(-8.0, 41.0, -7.0, 42.0)),
    ("1985-2", 1985, icnf.PRECISION_YEAR, box(-9.0, 38.0, -8.9, 38.1)),
]

#: Filed with a Portuguese boundary, digitised into the Atlantic. 2019 holds this
#: and the cross-border fire and nothing else.
IN_THE_SEA = box(-14.0, 39.0, -13.9, 39.1)

#: Filed with a Portuguese boundary, actually over the border in Spain.
OVER_THE_BORDER = box(-5.0, 40.0, -4.9, 40.1)


def hectares(geometry) -> float:
    """Geodesic area of a shapely polygon in hectares, computed by PROJ."""
    area, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / app.SQUARE_METRES_PER_HECTARE


def expected(sgif_code: str) -> float:
    """The area PROJ computes for one fixture fire."""
    for code, _, _, geometry in FIRES:
        if code == sgif_code:
            return hectares(geometry)
    raise KeyError(sgif_code)


@pytest.fixture
def populated(db_session):
    """Two countries and six consistent Portuguese fires across three years."""
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    icnf_provider = DataProvider(name=icnf.PROVIDER_NAME, product=icnf.PROVIDER_PRODUCT,
                                 full_name=icnf.PROVIDER_FULL_NAME, url=icnf.PROVIDER_URL)
    db_session.add_all([ocha_provider, icnf_provider])
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

    for code, year, precision, geometry in FIRES:
        # A 'year' row's start is 1 January of its year — a placeholder satisfying
        # a NOT NULL column, exactly as the importer stores it.
        start = (datetime.datetime(year, 1, 1, tzinfo=datetime.timezone.utc)
                 if precision == icnf.PRECISION_YEAR
                 else datetime.datetime(year, 7, 1, tzinfo=datetime.timezone.utc))
        db_session.add(IcnfWildfire(
            source_layer=f"ardida_{year}", sgif_code=code, year=year,
            date_time_precision=precision, area_ha_gis=hectares(geometry),
            data_provider_id=icnf_provider.id,
            start_date_time=start, time_zone=icnf.DEFAULT_TIME_ZONE,
            perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            admin_boundary_id=boundaries["Portugal"].id,
        ))
    db_session.commit()
    return db_session


@pytest.fixture
def misattributed(populated):
    """``populated`` plus two 2019 fires that are not where they are filed."""
    portugal = populated.scalar(
        select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "PRT"))
    provider_id = populated.scalar(
        select(DataProvider.id).where(DataProvider.name == icnf.PROVIDER_NAME))
    for code, geometry in (("2019-sea", IN_THE_SEA), ("2019-border", OVER_THE_BORDER)):
        populated.add(IcnfWildfire(
            source_layer="ardida_2019", sgif_code=code, year=2019,
            date_time_precision=icnf.PRECISION_DAY, area_ha_gis=hectares(geometry),
            data_provider_id=provider_id,
            start_date_time=datetime.datetime(2019, 7, 1, tzinfo=datetime.timezone.utc),
            time_zone=icnf.DEFAULT_TIME_ZONE,
            perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            admin_boundary_id=portugal.id,
        ))
    populated.commit()
    return populated


def rows_for(session, year=None, method=app.AREA_METHOD_GEODESIC,
             country_source=app.COUNTRY_SOURCE_GEOMETRY) -> list[app.Row]:
    return app.compute(session, year, logger, method, country_source)


def find(rows: list[app.Row], year: int | None, country: str = "Portugal") -> app.Row:
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


def test_the_scope_defaults_to_every_year():
    assert app.parse_arguments(["--csv", "out.csv"]).year is None


def test_there_is_no_country_option(capsys):
    """The ICNF publishes one country, so there is nothing to select between.

    Refused with a message that says so, rather than argparse's prefix matching
    resolving it to ``--country-source`` and complaining about an invalid choice —
    which is what anyone copying a GWIS command line would otherwise see.
    """
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Portugal"])

    assert "no --country here" in capsys.readouterr().err


def test_the_defaults_match_the_other_reports():
    parsed = app.parse_arguments(["--csv", "out.csv"])
    assert parsed.area_method == app.AREA_METHOD_GEODESIC
    assert parsed.country_source == app.COUNTRY_SOURCE_GEOMETRY


def test_the_columns_match_the_other_reports():
    """So the three CSVs can be concatenated and compared."""
    from src.apps.statistics.wildfires.gfa import wildfire_statistics as gfa_app
    from src.apps.statistics.wildfires.gwis import wildfire_statistics as gwis_app

    assert app.COLUMNS == gfa_app.COLUMNS == gwis_app.COLUMNS


# --------------------------------------------------------------------------
# The statistics themselves
# --------------------------------------------------------------------------

def test_the_area_matches_an_independent_geodesic_computation(populated):
    """PostGIS on the ellipsoid against PROJ on the ellipsoid: two implementations."""
    rows = rows_for(populated)
    year_2024 = find(rows, 2024)

    assert year_2024.maximum == pytest.approx(expected("2024-2"), rel=1e-6)
    assert year_2024.minimum == pytest.approx(expected("2024-1"), rel=1e-6)
    assert year_2024.total == pytest.approx(
        expected("2024-1") + expected("2024-2") + expected("2024-3"), rel=1e-6)


def test_the_areas_are_in_hectares(populated):
    """An order-of-magnitude check, to catch a missing or doubled unit conversion.

    ``1985-1`` is a one-degree square at 41-42°N. A degree of latitude is about
    111 km; a degree of longitude there is 111 km x cos(41.5°), about 83 km. So
    roughly 111 x 83 = 9,200 km², which is ~920,000 ha — not 92 (m² mistaken for
    ha) and not 9.2e9 (m² left unconverted).
    """
    assert 850_000 < find(rows_for(populated), 1985).maximum < 1_000_000


def test_each_year_gets_a_row_newest_first_with_the_total_last(populated):
    assert [(row.country, row.year_label) for row in rows_for(populated)] == [
        ("Portugal", "2024"), ("Portugal", "2023"), ("Portugal", "1985"),
        ("Portugal", "Total"),
    ]


def test_the_total_row_summarises_every_year(populated):
    """Fires and hectares are sums; the minimum and maximum are not."""
    rows = rows_for(populated)
    total = find(rows, None)
    years = [find(rows, year) for year in (2024, 2023, 1985)]

    assert total.fires == sum(row.fires for row in years) == len(FIRES)
    assert total.total == pytest.approx(sum(row.total for row in years))
    assert total.minimum == pytest.approx(min(row.minimum for row in years))
    assert total.maximum == pytest.approx(max(row.maximum for row in years))
    # The two ends come from different years, which a per-year total could not give.
    assert total.minimum == pytest.approx(expected("2023-1"), rel=1e-6)
    assert total.maximum == pytest.approx(expected("1985-1"), rel=1e-6)


def test_each_row_counts_its_own_wildfire_events(populated):
    rows = rows_for(populated)
    assert find(rows, 2024).fires == 3
    assert find(rows, 2023).fires == 1
    assert find(rows, 1985).fires == 2


# --------------------------------------------------------------------------
# The year: published, not derived
# --------------------------------------------------------------------------

def test_undated_fires_are_grouped_by_their_published_year(populated):
    """71% of the real dataset has no date; those fires still have to count.

    The 1985 fires carry ``date_time_precision = 'year'`` and a 1 January
    placeholder. Grouping on the published ``Ano`` puts them in 1985 without ever
    reading that placeholder.
    """
    year_1985 = find(rows_for(populated), 1985)
    assert year_1985.fires == 2
    assert year_1985.total == pytest.approx(
        expected("1985-1") + expected("1985-2"), rel=1e-6)


def test_the_published_year_is_used_even_when_the_start_date_disagrees(populated):
    """A fire filed under one year whose date falls in another follows the filing.

    ``Ano`` is the year the ICNF published the fire under and the layer it came
    from; the start date is an attribute of the fire. When they disagree the
    report follows the provider, because that is what a published yearly total is
    a total of.
    """
    portugal = populated.scalar(
        select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "PRT"))
    geometry = box(-8.2, 40.5, -8.15, 40.55)
    populated.add(IcnfWildfire(
        source_layer="ardida_2022", sgif_code="straddler", year=2022,
        date_time_precision=icnf.PRECISION_MINUTE, area_ha_gis=hectares(geometry),
        data_provider_id=populated.scalar(
            select(DataProvider.id).where(DataProvider.name == icnf.PROVIDER_NAME)),
        # Filed under 2022; burnt on New Year's Eve into 2023 by the clock.
        start_date_time=datetime.datetime(2023, 1, 1, 0, 30, tzinfo=datetime.timezone.utc),
        time_zone=icnf.DEFAULT_TIME_ZONE,
        perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
        admin_boundary_id=portugal.id,
    ))
    populated.commit()

    rows = rows_for(populated)
    # It lands in 2022, its published year — not in 2023, where its clock puts it.
    assert find(rows, 2022).fires == 1
    assert find(rows, 2022).total == pytest.approx(hectares(geometry), rel=1e-6)
    # And 2023 is untouched: still just the one fire the fixture put there.
    assert find(rows, 2023).fires == 1
    assert find(rows, 2023).total == pytest.approx(expected("2023-1"), rel=1e-6)


def test_a_single_year_can_be_selected(populated):
    rows = rows_for(populated, year=1985)
    assert [row.year_label for row in rows] == ["1985", "Total"]
    assert rows[0].total == pytest.approx(rows[1].total)


def test_a_year_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    args = app.parse_arguments(["--year", "1999", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# How the area is measured
# --------------------------------------------------------------------------

def test_the_two_area_methods_agree(populated):
    geodesic = rows_for(populated, method=app.AREA_METHOD_GEODESIC)
    projected = rows_for(populated, method=app.AREA_METHOD_EQUAL_AREA)

    for measured, transformed in zip(geodesic, projected):
        assert (measured.country, measured.year) == (transformed.country, transformed.year)
        for figure in ("minimum", "maximum", "total"):
            assert getattr(transformed, figure) == pytest.approx(
                getattr(measured, figure), rel=1e-4), f"{measured.year} {figure}"


def test_an_unknown_area_method_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--area-method", "national-grid"])
    with pytest.raises(ValueError, match="unknown area method"):
        app.burnt_area("national-grid")


def test_the_published_national_grid_is_not_offered():
    """EPSG:3763 reproduces ``AreaHaSIG`` but is conformal, not equal-area.

    It is 0.03% out on the mainland and **7.6% out in the Azores**, and a report
    cannot know in advance that no island fire will appear in it. Asserted here so
    that the omission is deliberate and stays that way.
    """
    assert icnf.SOURCE_SRID == 3763
    assert str(icnf.SOURCE_SRID) not in " ".join(app.AREA_METHODS)
    assert app.EQUAL_AREA_SRID != icnf.SOURCE_SRID


# --------------------------------------------------------------------------
# Where the country comes from
# --------------------------------------------------------------------------

def test_both_sources_agree_when_the_dataset_is_consistent(populated):
    by_geometry = rows_for(populated, country_source=app.COUNTRY_SOURCE_GEOMETRY)
    by_report = rows_for(populated, country_source=app.COUNTRY_SOURCE_REPORTED)

    assert [(r.country, r.year, r.fires) for r in by_geometry] == \
           [(r.country, r.year, r.fires) for r in by_report]


def test_an_unknown_country_source_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "vibes"])
    with pytest.raises(ValueError, match="unknown country source"):
        app.country_columns("vibes")


def test_a_perimeter_in_the_sea_is_dropped(misattributed):
    """A Portuguese ``admin_boundary_id`` is not evidence the fire was on land.

    This is the single-country case for ``--country-source``: not choosing between
    countries, but catching what is in none of them.
    """
    geometry = rows_for(misattributed, year=2019,
                        country_source=app.COUNTRY_SOURCE_GEOMETRY)
    assert "2019-sea" not in {row.country for row in geometry}
    portugal = [row for row in geometry if row.country == "Portugal"]
    assert portugal == [], "the sea fire was the only Portuguese-filed 2019 fire on land"


def test_a_cross_border_perimeter_is_attributed_where_it_actually_is(misattributed):
    """The Country column is what makes this visible, which is why it is kept."""
    geometry = rows_for(misattributed, year=2019,
                        country_source=app.COUNTRY_SOURCE_GEOMETRY)
    assert [(row.country, row.year_label, row.fires) for row in geometry] == [
        ("Spain", "2019", 1), ("Spain", "Total", 1)]
    assert geometry[0].total == pytest.approx(hectares(OVER_THE_BORDER), rel=1e-6)


def test_trusting_the_row_puts_both_in_portugal(misattributed):
    """What the default protects against: two fires counted in a country neither is in."""
    reported = rows_for(misattributed, year=2019,
                        country_source=app.COUNTRY_SOURCE_REPORTED)
    assert [(row.country, row.year_label, row.fires) for row in reported] == [
        ("Portugal", "2019", 2), ("Portugal", "Total", 2)]
    assert reported[0].total == pytest.approx(
        hectares(IN_THE_SEA) + hectares(OVER_THE_BORDER), rel=1e-6)


def test_the_consistent_years_are_untouched_either_way(misattributed):
    rows = rows_for(misattributed, country_source=app.COUNTRY_SOURCE_GEOMETRY)
    assert find(rows, 2024).fires == 3
    assert find(rows, None).fires == len(FIRES)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_asked_for_columns(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == list(app.COLUMNS)
    assert [line[1] for line in table[1:]] == ["2024", "2023", "1985", "Total"]
    assert {line[0] for line in table[1:]} == {"Portugal"}


def test_the_csv_numbers_are_machine_readable(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        for column in ("Fires", "Minimum (ha)", "Maximum (ha)", "Total (ha)"):
            assert "," not in row[column]
            float(row[column])


def test_the_docx_is_a_word_table_with_every_row(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    assert len(table.rows) == len(computed) + 1
    assert [cell.text for cell in table.rows[0].cells] == list(app.COLUMNS)


def test_the_docx_total_row_is_bold(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    for row, written in zip(computed, table.rows[1:]):
        bold = [run.bold for cell in written.cells for run in cell.paragraphs[0].runs]
        assert all(value is row.is_total for value in bold), row.year_label


def test_the_docx_names_the_dataset_and_the_scope(populated, tmp_path):
    """An ICNF report must not be mistakable for a GWIS or GFA one."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, year=2024), target, 2024, logger)

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    prose = "\n".join(p.text for p in document.paragraphs)
    assert any("ICNF" in heading for heading in headings)
    assert "2024" in prose and "hectares" in prose
    # The year rule is stated in the document, not only in the manual.
    assert "Ano" in prose


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "b.csv"),
                                "--docx", str(tmp_path / "b.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "b.csv").exists()
    assert (tmp_path / "b.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2024" / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    assert target.exists()
