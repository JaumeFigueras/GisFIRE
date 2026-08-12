#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF perimeter ↔ report binding application (Chile).

These are one agency's two publications of one incident record, so unlike the
Canadian pair there really is a shared identifier — the office's ``NUMERO_REG`` —
and the strongest rules use it. What makes it hard is that **the identifier is not
unique**: 93 perimeters of 2016-2017 have a ``(CODREG, NUMERO_REG)`` that matches two
reports, which is why the cascade has two tie-breaks above the bare pair, one textual
and one spatial.

So the tests are about which rule fires, and above all about the **refusals**: a
binding is only written when the best-labelled group holds exactly one candidate, and
a report two perimeters both claim unbinds them both.

The geometry is in EPSG:32719 metres, as the mainland archives publish it, so a
fixture coordinate is a distance in metres and ``--max-distance`` can be checked by
hand.
"""

import csv
import datetime
import logging

import pytest

from sqlalchemy import select

from src.apps.bindings.wildfires.chile_conaf_magnitud import bind_conaf_wildfires as app
from src.data_model.data_provider import DataProvider
from src.providers import chile_conaf
from src.providers import chile_conaf_magnitud
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire
from src.providers.chile_conaf_magnitud import DEFAULT_MATCH_DISTANCE_M
from src.providers.chile_conaf_magnitud import MATCH_INSIDE_SINGLE
from src.providers.chile_conaf_magnitud import MATCH_METHODS
from src.providers.chile_conaf_magnitud import MATCH_METHOD_CONFIDENCE
from src.providers.chile_conaf_magnitud import MATCH_NAME_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NAME_SEASON_INSIDE
from src.providers.chile_conaf_magnitud import MATCH_NEAR_SINGLE
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_NAME_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_REGION_INSIDE_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_REGION_NAME_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_REGION_SEASON
from src.providers.chile_conaf_magnitud.wildfire import ConafMagnitudWildfire

UTC = datetime.timezone.utc

logger = logging.getLogger("test-conaf-bind")

SEASON = 2016

#: The fixture perimeter: a 10 km square on the mainland grid, so that a point's
#: distance from it is a number of metres anyone can check by hand.
SIDE = 10_000.0
ORIGIN_X, ORIGIN_Y = 670_000.0, 5_920_000.0


def square(x: float, y: float, side: float = SIDE) -> str:
    return (f"SRID={chile_conaf.SOURCE_SRID_MAINLAND};MULTIPOLYGON((({x} {y}, "
            f"{x + side} {y}, {x + side} {y + side}, {x} {y + side}, {x} {y})))")


@pytest.fixture
def providers(db_session):
    reports = DataProvider(name=chile_conaf.PROVIDER_NAME,
                           product=chile_conaf.PROVIDER_PRODUCT,
                           full_name=chile_conaf.PROVIDER_FULL_NAME,
                           url=chile_conaf.PROVIDER_URL)
    perimeters = DataProvider(name=chile_conaf_magnitud.PROVIDER_NAME,
                              product=chile_conaf_magnitud.PROVIDER_PRODUCT,
                              full_name=chile_conaf.PROVIDER_FULL_NAME,
                              url=chile_conaf_magnitud.PROVIDER_URL)
    db_session.add_all([reports, perimeters])
    db_session.commit()
    return reports, perimeters


def add_perimeter(session, provider, name, *, number=None, region_code="08",
                  x=ORIGIN_X, y=ORIGIN_Y, side=SIDE,
                  season=SEASON) -> ConafMagnitudWildfire:
    """One mapped fire, its square anchored at ``(x, y)`` in UTM 19S metres."""
    fire = ConafMagnitudWildfire(
        data_provider=provider, season=f"{season}-{season + 1}",
        season_start_year=season, number=number, name=name,
        region_code=region_code, cause_published=None,
        area_ha_mapped=10_000.0, area_ha_published=10_000.0, part_count=1,
        date_time_precision=chile_conaf.PRECISION_DAY,
        perimeter=None, perimeter_utm19s=square(x, y, side),
        start_date_time=datetime.datetime(season + 1, 1, 18, tzinfo=UTC),
        time_zone=chile_conaf.DEFAULT_TIME_ZONE)
    session.add(fire)
    session.flush()
    return fire


def add_report(session, provider, name, *, number=None, region_code="08",
               x=ORIGIN_X + SIDE / 2, y=ORIGIN_Y + SIDE / 2,
               season=SEASON) -> ConafWildfire:
    """One seasonal report, its point at ``(x, y)`` in UTM 19S metres."""
    ignition = ConafIgnition(
        data_provider=provider, season_start_year=season, number=number,
        region_code=region_code,
        geometry="SRID=4326;POINT(-73.05 -36.83)",
        geometry_utm19s=f"SRID={chile_conaf.SOURCE_SRID_MAINLAND};POINT({x} {y})",
        date_time=datetime.datetime(season + 1, 1, 18, tzinfo=UTC),
        time_zone=chile_conaf.DEFAULT_TIME_ZONE)
    session.add(ignition)
    session.flush()
    report = ConafWildfire(
        data_provider=provider, ignition_id=ignition.id,
        season=f"{season}-{season + 1}", season_start_year=season, number=number,
        name=name, region_code=region_code,
        date_time_precision=chile_conaf.PRECISION_DAY,
        area_ha_total=9_000.0, area_totals_agree=True,
        start_date_time=datetime.datetime(season + 1, 1, 18, tzinfo=UTC),
        time_zone=chile_conaf.DEFAULT_TIME_ZONE)
    session.add(report)
    session.flush()
    return report


def run(session, **kwargs) -> list[app.Binding]:
    """Bind one season over the fixture."""
    return app.bind_season(session, kwargs.pop("season", SEASON),
                           kwargs.pop("max_distance", DEFAULT_MATCH_DISTANCE_M),
                           kwargs.pop("only_unbound", False),
                           kwargs.pop("dry_run", False), logger)


def only(bindings: list[app.Binding]) -> app.Binding:
    assert len(bindings) == 1, f"expected one perimeter, got {len(bindings)}"
    return bindings[0]


# --------------------------------------------------------------------------
# The labels: which rule a candidate satisfies
# --------------------------------------------------------------------------

def perimeter(**kwargs) -> app.Perimeter:
    values = dict(id=1, season_start_year=SEASON, number=402, name="SAN GUILLERMO",
                  region_code="08", area_ha_mapped=100.0)
    values.update(kwargs)
    return app.Perimeter(**values)


def report_of(**kwargs) -> app.Report:
    values = dict(id=1, number=402, name="SAN GUILLERMO", region_code="08",
                  area_ha_total=90.0, start_date_time=None)
    values.update(kwargs)
    return app.Report(**values)


def candidate(metres=0.0, inside=True, **kwargs) -> app.Candidate:
    return app.Candidate(report=report_of(**kwargs), metres=metres, inside=inside)


UNIQUE = {chile_conaf.normalise("SAN GUILLERMO")}


@pytest.mark.parametrize("perimeter_kwargs, candidate_kwargs, expected", [
    # Everything agrees.
    ({}, {}, MATCH_NUMBER_REGION_NAME_SEASON),
    # The número and the región agree; the names do not, but the point is inside.
    ({}, {"name": "OTRO FUNDO"}, MATCH_NUMBER_REGION_INSIDE_SEASON),
    # The número and the región agree and nothing else does.
    ({}, {"name": "OTRO FUNDO", "inside": False, "metres": 5000.0},
     MATCH_NUMBER_REGION_SEASON),
    # The región is unpublished — three whole archives are like that.
    ({"region_code": None}, {"inside": False, "metres": 5000.0},
     MATCH_NUMBER_NAME_SEASON),
    # No número at all, but the names agree and the point is inside.
    ({"number": None}, {"number": None}, MATCH_NAME_SEASON_INSIDE),
    # The names agree, the name is unique in the season, and the point is elsewhere.
    ({"number": None}, {"number": None, "inside": False, "metres": 5000.0},
     MATCH_NAME_SEASON),
    # Nothing textual agrees; the point is inside.
    ({"number": None, "name": None}, {"number": None, "name": "OTRO FUNDO"},
     MATCH_INSIDE_SINGLE),
    # Nothing textual agrees and the point is merely near.
    ({"number": None, "name": None},
     {"number": None, "name": "OTRO FUNDO", "inside": False, "metres": 900.0},
     MATCH_NEAR_SINGLE),
])
def test_a_candidate_gets_the_strongest_rule_it_satisfies(perimeter_kwargs,
                                                          candidate_kwargs, expected):
    inside = candidate_kwargs.pop("inside", True)
    metres = candidate_kwargs.pop("metres", 0.0)
    assert app.label(perimeter(**perimeter_kwargs),
                     candidate(metres=metres, inside=inside, **candidate_kwargs),
                     UNIQUE) == expected


def test_a_report_that_agrees_on_nothing_and_is_nowhere_near_is_no_candidate():
    """``metres`` of ``None`` means the pair was never compared spatially.

    It gets into the candidate list on a número or a name; if neither turns out to
    agree there is nothing left, and labelling it anyway would make well-determined
    fires ambiguous for nothing.
    """
    assert app.label(perimeter(number=None, name=None),
                     app.Candidate(report=report_of(number=None, name="OTRO"),
                                   metres=None, inside=False),
                     UNIQUE) is None


def test_two_missing_numbers_are_not_an_agreement():
    """``NUMERO_REG`` is unpublished on two whole seasons of reports.

    Treating *neither has one* as agreement would bind every perimeter of 2013-2014
    to whichever report happened to be nearest, and score it 0.95.
    """
    method = app.label(perimeter(number=None, name="OTRO FUNDO"),
                       candidate(number=None, name="DISTINTO", inside=False,
                                 metres=900.0),
                       UNIQUE)
    assert method == MATCH_NEAR_SINGLE
    assert method != MATCH_NUMBER_REGION_SEASON


def test_a_shared_name_is_not_an_identification():
    """``LOS MAITENES`` names two fires of 2016-2017 and any number of places.

    The uniqueness is tested here rather than by counting the resulting group, so
    that the reason a fire goes unbound stays honest: it is *the name is not
    unique*, not *two candidates tied*.
    """
    shared = app.Candidate(report=report_of(number=None), metres=None, inside=False)
    assert app.label(perimeter(number=None), shared, UNIQUE) == MATCH_NAME_SEASON
    assert app.label(perimeter(number=None), shared, set()) is None


def test_two_missing_regions_are_not_an_agreement():
    """Six of the fifteen mainland seasons publish no ``CODREG`` on the perimeters."""
    method = app.label(perimeter(region_code=None),
                       candidate(region_code=None, inside=False, metres=5000.0),
                       UNIQUE)
    assert method == MATCH_NUMBER_NAME_SEASON


def test_every_method_is_ranked_and_scored():
    """So that a rule added later cannot reach the database without either."""
    assert set(app.RANKED_METHODS) == set(MATCH_METHODS)
    assert set(MATCH_METHOD_CONFIDENCE) == set(MATCH_METHODS)
    assert [app.rank_of(method) for method in app.RANKED_METHODS] \
        == list(range(len(MATCH_METHODS)))


def test_nothing_is_certain_here():
    """No published key joins the two products, so no rule scores 1.00.

    The strongest is 0.98, and it is three agreeing attributes rather than an
    identifier: the número is CONAF's own, but it repeats within a season and even
    within a región.
    """
    assert max(MATCH_METHOD_CONFIDENCE.values()) < 1.0


# --------------------------------------------------------------------------
# The cascade: taking the best group, and only if it holds one
# --------------------------------------------------------------------------

def test_a_stronger_rule_wins_over_a_weaker_one(db_session, providers):
    """Two candidates, both plausible; the número and the name settle it."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    wanted = add_report(db_session, reports, "SAN GUILLERMO", number=402)
    add_report(db_session, reports, "OTRO FUNDO", number=999,
               x=ORIGIN_X + 100, y=ORIGIN_Y + 100)
    db_session.commit()

    binding = only(run(db_session))
    assert binding.method == MATCH_NUMBER_REGION_NAME_SEASON
    assert binding.candidate.report.id == wanted.id


def test_two_candidates_tied_on_the_best_rule_bind_neither(db_session, providers):
    """``(CODREG, NUMERO_REG)`` matches two reports for 93 perimeters of 2016-2017.

    Where neither the name nor containment separates them, the honest answer is no
    binding. Picking one would be picking at random and scoring it 0.95.
    """
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE", number=402)
    add_report(db_session, reports, "UNO", number=402, x=ORIGIN_X - 50_000,
               y=ORIGIN_Y - 50_000)
    add_report(db_session, reports, "DOS", number=402, x=ORIGIN_X - 60_000,
               y=ORIGIN_Y - 60_000)
    db_session.commit()

    binding = only(run(db_session))
    assert not binding.is_bound
    assert binding.reason == app.UNBOUND_AMBIGUOUS
    assert binding.candidates == 2


def test_the_name_breaks_a_tie_the_number_cannot(db_session, providers):
    """83 of those 93 are settled this way: exactly one of the two carries the name."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    wanted = add_report(db_session, reports, "SAN GUILLERMO", number=402,
                        x=ORIGIN_X - 50_000, y=ORIGIN_Y - 50_000)
    add_report(db_session, reports, "OTRO FUNDO", number=402, x=ORIGIN_X - 60_000,
               y=ORIGIN_Y - 60_000)
    db_session.commit()

    binding = only(run(db_session))
    assert binding.method == MATCH_NUMBER_REGION_NAME_SEASON
    assert binding.candidate.report.id == wanted.id


def test_containment_breaks_a_tie_the_name_cannot(db_session, providers):
    """The other tie-break, and independent of the first: it uses the geometry.

    77 of the 93 are settled this way, which matters for the fires whose two
    candidates are named alike or unnamed.
    """
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE", number=402)
    wanted = add_report(db_session, reports, "OTRO", number=402)
    add_report(db_session, reports, "OTRO", number=402, x=ORIGIN_X - 60_000,
               y=ORIGIN_Y - 60_000)
    db_session.commit()

    binding = only(run(db_session))
    assert binding.method == MATCH_NUMBER_REGION_INSIDE_SEASON
    assert binding.candidate.report.id == wanted.id


def test_a_perimeter_with_no_candidate_at_all_says_so(db_session, providers):
    """Three of the 743. The reason is recorded so the CSV can be acted on."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SOLITARIO", number=7)
    add_report(db_session, reports, "OTRO FUNDO", number=999,
               x=ORIGIN_X - 500_000, y=ORIGIN_Y - 500_000)
    db_session.commit()

    binding = only(run(db_session))
    assert not binding.is_bound
    assert binding.reason == app.UNBOUND_NO_CANDIDATE


def test_two_perimeters_claiming_one_report_bind_neither(db_session, providers):
    """Both are dropped rather than one picked: nothing in the data would choose.

    A contest here usually means one report covers a fire CONAF mapped in two
    separately-named pieces — a dissolve the import did not make, and worth looking
    at rather than papering over.
    """
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402,
                  x=ORIGIN_X + 200, y=ORIGIN_Y + 200)
    add_report(db_session, reports, "SAN GUILLERMO", number=402)
    db_session.commit()

    bindings = run(db_session)
    assert len(bindings) == 2
    assert not any(binding.is_bound for binding in bindings)
    assert {binding.reason for binding in bindings} == {app.UNBOUND_REPORT_CONTESTED}


# --------------------------------------------------------------------------
# The tolerance stage
# --------------------------------------------------------------------------

def test_a_point_just_outside_the_burn_is_still_the_fire(db_session, providers):
    """A report's point is where the fire was *reported*.

    For a 200-hectare fire that is often the road it was seen from, which is why
    there is a tolerance stage at all — and why it is the weakest rule there is.
    """
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE")
    add_report(db_session, reports, "OTRO", x=ORIGIN_X - 500, y=ORIGIN_Y + SIDE / 2)
    db_session.commit()

    binding = only(run(db_session))
    assert binding.method == MATCH_NEAR_SINGLE
    assert binding.candidate.metres == pytest.approx(500.0, abs=1.0)


def test_the_tolerance_can_be_turned_off(db_session, providers):
    """``--max-distance 0`` keeps only the points that are actually inside."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE")
    add_report(db_session, reports, "OTRO", x=ORIGIN_X - 500, y=ORIGIN_Y + SIDE / 2)
    db_session.commit()

    binding = only(run(db_session, max_distance=0.0))
    assert not binding.is_bound
    assert binding.reason == app.UNBOUND_NO_CANDIDATE


def test_a_point_beyond_the_tolerance_is_not_a_candidate(db_session, providers):
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE")
    add_report(db_session, reports, "OTRO", x=ORIGIN_X - 5_000, y=ORIGIN_Y + SIDE / 2)
    db_session.commit()

    assert not only(run(db_session)).is_bound


def test_the_number_rules_are_not_gated_on_distance(db_session, providers):
    """Deliberate: gating them would throw away the strongest evidence in the archive.

    In the older seasons a report's point can be the comuna's centre, tens of
    kilometres from the fire. The número is still the número.
    """
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    add_report(db_session, reports, "SAN GUILLERMO", number=402,
               x=ORIGIN_X - 200_000, y=ORIGIN_Y - 200_000)
    db_session.commit()

    binding = only(run(db_session))
    assert binding.method == MATCH_NUMBER_REGION_NAME_SEASON


# --------------------------------------------------------------------------
# What gets written
# --------------------------------------------------------------------------

def test_a_binding_is_written_with_its_method_and_confidence(db_session, providers):
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    wanted = add_report(db_session, reports, "SAN GUILLERMO", number=402)
    db_session.commit()

    run(db_session)

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.conaf_wildfire_id == wanted.id
    assert stored.match_method == MATCH_NUMBER_REGION_NAME_SEASON
    assert stored.match_confidence == pytest.approx(
        MATCH_METHOD_CONFIDENCE[MATCH_NUMBER_REGION_NAME_SEASON])
    assert stored.matched_at is not None


def test_a_refusal_leaves_the_row_unbound(db_session, providers):
    """And leaves it a fire: an unbindable perimeter is still published data."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SOLITARIO", number=7)
    db_session.commit()

    run(db_session)

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.conaf_wildfire_id is None
    assert stored.match_method is None
    assert stored.match_confidence is None


def test_rerunning_recomputes_a_binding_from_scratch(db_session, providers):
    """The default. A binding is a conclusion about the current data, not a record."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE")
    add_report(db_session, reports, "OTRO")
    db_session.commit()
    run(db_session)
    assert db_session.scalar(select(ConafMagnitudWildfire)).match_method \
        == MATCH_INSIDE_SINGLE

    # A second report inside the same perimeter makes the evidence ambiguous.
    add_report(db_session, reports, "TERCERO", x=ORIGIN_X + 100, y=ORIGIN_Y + 100)
    db_session.commit()
    run(db_session)

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.match_method is None
    assert stored.conaf_wildfire_id is None


def test_only_unbound_leaves_an_existing_binding_alone(db_session, providers):
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SIN NOMBRE")
    add_report(db_session, reports, "OTRO")
    db_session.commit()
    run(db_session)

    add_report(db_session, reports, "TERCERO", x=ORIGIN_X + 100, y=ORIGIN_Y + 100)
    db_session.commit()
    run(db_session, only_unbound=True)

    assert db_session.scalar(select(ConafMagnitudWildfire)).match_method \
        == MATCH_INSIDE_SINGLE


def test_a_dry_run_writes_nothing(db_session, providers):
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    add_report(db_session, reports, "SAN GUILLERMO", number=402)
    db_session.commit()

    bindings = run(db_session, dry_run=True)
    assert only(bindings).is_bound, "it still says what it would have done"
    assert db_session.scalar(select(ConafMagnitudWildfire)).match_method is None


def test_a_season_with_no_reports_at_all_binds_nothing(db_session, providers):
    """The perimeter archive can be imported first; that is not an error."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    db_session.commit()

    binding = only(run(db_session))
    assert not binding.is_bound
    assert binding.reason == app.UNBOUND_NO_CANDIDATE


def test_reports_of_another_season_are_never_candidates(db_session, providers):
    """The same número is reused every season; the season is the frame."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    add_report(db_session, reports, "SAN GUILLERMO", number=402, season=SEASON + 1)
    db_session.commit()

    assert not only(run(db_session)).is_bound


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------

def test_the_csv_carries_the_unbound_rows_too(db_session, providers, tmp_path):
    """The unbound rows are the point of it: a binding that happened needs no looking at."""
    reports, perimeters = providers
    add_perimeter(db_session, perimeters, "SAN GUILLERMO", number=402)
    add_perimeter(db_session, perimeters, "SOLITARIO", number=7,
                  x=ORIGIN_X - 500_000, y=ORIGIN_Y - 500_000)
    add_report(db_session, reports, "SAN GUILLERMO", number=402)
    db_session.commit()

    bindings = run(db_session)
    path = tmp_path / "bindings.csv"
    app.write_csv(bindings, path, logger)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 2
    assert {row["outcome"] for row in rows} == {"bound", "unbound"}
    unbound = next(row for row in rows if row["outcome"] == "unbound")
    assert unbound["method"] == app.UNBOUND_NO_CANDIDATE
    assert unbound["confidence"] == ""
