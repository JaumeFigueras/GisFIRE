#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Guatemalan INAB wildfire classification application.

The report that occupies the slot a counts-by-cause report occupies for Portugal,
Spain and Canada — over a dataset that publishes **no cause**. So the first thing
asserted is that it never claims to be one, and the second is that its percentages are
shares of the *classified* fires rather than of all of them, which with
``tipo_incendio`` absent from 89% of the archive is a factor-of-nine difference.

After that: that a published vocabulary gives the same columns whatever is in the
database, that a value INAB has added since is reported and counted rather than
dropped, and that ``institution`` — the one vocabulary with no published list — takes
its columns from the data and says so.

See ``conftest.py`` for the eight fires, which are the same eight the companion
statistics report is tested over.
"""

import csv
import datetime
import logging

import pytest

from src.apps.statistics.wildfires.guatemala_inab import wildfire_classification as app
from src.apps.statistics.wildfires.guatemala_inab import wildfire_statistics as statistics
from src.providers import guatemala_inab

from .conftest import store

logger = logging.getLogger("test-inab-classification")

UTC = datetime.timezone.utc

LOCATION = app.CLASSIFICATIONS[app.CLASSIFICATION_LOCATION]
STATUS = app.CLASSIFICATIONS[app.CLASSIFICATION_STATUS]
CHANNEL = app.CLASSIFICATIONS[app.CLASSIFICATION_CHANNEL]
INSTITUTION = app.CLASSIFICATIONS[app.CLASSIFICATION_INSTITUTION]


def run(db_session, classification=None, **kwargs):
    """Compute the report over the fixture, returning ``(rows, values)``."""
    return app.compute(db_session, classification or LOCATION,
                       kwargs.pop("year", None), logger, **kwargs)


def rows_by_year(rows):
    return {row.year: row for row in rows}


def counts(row, values, value):
    """One value's count off a row, found by its position in ``values``."""
    return row.counts[values.index(value)]


# --------------------------------------------------------------------------
# It is not a causes report
# --------------------------------------------------------------------------

def test_no_classification_is_a_cause():
    """Nothing in the thirty-three published attributes says why a fire started."""
    for classification in app.CLASSIFICATIONS.values():
        assert "cause" not in classification.column
        assert "Cause" not in classification.labels.values()


def test_no_column_is_ever_headed_cause(fires):
    for key, classification in app.CLASSIFICATIONS.items():
        _, values = run(fires, classification)
        assert not [name for name in app.columns(values, classification)
                    if "cause" in name.lower()], key


def test_the_cause_option_is_refused_with_a_reason(capsys):
    """Anyone passing it has copied a command line from the Canadian report."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--cause", "natural", "--csv", "a.csv",
                             "--db-name", "x", "--db-user", "y"])
    error = capsys.readouterr().err
    assert "publishes no cause" in error
    assert "--classification" in error


def test_the_module_is_not_named_causes():
    assert app.__name__.endswith("wildfire_classification")


# --------------------------------------------------------------------------
# The default: tipo_incendio
# --------------------------------------------------------------------------

def test_the_default_classification_is_the_one_about_the_fire():
    assert app.DEFAULT_CLASSIFICATION == app.CLASSIFICATION_LOCATION
    assert LOCATION.column == "fire_location"


def test_the_location_breakdown(fires):
    rows, values = run(fires)
    assert values == guatemala_inab.FIRE_LOCATIONS

    years = rows_by_year(rows)
    assert (years[2024].fires, years[2024].classified) == (3, 2)
    assert (years[2025].fires, years[2025].classified) == (3, 2)

    total = rows[-1]
    assert (total.fires, total.classified) == (6, 4)
    assert counts(total, values, guatemala_inab.LOCATION_IN_FOREST) == 2
    assert counts(total, values, guatemala_inab.LOCATION_OUT_OF_FOREST) == 2


def test_the_columns_are_the_published_labels(fires):
    _, values = run(fires)
    assert app.columns(values, LOCATION) == (
        "Country", "Year", "Fires", "Classified", "Classified (%)",
        "In forest", "In forest (%)", "Outside forest", "Outside forest (%)")


# --------------------------------------------------------------------------
# The denominator is the classified fires
# --------------------------------------------------------------------------

def test_a_value_share_is_of_the_classified_not_of_the_fires(fires):
    """The mistake this report is shaped to prevent: 50% of four, not 33% of six."""
    rows, values = run(fires)
    total = rows[-1]
    assert total.classified == 4 and total.fires == 6
    assert total.value_share(values.index(guatemala_inab.LOCATION_IN_FOREST)) == \
        pytest.approx(50.0)


def test_the_coverage_is_its_own_column(fires):
    total = run(fires)[0][-1]
    assert total.classified_share == pytest.approx(100.0 * 4 / 6)


def test_a_year_that_classified_nothing_has_no_percentage(db_session, provider):
    """A percentage of nothing is no answer, not zero percent."""
    store(db_session, provider, "unclassified",
          datetime.datetime(2023, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_CLOSED, None, "conred", "telefono", True, False)
    db_session.commit()

    rows, values = run(db_session)
    assert (rows[0].fires, rows[0].classified) == (1, 0)
    assert rows[0].classified_share == pytest.approx(0.0)
    assert rows[0].value_share(0) is None
    assert rows[0].values[5:] == ("0", "", "0", "")


def test_the_total_percentages_are_ratios_of_the_totals(fires):
    rows, values = run(fires)
    total = rows[-1]
    assert total.classified_share == pytest.approx(
        100.0 * sum(row.classified for row in rows[:-1])
        / sum(row.fires for row in rows[:-1]))


# --------------------------------------------------------------------------
# The columns come from the published vocabulary
# --------------------------------------------------------------------------

def test_a_published_value_nobody_carries_still_gets_a_column(fires):
    """Two years' CSVs have to have the same header."""
    rows, values = run(fires, CHANNEL)
    assert values == guatemala_inab.REPORT_CHANNELS

    total = rows[-1]
    assert counts(total, values, "telefono") == 3
    assert counts(total, values, "radio") == 0, "the only radio record is a false alarm"
    assert counts(total, values, "redes_sociales") == 0


def test_the_published_order_is_kept(fires):
    _, values = run(fires, STATUS)
    assert values == guatemala_inab.REPORT_STATUSES


def test_an_unpublished_value_is_counted_in_a_column_of_its_own(db_session, provider,
                                                                caplog):
    """These vocabularies carry no CHECK precisely so INAB can add a value."""
    store(db_session, provider, "new-channel",
          datetime.datetime(2025, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_CLOSED, None, "conred", "whatsapp", True, False)
    db_session.commit()

    rows, values = run(db_session, CHANNEL)
    assert values == guatemala_inab.REPORT_CHANNELS + ("whatsapp",)
    assert counts(rows[-1], values, "whatsapp") == 1
    assert "not in the published vocabulary" in caplog.text
    assert "whatsapp" in caplog.text


def test_a_published_vocabulary_is_the_provider_module_s(fires):
    """Pointed at, not copied, so a value added there appears here without an edit."""
    assert LOCATION.published is guatemala_inab.FIRE_LOCATIONS
    assert STATUS.published is guatemala_inab.REPORT_STATUSES
    assert CHANNEL.published is guatemala_inab.REPORT_CHANNELS


# --------------------------------------------------------------------------
# institution: the one with no published list
# --------------------------------------------------------------------------

def test_the_institution_columns_come_from_the_data(fires):
    assert INSTITUTION.published is None
    rows, values = run(fires, INSTITUTION)
    assert values == ("conap", "conred", "otra"), "most frequent first, then by name"

    total = rows[-1]
    assert counts(total, values, "conred") == 2
    assert counts(total, values, "otra") == 1


def test_the_institution_columns_can_differ_between_scopes(fires):
    """The stated cost of having no published vocabulary: two runs, two headers."""
    _, everything = run(fires, INSTITUTION)
    _, one_year = run(fires, INSTITUTION, year=2025)
    assert everything == ("conap", "conred", "otra")
    assert one_year == ("conap", "conred"), "2025 has no 'otra' report"
    assert everything != one_year


def test_the_order_is_total_so_two_runs_agree(fires):
    """conap and conred both have two; without the tie-break the order could flip."""
    assert run(fires, INSTITUTION)[1] == run(fires, INSTITUTION)[1]


# --------------------------------------------------------------------------
# Scope agrees with the companion report
# --------------------------------------------------------------------------

def test_the_fires_column_agrees_with_the_statistics_report(fires):
    """The whole reason the scope is imported rather than copied."""
    counted = rows_by_year(statistics.compute(fires, None, logger))
    for classification in app.CLASSIFICATIONS.values():
        rows, _ = run(fires, classification)
        for row in rows[:-1]:
            assert row.fires == counted[row.year].fires, classification.key


def test_a_false_alarm_is_left_out_by_default(fires):
    rows, values = run(fires, STATUS)
    assert counts(rows[-1], values, guatemala_inab.STATUS_FALSE) == 0, \
        "excluded from the scope, so its own column is empty"
    assert rows[-1].fires == 6


def test_a_false_alarm_can_be_counted_on_request(fires):
    """Which is how the status breakdown is meant to be read."""
    rows, values = run(fires, STATUS, include_false_alarms=True)
    total = rows[-1]
    assert total.fires == 8
    assert counts(total, values, guatemala_inab.STATUS_FALSE) == 2
    assert counts(total, values, guatemala_inab.STATUS_CLOSED) == 4
    assert counts(total, values, guatemala_inab.STATUS_UNVERIFIED) == 1


def test_the_year_is_the_local_one(fires):
    """Same six-hour question as the companion report, answered the same way."""
    years = rows_by_year(run(fires)[0])
    assert years[2024].fires == 3, "the New Year fire counts towards 2024"


def test_one_year_can_be_selected(fires):
    rows, _ = run(fires, year=2025)
    assert [row.year for row in rows] == [2025, None]


def test_the_years_are_newest_first(fires):
    rows, _ = run(fires, STATUS)
    assert [row.year for row in rows] == [2025, 2024, None]


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--db-name", "x", "--db-user", "y"])


def test_listing_the_classifications_needs_no_output():
    args = app.parse_arguments(["--list-classifications"])
    assert args.list_classifications


def test_every_classification_is_listed(capsys):
    app.list_classifications()
    printed = capsys.readouterr().out
    for classification in app.CLASSIFICATIONS.values():
        assert classification.key in printed
        assert classification.column in printed
        assert classification.published_name in printed
    assert "None of these is a cause" in printed


def test_an_unknown_classification_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--classification", "ignition-source", "--csv", "a.csv",
                             "--db-name", "x", "--db-user", "y"])


@pytest.mark.parametrize("option, value", [("--area-method", "geometry"),
                                           ("--surface", "burnt"),
                                           ("--country", "Guatemala")])
def test_the_companion_s_refusals_apply_here_too(capsys, option, value):
    with pytest.raises(SystemExit):
        app.parse_arguments([option, value, "--csv", "a.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert capsys.readouterr().err


def test_every_classification_has_prose():
    """The Word document names what it counted; a missing line would be a blank claim."""
    for classification in app.CLASSIFICATIONS.values():
        assert classification.prose
        assert classification.prose.startswith(classification.published_name), \
            "the prose names the attribute INAB publishes, not the column it lands in"


def test_the_published_name_is_the_spanish_one():
    """A reader coming from the provider docs is thinking in tipo_incendio."""
    assert LOCATION.published_name == "tipo_incendio"
    assert STATUS.published_name == "estado_aviso"
    assert CHANNEL.published_name == "forma_comunicacion"
    assert INSTITUTION.published_name == "institucion"


def test_a_value_with_no_label_is_titled_from_its_slug():
    assert INSTITUTION.label("conred") == "Conred"
    assert CHANNEL.label("redes_sociales") == "Social media"


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_header_names_the_values(tmp_path, fires):
    rows, values = run(fires)
    path = tmp_path / "location.csv"
    app.write_csv(rows, values, LOCATION, path, logger)

    with path.open(encoding="utf-8") as handle:
        header, *body = list(csv.reader(handle))
    assert tuple(header) == app.columns(values, LOCATION)
    assert len(body) == 3


def test_the_csv_carries_the_counts_and_the_shares(tmp_path, fires):
    rows, values = run(fires)
    path = tmp_path / "location.csv"
    app.write_csv(rows, values, LOCATION, path, logger)

    with path.open(encoding="utf-8") as handle:
        total = list(csv.DictReader(handle))[-1]
    assert total["Year"] == statistics.TOTAL_LABEL
    assert total["Fires"] == "6"
    assert total["Classified"] == "4"
    assert total["In forest"] == "2"
    assert total["In forest (%)"] == "50.00"


def test_the_docx_is_written(tmp_path, fires):
    pytest.importorskip("docx")
    rows, values = run(fires)
    path = tmp_path / "location.docx"
    app.write_docx(rows, values, LOCATION, path, None, logger)
    assert path.exists() and path.stat().st_size > 0


def test_the_docx_says_it_is_not_a_causes_report(tmp_path, fires):
    docx = pytest.importorskip("docx")
    rows, values = run(fires)
    path = tmp_path / "location.docx"
    app.write_docx(rows, values, LOCATION, path, None, logger)

    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    assert "This is not a report of causes" in text
    assert "publishes no cause for any fire" in text


def test_the_docx_explains_the_denominator(tmp_path, fires):
    docx = pytest.importorskip("docx")
    rows, values = run(fires)
    path = tmp_path / "location.docx"
    app.write_docx(rows, values, LOCATION, path, None, logger)

    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    assert "share of that rather than of Fires" in text


def test_the_docx_says_where_the_columns_came_from(tmp_path, fires):
    docx = pytest.importorskip("docx")

    published = tmp_path / "channel.docx"
    rows, values = run(fires, CHANNEL)
    app.write_docx(rows, values, CHANNEL, published, None, logger)

    derived = tmp_path / "institution.docx"
    rows, values = run(fires, INSTITUTION)
    app.write_docx(rows, values, INSTITUTION, derived, None, logger)

    def prose(path):
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)

    assert "the published vocabulary, in its published order" in prose(published)
    assert "come from the data in scope" in prose(derived)


# --------------------------------------------------------------------------
# Refusals at the report level
# --------------------------------------------------------------------------

def test_a_low_coverage_breakdown_is_warned_about(fires, caplog):
    """Two thirds classified is not low; one record in ten is."""
    caplog.set_level(logging.INFO)
    run(fires)
    assert "4 of 6 fire(s) carry a fire_location" in caplog.text


def test_a_scope_that_classified_nothing_is_warned_about(db_session, provider, caplog):
    store(db_session, provider, "unclassified",
          datetime.datetime(2023, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_CLOSED, None, "conred", "telefono", True, False)
    db_session.commit()

    run(db_session)
    assert "No fire in scope carries a fire_location" in caplog.text


# --------------------------------------------------------------------------
# End to end, through the entry point
# --------------------------------------------------------------------------

def arguments(**overrides):
    """A parsed namespace for :func:`report`, without going through argparse."""
    import argparse
    values = {"classification": app.DEFAULT_CLASSIFICATION, "year": None,
              "include_false_alarms": False, "csv": None, "docx": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_report_writes_both_outputs(tmp_path, fires):
    pytest.importorskip("docx")
    csv_path, docx_path = tmp_path / "a.csv", tmp_path / "a.docx"
    rows = app.report(arguments(csv=csv_path, docx=docx_path),
                      fires.get_bind(), logger)

    assert csv_path.exists() and docx_path.exists()
    assert rows[-1].classified == 4


def test_report_refuses_a_scope_with_no_fires(tmp_path, fires):
    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(arguments(year=1999, csv=tmp_path / "a.csv"),
                   fires.get_bind(), logger)


def test_report_refuses_a_breakdown_with_no_columns(tmp_path, db_session, provider):
    """Only reachable for a data-derived vocabulary: a published one always has columns."""
    store(db_session, provider, "no-institution",
          datetime.datetime(2023, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_CLOSED, None, None, "telefono", True, False)
    db_session.commit()

    with pytest.raises(RuntimeError, match="nothing to break down"):
        app.report(arguments(classification=app.CLASSIFICATION_INSTITUTION,
                             csv=tmp_path / "a.csv"), db_session.get_bind(), logger)
    assert not (tmp_path / "a.csv").exists()


def test_a_published_vocabulary_still_reports_when_nothing_is_classified(tmp_path,
                                                                        db_session,
                                                                        provider):
    """Zero in every column is an answer; the columns are the published ones."""
    store(db_session, provider, "unclassified",
          datetime.datetime(2023, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_CLOSED, None, "conred", "telefono", True, False)
    db_session.commit()

    rows = app.report(arguments(csv=tmp_path / "a.csv"), db_session.get_bind(), logger)
    assert rows[-1].classified == 0
    assert (tmp_path / "a.csv").exists()


def test_an_empty_report_has_no_total_row():
    assert app.summarise([]) == []


def test_a_breakdown_of_a_small_minority_is_warned_about(db_session, provider, caplog):
    """One record in ten is a sample of who filled the form in, not of fire."""
    caplog.set_level(logging.INFO)
    for index in range(4):
        store(db_session, provider, f"plain-{index}",
              datetime.datetime(2025, 5, 1 + index, 18, 0, tzinfo=UTC),
              guatemala_inab.STATUS_CLOSED,
              guatemala_inab.LOCATION_IN_FOREST if index == 0 else None,
              "conred", "telefono", True, False)
    db_session.commit()

    run(db_session)
    assert "describes 25.00% of the fires in scope" in caplog.text
    assert "not of Guatemalan fire" in caplog.text
