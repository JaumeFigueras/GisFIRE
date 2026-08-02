#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ICNF wildfire-count-by-cause application.

The fixture is built around the two facts this report exists to get right: the
ICNF **classifies no fire before 2014**, so a percentage of all fires would be a
statement about coverage rather than about causes; and it **publishes no lightning
category**, so ``Natural`` is a proxy and has to be named as one.

The companion :mod:`wildfire_statistics <...portugal_icnf.wildfire_statistics>`
report counts the same fires under the same rule, and one test here holds the two
together — a drift between them would be invisible in either alone.
"""

import argparse
import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box
from sqlalchemy import select

from src.apps.statistics.wildfires.portugal_icnf import wildfire_causes as app
from src.apps.statistics.wildfires.portugal_icnf import wildfire_statistics as stats_app
from src.data_model.data_provider import DataProvider
from src.providers import ocha
from src.providers import portugal_icnf
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.providers.portugal_icnf.fire_cause import IcnfFireCause
from src.providers.portugal_icnf.wildfire import IcnfWildfire

logger = logging.getLogger("test-icnf-causes")

UTC = datetime.timezone.utc

COUNTRIES = [
    ("PRT", "Portugal", box(-9.6, 37.0, -6.2, 42.2)),
    ("ESP", "Spain", box(-6.2, 36.0, 3.0, 43.8)),
]

#: The published classifications the fixture uses, as ``(code, type, description)``
#: — the whole triple, because that is the natural key of the real table.
CAUSES = [
    ("100", "Natural", "Naturais"),
    ("300", "Intencional", "Incendiarismo - Sem motivação conhecida"),
    ("130", "Negligente", "Uso do fogo - Fogueiras"),
    ("500", "Desconhecida", "Indeterminadas"),
]

#: (sgif_code, year, cause code or None, perimeter). ``None`` is an unclassified
#: fire, which is every fire before 2014 and some after it.
#:
#: 2024 has four fires, one of each cause. 2023 has three, none of them natural.
#: 1985 has two, neither classified — the pre-2014 case.
FIRES = [
    ("2024-nat", 2024, "100", box(-8.0, 40.0, -7.9, 40.1)),
    ("2024-int", 2024, "300", box(-8.5, 40.0, -8.4, 40.1)),
    ("2024-neg", 2024, "130", box(-7.5, 40.0, -7.4, 40.1)),
    ("2024-unk", 2024, "500", box(-7.2, 40.0, -7.1, 40.1)),
    ("2023-int", 2023, "300", box(-8.0, 39.0, -7.9, 39.1)),
    ("2023-neg", 2023, "130", box(-8.3, 39.0, -8.2, 39.1)),
    ("2023-non", 2023, None, box(-8.6, 39.0, -8.5, 39.1)),
    ("1985-a", 1985, None, box(-8.0, 41.0, -7.9, 41.1)),
    ("1985-b", 1985, None, box(-9.0, 38.0, -8.9, 38.1)),
]

#: Filed with a Portuguese boundary, digitised into the Atlantic, and natural —
#: so that dropping it changes the natural count and not only the total.
IN_THE_SEA = ("2019-sea", 2019, "100", box(-14.0, 39.0, -13.9, 39.1))


@pytest.fixture
def populated(db_session):
    """Two countries, four classifications and nine Portuguese fires."""
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    icnf_provider = DataProvider(name=portugal_icnf.PROVIDER_NAME,
                                 product=portugal_icnf.PROVIDER_PRODUCT,
                                 full_name=portugal_icnf.PROVIDER_FULL_NAME,
                                 url=portugal_icnf.PROVIDER_URL)
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

    causes = {}
    for code, kind, description in CAUSES:
        cause = IcnfFireCause(code=code, type=kind, description=description)
        db_session.add(cause)
        db_session.flush()
        causes[code] = cause

    for sgif, year, cause_code, geometry in FIRES:
        db_session.add(IcnfWildfire(
            source_layer=f"ardida_{year}", sgif_code=sgif, year=year,
            date_time_precision=portugal_icnf.PRECISION_DAY,
            area_ha_gis=1.0, data_provider_id=icnf_provider.id,
            start_date_time=datetime.datetime(year, 7, 1, tzinfo=UTC),
            time_zone=portugal_icnf.DEFAULT_TIME_ZONE,
            perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            admin_boundary_id=boundaries["Portugal"].id,
            cause_id=None if cause_code is None else causes[cause_code].id,
        ))
    db_session.commit()
    return db_session


@pytest.fixture
def with_sea_fire(populated):
    """``populated`` plus a natural fire digitised into the Atlantic."""
    portugal = populated.scalar(
        select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "PRT"))
    provider_id = populated.scalar(
        select(DataProvider.id).where(DataProvider.name == portugal_icnf.PROVIDER_NAME))
    natural = populated.scalar(select(IcnfFireCause).where(IcnfFireCause.code == "100"))
    sgif, year, _, geometry = IN_THE_SEA
    populated.add(IcnfWildfire(
        source_layer=f"ardida_{year}", sgif_code=sgif, year=year,
        date_time_precision=portugal_icnf.PRECISION_DAY, area_ha_gis=1.0,
        data_provider_id=provider_id,
        start_date_time=datetime.datetime(year, 7, 1, tzinfo=UTC),
        time_zone=portugal_icnf.DEFAULT_TIME_ZONE,
        perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
        admin_boundary_id=portugal.id, cause_id=natural.id,
    ))
    populated.commit()
    return populated


def rows_for(session, year=None, cause_type=app.DEFAULT_CAUSE_TYPE,
             country_source=stats_app.COUNTRY_SOURCE_GEOMETRY) -> list[app.Row]:
    return app.compute(session, year, logger, cause_type, country_source)


def find(rows: list[app.Row], year: int | None, country: str = "Portugal") -> app.Row:
    matches = [row for row in rows if row.country == country and row.year == year]
    assert len(matches) == 1, f"expected one row for {country}/{year}, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_the_default_cause_is_natural():
    """The nearest thing the ICNF has to a lightning fire."""
    assert app.parse_arguments(["--csv", "out.csv"]).cause_type == "Natural"
    assert app.DEFAULT_CAUSE_TYPE == "Natural"


def test_the_selectable_causes_are_the_ones_the_provider_publishes():
    """Taken from the model's translation table, so the two cannot drift apart."""
    from src.providers.portugal_icnf.fire_cause import TYPE_TRANSLATIONS

    assert set(app.CAUSE_TYPES) == set(TYPE_TRANSLATIONS)
    assert "Natural" in app.CAUSE_TYPES


def test_there_is_no_lightning_cause_to_select():
    """Asserted so the omission stays deliberate rather than looking like an oversight.

    If the ICNF ever publishes one, this test fails and the module docstring, which
    explains at length that Natural is a proxy, has to be revisited.
    """
    assert not any("Rayo" in kind or "lightning" in kind.lower() for kind in app.CAUSE_TYPES)

    from src.providers.portugal_icnf.fire_cause import DESCRIPTION_TRANSLATIONS

    assert not any("lightning" in english.lower()
                   for english in DESCRIPTION_TRANSLATIONS.values())


def test_an_unknown_cause_type_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--cause-type", "Rayo"])


def test_there_is_no_country_option(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Portugal"])

    assert "no --country here" in capsys.readouterr().err


def test_the_first_three_columns_match_the_statistics_report():
    """So the pair can be read side by side, which is the point of a companion."""
    assert app.columns()[:3] == stats_app.COLUMNS[:3] == ("Country", "Year", "Fires")


def test_the_columns_name_the_cause_being_counted():
    """A file of Intencional counts under a Natural heading would be a trap."""
    assert app.columns("Natural")[4] == "Natural"
    assert app.columns("Intencional")[4] == "Intentional"
    assert "% of classified" in app.columns()[5]


# --------------------------------------------------------------------------
# The counts themselves
# --------------------------------------------------------------------------

def test_every_fire_is_counted_whether_classified_or_not(populated):
    rows = rows_for(populated)

    assert find(rows, 2024).fires == 4
    assert find(rows, 2023).fires == 3
    assert find(rows, 1985).fires == 2
    assert find(rows, None).fires == len(FIRES)


def test_the_natural_fires_are_counted(populated):
    assert find(rows_for(populated), 2024).matching == 1
    assert find(rows_for(populated), 2023).matching == 0, "2023 has no natural fire"


def test_another_cause_type_can_be_counted(populated):
    rows = rows_for(populated, cause_type="Intencional")

    assert find(rows, 2024).matching == 1
    assert find(rows, 2023).matching == 1
    assert find(rows, None).matching == 2


def test_the_classified_column_counts_the_fires_with_a_cause(populated):
    rows = rows_for(populated)

    assert find(rows, 2024).classified == 4
    assert find(rows, 2023).classified == 2, "one 2023 fire carries no cause"
    assert find(rows, 1985).classified == 0, "nothing before 2014 is classified"


def test_the_three_counts_are_ordered(populated):
    for row in rows_for(populated):
        assert row.matching <= row.classified <= row.fires, row.year_label


def test_each_year_gets_a_row_newest_first_with_the_total_last(populated):
    assert [(row.country, row.year_label) for row in rows_for(populated)] == [
        ("Portugal", "2024"), ("Portugal", "2023"), ("Portugal", "1985"),
        ("Portugal", "Total"),
    ]


def test_the_total_row_adds_the_counts_up(populated):
    rows = rows_for(populated)
    total = find(rows, None)
    years = [find(rows, year) for year in (2024, 2023, 1985)]

    assert total.fires == sum(row.fires for row in years)
    assert total.classified == sum(row.classified for row in years)
    assert total.matching == sum(row.matching for row in years)


def test_a_year_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    args = app.parse_arguments(["--year", "1999", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# The percentage, and its denominator
# --------------------------------------------------------------------------

def test_the_share_is_of_the_classified_fires_not_of_all_of_them(populated):
    """2024: one natural fire in four, all four classified."""
    assert find(rows_for(populated), 2024).share == pytest.approx(25.0)


def test_the_share_ignores_the_unclassified_fires_in_its_year(populated):
    """2023 has three fires but only two causes, and neither is natural."""
    year_2023 = find(rows_for(populated), 2023)

    assert (year_2023.fires, year_2023.classified) == (3, 2)
    assert year_2023.share == pytest.approx(0.0), "0 of 2, which is an answer"


def test_a_year_with_nothing_classified_has_no_share_at_all(populated):
    """1985 is before 2014. Zero would be a claim that none of its fires was natural."""
    year_1985 = find(rows_for(populated), 1985)

    assert year_1985.classified == 0
    assert year_1985.share is None
    assert year_1985.share_label == ""


def test_the_total_share_is_the_ratio_of_totals_not_the_mean_of_ratios(populated):
    """A year with two classified fires must not weigh as much as one with a thousand."""
    rows = rows_for(populated)
    total = find(rows, None)

    # 1 natural of 6 classified across every year: 16.67%, not the mean of
    # 25%, 0% and (no share at all).
    assert (total.matching, total.classified) == (1, 6)
    assert total.share == pytest.approx(100.0 / 6.0)
    years = [find(rows, year) for year in (2024, 2023)]
    assert total.share != pytest.approx(sum(row.share for row in years) / len(years))


def test_a_run_over_unclassified_years_only_says_so(populated, caplog):
    """A table of zeros with no explanation would look like an answer."""
    with caplog.at_level(logging.WARNING):
        rows = rows_for(populated, year=1985)

    assert find(rows, 1985).matching == 0
    assert "cause only from 2014" in "\n".join(r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------
# Which fires are counted: the same rule as the companion report
# --------------------------------------------------------------------------

def test_the_fire_count_matches_the_statistics_report(populated):
    """The property that makes this a companion rather than a second opinion."""
    counted = rows_for(populated)
    measured = stats_app.compute(populated, None, logger)

    assert [(row.country, row.year_label, row.fires) for row in counted] == \
           [(row.country, row.year_label, row.fires) for row in measured]


def test_a_perimeter_in_the_sea_is_dropped_here_too(with_sea_fire):
    """And it was a natural fire, so both counts move, not just the total."""
    geometry = rows_for(with_sea_fire, year=2019,
                        country_source=stats_app.COUNTRY_SOURCE_GEOMETRY)
    assert geometry == [], "the sea fire was the only 2019 fire"

    reported = rows_for(with_sea_fire, year=2019,
                        country_source=stats_app.COUNTRY_SOURCE_REPORTED)
    assert find(reported, 2019).fires == 1
    assert find(reported, 2019).matching == 1, "trusting the row keeps the sea fire"


def test_both_country_sources_agree_when_the_dataset_is_consistent(populated):
    by_geometry = rows_for(populated, country_source=stats_app.COUNTRY_SOURCE_GEOMETRY)
    by_report = rows_for(populated, country_source=stats_app.COUNTRY_SOURCE_REPORTED)

    assert [(r.country, r.year, r.fires, r.matching) for r in by_geometry] == \
           [(r.country, r.year, r.fires, r.matching) for r in by_report]


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_asked_for_columns(populated, tmp_path):
    target = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == list(app.columns())
    assert [line[1] for line in table[1:]] == ["2024", "2023", "1985", "Total"]


def test_the_csv_leaves_an_absent_share_empty(populated, tmp_path):
    """Empty reads as no answer to whatever parses this; zero would read as one."""
    target = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        rows = {line["Year"]: line for line in csv.DictReader(handle)}

    share = app.columns()[5]
    assert rows["1985"][share] == ""
    assert float(rows["2024"][share]) == pytest.approx(25.0)
    # And the counts are all plain integers, with no thousands separators.
    for line in rows.values():
        for column in ("Fires", "Classified", "Natural"):
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


def test_the_docx_total_row_is_bold(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    for row, written in zip(computed, table.rows[1:]):
        bold = [run.bold for cell in written.cells for run in cell.paragraphs[0].runs]
        assert all(value is row.is_total for value in bold), row.year_label


def test_the_docx_says_natural_is_not_lightning(populated, tmp_path):
    """The caveat belongs in the document, not only in the manual."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated), target, None, logger)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "no lightning category" in prose
    assert "proxy" in prose
    # And that the classification only starts in 2014.
    assert "2014" in prose


def test_the_docx_names_the_cause_it_counted(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated, cause_type="Intencional"), target, None, logger,
                   cause_type="Intencional")

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert any("Intentional" in heading for heading in headings)


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "c.csv"),
                                "--docx", str(tmp_path / "c.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "c.csv").exists()
    assert (tmp_path / "c.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2024" / "causes.csv"
    app.write_csv(rows_for(populated), target, logger)

    assert target.exists()


# --------------------------------------------------------------------------
# One year at a time
# --------------------------------------------------------------------------

def test_the_fires_are_counted_one_year_at_a_time(populated, monkeypatch):
    """The same shape as the companion report, and for the same reason."""
    years: list[int] = []
    original = app.counts_query

    def spy(year, *arguments, **keywords):
        years.append(year)
        return original(year, *arguments, **keywords)

    monkeypatch.setattr(app, "counts_query", spy)
    rows = rows_for(populated)

    assert years == sorted(years, reverse=True)
    assert years == [row.year for row in rows if not row.is_total]


def test_a_narrowed_year_is_counted_by_one_statement(populated, monkeypatch):
    monkeypatch.setattr(app, "years_query",
                        lambda: pytest.fail("the years were listed for a run of one"))
    assert find(rows_for(populated, year=2024), 2024).fires == 4
