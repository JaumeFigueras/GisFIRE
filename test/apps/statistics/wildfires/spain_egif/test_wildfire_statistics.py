#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the EGIF burnt-area statistics application.

The fires are inserted through the ORM with areas chosen by hand. Unlike the
other three reports there is nothing to check against an independent geometry
library here — the areas are not computed from anything, they are the numbers on
the report form — so what has to be asserted instead is that the report says back
exactly what was filed, and that it never mixes the five surfaces EGIF publishes.

The fixture carries the three facts this report has to get right: a fire whose
**forest area is NULL** (the form does not say, which is not the same as zero), a
fire whose forest area is a reported **zero** while it burnt agricultural land,
and a fire whose **campaign and detection date disagree**.
"""

import argparse
import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box

from src.apps.statistics.wildfires.spain_egif import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import ocha
from src.providers import spain_egif
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.providers.spain_egif.ignition import EgifIgnition
from src.providers.spain_egif.wildfire import EgifWildfire

logger = logging.getLogger("test-egif-statistics")

UTC = datetime.timezone.utc

#: (report_number, campaign, wooded, non_wooded, agricultural, other) in hectares.
#: ``forest`` is wooded + non-wooded, as EGIF publishes it, and is filled in by the
#: fixture rather than written out, so the two can never drift apart here.
#:
#: Sizes are deliberately unequal within a campaign so a minimum and a maximum are
#: distinguishable from each other and from the total.
FIRES = [
    # 2023: three fires, forest totals 30, 300 and 3 ha.
    ("2023080001", 2023, 10.0, 20.0, 5.0, 1.0),
    ("2023080002", 2023, 100.0, 200.0, 0.0, 0.0),
    ("2023080003", 2023, 1.0, 2.0, 50.0, 0.0),
    # 2022: one fire, forest total 7.5 ha, larger than nothing else.
    ("2022310001", 2022, 2.5, 5.0, 0.0, 0.0),
]

#: Burnt only farmland: its forest total is a reported **zero**, which is an
#: answer and has to be counted. Campaign 2021, on its own, so a minimum of 0.00
#: cannot be confused with another fire's.
FARMLAND_ONLY = ("2021280001", 2021, 0.0, 0.0, 42.0, 0.0)

#: Reports no forest area at all — an Excel-only row whose form is blank. Campaign
#: 2020, on its own, so that excluding it empties a campaign visibly.
UNREPORTED = ("2020120001", 2020)


def forest(report_number: str) -> float:
    """The forest total of one fixture fire: wooded plus non-wooded, as EGIF has it."""
    for number, _, wooded, non_wooded, _, _ in [*FIRES, FARMLAND_ONLY]:
        if number == report_number:
            return wooded + non_wooded
    raise KeyError(report_number)


def burnt(report_number: str) -> float:
    """Everything one fixture fire burnt: forest plus agricultural plus other."""
    for number, _, wooded, non_wooded, agricultural, other in [*FIRES, FARMLAND_ONLY]:
        if number == report_number:
            return wooded + non_wooded + agricultural + other
    raise KeyError(report_number)


def add_fire(session, provider_id, number, campaign, wooded, non_wooded,
             agricultural, other, detected=None):
    """One EGIF fire with its areas filled in as the export publishes them."""
    session.add(EgifWildfire(
        report_number=number, campaign=campaign,
        province_ine_code=number[4:6],
        data_provider_id=provider_id,
        start_date_time=detected or datetime.datetime(campaign, 7, 1, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE,
        area_ha_wooded=wooded, area_ha_non_wooded=non_wooded,
        area_ha_forest_total=None if wooded is None else wooded + non_wooded,
        area_ha_agricultural=agricultural, area_ha_other_non_forest=other,
    ))


@pytest.fixture
def provider_id(db_session):
    provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                            product=spain_egif.PROVIDER_PRODUCT,
                            full_name=spain_egif.PROVIDER_FULL_NAME,
                            url=spain_egif.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider.id


@pytest.fixture
def populated(db_session, provider_id):
    """Four fires over two campaigns, all of them reporting every surface."""
    for number, campaign, wooded, non_wooded, agricultural, other in FIRES:
        add_fire(db_session, provider_id, number, campaign, wooded, non_wooded,
                 agricultural, other)
    db_session.commit()
    return db_session


@pytest.fixture
def with_edge_cases(populated, provider_id):
    """``populated`` plus the reported zero and the unreported form."""
    add_fire(populated, provider_id, *FARMLAND_ONLY)
    populated.add(EgifWildfire(
        report_number=UNREPORTED[0], campaign=UNREPORTED[1],
        province_ine_code=UNREPORTED[0][4:6],
        data_provider_id=provider_id,
        start_date_time=datetime.datetime(UNREPORTED[1], 7, 1, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE,
    ))
    populated.commit()
    return populated


def rows_for(session, year=None, surface=app.SURFACE_FOREST, min_area=None,
             country_source=app.COUNTRY_SOURCE_FILED, region=None) -> list[app.Row]:
    return app.compute(session, year, logger, surface, min_area, country_source, region)


def find(rows: list[app.Row], year: int | None) -> app.Row:
    matches = [row for row in rows if row.year == year]
    assert len(matches) == 1, f"expected one row for {year}, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_either_output_alone_is_enough():
    assert app.parse_arguments(["--csv", "out.csv"]).docx is None
    assert app.parse_arguments(["--docx", "out.docx"]).csv is None


def test_the_defaults_are_every_campaign_of_forest_area():
    parsed = app.parse_arguments(["--csv", "out.csv"])
    assert parsed.year is None
    assert parsed.surface == app.SURFACE_FOREST
    assert parsed.min_area is None


def test_the_country_source_defaults_to_filed_unlike_the_other_reports():
    """Deliberately the opposite default: 'geometry' would drop half the archive."""
    assert app.parse_arguments(["--csv", "out.csv"]).country_source == app.COUNTRY_SOURCE_FILED


def test_an_unknown_country_source_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "vibes"])
    with pytest.raises(ValueError, match="unknown country source"):
        app.country_columns("vibes")


def test_the_columns_match_the_other_reports():
    """So the four CSVs can be concatenated and compared."""
    from src.apps.statistics.wildfires.gfa import wildfire_statistics as gfa_app
    from src.apps.statistics.wildfires.gwis import wildfire_statistics as gwis_app
    from src.apps.statistics.wildfires.portugal_icnf import wildfire_statistics as icnf_app

    assert app.COLUMNS == gfa_app.COLUMNS == gwis_app.COLUMNS == icnf_app.COLUMNS


def test_there_is_no_country_option(capsys):
    """EGIF is the Spanish national statistic; there is nothing to select between."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Spain"])

    assert "no --country here" in capsys.readouterr().err


def test_there_is_no_area_method_option(capsys):
    """The one refusal that carries the whole point: nothing here is measured.

    Anyone passing it has copied a command line from a perimeter report and is
    about to assume these hectares came off an ellipsoid.
    """
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--area-method", "geodesic"])

    error = capsys.readouterr().err
    assert "no --area-method here" in error
    assert "--surface" in error


def test_an_unknown_surface_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--surface", "grassland"])
    with pytest.raises(ValueError, match="unknown surface"):
        app.reported_surface("grassland")


@pytest.mark.parametrize("value", ["five", "", "-5", "nan", "inf"])
def test_a_nonsense_minimum_area_is_refused(value):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-area", value])
    with pytest.raises(argparse.ArgumentTypeError):
        app.hectares(value)


# --------------------------------------------------------------------------
# The statistics themselves
# --------------------------------------------------------------------------

def test_the_report_gives_back_the_areas_that_were_filed(populated):
    """Nothing is computed here, so the test is that nothing is transformed."""
    year_2023 = find(rows_for(populated), 2023)

    assert year_2023.minimum == pytest.approx(forest("2023080003"))
    assert year_2023.maximum == pytest.approx(forest("2023080002"))
    assert year_2023.total == pytest.approx(
        forest("2023080001") + forest("2023080002") + forest("2023080003"))
    assert year_2023.fires == 3


def test_each_campaign_gets_a_row_newest_first_with_the_total_last(populated):
    assert [(row.country, row.year_label) for row in rows_for(populated)] == [
        ("Spain", "2023"), ("Spain", "2022"), ("Spain", "Total"),
    ]


def test_the_total_row_summarises_every_campaign(populated):
    rows = rows_for(populated)
    total = find(rows, None)
    years = [find(rows, year) for year in (2023, 2022)]

    assert total.fires == sum(row.fires for row in years) == len(FIRES)
    assert total.total == pytest.approx(sum(row.total for row in years))
    assert total.minimum == pytest.approx(min(row.minimum for row in years))
    assert total.maximum == pytest.approx(max(row.maximum for row in years))
    # The two ends come from different campaigns, which a per-campaign total could not give.
    assert total.minimum == pytest.approx(forest("2023080003"))
    assert total.maximum == pytest.approx(forest("2023080002"))


def test_the_country_column_is_spain_on_every_row(populated):
    """Constant, and spelled as the other three reports spell it."""
    assert {row.country for row in rows_for(populated)} == {"Spain"}
    assert app.COUNTRY_NAME == "Spain"


def test_a_single_campaign_can_be_selected(populated):
    rows = rows_for(populated, year=2022)
    assert [row.year_label for row in rows] == ["2022", "Total"]
    assert rows[0].total == pytest.approx(rows[1].total)


def test_a_campaign_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    args = app.parse_arguments(["--year", "1999", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# The campaign, not the clock
# --------------------------------------------------------------------------

def test_the_campaign_is_used_even_when_the_detection_date_disagrees(populated, provider_id):
    """A fire filed under one campaign but detected in the next follows the filing."""
    add_fire(populated, provider_id, "2019330001", 2019, 4.0, 6.0, 0.0, 0.0,
             detected=datetime.datetime(2020, 1, 1, 0, 30, tzinfo=UTC))
    populated.commit()

    rows = rows_for(populated)
    assert find(rows, 2019).fires == 1
    assert find(rows, 2019).total == pytest.approx(10.0)
    assert 2020 not in {row.year for row in rows}


# --------------------------------------------------------------------------
# Which surface
# --------------------------------------------------------------------------

def test_the_two_forest_parts_add_up_to_the_forest_total(populated):
    """EGIF's own arithmetic, which the report must not disturb."""
    wooded = find(rows_for(populated, surface=app.SURFACE_WOODED), 2023)
    non_wooded = find(rows_for(populated, surface=app.SURFACE_NON_WOODED), 2023)
    total = find(rows_for(populated, surface=app.SURFACE_FOREST), 2023)

    assert wooded.total + non_wooded.total == pytest.approx(total.total)
    assert wooded.fires == non_wooded.fires == total.fires


def test_the_surfaces_are_not_mixed(populated):
    """Each one reports its own column and no other."""
    year = 2023
    figures = {surface: find(rows_for(populated, surface=surface), year).total
               for surface in app.SURFACES}

    assert figures[app.SURFACE_WOODED] == pytest.approx(111.0)
    assert figures[app.SURFACE_NON_WOODED] == pytest.approx(222.0)
    assert figures[app.SURFACE_FOREST] == pytest.approx(333.0)
    assert figures[app.SURFACE_AGRICULTURAL] == pytest.approx(55.0)
    assert figures[app.SURFACE_OTHER_NON_FOREST] == pytest.approx(1.0)


def test_burnt_adds_the_forest_and_non_forest_areas(populated):
    """The one composite, and the one EGIF does not publish."""
    year_2023 = find(rows_for(populated, surface=app.SURFACE_BURNT), 2023)

    assert year_2023.total == pytest.approx(
        burnt("2023080001") + burnt("2023080002") + burnt("2023080003"))
    # 2023080003 burnt 3 ha of forest and 50 of farmland: under 'burnt' it is the
    # middle fire, not the smallest, so this is not the forest ordering renamed.
    assert year_2023.minimum == pytest.approx(burnt("2023080001"))
    assert year_2023.maximum == pytest.approx(burnt("2023080002"))


def test_the_minimum_of_two_surfaces_is_not_the_minimum_of_their_sum(populated):
    """Why the report tells you to ask for 'burnt' rather than add two runs.

    The smallest forest fire and the smallest agricultural fire are different
    fires, so their minima do not add up to the smallest fire overall.
    """
    forest_rows = find(rows_for(populated, surface=app.SURFACE_FOREST), 2023)
    agricultural = find(rows_for(populated, surface=app.SURFACE_AGRICULTURAL), 2023)
    combined = find(rows_for(populated, surface=app.SURFACE_BURNT), 2023)

    assert combined.total == pytest.approx(
        forest_rows.total + agricultural.total
        + find(rows_for(populated, surface=app.SURFACE_OTHER_NON_FOREST), 2023).total)
    assert combined.minimum != pytest.approx(forest_rows.minimum + agricultural.minimum)


# --------------------------------------------------------------------------
# Reported, unreported, and zero
# --------------------------------------------------------------------------

def test_a_reported_zero_is_counted(with_edge_cases):
    """A fire that burnt only farmland reports 0.00 ha of forest, which is an answer."""
    year_2021 = find(rows_for(with_edge_cases), 2021)

    assert year_2021.fires == 1
    assert year_2021.minimum == year_2021.maximum == year_2021.total == 0.0


def test_the_same_fire_is_not_zero_under_burnt(with_edge_cases):
    """Which is the check that the zero was the forest column and not a dropped row."""
    year_2021 = find(rows_for(with_edge_cases, surface=app.SURFACE_BURNT), 2021)

    assert year_2021.fires == 1
    assert year_2021.total == pytest.approx(burnt(FARMLAND_ONLY[0])) == 42.0


def test_an_unreported_surface_is_not_a_zero(with_edge_cases):
    """A blank form is a silence, and a silence is left out of the count as well.

    Counting it would put a fire in the Fires column whose hectares are in none of
    the three figures beside it.
    """
    rows = rows_for(with_edge_cases)

    assert 2020 not in {row.year for row in rows}, "the only 2020 fire reports no forest area"
    assert find(rows, None).fires == len(FIRES) + 1  # the four, plus the reported zero


def test_a_fire_counts_under_the_surfaces_it_does_report(with_edge_cases, provider_id):
    """Reporting one surface and not another is per-surface, not per-fire."""
    populated = with_edge_cases
    populated.add(EgifWildfire(
        report_number="2018410001", campaign=2018, province_ine_code="41",
        data_provider_id=provider_id,
        start_date_time=datetime.datetime(2018, 7, 1, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE,
        area_ha_agricultural=9.0,  # and no forest figure at all
    ))
    populated.commit()

    assert 2018 not in {row.year for row in rows_for(populated)}
    agricultural = find(rows_for(populated, surface=app.SURFACE_AGRICULTURAL), 2018)
    assert agricultural.fires == 1
    assert agricultural.total == pytest.approx(9.0)
    # And under 'burnt' it counts too, the unreported components contributing nothing.
    assert find(rows_for(populated, surface=app.SURFACE_BURNT), 2018).total == pytest.approx(9.0)


# --------------------------------------------------------------------------
# The minimum burnt area
# --------------------------------------------------------------------------

def test_no_minimum_area_counts_every_fire(populated):
    assert rows_for(populated, min_area=None) == rows_for(populated)


def test_the_smaller_fires_stop_being_counted(populated):
    """2023's forest totals are 3, 30 and 300 ha; keep the largest two."""
    year_2023 = find(rows_for(populated, min_area=10.0), 2023)

    assert year_2023.fires == 2
    assert year_2023.minimum == pytest.approx(forest("2023080001"))
    assert year_2023.total == pytest.approx(forest("2023080001") + forest("2023080002"))


def test_a_campaign_whose_fires_are_all_too_small_drops_out(populated):
    """2022 holds one fire of 7.5 ha and nothing else, so the campaign goes with it."""
    rows = rows_for(populated, min_area=10.0)

    assert [row.year_label for row in rows] == ["2023", "Total"]
    assert find(rows, None).fires == 2


def test_a_threshold_above_every_fire_reports_nothing(populated):
    assert rows_for(populated, min_area=10_000.0) == []


def test_a_reported_zero_is_dropped_by_any_positive_threshold(with_edge_cases):
    assert 2021 in {row.year for row in rows_for(with_edge_cases, min_area=0.0)}
    assert 2021 not in {row.year for row in rows_for(with_edge_cases, min_area=0.5)}


def test_an_empty_report_names_the_threshold(populated, tmp_path):
    args = app.parse_arguments(["--min-area", "10000", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="--min-area"):
        app.report(args, populated.get_bind(), logger)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_asked_for_columns(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == list(app.COLUMNS)
    assert [line[1] for line in table[1:]] == ["2023", "2022", "Total"]
    assert {line[0] for line in table[1:]} == {"Spain"}


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


def test_the_docx_says_the_area_is_reported_and_which_one(populated, tmp_path):
    """An EGIF report must not be mistakable for a perimeter one, or for another surface."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, surface=app.SURFACE_AGRICULTURAL), target, 2023,
                   logger, surface=app.SURFACE_AGRICULTURAL)

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    prose = "\n".join(p.text for p in document.paragraphs)
    assert any("EGIF" in heading for heading in headings)
    assert "reported by EGIF" in prose and "not" in prose
    assert "SuperficieAgricola" in prose
    assert "2023" in prose
    # The incompleteness of a freshly exported campaign is in the document itself.
    assert "floor" in prose


def test_the_docx_names_the_minimum_area(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, min_area=5.0), target, None, logger, min_area=5.0)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "5 ha or more" in prose


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "b.csv"),
                                "--docx", str(tmp_path / "b.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "b.csv").exists()
    assert (tmp_path / "b.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2023" / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    assert target.exists()


# --------------------------------------------------------------------------
# One statement
# --------------------------------------------------------------------------

def test_the_whole_report_is_one_statement(populated, monkeypatch):
    """This report does no geometry, so it needs none of the per-year machinery."""
    built = []
    original = app.statistics_query

    def spy(*arguments, **keywords):
        built.append(arguments)
        return original(*arguments, **keywords)

    monkeypatch.setattr(app, "statistics_query", spy)
    rows_for(populated)

    assert len(built) == 1


def test_the_total_row_is_combined_from_the_campaigns_measured(populated):
    """The summary row comes from no statement of its own: it is arithmetic."""
    rows = rows_for(populated)
    campaigns = [row for row in rows if not row.is_total]

    assert find(rows, None) == app.combine(campaigns, "Spain", None)


# --------------------------------------------------------------------------
# Where the country comes from, and the points in the sea
# --------------------------------------------------------------------------

#: Spain, and France next door so a coordinate over the border has somewhere to go.
COUNTRIES = [
    ("ESP", "Spain", box(-9.3, 36.0, 3.0, 43.8)),
    ("FRA", "France", box(3.0, 42.0, 8.0, 51.0)),
]

#: (report_number, longitude, latitude or None, forest hectares). ``None`` for the
#: coordinate means the fire publishes no point at all, which half the archive does.
LOCATED = [
    ("2015280001", -3.70, 40.42, 10.0),   # Madrid: inland, in Spain
    ("2015280002", -12.00, 40.00, 20.0),  # the Atlantic: a point in no country
    ("2015280003", 5.00, 44.00, 30.0),    # over the French border
    ("2015280004", None, None, 40.0),     # no coordinate published
]


@pytest.fixture
def located(db_session, provider_id):
    """Four 2015 fires: one in Spain, one in the sea, one in France, one unlocated."""
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    db_session.add(ocha_provider)
    db_session.flush()
    for code, name, geometry in COUNTRIES:
        db_session.add(OchaAdminBoundary(
            data_provider_id=ocha_provider.id, source_id=code, level=0, name=name,
            geometry=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            source=code, iso_code=1, iso_2=code[:2], iso_3=code, iso_name=name,
            iso_3_group=code, region1_code=1, region1_name="r1", region2_code=2,
            region2_name="r2", region3_code=3, region3_name="r3", status_code=1,
            status_name="State", valid_date=datetime.date(2025, 1, 1),
            update_date=datetime.date(2025, 1, 1), land_source="osm", view="intl",
        ))

    for number, longitude, latitude, hectares in LOCATED:
        ignition_id = None
        if longitude is not None:
            ignition = EgifIgnition(
                data_provider_id=provider_id, report_number=number,
                geometry=f"SRID=4326;POINT({longitude} {latitude})",
                date_time=datetime.datetime(2015, 7, 1, tzinfo=UTC),
                time_zone=spain_egif.DEFAULT_TIME_ZONE,
                utm_zone=30, utm_x=440000.0, utm_y=4474000.0,
                datum=spain_egif.DATUM_ETRS89, start_point_count=1)
            db_session.add(ignition)
            db_session.flush()
            ignition_id = ignition.id
        db_session.add(EgifWildfire(
            report_number=number, campaign=2015, province_ine_code=number[4:6],
            data_provider_id=provider_id, ignition_id=ignition_id,
            start_date_time=datetime.datetime(2015, 7, 1, tzinfo=UTC),
            time_zone=spain_egif.DEFAULT_TIME_ZONE,
            area_ha_wooded=hectares, area_ha_non_wooded=0.0,
            area_ha_forest_total=hectares,
            area_ha_agricultural=0.0, area_ha_other_non_forest=0.0))
    db_session.commit()
    return db_session


def find_country(rows, country, year):
    matches = [row for row in rows if row.country == country and row.year == year]
    assert len(matches) == 1, f"expected one row for {country}/{year}, got {len(matches)}"
    return matches[0]


def test_filed_counts_every_fire_wherever_its_point_is(located):
    """The default takes EGIF's word for it, and the coordinate never comes into it."""
    rows = rows_for(located, country_source=app.COUNTRY_SOURCE_FILED)
    year_2015 = find_country(rows, "Spain", 2015)

    assert year_2015.fires == len(LOCATED)
    assert year_2015.total == pytest.approx(sum(fire[3] for fire in LOCATED))
    assert {row.country for row in rows} == {"Spain"}


def test_a_point_in_the_sea_is_dropped(located):
    """What the option is for: a coordinate that is somewhere a Spanish fire is not.

    It keeps its Spanish province code and its report number, and nothing before
    this test looks at where it actually is.
    """
    rows = rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY)
    spain = find_country(rows, "Spain", 2015)

    assert spain.fires == 1
    assert spain.total == pytest.approx(10.0), "only the Madrid fire is in Spain"


def test_a_point_over_the_border_is_attributed_where_it_actually_is(located):
    """The Country column is what makes this visible, which is why it is kept."""
    rows = rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY)

    france = find_country(rows, "France", 2015)
    assert france.fires == 1
    assert france.total == pytest.approx(30.0)
    assert [(row.country, row.year_label) for row in rows] == [
        ("France", "2015"), ("France", "Total"), ("Spain", "2015"), ("Spain", "Total")]


def test_a_fire_with_no_point_is_dropped_too(located):
    """Half the archive, and the reason this is not the default."""
    counted = sum(row.fires for row in rows_for(
        located, country_source=app.COUNTRY_SOURCE_GEOMETRY) if not row.is_total)

    assert counted == 2, "the sea fire and the unlocated one both go"


def test_the_audit_separates_no_point_from_a_point_in_no_country(located):
    """The two mean entirely different things, so the report does not add them up."""
    audit = located.execute(app.location_audit()).one()

    assert audit.no_point == 1
    assert audit.outside == 1


def test_the_audit_and_the_report_account_for_every_fire(located):
    """counted + no point + outside == the fires that reported the surface."""
    rows = rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY)
    counted = sum(row.fires for row in rows if not row.is_total)
    audit = located.execute(app.location_audit()).one()

    assert counted + audit.no_point + audit.outside == len(LOCATED)


def test_the_audit_follows_the_scope_it_is_given(located):
    """Otherwise its numbers would not add up to the report standing beside it."""
    assert located.execute(app.location_audit(year=1999)).one() == (0, 0)
    # The unlocated fire burnt 40 ha and the sea fire 20: a threshold between them
    # leaves only the unlocated one to account for.
    audit = located.execute(app.location_audit(min_area=30.0)).one()
    assert (audit.no_point, audit.outside) == (1, 0)


def test_the_geometry_run_warns_about_the_points_in_the_sea(located, caplog):
    """A run that silently halved itself would be worse than no option at all."""
    with caplog.at_level(logging.INFO):
        rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "publish no point" in messages
    assert "point in no country" in messages
    # And it says how many of each, not just that some exist.
    assert "1 publish no point" in messages


def test_the_docx_says_the_run_only_covers_located_fires(located, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    rows = rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY)
    app.write_docx(rows, target, None, logger, country_source=app.COUNTRY_SOURCE_GEOMETRY)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "usable published coordinate" in prose
    assert "not comparable" in prose


def test_the_docx_claims_no_such_restriction_by_default(located, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(located), target, None, logger)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "usable published coordinate" not in prose


# --------------------------------------------------------------------------
# One autonomous community
# --------------------------------------------------------------------------

#: (INE code, IGN name, province INE codes). Only what the fixture fires need, plus
#: the two that make the matching rules testable: a bilingual name and two whose
#: names begin alike, so an ambiguous ``--region`` has something to be ambiguous
#: between.
#:
#: The provinces are the real ones, because the fixture fires are filed under real
#: INE province codes — 08 Barcelona (Cataluña), 31 Navarra, 28 Madrid, 12 Castellón.
REGIONS = [
    ("09", "Cataluña/Catalunya", ["08", "17", "25", "43"]),
    ("15", "Comunidad Foral de Navarra", ["31"]),
    ("13", "Comunidad de Madrid", ["28"]),
    ("10", "Comunitat Valenciana", ["03", "12", "46"]),
]

#: A box big enough to be a polygon and small enough to be nowhere near a fire: the
#: region filter never touches geometry, but ``admin_boundary.geometry`` is NOT NULL.
REGION_GEOMETRY = f"SRID=4326;{MultiPolygon([box(0.0, 40.0, 0.1, 40.1)]).wkt}"


@pytest.fixture
def ign_provider_id(db_session):
    from src.providers import spain_ign

    provider = DataProvider(name=spain_ign.PROVIDER_NAME,
                            product=spain_ign.PROVIDER_PRODUCT_TEMPLATE.format(edition="2026"),
                            full_name=spain_ign.PROVIDER_FULL_NAME, url=spain_ign.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider.id


def add_region(session, provider_id, code, name, provinces):
    """One comunidad autónoma and its provincias, with IGN NATCODEs."""
    from src.providers import spain_ign
    from src.providers.spain_ign.admin_boundary import IgnAdminBoundary

    region = IgnAdminBoundary(
        data_provider_id=provider_id, source_id=f"34{code}0000000",
        level=app.REGION_LEVEL, name=name, geometry=REGION_GEOMETRY,
        edition="2026", kind=spain_ign.KIND_COMUNIDAD_AUTONOMA)
    session.add(region)
    session.flush()
    for province in provinces:
        session.add(IgnAdminBoundary(
            data_provider_id=provider_id, source_id=f"34{code}{province}00000",
            level=app.PROVINCE_LEVEL, name=f"Provincia {province}",
            parent_id=region.id, geometry=REGION_GEOMETRY,
            edition="2026", kind=spain_ign.KIND_PROVINCIA))
    session.flush()
    return region


@pytest.fixture
def regions(populated, ign_provider_id):
    """``populated`` plus the four IGN communities the fixture fires are filed in."""
    for code, name, provinces in REGIONS:
        add_region(populated, ign_provider_id, code, name, provinces)
    populated.commit()
    return populated


def catalonia(session) -> app.Region:
    return app.resolve_region(session, "Cataluña")


def test_the_region_defaults_to_the_whole_country():
    assert app.parse_arguments(["--csv", "out.csv"]).region is None


def test_the_region_has_a_short_option():
    assert app.parse_arguments(["--csv", "out.csv", "-r", "Catalonia"]).region == "Catalonia"


@pytest.mark.parametrize("wanted", [
    "Cataluña/Catalunya",   # the published name, whole
    "Cataluña",             # the Spanish half of it
    "Catalunya",            # the Catalan half
    "Catalonia",            # the English name
    "cataluna",             # no accents, no capitals
    "  CATALUÑA  ",         # and no tidying up asked of the caller
    "09",                   # the INE code
    "9",                    # which need not be padded
])
def test_a_region_is_recognised_however_it_is_spelled(regions, wanted):
    assert app.resolve_region(regions, wanted).code == "09"


def test_a_name_that_picks_out_one_region_is_enough(regions):
    """'Madrid' is not the name of a community; 'Comunidad de Madrid' is."""
    assert app.resolve_region(regions, "Madrid").code == "13"


def test_a_name_several_regions_share_is_refused(regions):
    """Rather than one of them being guessed at: 'Comunidad' is three of the four."""
    with pytest.raises(RuntimeError, match="matches several"):
        app.resolve_region(regions, "Comunidad")


def test_an_exact_name_beats_a_longer_one_containing_it(regions, ign_provider_id):
    """'Aragón' must not be dragged away by a region that merely contains the word."""
    add_region(regions, ign_provider_id, "02", "Aragón", ["22", "44", "50"])
    add_region(regions, ign_provider_id, "20", "Reino de Aragón y algo más", ["99"])
    regions.commit()

    assert app.resolve_region(regions, "Aragón").code == "02"


def test_an_unknown_region_lists_the_ones_imported(regions):
    with pytest.raises(RuntimeError, match="No comunidad autónoma matches") as error:
        app.resolve_region(regions, "Atlantis")

    assert "Cataluña/Catalunya (Catalonia)" in str(error.value)


def test_a_region_needs_the_ign_boundaries_imported(populated):
    """With none imported the error names the application that imports them."""
    with pytest.raises(RuntimeError, match="import_admin_boundaries"):
        app.resolve_region(populated, "Catalonia")


def test_a_region_with_no_provinces_is_refused(populated, ign_provider_id):
    """An EGIF fire is filed to a province, so a community alone selects nothing."""
    add_region(populated, ign_provider_id, "09", "Cataluña/Catalunya", [])
    populated.commit()

    with pytest.raises(RuntimeError, match="none of its provincias"):
        app.resolve_region(populated, "Catalonia")


def test_only_the_ign_publishes_a_spanish_community(populated, ign_provider_id):
    """Level 1 is some provider's first division below the country, not only Spain's.

    The Portuguese CAOP *distritos* are at level 1 too, and one of them must never
    turn up as an answer to ``--region``. Stood in for here by an OCHA row at level 1,
    which is the same shape of mistake: a boundary of another provider at that level.
    """
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    populated.add(ocha_provider)
    populated.flush()
    populated.add(OchaAdminBoundary(
        data_provider_id=ocha_provider.id, source_id="PT-BRG", level=app.REGION_LEVEL,
        name="Braga", geometry=REGION_GEOMETRY,
        source="PT", iso_code=1, iso_2="PT", iso_3="PRT", iso_name="Portugal",
        iso_3_group="PRT", region1_code=1, region1_name="r1", region2_code=2,
        region2_name="r2", region3_code=3, region3_name="r3", status_code=1,
        status_name="State", valid_date=datetime.date(2025, 1, 1),
        update_date=datetime.date(2025, 1, 1), land_source="osm", view="intl"))
    populated.commit()

    assert app.available_regions(populated) == []


def test_a_region_reports_only_the_fires_filed_in_it(regions):
    """The 2023 fires are province 08, Barcelona; the 2022 one is 31, Navarra."""
    rows = rows_for(regions, region=catalonia(regions))

    assert [row.year_label for row in rows] == ["2023", "Total"]
    assert find(rows, 2023).fires == 3
    assert find(rows, None).total == pytest.approx(
        forest("2023080001") + forest("2023080002") + forest("2023080003"))


def test_another_region_reports_its_own(regions):
    rows = rows_for(regions, region=app.resolve_region(regions, "Navarre"))

    assert [row.year_label for row in rows] == ["2022", "Total"]
    assert find(rows, 2022).fires == 1
    assert find(rows, 2022).total == pytest.approx(forest("2022310001"))


def test_no_region_reports_the_whole_country(regions):
    """The default has to leave the report exactly as it was."""
    assert rows_for(regions, region=None) == rows_for(regions)


def test_the_regions_add_up_to_the_country(regions):
    """Every fixture fire is filed in one of the four, and none in two."""
    whole = find(rows_for(regions), None)
    parts = [find(rows_for(regions, region=app.resolve_region(regions, code)), None)
             for code, *_ in REGIONS
             if rows_for(regions, region=app.resolve_region(regions, code))]

    assert sum(part.fires for part in parts) == whole.fires
    assert sum(part.total for part in parts) == pytest.approx(whole.total)


def test_the_region_and_a_campaign_combine(regions):
    assert rows_for(regions, year=2022, region=catalonia(regions)) == []
    assert [row.year_label for row in rows_for(regions, year=2023,
                                               region=catalonia(regions))] == \
           ["2023", "Total"]


def test_the_region_and_a_threshold_combine(regions):
    """2023's forest totals are 3, 30 and 300 ha; keep the largest two."""
    rows = rows_for(regions, min_area=10.0, region=catalonia(regions))

    assert find(rows, 2023).fires == 2
    assert find(rows, 2023).minimum == pytest.approx(forest("2023080001"))


def test_the_region_and_a_surface_combine(regions):
    rows = rows_for(regions, surface=app.SURFACE_AGRICULTURAL, region=catalonia(regions))

    assert find(rows, 2023).fires == 3
    assert find(rows, 2023).total == pytest.approx(5.0 + 0.0 + 50.0)


def test_a_region_with_no_fires_yields_nothing(regions, ign_provider_id):
    add_region(regions, ign_provider_id, "01", "Andalucía", ["04", "41"])
    regions.commit()

    assert rows_for(regions, region=app.resolve_region(regions, "Andalusia")) == []


def test_an_empty_region_report_names_the_region(regions, tmp_path, ign_provider_id):
    add_region(regions, ign_provider_id, "01", "Andalucía", ["04", "41"])
    regions.commit()
    args = app.parse_arguments(["--region", "Andalusia", "--csv", str(tmp_path / "a.csv")])

    with pytest.raises(RuntimeError, match="Andalucía"):
        app.report(args, regions.get_bind(), logger)
    assert not (tmp_path / "a.csv").exists()


def test_the_region_is_a_filter_on_the_filing_and_not_on_the_point(located, ign_provider_id):
    """Half the archive publishes no coordinate, and those fires are in the report.

    The four ``located`` fires are all filed in Madrid, one of them with no point at
    all and two with a point outside Spain. Under the default they all count, because
    what selects them is the province on the parte.
    """
    add_region(located, ign_provider_id, "13", "Comunidad de Madrid", ["28"])
    located.commit()

    rows = rows_for(located, region=app.resolve_region(located, "Madrid"))
    assert find(rows, 2015).fires == len(LOCATED)


def test_the_region_narrows_the_geometry_run_too(located, ign_provider_id):
    """And the audit with it, so its numbers still account for the report's fires."""
    add_region(located, ign_provider_id, "13", "Comunidad de Madrid", ["28"])
    add_region(located, ign_provider_id, "09", "Cataluña/Catalunya", ["08"])
    located.commit()
    madrid = app.resolve_region(located, "Madrid")

    rows = rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY, region=madrid)
    audit = located.execute(app.location_audit(region=madrid)).one()

    assert find_country(rows, "Spain", 2015).fires == 1
    assert (audit.no_point, audit.outside) == (1, 1)
    # And a community none of them is filed in gets none of them, geometry or not.
    assert rows_for(located, country_source=app.COUNTRY_SOURCE_GEOMETRY,
                    region=app.resolve_region(located, "Catalonia")) == []


def test_the_csv_keeps_its_shape_for_a_region(regions, tmp_path):
    """The Country column still says Spain, so the file can still be concatenated."""
    target = tmp_path / "catalonia.csv"
    app.write_csv(rows_for(regions, region=catalonia(regions)), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == list(app.COLUMNS)
    assert {line[0] for line in table[1:]} == {app.COUNTRY_NAME}


def test_the_docx_says_which_community_it_is_of(regions, tmp_path):
    """Because the Country column says Spain on every row of it."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "catalonia.docx"
    region = catalonia(regions)
    app.write_docx(rows_for(regions, region=region), target, None, logger, region=region)

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    prose = "\n".join(p.text for p in document.paragraphs)

    assert any("Cataluña/Catalunya" in heading for heading in headings)
    assert "not a national total" in prose
    # The provinces the selection was actually made on, not only the region's name.
    assert "08, 17, 25, 43" in prose


def test_the_docx_claims_no_region_when_there_is_none(regions, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "spain.docx"
    app.write_docx(rows_for(regions), target, None, logger)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "not a national total" not in prose
