#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the EGIF wildfire-count-by-cause application.

The fixture is built around the two facts this report exists to get right.

EGIF **names lightning outright** — ``idcausa`` family ``100``, *Rayo* — unlike the
ICNF, whose :mod:`counterpart <...portugal_icnf.wildfire_causes>` has to count
``Natural`` and say at length that it is a proxy. So the default column here is a
count of lightning fires, and one test holds that contrast in place.

And an EGIF **coordinate can be somewhere a Spanish fire is not**: the import's only
geometric guard is a plausibility box on the published UTM easting and northing, so
a point in the Atlantic or over the French border survives it, and half the archive
publishes no point at all. That is why every count appears twice — once over the
filed fires and once over the fires whose point really falls inside Spain — and the
fixture carries one fire of each kind so the two blocks can be told apart.
"""

import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box

from src.apps.statistics.wildfires.spain_egif import wildfire_causes as app
from src.apps.statistics.wildfires.spain_egif import wildfire_statistics as stats_app
from src.data_model.data_provider import DataProvider
from src.providers import ocha
from src.providers import spain_egif
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.providers.spain_egif.fire_cause import EgifFireCause
from src.providers.spain_egif.ignition import EgifIgnition
from src.providers.spain_egif.wildfire import EgifWildfire

logger = logging.getLogger("test-egif-causes")

UTC = datetime.timezone.utc

#: Spain, and France next door so a coordinate over the border has somewhere to be.
COUNTRIES = [
    ("ESP", "Spain", box(-9.3, 36.0, 3.0, 43.8)),
    ("FRA", "France", box(3.0, 42.0, 8.0, 51.0)),
]

#: The published classifications the fixture uses, as ``(idcausa, label)``. One of
#: each family that has a bare code, plus a ``2xx`` and a ``3xx``, which have only
#: subcodes.
CAUSES = [
    ("100", "Rayo"),
    ("231", "Quema de restos agrícolas (viñas,etc)"),
    ("311", "Líneas eléctricas"),
    ("400", "Intencionado"),
    ("500", "Desconocida"),
]

#: A coordinate inside Spain, used by every fire that is meant to be in it.
IN_SPAIN = (-3.70, 40.42)      # Madrid
#: A coordinate in no country at all: the Atlantic, west of Portugal.
IN_THE_SEA = (-12.00, 40.00)
#: A coordinate over the French border.
IN_FRANCE = (5.00, 44.00)

#: ``(report_number, campaign, cause code or None, coordinate or None)``.
#:
#: 2023 has five fires: two lightning (one of them unlocated), one intentional, one
#: negligent digitised into the sea, and one carrying no cause at all. 2022 has
#: three, one of them a lightning fire whose point landed in France. 2019 has two,
#: neither classified — the case with no percentage to give.
FIRES = [
    ("2023280001", 2023, "100", IN_SPAIN),
    ("2023280002", 2023, "100", None),
    ("2023280003", 2023, "400", IN_SPAIN),
    ("2023280004", 2023, "231", IN_THE_SEA),
    ("2023280005", 2023, None, IN_SPAIN),
    ("2022170001", 2022, "100", IN_FRANCE),
    ("2022170002", 2022, "400", IN_SPAIN),
    ("2022170003", 2022, "311", IN_SPAIN),
    ("2019120001", 2019, None, IN_SPAIN),
    ("2019120002", 2019, None, IN_SPAIN),
]

#: A subcode of the lightning family that does not exist today. The catalogue is
#: versioned and every revision so far has added subcodes, which is why the report
#: matches on the family digit rather than on ``100``.
FUTURE_LIGHTNING = ("2023280006", 2023, "101", "Rayo seco", IN_SPAIN)


def add_ignition(session, provider_id, number, coordinate):
    """The published ignition point of one fire, or nothing where it publishes none."""
    if coordinate is None:
        return None
    longitude, latitude = coordinate
    ignition = EgifIgnition(
        data_provider_id=provider_id, report_number=number,
        geometry=f"SRID=4326;POINT({longitude} {latitude})",
        date_time=datetime.datetime(int(number[:4]), 7, 1, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE,
        utm_zone=30, utm_x=440000.0, utm_y=4474000.0,
        datum=spain_egif.DATUM_ETRS89, start_point_count=1)
    session.add(ignition)
    session.flush()
    return ignition.id


def add_fire(session, provider_id, number, campaign, cause_id, coordinate):
    """One EGIF fire, with its cause and its point as the export publishes them."""
    session.add(EgifWildfire(
        report_number=number, campaign=campaign, province_ine_code=number[4:6],
        data_provider_id=provider_id, cause_id=cause_id,
        ignition_id=add_ignition(session, provider_id, number, coordinate),
        start_date_time=datetime.datetime(campaign, 7, 1, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE,
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
def boundaries(db_session):
    """Spain and France, as OCHA level-0 outlines."""
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
    db_session.commit()
    return db_session


@pytest.fixture
def causes(db_session):
    """The five classifications, by ``idcausa``."""
    resolved = {}
    for code, label in CAUSES:
        cause = EgifFireCause(code=code, label=label)
        db_session.add(cause)
        db_session.flush()
        resolved[code] = cause.id
    db_session.commit()
    return resolved


@pytest.fixture
def populated(db_session, provider_id, boundaries, causes):
    """Ten fires over three campaigns, two countries and five classifications."""
    for number, campaign, code, coordinate in FIRES:
        add_fire(db_session, provider_id, number, campaign,
                 None if code is None else causes[code], coordinate)
    db_session.commit()
    return db_session


@pytest.fixture
def with_future_subcode(populated, provider_id):
    """``populated`` plus a lightning fire under a subcode that does not exist yet."""
    number, campaign, code, label, coordinate = FUTURE_LIGHTNING
    cause = EgifFireCause(code=code, label=label)
    populated.add(cause)
    populated.flush()
    add_fire(populated, provider_id, number, campaign, cause.id, coordinate)
    populated.commit()
    return populated


@pytest.fixture
def without_boundaries(db_session, provider_id, causes):
    """The same fires, into a database whose OCHA boundaries were never imported."""
    for number, campaign, code, coordinate in FIRES:
        add_fire(db_session, provider_id, number, campaign,
                 None if code is None else causes[code], coordinate)
    db_session.commit()
    return db_session


def rows_for(session, year=None, family=app.DEFAULT_FAMILY) -> list[app.Row]:
    return app.compute(session, year, logger, family)


def find(rows: list[app.Row], year: int | None, country: str = "Spain") -> app.Row:
    matches = [row for row in rows if row.country == country and row.year == year]
    assert len(matches) == 1, f"expected one row for {country}/{year}, got {len(matches)}"
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


def test_the_default_is_lightning_over_every_campaign():
    parsed = app.parse_arguments(["--csv", "out.csv"])

    assert parsed.year is None
    assert parsed.cause_family == "lightning"
    assert app.DEFAULT_FAMILY == "lightning"


def test_lightning_is_a_real_category_here_unlike_the_icnf_report():
    """The contrast that makes this report different from its Portuguese counterpart.

    The ICNF publishes no lightning category and counts ``Natural`` as a proxy; EGIF
    names it, so this column means what it says.
    """
    from src.apps.statistics.wildfires.portugal_icnf import wildfire_causes as icnf_app

    assert app.columns()[4] == "Lightning"
    assert icnf_app.columns()[4] == "Natural"
    assert not any("lightning" in kind.lower() for kind in icnf_app.CAUSE_TYPES)


def test_the_family_digits_come_from_the_provider_constants():
    """So a renumbering there cannot leave this report counting the old digit."""
    assert app.CAUSE_FAMILIES["lightning"].digit == spain_egif.CAUSE_LIGHTNING[0]
    assert app.CAUSE_FAMILIES["intentional"].digit == spain_egif.CAUSE_INTENTIONAL[0]
    assert app.CAUSE_FAMILIES["unknown"].digit == spain_egif.CAUSE_UNKNOWN[0]
    assert app.CAUSE_FAMILIES["rekindle"].digit == spain_egif.CAUSE_REKINDLE[0]
    assert {family.digit for family in app.CAUSE_FAMILIES.values()} == set("123456")


def test_an_unknown_cause_family_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--cause-family", "arson"])
    with pytest.raises(ValueError, match="unknown cause family"):
        app.cause_family("arson")


def test_there_is_no_country_option(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Spain"])

    assert "no --country here" in capsys.readouterr().err


def test_there_is_no_country_source_option(capsys):
    """This report gives both answers at once, so there is nothing to choose."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "geometry"])

    assert "no --country-source here" in capsys.readouterr().err


def test_there_is_no_cause_type_option(capsys):
    """The ICNF report's option; EGIF publishes no Causa_Tipo."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--cause-type", "Natural"])

    error = capsys.readouterr().err
    assert "no --cause-type here" in error
    assert "--cause-family" in error


def test_there_is_no_surface_option(capsys):
    """A fire whose form leaves the burnt area blank is still a fire."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--surface", "forest"])

    assert "no --surface here" in capsys.readouterr().err


def test_the_first_three_columns_match_the_statistics_report():
    assert app.columns()[:3] == stats_app.COLUMNS[:3] == ("Country", "Year", "Fires")


def test_the_columns_name_the_family_being_counted():
    """A file of intentional fires under a Lightning heading would be a trap."""
    lightning = app.columns("lightning")
    intentional = app.columns("intentional")

    assert (lightning[4], lightning[9]) == ("Lightning", "Lightning inside")
    assert (intentional[4], intentional[9]) == ("Intentional", "Intentional inside")
    assert "% of classified" in lightning[5]
    assert "% of classified inside" in lightning[10]


# --------------------------------------------------------------------------
# The counts themselves
# --------------------------------------------------------------------------

def test_every_filed_fire_is_counted_whatever_its_cause_or_coordinate(populated):
    rows = rows_for(populated)

    assert find(rows, 2023).fires == 5
    assert find(rows, 2022).fires == 3
    assert find(rows, 2019).fires == 2
    assert find(rows, None).fires == len(FIRES)


def test_the_lightning_fires_are_counted(populated):
    rows = rows_for(populated)

    assert find(rows, 2023).matching == 2
    assert find(rows, 2022).matching == 1
    assert find(rows, 2019).matching == 0, "nothing in 2019 is classified at all"
    assert find(rows, None).matching == 3


def test_another_family_can_be_counted(populated):
    rows = rows_for(populated, family="intentional")

    assert find(rows, 2023).matching == 1
    assert find(rows, 2022).matching == 1
    assert find(rows, None).matching == 2


def test_a_family_of_subcodes_is_counted_by_its_leading_digit(populated):
    """``231`` and ``311`` have no bare parent code; the digit is what matches."""
    assert find(rows_for(populated, family="negligence"), 2023).matching == 1
    assert find(rows_for(populated, family="accident"), 2022).matching == 1


def test_a_lightning_subcode_the_catalogue_does_not_have_yet_is_counted(with_future_subcode):
    """The reason matching is on the family and not on the code ``100``."""
    rows = rows_for(with_future_subcode)

    assert find(rows, 2023).matching == 3, "the two 100 fires plus the new 101"
    assert find(rows, 2023).inside_matching == 2


def test_the_classified_column_counts_the_fires_with_a_cause(populated):
    rows = rows_for(populated)

    assert find(rows, 2023).classified == 4, "one 2023 fire carries no cause"
    assert find(rows, 2022).classified == 3
    assert find(rows, 2019).classified == 0


def test_the_counts_are_ordered(populated):
    for row in rows_for(populated):
        assert row.matching <= row.classified <= row.fires, row.year_label
        assert row.inside_matching <= row.inside_classified <= row.inside_fires
        assert row.inside_fires <= row.fires
        assert row.inside_classified <= row.classified
        assert row.inside_matching <= row.matching


def test_each_campaign_gets_a_row_newest_first_with_the_total_last(populated):
    assert [(row.country, row.year_label) for row in rows_for(populated)] == [
        ("Spain", "2023"), ("Spain", "2022"), ("Spain", "2019"), ("Spain", "Total"),
    ]


def test_the_total_row_adds_every_count_up(populated):
    rows = rows_for(populated)
    total = find(rows, None)
    years = [find(rows, year) for year in (2023, 2022, 2019)]

    for count in ("fires", "classified", "matching",
                  "inside_fires", "inside_classified", "inside_matching"):
        assert getattr(total, count) == sum(getattr(row, count) for row in years), count


def test_a_campaign_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    args = app.parse_arguments(["--year", "1999", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# The percentages, and their denominators
# --------------------------------------------------------------------------

def test_the_share_is_of_the_classified_fires_not_of_all_of_them(populated):
    """2023: two lightning fires of four classified, out of five filed."""
    year_2023 = find(rows_for(populated), 2023)

    assert (year_2023.matching, year_2023.classified, year_2023.fires) == (2, 4, 5)
    assert year_2023.share == pytest.approx(50.0)


def test_a_campaign_with_nothing_classified_has_no_share_at_all(populated):
    """Zero would be a claim that none of its fires was a lightning fire."""
    year_2019 = find(rows_for(populated), 2019)

    assert year_2019.classified == 0
    assert year_2019.share is None
    assert year_2019.inside_share is None


def test_the_total_share_is_the_ratio_of_totals_not_the_mean_of_ratios(populated):
    """A campaign with three classified fires must not weigh as much as one with a thousand."""
    rows = rows_for(populated)
    total = find(rows, None)

    assert (total.matching, total.classified) == (3, 7)
    assert total.share == pytest.approx(300.0 / 7.0)
    years = [find(rows, year) for year in (2023, 2022)]
    assert total.share != pytest.approx(sum(row.share for row in years) / len(years))


def test_the_located_share_says_how_much_can_be_placed_on_the_ground(populated):
    """2023: three of five fires have a point inside Spain."""
    assert find(rows_for(populated), 2023).located_share == pytest.approx(60.0)
    assert find(rows_for(populated), 2019).located_share == pytest.approx(100.0)
    assert find(rows_for(populated), None).located_share == pytest.approx(70.0)


def test_the_inside_share_has_its_own_denominator(populated):
    """1 lightning fire of the 2 classified fires that are inside, not of the 4."""
    year_2023 = find(rows_for(populated), 2023)

    assert (year_2023.inside_matching, year_2023.inside_classified) == (1, 2)
    assert year_2023.inside_share == pytest.approx(50.0)
    assert find(rows_for(populated), None).inside_share == pytest.approx(25.0)


def test_a_run_over_unclassified_campaigns_only_says_so(populated, caplog):
    """A table of zeros with no explanation would look like an answer."""
    with caplog.at_level(logging.WARNING):
        rows = rows_for(populated, year=2019)

    assert find(rows, 2019).matching == 0
    assert "cause catalogue has been seeded" in \
           "\n".join(record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------
# The points outside the border
# --------------------------------------------------------------------------

def test_only_the_points_really_inside_spain_are_counted_inside(populated):
    """The sea fire, the French fire and the unlocated one are all outside."""
    rows = rows_for(populated)

    assert find(rows, 2023).inside_fires == 3, "one in the sea, one with no point"
    assert find(rows, 2022).inside_fires == 2, "one is over the French border"
    assert find(rows, 2019).inside_fires == 2
    assert find(rows, None).inside_fires == 7


def test_a_fire_whose_point_is_in_france_is_still_a_spanish_fire(populated):
    """It is a Spanish parte: the coordinate is wrong, the filing is not."""
    rows = rows_for(populated)

    assert {row.country for row in rows} == {"Spain"}
    year_2022 = find(rows, 2022)
    assert year_2022.fires == 3, "the French-pointed fire is counted here"
    assert year_2022.matching == 1, "and it is the campaign's only lightning fire"
    assert year_2022.inside_matching == 0, "but not inside Spain"


def test_the_audit_separates_the_three_ways_of_being_outside(populated):
    """They mean entirely different things, so the report never adds them up."""
    groups = [
        app.Group(country=record.country, year=record.year, has_point=record.has_point,
                  placement=record.placement, fires=record.fires,
                  classified=record.classified, matching=record.matching)
        for record in populated.execute(app.counts_query())
    ]
    where = app.placements(groups)

    assert where.inside == 7
    assert where.no_point == 1
    assert where.no_country == 1
    assert where.elsewhere == (("France", 1),)


def test_the_audit_accounts_for_every_fire(populated):
    groups = [
        app.Group(country=record.country, year=record.year, has_point=record.has_point,
                  placement=record.placement, fires=record.fires,
                  classified=record.classified, matching=record.matching)
        for record in populated.execute(app.counts_query())
    ]
    where = app.placements(groups)

    assert where.inside + where.outside == len(FIRES)


def test_the_run_says_where_the_points_that_are_not_inside_went(populated, caplog):
    with caplog.at_level(logging.INFO):
        rows_for(populated)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "1 publish no point" in messages
    assert "1 publish a point in no country" in messages
    assert "inside Spain" in messages
    # And the border crossing is named rather than lumped in with the sea.
    assert "coordinate inside France" in messages


def test_a_run_with_no_boundaries_imported_says_so(without_boundaries, caplog):
    """Every 'inside' column zero looks exactly like an answer, so it must not pass for one."""
    with caplog.at_level(logging.WARNING):
        rows = rows_for(without_boundaries)

    assert find(rows, None).fires == len(FIRES), "the first block is unaffected"
    assert find(rows, None).inside_fires == 0
    assert "No OCHA level-0 boundary named Spain is imported" in \
           "\n".join(record.getMessage() for record in caplog.records)


def test_a_report_with_boundaries_makes_no_such_claim(populated, caplog):
    with caplog.at_level(logging.WARNING):
        rows_for(populated)

    assert "is imported" not in "\n".join(record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_asked_for_columns(populated, tmp_path):
    target = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == list(app.columns())
    assert [line[1] for line in table[1:]] == ["2023", "2022", "2019", "Total"]


def test_the_csv_writes_both_blocks_of_counts(populated, tmp_path):
    target = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        lines = {line["Year"]: line for line in csv.DictReader(handle)}

    assert lines["2023"]["Fires"] == "5"
    assert lines["2023"]["Lightning"] == "2"
    assert lines["2023"]["Fires inside"] == "3"
    assert lines["2023"]["Lightning inside"] == "1"


def test_the_csv_leaves_an_absent_share_empty(populated, tmp_path):
    """Empty reads as no answer to whatever parses this; zero would read as one."""
    target = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        lines = {line["Year"]: line for line in csv.DictReader(handle)}

    share = app.columns()[5]
    assert lines["2019"][share] == ""
    assert lines["2019"][app.columns()[10]] == ""
    assert float(lines["2023"][share]) == pytest.approx(50.0)
    # And the counts are plain integers, with no thousands separators.
    for line in lines.values():
        for column in ("Fires", "Classified", "Lightning",
                       "Fires inside", "Classified inside", "Lightning inside"):
            assert "," not in line[column]
            int(line[column])


def test_the_docx_is_a_word_table_with_every_row(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    assert len(table.rows) == len(computed) + 1
    assert [cell.text for cell in table.rows[0].cells] == list(app.columns())


def test_the_docx_page_is_landscape(populated, tmp_path):
    """Eleven columns do not fit across a portrait page, and a table that wraps is unread."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated), target, None, logger)

    section = docx.Document(str(target)).sections[0]
    assert section.page_width > section.page_height


def test_the_docx_total_row_is_bold(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    for row, written in zip(computed, table.rows[1:]):
        bold = [run.bold for cell in written.cells for run in cell.paragraphs[0].runs]
        assert all(value is row.is_total for value in bold), row.year_label


def test_the_docx_says_what_the_inside_columns_are(populated, tmp_path):
    """A reader taking them for the archive would conclude half of Spain's fires never happened."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated), target, None, logger)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "no coordinate at all" in prose
    assert "1998" in prose
    assert "in the sea or over a border" in prose


def test_the_docx_names_the_family_it_counted(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated, family="intentional"), target, None, logger,
                   family="intentional")

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert any("Intentional" in heading for heading in headings)
    assert "Intencionado" in "\n".join(p.text for p in document.paragraphs)


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "c.csv"),
                                "--docx", str(tmp_path / "c.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "c.csv").exists()
    assert (tmp_path / "c.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2023" / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    assert target.exists()


# --------------------------------------------------------------------------
# One statement
# --------------------------------------------------------------------------

def test_the_whole_report_is_one_statement(populated, monkeypatch):
    """Both blocks, the Total row and the audit come out of a single pass."""
    built: list[int | None] = []
    original = app.counts_query

    def spy(year=None, *arguments, **keywords):
        built.append(year)
        return original(year, *arguments, **keywords)

    monkeypatch.setattr(app, "counts_query", spy)
    rows = rows_for(populated)

    assert built == [None]
    assert len(rows) == 4


def test_the_placement_audit_needs_no_query_of_its_own(populated, monkeypatch):
    """It is arithmetic over the groups, so it cannot disagree with the table."""
    monkeypatch.setattr(
        app, "fire_details",
        lambda *arguments, **keywords: pytest.fail("the fires were read a second time"))
    groups = [app.Group("Spain", 2023, True, "Spain", 3, 2, 1),
              app.Group("Spain", 2023, False, None, 1, 1, 1)]

    where = app.placements(groups)
    assert (where.inside, where.no_point, where.outside) == (3, 1, 1)
