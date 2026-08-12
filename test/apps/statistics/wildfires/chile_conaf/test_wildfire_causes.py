#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF fire cause report (Chile).

This report exists to be read across fifteen seasons, and the archive it reads has a
**discontinuity in 2023-2024**: CONAF renumbered the taxonomy and renamed ten of the
categories, so *Accidentes eléctricos* stops and *Líneas eléctricas* starts. What is
pinned here is that the report groups on the canonical name and never on the reused
code, that it says where the series breaks instead of quietly joining it, and that
``--bridge-schemes`` joins it only when a reader asks.

The second thing is the three synthetic labels. 1,012 fires publish no classification
at all, 6,221 publish only a *causa específica*, and a handful publish a *causa
general* the reconciliation tables do not know. All three are rows in this report
rather than fires that vanish from it, and they are three rows and not one because
they mean three different things.
"""

import csv
import datetime
import logging

import pytest

from src.apps.statistics.wildfires.chile_conaf import wildfire_causes as app
from src.data_model.data_provider import DataProvider
from src.providers import chile_conaf
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.fire_cause import SCHEME_SUCCESSORS
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire

logger = logging.getLogger("test-conaf-causes")

UTC = datetime.timezone.utc

#: The classifications the fixture files fires under.
#:
#: ``(key, cause, cause_code, cause_normalised, cause_en, specific_cause, scheme)``.
#: The pre- and post-2023 electrical causes are both here, because the break between
#: them is what this report has to be honest about.
CAUSES = [
    ("electrical_pre", "1.9. Accidentes eléctricos", "1.9", "Accidentes eléctricos",
     "Electrical accidents", None, "pre_2023"),
    ("electrical_post", "4.9 - Líneas eléctricas", "4.9", "Líneas eléctricas",
     "Power lines", None, "post_2023"),
    ("intentional", "2.1. Incendios intencionales", "2.1", "Incendios intencionales",
     "Intentional fires", None, None),
    # A published *causa general* the tables do not know: mojibake, one letter lost.
    ("unreconciled", "TRANSEONTES", None, None, None, None, None),
    # A specific cause with no general one — the shape six seasons publish.
    ("specific_only", None, None, None, None, "1.7.1. Uso de fuego por transeúntes",
     None),
]

#: ``(season, cause key or None, hectares)``.
FIRES = [
    # 2016-2017: the old vocabulary.
    (2016, "electrical_pre", 10.0),
    (2016, "electrical_pre", 20.0),
    (2016, "intentional", 30.0),
    (2016, "unreconciled", 5.0),
    (2016, "specific_only", 1.0),
    (2016, None, 4.0),
    # 2023-2024: the new one. The electrical cause has changed its name.
    (2023, "electrical_post", 100.0),
    (2023, "intentional", 50.0),
]


@pytest.fixture
def populated(db_session):
    provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                            product=chile_conaf.PROVIDER_PRODUCT,
                            full_name=chile_conaf.PROVIDER_FULL_NAME,
                            url=chile_conaf.PROVIDER_URL)
    db_session.add(provider)
    db_session.flush()

    causes = {}
    for (key, cause, code, normalised, english, specific, scheme) in CAUSES:
        row = ConafFireCause(cause=cause, cause_code=code, cause_normalised=normalised,
                             cause_en=english, specific_cause=specific, scheme=scheme)
        db_session.add(row)
        db_session.flush()
        causes[key] = row.id

    for index, (season, key, hectares) in enumerate(FIRES):
        instant = datetime.datetime(season, 7, 1, tzinfo=UTC)
        ignition = ConafIgnition(
            data_provider_id=provider.id, season_start_year=season, number=index,
            geometry="SRID=4326;POINT(-73.05 -36.83)",
            geometry_utm19s=f"SRID={chile_conaf.SOURCE_SRID_MAINLAND};"
                            f"POINT({670000 + index * 1000} 5920000)",
            date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE)
        db_session.add(ignition)
        db_session.flush()
        db_session.add(ConafWildfire(
            data_provider_id=provider.id, ignition_id=ignition.id,
            season=f"{season}-{season + 1}", season_start_year=season, number=index,
            name=f"FUEGO {index}",
            cause_id=None if key is None else causes[key],
            date_time_precision=chile_conaf.PRECISION_SEASON,
            area_ha_total=hectares, area_totals_agree=True,
            start_date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE))
    db_session.commit()
    return db_session


def run(session, **kwargs):
    return app.compute(session, kwargs.pop("season", None), logger, **kwargs)


def find(rows, season, cause):
    matches = [row for row in rows if row.season == season and row.cause == cause]
    assert len(matches) == 1, f"expected one row for {cause} in {season}"
    return matches[0]


# --------------------------------------------------------------------------
# What is grouped on
# --------------------------------------------------------------------------

def test_the_report_groups_on_the_canonical_name(populated):
    """Never on the code: ``4.1`` names two different causes on the two sides of the break.

    A fifteen-season series grouped on the code merges every fire whose cause was
    unknown with every fire started by forestry work.
    """
    rows = run(populated)

    assert find(rows, 2016, "Accidentes eléctricos").fires == 2
    assert find(rows, 2016, "Accidentes eléctricos").hectares == pytest.approx(30.0)


def test_a_season_reports_each_cause_as_a_share_of_itself(populated):
    """The percentage is of the season, not of the archive: coverage varies by season."""
    row = find(run(populated), 2016, "Incendios intencionales")

    assert row.season_fires == 6
    assert row.fires_percent == pytest.approx(100.0 / 6)
    assert row.hectares_percent == pytest.approx(100.0 * 30.0 / 70.0)


# --------------------------------------------------------------------------
# The break at 2023-2024
# --------------------------------------------------------------------------

def test_a_renamed_cause_is_two_series_and_the_report_says_so(populated):
    """*Accidentes eléctricos* stops and *Líneas eléctricas* starts, in the same slot.

    Reported rather than repaired: a reader looking at a column of counts that goes
    to zero needs to know whether the fires stopped or the category did.
    """
    rows = run(populated)

    assert find(rows, 2016, "Accidentes eléctricos").fires == 2
    assert not [row for row in rows
                if row.season == 2023 and row.cause == "Accidentes eléctricos"]
    assert find(rows, 2023, "Líneas eléctricas").fires == 1

    broken = app.broken_series(rows)
    assert "Accidentes eléctricos" in broken
    assert "Líneas eléctricas" in broken


def test_a_cause_that_did_not_change_is_not_reported_as_broken(populated):
    """*Incendios intencionales* is one of the four CONAF kept unchanged."""
    assert "Incendios intencionales" not in app.broken_series(run(populated))


def test_bridging_joins_the_two_halves_under_the_current_name(populated):
    """Only when asked, and under the name CONAF publishes now.

    A series that ends in the current vocabulary is easier to extend than one that
    ends in a retired one.
    """
    rows = run(populated, bridge_schemes=True)

    assert find(rows, 2016, "Líneas eléctricas").fires == 2
    assert not [row for row in rows if row.cause == "Accidentes eléctricos"]


def test_the_bridge_is_not_the_default(populated):
    """It asserts a continuity CONAF did not publish, so a reader has to ask for it."""
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.bridge_schemes is False


def test_the_bridge_only_moves_the_renamed_causes():
    """Everything not in the table comes back unchanged, the synthetic labels included.

    A bridge that touched anything else would silently rename a category CONAF did
    keep, which is the error this whole option is trying not to make.
    """
    assert app.bridge("Accidentes eléctricos") == "Líneas eléctricas"
    for cause in ("Incendios intencionales", "Faenas forestales", *app.SYNTHETIC_LABELS):
        assert cause not in SCHEME_SUCCESSORS
        assert app.bridge(cause) == cause


# --------------------------------------------------------------------------
# The three synthetic labels
# --------------------------------------------------------------------------

def test_a_fire_with_no_classification_is_a_row_and_not_a_disappearance(populated):
    """1,012 fires. Dropping them would make every percentage in the report wrong."""
    row = find(run(populated), 2016, app.NO_CAUSE_LABEL)

    assert row.fires == 1
    assert row.hectares == pytest.approx(4.0)


def test_a_specific_cause_alone_is_not_the_same_as_no_cause(populated):
    """A fire whose specific cause is *uso de fuego por transeúntes* is classified.

    Just not at the level this report groups by — and calling that "no cause
    published" would be false. 6,221 fires are like that.
    """
    rows = run(populated)

    assert find(rows, 2016, app.SPECIFIC_ONLY_LABEL).fires == 1
    assert find(rows, 2016, app.NO_CAUSE_LABEL).fires == 1
    assert app.SPECIFIC_ONLY_LABEL != app.NO_CAUSE_LABEL


def test_an_unreconciled_cause_is_its_own_row_too(populated):
    """``'TRANSEONTES'`` lost a letter to a bad decode and cannot be guessed back.

    It is a published classification the tables do not know yet, which is a third
    thing again — and the row is how a reader finds out the tables need extending.
    """
    row = find(run(populated), 2016, app.UNRECONCILED_LABEL)

    assert row.fires == 1
    assert row.cause_en is None


def test_the_three_labels_are_printed_after_the_real_causes(populated):
    """They are not causes, and sorting them among the causes by count would suggest
    they were."""
    season_rows = [row for row in run(populated) if row.season == 2016]
    labels = [row.cause for row in season_rows]

    assert labels[-3:] == list(app.SYNTHETIC_LABELS)


def test_the_real_causes_are_ordered_by_how_many_fires_they_hold(populated):
    real = [row for row in run(populated)
            if row.season == 2016 and row.cause not in app.SYNTHETIC_LABELS]

    assert [row.fires for row in real] == sorted((row.fires for row in real),
                                                 reverse=True)


# --------------------------------------------------------------------------
# Scope and output
# --------------------------------------------------------------------------

def test_a_summary_block_covers_every_season(populated):
    rows = run(populated)
    totals = [row for row in rows if row.is_total]

    assert find(totals, None, "Incendios intencionales").fires == 2
    assert find(totals, None, "Incendios intencionales").hectares == pytest.approx(80.0)


def test_one_season_gets_no_summary_block(populated):
    """A total over one season is the season, printed twice."""
    rows = run(populated, season=2016)

    assert not [row for row in rows if row.is_total]


def test_an_empty_scope_reports_nothing_rather_than_zeros(db_session, caplog):
    with caplog.at_level(logging.WARNING):
        rows = run(db_session)

    assert rows == []
    assert any("No CONAF fire in scope" in record.message for record in caplog.records)


def test_the_csv_carries_both_languages(populated, tmp_path):
    path = tmp_path / "causes.csv"
    app.write_csv(run(populated), path, logger)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    electrical = next(row for row in rows
                      if row["Cause"] == "Accidentes eléctricos"
                      and row["Season"] == "2016-2017")
    assert electrical["Cause (English)"] == "Electrical accidents"
    assert electrical["Fires"] == "2"


def test_a_synthetic_label_has_no_english_to_print(populated, tmp_path):
    path = tmp_path / "causes.csv"
    app.write_csv(run(populated), path, logger)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    synthetic = next(row for row in rows if row["Cause"] == app.NO_CAUSE_LABEL)
    assert synthetic["Cause (English)"] == ""
