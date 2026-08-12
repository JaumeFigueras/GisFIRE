#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Guatemalan INAB wildfire statistics application.

What is asserted here is what this report has that the other seven do not: that the
three hectare columns are **present and empty** rather than absent or zero; that the
year is the Guatemalan one and not the UTC one; that the false alarms leave ``Fires``
but keep a column; and that a ``NULL`` report status does not silently drop a fire.

See ``conftest.py`` for the eight fires and why each of them is there.
"""

import csv
import datetime
import logging

import pytest

from src.apps.statistics.wildfires.guatemala_inab import wildfire_statistics as app
from src.providers import guatemala_inab

from .conftest import store

logger = logging.getLogger("test-inab-statistics")

UTC = datetime.timezone.utc


def run(db_session, **kwargs):
    """Compute the report over the fixture."""
    return app.compute(db_session, kwargs.pop("year", None), logger, **kwargs)


def rows_by_year(rows):
    return {row.year: row for row in rows}


# --------------------------------------------------------------------------
# There are no hectares, and that is the shape of the report
# --------------------------------------------------------------------------

def test_the_hectare_columns_are_in_the_shared_position(fires):
    """The CSV has to concatenate with the other seven reports' CSVs."""
    assert app.SHARED_COLUMNS == ("Country", "Year", "Fires", "Minimum (ha)",
                                  "Maximum (ha)", "Total (ha)")
    assert app.COLUMNS[:len(app.SHARED_COLUMNS)] == app.SHARED_COLUMNS


def test_every_hectare_cell_is_empty(fires):
    """Empty says nothing was published; a zero would say nothing burnt."""
    for row in run(fires):
        assert row.values[3:6] == ("", "", "")
        assert row.readable_values[3:6] == ("", "", "")


def test_the_row_carries_no_area_at_all():
    """Not stored as ``None`` and rendered blank — there is no attribute for it."""
    assert not hasattr(app.Row(country="Guatemala", year=2025, fires=1,
                               false_alarms=0, located=1, protected=0), "total")


def test_there_is_no_area_column_to_sum():
    """The assertion behind the whole report: the model publishes no size."""
    from src.providers.guatemala_inab.wildfire import InabWildfire
    names = [column.name for column in InabWildfire.__table__.columns]
    assert not [name for name in names if "area_ha" in name]


# --------------------------------------------------------------------------
# The year is the Guatemalan one
# --------------------------------------------------------------------------

def test_the_year_is_the_local_one_not_the_utc_one(fires):
    """2025-01-01 03:00 UTC is 2024-12-31 21:00 in Guatemala: a 2024 fire."""
    years = rows_by_year(run(fires))
    assert years[2024].fires == 3, "the New Year fire counts towards 2024"
    assert years[2025].fires == 3


def test_the_years_are_newest_first(fires):
    rows = run(fires)
    assert [row.year for row in rows] == [2025, 2024, None]


def test_one_year_can_be_selected(fires):
    rows = run(fires, year=2025)
    assert [row.year for row in rows] == [2025, None]
    assert rows[0].fires == 3


def test_a_year_with_no_fires_reports_nothing(fires):
    assert run(fires, year=1999) == []


# --------------------------------------------------------------------------
# The counts
# --------------------------------------------------------------------------

def test_the_country_is_guatemala_on_every_row(fires):
    assert {row.country for row in run(fires)} == {app.COUNTRY_NAME}


def test_the_total_row_is_the_sum_of_the_years(fires):
    rows = run(fires)
    total = rows[-1]
    assert total.is_total
    assert total.year_label == app.TOTAL_LABEL
    assert total.fires == 6
    assert total.false_alarms == 2
    assert total.located == 5
    assert total.protected == 3


def test_the_located_count_is_a_share_of_the_fires_beside_it(fires):
    years = rows_by_year(run(fires))
    assert (years[2024].fires, years[2024].located) == (3, 2), "the New Year fire has no point"
    assert (years[2025].fires, years[2025].located) == (3, 3)
    assert years[2025].located_share == pytest.approx(100.0)
    assert years[2024].located_share == pytest.approx(200 / 3)


def test_the_protected_area_count_is_over_the_counted_fires(fires):
    years = rows_by_year(run(fires))
    assert years[2024].protected == 1
    assert years[2025].protected == 2


def test_the_total_share_is_the_ratio_of_the_totals_not_the_mean_of_the_ratios(fires):
    """66.67% and 100% must not average to 83.33% by accident of being averaged."""
    rows = run(fires)
    total = rows[-1]
    assert total.located_share == pytest.approx(100.0 * 5 / 6)


# --------------------------------------------------------------------------
# False alarms
# --------------------------------------------------------------------------

def test_a_false_alarm_is_left_out_of_fires_by_default(fires):
    total = run(fires)[-1]
    assert total.fires == 6, "eight records, two of them false alarms"
    assert total.false_alarms == 2


def test_a_false_alarm_keeps_its_column_when_it_is_excluded(fires):
    """The whole reason it is a column and not a log line."""
    years = rows_by_year(run(fires))
    assert (years[2024].fires, years[2024].false_alarms) == (3, 1)
    assert (years[2025].fires, years[2025].false_alarms) == (3, 1)


def test_a_false_alarm_can_be_counted_on_request(fires):
    total = run(fires, include_false_alarms=True)[-1]
    assert total.fires == 8
    assert total.false_alarms == 2, "still reported, now also counted"
    assert total.located == 7


def test_a_null_status_is_still_a_fire(fires):
    """``<>`` would evaluate to NULL and drop it; ``IS DISTINCT FROM`` does not."""
    total = run(fires)[-1]
    assert total.fires == 6, "the bare record with no attributes is in the count"


def test_the_filter_is_null_safe_by_construction():
    """Asserted on the SQL as well as on the counts, so a rewrite cannot regress it."""
    condition = str(app.is_a_fire().compile(
        compile_kwargs={"literal_binds": True}))
    assert "IS DISTINCT FROM" in condition
    assert guatemala_inab.STATUS_FALSE in condition


def test_including_false_alarms_filters_nothing(fires):
    assert str(app.is_a_fire(include_false_alarms=True).compile(
        compile_kwargs={"literal_binds": True})) == "true"


def test_a_year_of_nothing_but_false_alarms_still_appears(db_session, provider):
    """Fires of zero is the honest answer; the year vanishing would not be."""
    store(db_session, provider, "only-false",
          datetime.datetime(2023, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_FALSE, None, "conred", "telefono", True, False)
    db_session.commit()

    rows = run(db_session)
    assert rows[0].year == 2023
    assert (rows[0].fires, rows[0].false_alarms) == (0, 1)


def test_an_unverified_report_stays_in_the_count(fires):
    """*Nobody looked* is not *there was no fire*, so it is not a false alarm."""
    years = rows_by_year(run(fires))
    assert years[2025].fires == 3, "the unverified record is one of the three"
    assert years[2025].false_alarms == 1


# --------------------------------------------------------------------------
# Located and protected are columns, not filters
# --------------------------------------------------------------------------

def test_an_unlocated_fire_still_counts_as_a_fire(fires):
    years = rows_by_year(run(fires))
    assert years[2024].fires == 3
    assert years[2024].located == 2


def test_the_protected_area_test_is_the_published_name(fires):
    """No boundary is tested against: INAB says which area, and the import folds ""."""
    condition = str(app.is_in_protected_area())
    assert "protected_area_name IS NOT NULL" in condition


# --------------------------------------------------------------------------
# Percentages
# --------------------------------------------------------------------------

def test_a_share_of_nothing_is_no_answer():
    assert app.share(0, 0) is None
    assert app.share_label(0, 0) == ""
    assert app.share_label(1, 4) == "25.00"


def test_a_year_with_no_counted_fires_has_no_located_share(db_session, provider):
    store(db_session, provider, "only-false",
          datetime.datetime(2023, 5, 1, 18, 0, tzinfo=UTC),
          guatemala_inab.STATUS_FALSE, None, "conred", "telefono", True, False)
    db_session.commit()

    assert run(db_session)[0].located_share is None


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--db-name", "x", "--db-user", "y"])


@pytest.mark.parametrize("option", ["--country", "--country-source"])
def test_the_country_options_are_refused_with_a_reason(capsys, option):
    with pytest.raises(SystemExit):
        app.parse_arguments([option, "Guatemala", "--csv", "a.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert "Guatemala" in capsys.readouterr().err


@pytest.mark.parametrize("option, value", [("--area-method", "geometry"),
                                           ("--surface", "burnt"),
                                           ("--min-area", "10")])
def test_the_area_options_are_refused_with_a_reason(capsys, option, value):
    """Anyone passing one has copied a command line from a report that has hectares."""
    with pytest.raises(SystemExit):
        app.parse_arguments([option, value, "--csv", "a.csv",
                             "--db-name", "x", "--db-user", "y"])
    error = capsys.readouterr().err
    assert "no perimeter, no burnt area" in error
    assert option in error


def test_a_plain_run_is_accepted():
    args = app.parse_arguments(["--csv", "a.csv", "--db-name", "x", "--db-user", "y"])
    assert args.year is None
    assert args.include_false_alarms is False


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_shared_columns_first(tmp_path, fires):
    path = tmp_path / "guatemala.csv"
    app.write_csv(run(fires), path, logger)

    with path.open(encoding="utf-8") as handle:
        header, *body = list(csv.reader(handle))
    assert tuple(header) == app.COLUMNS
    assert header[:6] == list(app.SHARED_COLUMNS)
    assert len(body) == 3


def test_the_csv_leaves_the_hectare_fields_empty(tmp_path, fires):
    path = tmp_path / "guatemala.csv"
    app.write_csv(run(fires), path, logger)

    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["Total (ha)"] for row in rows} == {""}
    assert {row["Minimum (ha)"] for row in rows} == {""}
    assert {row["Maximum (ha)"] for row in rows} == {""}


def test_the_csv_writes_bare_numbers(tmp_path, fires):
    path = tmp_path / "guatemala.csv"
    app.write_csv(run(fires), path, logger)
    assert "," not in path.read_text(encoding="utf-8").split("\n")[1].split(",")[2]


def test_the_docx_is_written(tmp_path, fires):
    pytest.importorskip("docx")
    path = tmp_path / "guatemala.docx"
    app.write_docx(run(fires), path, None, logger)
    assert path.exists() and path.stat().st_size > 0


def test_the_docx_says_why_the_area_columns_are_empty(tmp_path, fires):
    """A table with three empty columns is the first thing a reader will ask about."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "guatemala.docx"
    app.write_docx(run(fires), path, None, logger)

    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    assert "no perimeter, no burnt area" in text
    assert "an empty cell says nothing was published" in text


def test_the_docx_says_there_is_no_cause(tmp_path, fires):
    docx = pytest.importorskip("docx")
    path = tmp_path / "guatemala.docx"
    app.write_docx(run(fires), path, None, logger)

    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    assert "publishes no cause" in text


def test_the_docx_says_which_scope_the_false_alarms_are_in(tmp_path, fires):
    docx = pytest.importorskip("docx")
    excluded, included = tmp_path / "a.docx", tmp_path / "b.docx"
    app.write_docx(run(fires), excluded, None, logger)
    app.write_docx(run(fires, include_false_alarms=True), included, None, logger,
                   include_false_alarms=True)

    def prose(path):
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)

    assert "false alarms excluded from Fires" in prose(excluded)
    assert "false alarms counted in Fires" in prose(included)


# --------------------------------------------------------------------------
# End to end, through the entry point
# --------------------------------------------------------------------------

def arguments(**overrides):
    """A parsed namespace for :func:`report`, without going through argparse."""
    import argparse
    values = {"year": None, "include_false_alarms": False, "csv": None, "docx": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_report_writes_both_outputs(tmp_path, fires):
    pytest.importorskip("docx")
    csv_path, docx_path = tmp_path / "a.csv", tmp_path / "a.docx"
    rows = app.report(arguments(csv=csv_path, docx=docx_path),
                      fires.get_bind(), logger)

    assert csv_path.exists() and docx_path.exists()
    assert rows[-1].fires == 6


def test_report_refuses_to_write_an_empty_file(tmp_path, fires):
    """An empty report is almost always a wrong --year, and a blank file hides that."""
    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(arguments(year=1999, csv=tmp_path / "a.csv"),
                   fires.get_bind(), logger)
    assert not (tmp_path / "a.csv").exists()


def test_an_empty_report_has_no_total_row(fires):
    assert app.summarise([]) == []


def test_main_reports_a_bad_scope_without_a_traceback(tmp_path, fires, caplog):
    url = fires.get_bind().url
    argv = ["--year", "1999", "--csv", str(tmp_path / "a.csv"),
            "--db-host", url.host, "--db-port", str(url.port),
            "--db-name", url.database, "--db-user", url.username,
            "--db-password", url.password or ""]
    assert app.main(argv) == 1
    assert "No wildfires matched" in caplog.text
