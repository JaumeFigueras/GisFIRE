#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NBAC <-> NFDB binding application.

The binding is inference and nothing else — the two datasets share no published
identifier — so what has to be pinned down is not only that it finds the right agency
report but that it **refuses** to find one when the evidence does not single one out.
Much of what follows is about the refusals.

This cascade differs from the Spanish pair in three ways that the tests concentrate on:

* **there is no code stage**, so no binding is ever certain and nothing scores 1.00;
* the strongest rule is geometric — the point inside the perimeter — with the agency
  and the exact day as the discriminators, and a *tolerance* stage below them that
  produces about half the bindings and carries all of the risk;
* a perimeter cut at a provincial boundary carries **several** administrations, so the
  agency test is membership and comparing with ``=`` would score those as
  disagreements.

The geometry is in EPSG:3978 metres, as both datasets publish it, so a fixture
coordinate is a distance in metres and ``--max-distance`` can be tested directly.
"""

import csv
import datetime
import logging

import pytest

from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.bindings.wildfires.canada_nbac import bind_nfdb_wildfires as app
from src.data_model.data_provider import DataProvider
from src.providers import canada_nbac
from src.providers import canada_nfdb
from src.providers.canada_nbac.wildfire import DEFAULT_MATCH_DISTANCE_M
from src.providers.canada_nbac.wildfire import MATCH_INSIDE
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_DATE_MISMATCH
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_DAY
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_UNDATED
from src.providers.canada_nbac.wildfire import MATCH_METHODS
from src.providers.canada_nbac.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.canada_nbac.wildfire import MATCH_NEAR_AGENCY_DAY
from src.providers.canada_nbac.wildfire import NbacWildfire
from src.providers.canada_nfdb.ignition import NfdbIgnition
from src.providers.canada_nfdb.wildfire import NfdbWildfire

UTC = datetime.timezone.utc

logger = logging.getLogger("test-nbac-nfdb-bind")

#: The fixture perimeter: a 10 km square on the Lambert grid, so that a point's
#: distance from it in the tests is a number of metres anyone can check by hand.
SIDE = 10_000.0

YEAR = 2023
FIRE_DATE = datetime.date(YEAR, 6, 15)


def square(x: float, y: float, side: float = SIDE) -> str:
    """A square in EPSG:3978 metres, as a MULTIPOLYGON."""
    return (f"SRID=3978;MULTIPOLYGON((({x} {y}, {x + side} {y}, "
            f"{x + side} {y + side}, {x} {y + side}, {x} {y})))")


@pytest.fixture
def providers(db_session):
    nbac = DataProvider(name=canada_nbac.PROVIDER_NAME,
                        product=canada_nbac.PROVIDER_PRODUCT,
                        full_name=canada_nbac.PROVIDER_FULL_NAME,
                        url=canada_nbac.PROVIDER_URL)
    nfdb = DataProvider(name=canada_nfdb.PROVIDER_NAME,
                        product=canada_nfdb.PROVIDER_PRODUCT,
                        full_name=canada_nfdb.PROVIDER_FULL_NAME,
                        url=canada_nfdb.PROVIDER_URL)
    db_session.add_all([nbac, nfdb])
    db_session.commit()
    return nbac, nfdb


def add_perimeter(session, provider, gid, x, y, *, admin="AB",
                  start=FIRE_DATE, year=YEAR, side=SIDE) -> NbacWildfire:
    """One NBAC perimeter, its square anchored at ``(x, y)`` in Lambert metres."""
    fire = NbacWildfire(
        data_provider=provider, gid=gid, nfireid=abs(hash(gid)) % 100000, year=year,
        start_date_time=datetime.datetime(year, 6, 15, tzinfo=UTC),
        time_zone=canada_nbac.DEFAULT_TIME_ZONE,
        perimeter=None,
        perimeter_lambert=square(x, y, side),
        part_count=1, crosses_admin=canada_nbac.ADMIN_SEPARATOR in admin,
        admin_name=admin,
        fire_cause=canada_nbac.CAUSE_NATURAL,
        agency_start_date=start,
        date_source=(canada_nbac.SOURCE_AGENCY if start else canada_nbac.SOURCE_YEAR),
        date_time_precision=(canada_nbac.PRECISION_DAY if start
                             else canada_nbac.PRECISION_YEAR),
        area_ha_polygon=100.0, area_ha_adjusted=100.0, area_adjusted=False,
        prescribed=False,
    )
    session.add(fire)
    session.flush()
    return fire


def add_report(session, provider, fire_id, x, y, *, agency="AB",
               reported=FIRE_DATE, year=YEAR) -> NfdbWildfire:
    """One NFDB agency report, its point at ``(x, y)`` in Lambert metres."""
    ignition = NfdbIgnition(
        data_provider=provider, nfdb_fire_id=fire_id, year=year, src_agency=agency,
        geometry="SRID=4326;POINT(-114.0 55.0)",
        geometry_lambert=f"SRID=3978;POINT({x} {y})",
        date_time=datetime.datetime(year, 6, 15, tzinfo=UTC),
        time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
    )
    session.add(ignition)
    session.flush()
    report = NfdbWildfire(
        data_provider=provider, nfdb_fire_id=fire_id, agency_fire_id=f"LWF-{fire_id}",
        src_agency=agency, year=year, size_ha=50.0,
        fire_cause=canada_nfdb.CAUSE_NATURAL, prescribed=False,
        report_date=reported,
        start_date_time=datetime.datetime(year, 6, 15, tzinfo=UTC),
        time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
        ignition_id=ignition.id,
    )
    session.add(report)
    session.flush()
    return report


def run(session, **kwargs) -> list[app.Binding]:
    """Bind one year over the fixture."""
    return app.bind_year(session, kwargs.pop("year", YEAR),
                         kwargs.pop("max_distance", DEFAULT_MATCH_DISTANCE_M),
                         kwargs.pop("only_unbound", False),
                         datetime.datetime.now(UTC), logger,
                         write=kwargs.pop("write", True))


def only(bindings: list[app.Binding]) -> app.Binding:
    assert len(bindings) == 1, f"expected one perimeter, got {len(bindings)}"
    return bindings[0]


# --------------------------------------------------------------------------
# The labels: which rule a candidate satisfies
# --------------------------------------------------------------------------

def candidate(**kwargs) -> app.Candidate:
    values = dict(nfdb_id=1, metres=0.0, same_agency=True, same_day=True,
                  nbac_undated=False, nfdb_fire_id="x", agency_fire_id="y",
                  src_agency="AB", report_date=FIRE_DATE, size_ha=1.0)
    values.update(kwargs)
    return app.Candidate(**values)


@pytest.mark.parametrize("kwargs, expected", [
    ({}, MATCH_INSIDE_AGENCY_DAY),
    ({"same_day": False, "nbac_undated": True}, MATCH_INSIDE_AGENCY_UNDATED),
    ({"same_day": False}, MATCH_INSIDE_AGENCY_DATE_MISMATCH),
    ({"same_agency": False}, MATCH_INSIDE),
    ({"metres": 900.0}, MATCH_NEAR_AGENCY_DAY),
    ({"metres": 900.0, "same_day": False}, None),
    ({"metres": 900.0, "same_agency": False}, None),
])
def test_a_candidate_gets_the_strongest_rule_it_satisfies(kwargs, expected):
    assert candidate(**kwargs).method == expected


def test_a_point_outside_on_another_day_is_not_a_candidate_at_all():
    """Being near a burnt area on an unrelated day is not evidence of anything.

    Admitting it would make well-determined fires ambiguous for nothing.
    """
    assert candidate(metres=1500.0, same_day=False, nbac_undated=True).method is None


def test_the_undated_label_is_a_silence_not_a_disagreement():
    """NBAC publishes no date for 9,941 of its 51,818 fires; that is not a mismatch."""
    assert candidate(same_day=False, nbac_undated=True).method \
        == MATCH_INSIDE_AGENCY_UNDATED
    assert candidate(same_day=False, nbac_undated=False).method \
        == MATCH_INSIDE_AGENCY_DATE_MISMATCH


def test_every_method_is_ranked_and_scored():
    """So that a rule added later cannot reach the database without either."""
    assert set(app.RANKED_METHODS) == set(MATCH_METHODS)
    assert set(MATCH_METHOD_CONFIDENCE) == set(MATCH_METHODS)
    assert [app.rank_of(method) for method in app.RANKED_METHODS] \
        == list(range(len(MATCH_METHODS)))


def test_nothing_is_certain_here():
    """The Spanish binders open at 1.00 on a published identifier; this one has none.

    Stated as a test because it is the single most important difference between this
    application and its two predecessors, and a later edit that quietly scored a rule
    1.00 would be claiming something the data cannot support.
    """
    assert max(MATCH_METHOD_CONFIDENCE.values()) < 1.0
    assert MATCH_METHOD_CONFIDENCE[MATCH_INSIDE_AGENCY_DAY] == 0.95


# --------------------------------------------------------------------------
# The cascade
# --------------------------------------------------------------------------

def perimeter_of(gid="2023_1") -> app.Perimeter:
    return app.Perimeter(id=1, gid=gid, year=YEAR, admin_name="AB",
                         agency_start_date=FIRE_DATE, area_ha_polygon=100.0)


def test_no_candidate_is_reported_as_such():
    binding = app.match(perimeter_of(), [])
    assert not binding.is_bound
    assert binding.reason == app.UNBOUND_NO_CANDIDATE
    assert binding.candidates == 0


def test_one_candidate_is_bound_with_its_rule():
    binding = app.match(perimeter_of(), [candidate(nfdb_id=7)])
    assert binding.is_bound
    assert binding.candidate.nfdb_id == 7
    assert binding.method == MATCH_INSIDE_AGENCY_DAY
    assert binding.confidence == 0.95


def test_a_stronger_candidate_wins_over_a_weaker_one():
    """Two candidates, different labels: the best group has one member, so it binds."""
    binding = app.match(perimeter_of(), [
        candidate(nfdb_id=1, metres=1200.0),   # near_agency_day
        candidate(nfdb_id=2),                   # inside_agency_day
    ])
    assert binding.candidate.nfdb_id == 2
    assert binding.method == MATCH_INSIDE_AGENCY_DAY


def test_two_candidates_of_the_same_strength_are_refused():
    binding = app.match(perimeter_of(), [candidate(nfdb_id=1), candidate(nfdb_id=2)])
    assert not binding.is_bound
    assert binding.reason == app.UNBOUND_AMBIGUOUS
    assert binding.candidates == 2


def test_an_ambiguous_best_group_does_not_fall_through_to_a_weaker_rule():
    """Widening can only add candidates, so there is nothing below that could separate.

    Two contained same-day candidates and one distant one: the answer is *refused*,
    not "the distant one, then".
    """
    binding = app.match(perimeter_of(), [
        candidate(nfdb_id=1), candidate(nfdb_id=2),
        candidate(nfdb_id=3, metres=1800.0),
    ])
    assert not binding.is_bound
    assert binding.candidates == 2


def test_a_contested_report_unbinds_both_perimeters():
    """Nothing in the data would make the choice, so neither is guessed at."""
    shared = candidate(nfdb_id=99)
    bindings = [
        app.Binding(perimeter=perimeter_of("a"), candidate=shared,
                    method=MATCH_INSIDE_AGENCY_DAY, candidates=1),
        app.Binding(perimeter=perimeter_of("b"), candidate=shared,
                    method=MATCH_INSIDE_AGENCY_DAY, candidates=1),
    ]
    dropped = app.resolve_contested(bindings, logger)

    assert dropped == 2
    assert not any(binding.is_bound for binding in bindings)
    assert all(binding.reason == app.UNBOUND_REPORT_CONTESTED for binding in bindings)


def test_an_uncontested_binding_survives_the_check():
    bindings = [app.Binding(perimeter=perimeter_of("a"), candidate=candidate(nfdb_id=1),
                            method=MATCH_INSIDE_AGENCY_DAY, candidates=1)]
    assert app.resolve_contested(bindings, logger) == 0
    assert bindings[0].is_bound


# --------------------------------------------------------------------------
# Against the database
# --------------------------------------------------------------------------

def test_a_contained_point_binds_the_perimeter(db_session, providers):
    nbac, nfdb = providers
    fire = add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    report = add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()

    binding = only(run(db_session))

    assert binding.method == MATCH_INSIDE_AGENCY_DAY
    assert binding.candidate.nfdb_id == report.id
    db_session.expire_all()
    assert db_session.get(NbacWildfire, fire.id).nfdb_wildfire_id == report.id
    assert db_session.get(NbacWildfire, fire.id).match_confidence == 0.95
    assert db_session.get(NbacWildfire, fire.id).matched_at is not None


def test_a_point_just_outside_binds_on_the_tolerance(db_session, providers):
    """1 km beyond the edge, same agency, same day: the stage that does half the work."""
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", SIDE + 1000.0, 5000.0)
    db_session.commit()

    binding = only(run(db_session))

    assert binding.method == MATCH_NEAR_AGENCY_DAY
    assert binding.candidate.metres == pytest.approx(1000.0, abs=1.0)


def test_the_tolerance_is_a_limit(db_session, providers):
    """A point beyond --max-distance is not a candidate."""
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", SIDE + 3000.0, 5000.0)
    db_session.commit()

    assert only(run(db_session)).reason == app.UNBOUND_NO_CANDIDATE
    assert only(run(db_session, max_distance=5000.0)).method == MATCH_NEAR_AGENCY_DAY


def test_zero_distance_keeps_only_the_contained_points(db_session, providers):
    """``--max-distance 0`` is containment, for an analysis that will accept nothing else."""
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", SIDE + 500.0, 5000.0)
    db_session.commit()

    assert only(run(db_session, max_distance=0.0)).reason == app.UNBOUND_NO_CANDIDATE


def test_a_cross_border_perimeter_matches_either_of_its_agencies(db_session, providers):
    """``'AB; SK'`` is one fire in two provinces, and ``=`` would call that a mismatch.

    450 of the 51,818 perimeters carry more than one administration.
    """
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0,
                  admin=f"AB{canada_nbac.ADMIN_SEPARATOR}SK")
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0, agency="SK")
    db_session.commit()

    assert only(run(db_session)).method == MATCH_INSIDE_AGENCY_DAY


def test_a_different_agency_inside_the_perimeter_is_the_weaker_rule(db_session, providers):
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0, admin="AB")
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0, agency="BC")
    db_session.commit()

    assert only(run(db_session)).method == MATCH_INSIDE


def test_an_undated_perimeter_binds_on_containment_and_agency(db_session, providers):
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0, start=None)
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()

    assert only(run(db_session)).method == MATCH_INSIDE_AGENCY_UNDATED


def test_a_date_that_disagrees_still_binds_but_is_labelled(db_session, providers):
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0,
               reported=FIRE_DATE + datetime.timedelta(days=9))
    db_session.commit()

    assert only(run(db_session)).method == MATCH_INSIDE_AGENCY_DATE_MISMATCH


def test_a_report_of_another_year_is_never_a_candidate(db_session, providers):
    """The year is the scope, and NFIREID is not an identifier to fall back on."""
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0, year=2022,
               reported=datetime.date(2022, 6, 15))
    db_session.commit()

    assert only(run(db_session)).reason == app.UNBOUND_NO_CANDIDATE


def test_two_perimeters_claiming_one_report_are_both_left_unbound(db_session, providers):
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_perimeter(db_session, nbac, "2023_2", SIDE, 0.0)
    # On the shared edge, so it is inside both squares.
    add_report(db_session, nfdb, "R1", SIDE, 5000.0)
    db_session.commit()

    bindings = run(db_session)
    assert len(bindings) == 2
    assert not any(binding.is_bound for binding in bindings)
    assert all(binding.reason == app.UNBOUND_REPORT_CONTESTED for binding in bindings)


def test_a_re_run_recomputes_rather_than_accumulates(db_session, providers):
    """A perimeter that no longer matches has to lose its link."""
    nbac, nfdb = providers
    fire = add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    report = add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()
    run(db_session)
    db_session.commit()

    # The report stops matching rather than disappearing: its point moves 400 km away,
    # which is what a corrected coordinate on either side looks like.
    db_session.execute(text(
        "UPDATE nfdb_ignition SET geometry_lambert = ST_GeomFromText("
        "'POINT(400000 400000)', 3978) WHERE id = :id"), {"id": report.ignition_id})
    db_session.commit()

    run(db_session)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(NbacWildfire, fire.id)
    assert stored.nfdb_wildfire_id is None
    assert stored.match_method is None
    assert stored.match_confidence is None


def test_only_unbound_leaves_existing_links_alone(db_session, providers):
    nbac, nfdb = providers
    fire = add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    report = add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()
    run(db_session)
    db_session.commit()

    bindings = run(db_session, only_unbound=True)
    db_session.commit()
    db_session.expire_all()

    assert bindings == [], "the bound perimeter is out of scope"
    assert db_session.get(NbacWildfire, fire.id).nfdb_wildfire_id == report.id


def test_a_dry_run_writes_nothing(db_session, providers):
    nbac, nfdb = providers
    fire = add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()

    binding = only(run(db_session, write=False))
    db_session.commit()
    db_session.expire_all()

    assert binding.is_bound, "the cascade still concludes"
    assert db_session.get(NbacWildfire, fire.id).nfdb_wildfire_id is None


def test_every_rule_the_cascade_can_produce_is_one_the_database_accepts(db_session,
                                                                       providers):
    """The vocabulary constraint and the cascade must not be able to drift apart."""
    nbac, nfdb = providers
    fire = add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    report = add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()

    for method in MATCH_METHODS:
        db_session.execute(text(
            "UPDATE nbac_wildfire SET nfdb_wildfire_id = :nfdb, match_method = :method, "
            "match_confidence = :confidence WHERE id = :id"),
            {"nfdb": report.id, "method": method, "id": fire.id,
             "confidence": MATCH_METHOD_CONFIDENCE[method]})
        db_session.commit()


def test_a_method_outside_the_vocabulary_is_refused_by_the_database(db_session,
                                                                    providers):
    """Which is what makes the constraint worth having rather than a comment."""
    from sqlalchemy.exc import IntegrityError

    nbac, nfdb = providers
    fire = add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    report = add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "UPDATE nbac_wildfire SET nfdb_wildfire_id = :nfdb, match_method = 'code' "
            "WHERE id = :id"), {"nfdb": report.id, "id": fire.id})
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------

def test_the_csv_holds_the_unbound_fires_too(tmp_path, db_session, providers):
    """The unbound rows are the point of the report."""
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_perimeter(db_session, nbac, "2023_far", 500_000.0, 500_000.0)
    add_report(db_session, nfdb, "R1", 5000.0, 5000.0)
    db_session.commit()

    path = tmp_path / "bindings.csv"
    app.write_csv(run(db_session), path, logger)

    with path.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert tuple(table[0]) == app.REPORT_COLUMNS
    outcomes = {row[0]: row[5] for row in table[1:]}
    assert outcomes == {"2023_1": "bound", "2023_far": "unbound"}


def test_the_csv_reports_the_distance_that_was_used(tmp_path, db_session, providers):
    nbac, nfdb = providers
    add_perimeter(db_session, nbac, "2023_1", 0.0, 0.0)
    add_report(db_session, nfdb, "R1", SIDE + 750.0, 5000.0)
    db_session.commit()

    path = tmp_path / "bindings.csv"
    app.write_csv(run(db_session), path, logger)
    row = list(csv.reader(path.open(encoding="utf-8")))[1]

    assert row[app.REPORT_COLUMNS.index("method")] == MATCH_NEAR_AGENCY_DAY
    assert row[app.REPORT_COLUMNS.index("distance_m")] == "750"


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_the_default_distance_is_the_measured_one():
    args = app.parse_arguments(["--db-name", "x", "--db-user", "y"])
    assert args.max_distance == DEFAULT_MATCH_DISTANCE_M == 2000.0
    assert args.only_unbound is False
    assert args.dry_run is False


@pytest.mark.parametrize("text_value", ["-1", "nan", "inf", "not a number"])
def test_a_nonsense_distance_is_refused(text_value):
    with pytest.raises(app.argparse.ArgumentTypeError):
        app.metres(text_value)


def test_zero_is_a_valid_distance():
    """It is the containment-only setting, not a mistake."""
    assert app.metres("0") == 0.0
