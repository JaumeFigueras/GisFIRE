#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAFOR wildfire-causes application.

The fires are inserted through the ORM, as in the companion report's tests: what
has to be asserted is counting over known causes in known years.

The fixture is built around the three facts this report exists to get right.
``CAUSAESP`` is published in some years and not others, so the ``Lightning``
column must be **blank and not zero** where it is absent. Causes are matched on
the reconciled canonical form, so the 2011 spelling ``Tormenta Electrica`` has to
count as ``Naturales``. And a fire whose published cause reached no canonical form
is classified and can never match, which is a discrepancy between two columns that
has to be reported rather than left to be noticed.
"""

import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box
from sqlalchemy import select

from src.apps.statistics.wildfires.mexico_conafor import wildfire_causes as app
from src.data_model.data_provider import DataProvider
from src.providers import mexico_conafor
from src.providers.mexico_conafor.fire_cause import ConaforFireCause
from src.providers.mexico_conafor.wildfire import ConaforWildfire

logger = logging.getLogger("test-conafor-causes")

UTC = datetime.timezone.utc

#: The catalogue rows, as the importer would have inserted them:
#: ``(cause, cause_normalised, cause_en, specific_cause, specific_cause_en)``.
#:
#: Two of them are the same canonical cause under two published spellings a decade
#: apart, which is the whole reason ``cause_normalised`` exists. One reached no
#: canonical form at all — a bare ``'12'``, which is what three fires of the real
#: 2011 layer have in their cause field.
CAUSES = {
    "natural-rayos": ("Naturales", "Naturales", "Natural", "Rayos", "Lightning"),
    "natural-plain": ("Naturales", "Naturales", "Natural", None, None),
    "natural-2011": ("Tormenta Electrica", "Naturales", "Natural",
                     "Descargas electricas", "Lightning"),
    "natural-volcano": ("Naturales", "Naturales", "Natural",
                        "Erupciones volcanicas", "Volcanic eruptions"),
    "arson": ("Intencional", "Intencional", "Intentional", "Vandalismo", "Vandalism"),
    "arson-plain": ("Intencional", "Intencional", "Intentional", None, None),
    "junk": ("12", None, None, None, None),
}

#: ``(fire_code, year, cause key or None)``.
#:
#: 2019 publishes a specific cause, as 2010 and 2012-2019 really do. 2023 does
#: not, as 2011 and 2020-2023 really do not — so its lightning count is unknowable
#: rather than zero, and that is the single most important thing here.
FIRES = [
    # 2019: CAUSAESP published. Two lightning fires, one volcanic, one arson,
    # one natural with no specific cause, and one fire with no cause at all.
    ("19-01-0001", 2019, "natural-rayos"),
    ("19-01-0002", 2019, "natural-2011"),
    ("19-01-0003", 2019, "natural-volcano"),
    ("19-14-0004", 2019, "arson"),
    ("19-20-0005", 2019, "natural-plain"),
    ("19-20-0006", 2019, None),
    # 2023: no CAUSAESP at all. One natural, two arson.
    ("23-01-0001", 2023, "natural-plain"),
    ("23-01-0002", 2023, "arson-plain"),
    ("23-14-0003", 2023, "arson-plain"),
    # 2011: the junk cause, plus one real one.
    ("11-01-0001", 2011, "junk"),
    ("11-01-0002", 2011, "arson-plain"),
]

PERIMETER = f"SRID=4326;{MultiPolygon([box(-102.3, 21.8, -102.2, 21.9)]).wkt}"


@pytest.fixture
def populated(db_session):
    """A catalogue, eleven fires over three years, and no boundaries."""
    provider = DataProvider(name=mexico_conafor.PROVIDER_NAME,
                            product=mexico_conafor.PROVIDER_PRODUCT,
                            full_name=mexico_conafor.PROVIDER_FULL_NAME,
                            url=mexico_conafor.PROVIDER_URL)
    db_session.add(provider)
    db_session.flush()

    stored = {}
    for key, (cause, normalised, english, specific, specific_en) in CAUSES.items():
        row = ConaforFireCause(cause=cause, cause_normalised=normalised, cause_en=english,
                               specific_cause=specific, specific_cause_en=specific_en)
        db_session.add(row)
        db_session.flush()
        stored[key] = row.id

    for fire_code, year, key in FIRES:
        db_session.add(ConaforWildfire(
            data_provider_id=provider.id,
            fire_code=fire_code, year=year, source_layer=f"incendios_{year}",
            state_code=int(fire_code.split("-")[1]), state_name="Aguascalientes",
            municipality_name="Aguascalientes",
            date_time_precision=mexico_conafor.PRECISION_DAY,
            start_date_time=datetime.datetime(year, 6, 1, 6, tzinfo=UTC),
            time_zone=mexico_conafor.DEFAULT_TIME_ZONE,
            area_ha=10.0, perimeter=PERIMETER,
            cause_id=None if key is None else stored[key],
        ))
    db_session.commit()
    return db_session


@pytest.fixture
def shapeless(populated):
    """``populated`` plus a fire with a cause and no perimeter.

    Nine of the real 2012 features are like this. This report counts it; the
    companion, under a measured method, does not.
    """
    provider_id = populated.scalar(
        select(DataProvider.id).where(DataProvider.name == mexico_conafor.PROVIDER_NAME))
    cause_id = populated.scalar(
        select(ConaforFireCause.id)
        .where(ConaforFireCause.cause == "Naturales")
        .where(ConaforFireCause.specific_cause.is_(None)))
    populated.add(ConaforWildfire(
        data_provider_id=provider_id,
        fire_code="12-14-0001", year=2023, source_layer="incendios_2023",
        state_code=14, state_name="Jalisco", municipality_name="Bolanos",
        date_time_precision=mexico_conafor.PRECISION_DAY,
        start_date_time=datetime.datetime(2023, 6, 1, 6, tzinfo=UTC),
        time_zone=mexico_conafor.DEFAULT_TIME_ZONE,
        area_ha=2.0, perimeter=None, cause_id=cause_id,
    ))
    populated.commit()
    return populated


def rows_for(session, year=None, cause=app.DEFAULT_CAUSE) -> list[app.Row]:
    return app.compute(session, year, logger, cause)


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


def test_the_default_cause_is_natural():
    assert app.parse_arguments(["--csv", "out.csv"]).cause == app.DEFAULT_CAUSE
    assert app.DEFAULT_CAUSE == "Naturales"


def test_the_causes_offered_are_the_canonical_ones():
    """Taken from the model's table, so adding one there is the only edit needed."""
    from src.providers.mexico_conafor.fire_cause import CAUSE_TRANSLATIONS
    assert app.CAUSES == tuple(CAUSE_TRANSLATIONS)
    assert "Naturales" in app.CAUSES
    assert "Intencional" in app.CAUSES


def test_a_published_spelling_is_not_a_valid_cause():
    """--cause takes the canonical form; 'Tormenta Electrica' is a published one."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--cause", "Tormenta Electrica"])


def test_there_is_no_country_option(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Mexico"])
    assert "no --country here" in capsys.readouterr().err


def test_there_is_no_country_source_option(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "geometry"])
    assert "no --country-source here" in capsys.readouterr().err


def test_the_icnf_spelling_of_the_option_is_refused_by_name(capsys):
    """CONAFOR publishes no cause *type*; the ICNF does, and its report says so."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--cause-type", "Natural"])
    assert "--cause here, not --cause-type" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Which fires are counted
# --------------------------------------------------------------------------

def test_every_fire_is_counted(populated):
    rows = rows_for(populated)
    assert find(rows, None).fires == len(FIRES)
    assert find(rows, 2019).fires == 6
    assert find(rows, 2023).fires == 3


def test_a_fire_with_no_perimeter_is_counted(shapeless):
    """It still has a cause, and a causes report that dropped it would be
    answering a question about polygons."""
    assert find(rows_for(shapeless), 2023).fires == 4


def test_the_years_come_from_the_companion_report(populated):
    rows = rows_for(populated)
    assert [row.year for row in rows] == [2023, 2019, 2011, None]


def test_a_year_with_no_imported_fires_finds_nothing(populated):
    assert rows_for(populated, year=2015) == []


# --------------------------------------------------------------------------
# Classified, and the percentage
# --------------------------------------------------------------------------

def test_a_fire_with_no_cause_is_counted_but_not_classified(populated):
    row = find(rows_for(populated), 2019)
    assert row.fires == 6
    assert row.classified == 5


def test_the_percentage_is_of_the_classified_fires(populated):
    row = find(rows_for(populated), 2019)
    assert row.matching == 4          # rayos, 2011 wording, volcanic, plain
    assert row.classified == 5
    assert row.share == pytest.approx(80.0)
    assert row.share_label == "80.00"


def test_a_year_with_nothing_classified_has_no_percentage(db_session):
    """Empty, not zero: no share to report is not a share of zero."""
    row = app.Row(country="Mexico", year=2020, fires=10, classified=0,
                  matching=0, detailed=0, lightning=0)
    assert row.share is None
    assert row.share_label == ""


# --------------------------------------------------------------------------
# Matching on the reconciled cause
# --------------------------------------------------------------------------

def test_the_2011_spelling_counts_as_natural(populated):
    """'Tormenta Electrica' is what later layers call 'Naturales'.

    A report matching on the published text would find none of these, and would
    say that no natural fire burnt in the years that use the older wording.
    """
    row = find(rows_for(populated), 2019)
    assert row.matching == 4
    # Of those four, one is stored under a completely different published string.
    stored = populated.scalars(
        select(ConaforFireCause.cause)
        .where(ConaforFireCause.cause_normalised == "Naturales")).all()
    assert "Tormenta Electrica" in stored
    assert "Naturales" in stored


def test_the_renamed_categories_are_deliberately_not_merged():
    """CONAFOR renamed the intentional category and the archive keeps both names.

    *Intencional* runs 2013-2019 and 2023; *Actividades ilícitas* covers 2020-2022
    and no other year. They are the same act under two administrative names, and a
    fourteen-year series of either has a three-year hole of exact zeros in it.

    They stay apart because *actividades ilícitas* is the broader phrase and the
    archive files *Cultivos ilícitos* separately as well — merging two published
    categories on a guess would be a worse error than reporting them apart. This
    test exists so that a later decision to merge them has to be a decision.
    """
    from src.providers.mexico_conafor.fire_cause import CAUSE_NORMALISATIONS

    assert CAUSE_NORMALISATIONS["intencional"] == "Intencional"
    assert CAUSE_NORMALISATIONS["actividades ilicitas"] == "Actividades ilícitas"
    assert CAUSE_NORMALISATIONS["cultivos ilicitos"] == "Cultivos ilícitos"
    assert len({"Intencional", "Actividades ilícitas", "Cultivos ilícitos"}
               & set(CAUSE_NORMALISATIONS.values())) == 3
    # And the 2018 split of the agropecuario category, for the same reason.
    assert (CAUSE_NORMALISATIONS["actividades agricolas"]
            != CAUSE_NORMALISATIONS["actividades pecuarias"]
            != CAUSE_NORMALISATIONS["actividades agropecuarias"])


def test_another_cause_may_be_counted(populated):
    row = find(rows_for(populated, cause="Intencional"), 2023)
    assert row.matching == 2
    assert row.classified == 3


def test_a_fire_whose_cause_reached_no_canonical_form_never_matches(populated, caplog):
    """It is classified and can never appear in the cause column beside it."""
    with caplog.at_level(logging.WARNING):
        row = find(rows_for(populated), 2011)

    assert row.fires == 2
    assert row.classified == 2
    assert row.matching == 0
    assert "reached no canonical form" in caplog.text


# --------------------------------------------------------------------------
# Lightning — the column this report exists for
# --------------------------------------------------------------------------

def test_lightning_is_counted_where_the_specific_cause_is_published(populated):
    """CONAFOR names lightning outright, unlike the ICNF."""
    row = find(rows_for(populated), 2019)
    assert row.lightning == 2
    assert row.lightning_label == "2"


def test_both_published_wordings_of_lightning_are_counted(populated):
    """'Rayos' from most layers and 'Descargas electricas' from 2011."""
    assert set(app.LIGHTNING_SPECIFIC_CAUSES) == {"rayos", "descargas electricas"}
    assert find(rows_for(populated), 2019).lightning == 2


def test_a_natural_fire_is_not_necessarily_a_lightning_fire(populated):
    """Erupciones volcanicas is natural and is not lightning; so is a fire with
    no specific cause published at all."""
    row = find(rows_for(populated), 2019)
    assert row.matching == 4
    assert row.lightning == 2


def test_a_year_that_publishes_no_specific_cause_has_a_blank_not_a_zero(populated):
    """The single most important cell in this report.

    2011 and every year from 2020 publish a cause and no specific cause. Writing
    ``0`` there would say lightning started no fires in Mexico in 2021.
    """
    row = find(rows_for(populated), 2023)
    assert row.detailed == 0
    assert row.lightning == 0
    assert row.lightning_label == ""


def test_the_blank_years_are_reported(populated, caplog):
    with caplog.at_level(logging.INFO):
        rows_for(populated)
    assert "No specific cause is published" in caplog.text
    assert "2011" in caplog.text and "2023" in caplog.text


def test_the_total_lightning_is_over_the_years_that_answer_the_question(populated):
    """Not of the period: the blanks are unknown, not zero."""
    total = find(rows_for(populated), None)
    assert total.lightning == 2
    # Only 2019 publishes a specific cause, and four of its six fires carry one:
    # Rayos, Descargas electricas, Erupciones volcanicas and Vandalismo.
    assert total.detailed == 4
    assert total.lightning_label == "2"


# --------------------------------------------------------------------------
# The total row
# --------------------------------------------------------------------------

def test_the_total_adds_the_counts_up(populated):
    rows = rows_for(populated)
    total = find(rows, None)
    assert total.fires == sum(find(rows, year).fires for year in (2023, 2019, 2011))
    assert total.classified == sum(
        find(rows, year).classified for year in (2023, 2019, 2011))
    assert total.matching == sum(find(rows, year).matching for year in (2023, 2019, 2011))


def test_the_total_share_is_the_ratio_of_the_totals_not_the_mean_of_the_ratios(populated):
    """A year with two classified fires must not weigh as much as one with eleven."""
    rows = rows_for(populated)
    total = find(rows, None)
    assert total.share == pytest.approx(100.0 * total.matching / total.classified)

    yearly = [find(rows, year).share for year in (2023, 2019, 2011)]
    mean_of_ratios = sum(yearly) / len(yearly)
    assert total.share != pytest.approx(mean_of_ratios)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_columns_start_like_the_companion_report(populated, tmp_path):
    from src.apps.statistics.wildfires.mexico_conafor import wildfire_statistics

    path = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), path, logger)
    with path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.reader(handle))

    assert written[0][:3] == list(wildfire_statistics.COLUMNS[:3])
    assert written[0] == ["Country", "Year", "Fires", "Classified", "Natural",
                          "Natural (% of classified)", "Lightning"]


def test_the_csv_headings_name_the_cause_asked_for(populated, tmp_path):
    """A file of Intencional counts under a heading saying Natural would be a trap."""
    path = tmp_path / "arson.csv"
    app.write_csv(rows_for(populated, cause="Intencional"), path, logger,
                  cause="Intencional")
    with path.open(newline="", encoding="utf-8") as handle:
        heading = next(csv.reader(handle))
    assert heading[4] == "Intentional"
    assert heading[5] == "Intentional (% of classified)"


def test_the_csv_leaves_the_lightning_cell_empty_where_there_is_no_answer(
        populated, tmp_path):
    path = tmp_path / "causes.csv"
    app.write_csv(rows_for(populated), path, logger)
    with path.open(newline="", encoding="utf-8") as handle:
        written = {row[1]: row for row in csv.reader(handle)}

    assert written["2019"][6] == "2"
    assert written["2023"][6] == ""
    assert written["2011"][6] == ""


def test_the_docx_is_written(populated, tmp_path):
    pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated), path, None, logger)
    assert path.exists() and path.stat().st_size > 0


def test_the_docx_explains_the_blank_lightning_cells(populated, tmp_path):
    """A reader who takes a blank for a zero would read a collapse after 2019."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(rows_for(populated), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "A blank is not a zero" in text
    assert "2012-2019" in text
    assert "reconciled canonical form" in text
