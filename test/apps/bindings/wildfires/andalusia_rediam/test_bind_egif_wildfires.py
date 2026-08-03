#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the REDIAM <-> EGIF binding application.

The binding is inference rather than transcription, so what has to be pinned down is
not only that it finds the right *parte* but that it **refuses** to find one when the
evidence does not single one out. Much of what follows is about the refusals.

This cascade is the Catalan one with the easy parts made easier and two rules removed,
so the tests concentrate on what is different here:

* the code is an identifier from the first year, in three published shapes — plain,
  ``IIFF``-prefixed and nine-digit — and all three have to reach the same *parte*;
* a code that carries no province is **not** matched on a date alone, which the Catalan
  cascade does and this one refuses to;
* a contested *parte* is settled in favour of an identifier match rather than dropped,
  which is the one place the two applications genuinely disagree — and which two real
  Andalusian fires need.
"""

import csv
import datetime
import logging

import pytest

from sqlalchemy import select
from sqlalchemy import text

from src.apps.bindings.wildfires.andalusia_rediam import bind_egif_wildfires as app
from src.data_model.data_provider import DataProvider
from src.providers import andalusia_rediam
from src.providers import spain_egif
from src.providers.andalusia_rediam.wildfire import MATCH_CODE
from src.providers.andalusia_rediam.wildfire import MATCH_CODE_DATE_MISMATCH
from src.providers.andalusia_rediam.wildfire import MATCH_CODE_REFORMATTED
from src.providers.andalusia_rediam.wildfire import MATCH_DATE_PROVINCE
from src.providers.andalusia_rediam.wildfire import MATCH_DATE_PROVINCE_NAME
from src.providers.andalusia_rediam.wildfire import MATCH_GEOMETRY
from src.providers.andalusia_rediam.wildfire import MATCH_METHODS
from src.providers.andalusia_rediam.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.andalusia_rediam.wildfire import RediamWildfire
from src.providers.spain_egif.ignition import EgifIgnition
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc

logger = logging.getLogger("test-rediam-egif-bind")


def perimeter(x: float, y: float, side: float = 0.02) -> str:
    """A square in EPSG:4326 degrees, as a MULTIPOLYGON."""
    return (f"SRID=4326;MULTIPOLYGON((({x} {y}, {x + side} {y}, {x + side} {y + side}, "
            f"{x} {y + side}, {x} {y})))")


def egif_fire(session, provider_id, report_number, date, municipality,
              province=None, point=None) -> EgifWildfire:
    """One *parte*, with a published point only where one is given."""
    ignition_id = None
    if point is not None:
        ignition = EgifIgnition(
            data_provider_id=provider_id, report_number=report_number,
            geometry=f"SRID=4326;POINT({point[0]} {point[1]})",
            date_time=datetime.datetime(date.year, date.month, date.day, 12, tzinfo=UTC),
            time_zone=spain_egif.DEFAULT_TIME_ZONE, utm_zone=30,
            utm_x=400000.0, utm_y=4100000.0, datum=spain_egif.DATUM_ETRS89,
            start_point_count=1)
        session.add(ignition)
        session.flush()
        ignition_id = ignition.id
    fire = EgifWildfire(
        data_provider_id=provider_id, report_number=report_number,
        campaign=date.year, province_ine_code=province or report_number[4:6],
        municipality_name=municipality, ignition_id=ignition_id,
        # Local noon, so the local date is unambiguously the published one whatever the
        # offset — a midnight instant would land on the previous day in summer.
        start_date_time=datetime.datetime(date.year, date.month, date.day, 12,
                                          tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE)
    session.add(fire)
    session.flush()
    return fire


def rediam_fire(session, provider_id, code, date, municipality, province="Almería",
                geometry=None) -> RediamWildfire:
    """One Andalusian perimeter."""
    fire = RediamWildfire(
        data_provider_id=provider_id,
        source_layer="PERIMETROS_COR_2008_2025", code=code, fire_date=date,
        year=date.year, municipality_name=municipality, province_name=province,
        part_count=1,
        start_date_time=datetime.datetime(date.year, date.month, date.day, tzinfo=UTC),
        time_zone=andalusia_rediam.DEFAULT_TIME_ZONE,
        perimeter=geometry or perimeter(-2.5, 37.0))
    session.add(fire)
    session.flush()
    return fire


@pytest.fixture
def providers(db_session):
    rediam = DataProvider(name=andalusia_rediam.PROVIDER_NAME,
                          product=andalusia_rediam.PROVIDER_PRODUCT,
                          full_name=andalusia_rediam.PROVIDER_FULL_NAME)
    egif = DataProvider(name=spain_egif.PROVIDER_NAME,
                        product=spain_egif.PROVIDER_PRODUCT,
                        full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add_all([rediam, egif])
    db_session.commit()
    return rediam.id, egif.id


def run(session, year=None, only_unbound=False, dry_run=False, csv_path=None):
    """Run the binding against an open session's engine, returning the bindings."""
    arguments = []
    if year is not None:
        arguments += ["--year", str(year)]
    if only_unbound:
        arguments.append("--only-unbound")
    if dry_run:
        arguments.append("--dry-run")
    if csv_path is not None:
        arguments += ["--csv", str(csv_path)]
    args = app.parse_arguments(arguments)
    bindings = app.bind_wildfires(args, session.get_bind(), logger)
    if csv_path is not None:
        app.write_csv(bindings, csv_path, logger)
    session.expire_all()
    return bindings


def stored(session, code) -> RediamWildfire:
    return session.scalar(select(RediamWildfire).where(RediamWildfire.code == code))


# --------------------------------------------------------------------------
# Name normalisation
# --------------------------------------------------------------------------

def test_the_spanish_article_is_un_inverted():
    """REDIAM writes ``EJIDO (EL)`` and EGIF ``EJIDO, EL``. One rule covers both."""
    assert app.normalise_name("EJIDO (EL)") == app.normalise_name("EJIDO, EL")
    assert app.normalise_name("El Ejido") == app.normalise_name("EJIDO (EL)")


def test_accents_and_punctuation_are_folded():
    assert app.normalise_name("ALMODÓVAR DEL RÍO") == "ALMODOVAR DEL RIO"
    assert app.normalise_name("Cañete la Real") == "CANETE LA REAL"


def test_a_municipality_that_is_only_an_article_survives():
    """Stripping it would leave the empty string, which matches nothing."""
    assert app.normalise_name("LA") == "LA"


def test_an_absent_name_never_matches():
    """Two blanks are not agreement, they are two absences."""
    assert not app.same_municipality(None, None)
    assert not app.same_municipality("", "")
    assert not app.same_municipality(None, "TARIFA")


def test_genuinely_different_names_stay_different():
    """REDIAM often names the paraje where EGIF names the municipality.

    ``DEHESA DE LAS YEGUAS`` is in Puerto Real and ``RETIN-BARBATE`` in Barbate, and
    no honest string rule turns one into the other — see the module docstring on the
    hyphen rule that was measured and rejected.
    """
    assert not app.same_municipality("DEHESA DE LAS YEGUAS", "PUERTO REAL")
    assert not app.same_municipality("RETIN-BARBATE", "BARBATE")


# --------------------------------------------------------------------------
# Stage 1: the code is the report number
# --------------------------------------------------------------------------

def test_a_code_that_is_a_report_number_is_the_match(db_session, providers):
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1),
                      "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2022040091")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_CODE
    assert fire.match_confidence == 1.0
    assert fire.matched_at is not None


def test_the_code_wins_even_when_the_dates_disagree(db_session, providers):
    """42 of the real identifier matches disagree about the date, by up to five weeks."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2008140021", datetime.date(2008, 7, 13),
              "HINOJOSA DEL DUQUE", province="14")
    rediam_fire(db_session, rediam_id, "2008140021", datetime.date(2008, 7, 1),
                "HINOJOSA DEL DUQUE", province="Córdoba")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2008140021")
    assert fire.match_method == MATCH_CODE_DATE_MISMATCH
    assert fire.match_confidence == MATCH_METHOD_CONFIDENCE[MATCH_CODE_DATE_MISMATCH]


def test_the_code_wins_even_when_the_municipality_disagrees(db_session, providers):
    """The identifier is not up for review by a field that often names the paraje."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2019110104", datetime.date(2019, 9, 2), "TARIFA",
              province="11")
    rediam_fire(db_session, rediam_id, "2019110104", datetime.date(2019, 9, 2),
                "SIERRA PLATA", province="Cádiz")
    db_session.commit()

    run(db_session)

    assert stored(db_session, "2019110104").match_method == MATCH_CODE


def test_the_iiff_prefix_is_read_off(db_session, providers):
    """The whole of 2025 is published this way; the prefix is a label, not a number."""
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2025040059", datetime.date(2025, 8, 28),
                      "LUBRIN")
    rediam_fire(db_session, rediam_id, "IIFF2025040059", datetime.date(2025, 8, 28),
                "Lubrín")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "IIFF2025040059")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_CODE_REFORMATTED
    assert fire.match_confidence == MATCH_METHOD_CONFIDENCE[MATCH_CODE_REFORMATTED]


def test_a_nine_digit_code_is_padded_back(db_session, providers):
    """Six 2019 codes write the four-digit sequence with three."""
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2019180044", datetime.date(2019, 7, 15),
                      "ALGARINEJO", province="18")
    rediam_fire(db_session, rediam_id, "201918044", datetime.date(2019, 7, 15),
                "ALGARINEJO", province="Granada")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "201918044")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_CODE_REFORMATTED


def test_a_decode_the_date_contradicts_is_still_the_identifier(db_session, providers):
    """One real 2019 fire is exactly this, and it binds as a date mismatch.

    A reading of the format is weaker than string equality, but it is still a reading
    of an *identifier*: refusing it here would make the missing zero the difference
    between a link and none.
    """
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2019180023", datetime.date(2019, 8, 20),
              "ALGARINEJO", province="18")
    rediam_fire(db_session, rediam_id, "201918023", datetime.date(2019, 7, 15),
                "ALGARINEJO", province="Granada")
    db_session.commit()

    run(db_session)

    assert stored(db_session, "201918023").match_method == MATCH_CODE_DATE_MISMATCH


# --------------------------------------------------------------------------
# Stage 2: the date, narrowed by the province, the name and the map
# --------------------------------------------------------------------------

def test_the_only_parte_of_that_day_and_province_is_a_match(db_session, providers):
    """Where EGIF has no such report number: 8 real fires end here."""
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2010040999", datetime.date(2010, 5, 27),
                      "NIJAR")
    rediam_fire(db_session, rediam_id, "2010040012", datetime.date(2010, 5, 27), "NIJAR")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2010040012")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_DATE_PROVINCE
    assert fire.match_confidence == MATCH_METHOD_CONFIDENCE[MATCH_DATE_PROVINCE]


def test_the_province_from_the_code_narrows_the_date(db_session, providers):
    """A Cádiz fire on the same day is not a candidate for an Almería code."""
    rediam_id, egif_id = providers
    almeria = egif_fire(db_session, egif_id, "2010040999", datetime.date(2010, 5, 27),
                        "NIJAR", province="04")
    egif_fire(db_session, egif_id, "2010110999", datetime.date(2010, 5, 27), "TARIFA",
              province="11")
    rediam_fire(db_session, rediam_id, "2010040012", datetime.date(2010, 5, 27), "NIJAR")
    db_session.commit()

    run(db_session)

    assert stored(db_session, "2010040012").egif_wildfire_id == almeria.id


def test_the_municipality_narrows_what_the_province_could_not(db_session, providers):
    rediam_id, egif_id = providers
    wanted = egif_fire(db_session, egif_id, "2019110998", datetime.date(2019, 9, 2),
                       "TARIFA", province="11")
    egif_fire(db_session, egif_id, "2019110999", datetime.date(2019, 9, 2),
              "ALGECIRAS", province="11")
    rediam_fire(db_session, rediam_id, "2019110104", datetime.date(2019, 9, 2),
                "Tarifa", province="Cádiz")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2019110104")
    assert fire.egif_wildfire_id == wanted.id
    assert fire.match_method == MATCH_DATE_PROVINCE_NAME


def test_the_perimeter_narrows_what_the_name_could_not(db_session, providers):
    """The strongest fallback, and the one EGIF's coordinates make possible here."""
    rediam_id, egif_id = providers
    inside = egif_fire(db_session, egif_id, "2019110998", datetime.date(2019, 9, 2),
                       "SIERRA UNO", province="11", point=(-2.495, 37.005))
    egif_fire(db_session, egif_id, "2019110999", datetime.date(2019, 9, 2),
              "SIERRA DOS", province="11", point=(-5.0, 37.5))
    rediam_fire(db_session, rediam_id, "2019110104", datetime.date(2019, 9, 2),
                "UN PARAJE", province="Cádiz", geometry=perimeter(-2.5, 37.0))
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2019110104")
    assert fire.egif_wildfire_id == inside.id
    assert fire.match_method == MATCH_GEOMETRY


def test_a_test_that_would_reject_everything_rejects_nothing(db_session, providers):
    """A point outside the perimeter is ordinary: 331 of 748 identifier matches are.

    So a containment test that leaves no candidate standing has said nothing, and the
    cascade carries on with the set it had rather than concluding the fire is neither.
    """
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2019110998", datetime.date(2019, 9, 2), "UNO",
              province="11", point=(-8.0, 37.0))
    egif_fire(db_session, egif_id, "2019110999", datetime.date(2019, 9, 2), "DOS",
              province="11", point=(-8.5, 37.5))
    rediam_fire(db_session, rediam_id, "2019110104", datetime.date(2019, 9, 2),
                "UN PARAJE", province="Cádiz", geometry=perimeter(-2.5, 37.0))
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2019110104")
    # Still ambiguous, and still two candidates — not narrowed to zero and not bound.
    assert fire.egif_wildfire_id is None


def test_a_code_with_no_province_is_never_bound_on_a_date(db_session, providers):
    """The Catalan cascade would bind this; this one refuses, and says why.

    Every published Andalusian code decodes to a province, so a code that does not is
    a format the service has not used yet. A date alone, against a region with 40,757
    *partes*, is not evidence.
    """
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2012040999", datetime.date(2012, 8, 1), "NIJAR")
    rediam_fire(db_session, rediam_id, "SOMETHING/ELSE", datetime.date(2012, 8, 1),
                "NIJAR")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "SOMETHING/ELSE").egif_wildfire_id is None
    assert [binding.reason for binding in bindings] == [app.UNBOUND_NO_PROVINCE]


# --------------------------------------------------------------------------
# The refusals
# --------------------------------------------------------------------------

def test_no_candidate_leaves_the_fire_unbound(db_session, providers):
    """2024 and 2025: 133 real fires, with no campaign to match against at all."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "IIFF2025040059", datetime.date(2025, 8, 28),
                "LUBRIN")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "IIFF2025040059").egif_wildfire_id is None
    assert [binding.reason for binding in bindings] == [app.UNBOUND_NO_CANDIDATE]


def test_several_candidates_leave_the_fire_unbound(db_session, providers):
    """No scoring, no best guess: an ambiguous fire is reported, not resolved."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2014040998", datetime.date(2014, 6, 29), "UNO")
    egif_fire(db_session, egif_id, "2014040999", datetime.date(2014, 6, 29), "DOS")
    rediam_fire(db_session, rediam_id, "2014040097", datetime.date(2014, 6, 29),
                "EJIDO (EL)")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "2014040097").egif_wildfire_id is None
    assert bindings[0].reason == app.UNBOUND_AMBIGUOUS
    assert bindings[0].candidates == 2


def test_an_identifier_beats_a_guess_for_a_contested_parte(db_session, providers,
                                                           caplog):
    """The one place this cascade parts company with the Catalan one.

    Two real fires need it: ``2014040066`` and ``2018140034`` match their *parte* by
    code while the previous fire of the same day and province reaches the same one
    through the date-and-province rule. Dropping both would throw away an identifier
    match because a guess collided with it.
    """
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2014040066", datetime.date(2014, 4, 20),
                      "SOMONTIN")
    rediam_fire(db_session, rediam_id, "2014040066", datetime.date(2014, 4, 20),
                "SOMONTIN")
    rediam_fire(db_session, rediam_id, "2014040065", datetime.date(2014, 4, 20),
                "OTRO PARAJE")
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        run(db_session)

    assert stored(db_session, "2014040066").egif_wildfire_id == parte.id
    assert stored(db_session, "2014040066").match_method == MATCH_CODE
    assert stored(db_session, "2014040065").egif_wildfire_id is None
    assert "matched on the published identifier" in caplog.text


def test_two_guesses_for_one_parte_bind_neither(db_session, providers):
    """Nothing in the data would make the choice, so neither is made."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2014040999", datetime.date(2014, 4, 20), "SOMONTIN")
    rediam_fire(db_session, rediam_id, "2014040065", datetime.date(2014, 4, 20), "UNO")
    rediam_fire(db_session, rediam_id, "2014040067", datetime.date(2014, 4, 20), "DOS")
    db_session.commit()

    bindings = run(db_session)

    assert all(binding.egif is None for binding in bindings)
    assert {binding.reason for binding in bindings} == {app.UNBOUND_PARTE_CONTESTED}


def test_a_parte_outside_andalusia_is_never_a_candidate(db_session, providers):
    """The candidate side is the eight Andalusian provinces, not the national archive."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2012080999", datetime.date(2012, 8, 1), "BARCELONA",
              province="08")
    # An Andalusian parte on another day, so the candidate side is not empty and the
    # run reaches the cascade rather than stopping at "nothing to bind to".
    egif_fire(db_session, egif_id, "2012040998", datetime.date(2012, 9, 1), "NIJAR")
    rediam_fire(db_session, rediam_id, "2012040012", datetime.date(2012, 8, 1), "NIJAR")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "2012040012").egif_wildfire_id is None
    assert bindings[0].reason == app.UNBOUND_NO_CANDIDATE


# --------------------------------------------------------------------------
# What it writes
# --------------------------------------------------------------------------

def test_the_link_and_the_method_are_all_or_nothing(db_session, providers):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "IIFF2025040059", datetime.date(2025, 8, 28),
                "LUBRIN")
    db_session.commit()

    run(db_session)

    for code in ("2022040091", "IIFF2025040059"):
        fire = stored(db_session, code)
        assert (fire.egif_wildfire_id is None) == (fire.match_method is None)
        assert (fire.match_method is None) == (fire.match_confidence is None)


def test_every_method_it_can_write_is_a_known_one(db_session, providers):
    """The database checks this too, since b1c47d9e3f52 — here it is checked in Python."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()

    bindings = run(db_session)

    assert all(binding.method in MATCH_METHODS for binding in bindings if binding.is_bound)


def test_a_re_run_is_idempotent(db_session, providers):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()

    run(db_session)
    first = stored(db_session, "2022040091").egif_wildfire_id
    run(db_session)

    assert stored(db_session, "2022040091").egif_wildfire_id == first


def test_a_re_run_clears_a_binding_that_no_longer_holds(db_session, providers):
    """A correction to either dataset has to be able to take effect."""
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1),
                      "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()
    run(db_session)
    assert stored(db_session, "2022040091").egif_wildfire_id is not None

    # The parte is renumbered, as a re-export could renumber it.
    db_session.execute(text("UPDATE egif_wildfire SET report_number = '2022049999' "
                            "WHERE id = :id"), {"id": parte.id})
    db_session.commit()
    run(db_session)

    fire = stored(db_session, "2022040091")
    # Not bound by code any more. It is now the only parte of that day and province,
    # so the fallback finds it — under a method that says the evidence changed.
    assert fire.match_method == MATCH_DATE_PROVINCE


def test_only_unbound_leaves_an_existing_link_alone(db_session, providers):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    fire = rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1),
                       "DALIAS")
    other = egif_fire(db_session, egif_id, "2022049999", datetime.date(2022, 8, 1),
                      "OTRO")
    fire.egif_wildfire_id = other.id
    fire.match_method = MATCH_DATE_PROVINCE
    fire.match_confidence = MATCH_METHOD_CONFIDENCE[MATCH_DATE_PROVINCE]
    fire.matched_at = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    db_session.commit()

    run(db_session, only_unbound=True)

    assert stored(db_session, "2022040091").egif_wildfire_id == other.id


def test_without_only_unbound_the_binding_is_recomputed(db_session, providers):
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1),
                      "DALIAS")
    fire = rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1),
                       "DALIAS")
    other = egif_fire(db_session, egif_id, "2022049999", datetime.date(2022, 8, 2),
                      "OTRO")
    fire.egif_wildfire_id = other.id
    fire.match_method = MATCH_DATE_PROVINCE
    fire.match_confidence = MATCH_METHOD_CONFIDENCE[MATCH_DATE_PROVINCE]
    fire.matched_at = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    db_session.commit()

    run(db_session)

    stored_fire = stored(db_session, "2022040091")
    assert stored_fire.egif_wildfire_id == parte.id
    assert stored_fire.match_method == MATCH_CODE


def test_a_year_restricts_the_perimeters_but_not_the_partes(db_session, providers):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    egif_fire(db_session, egif_id, "2021040003", datetime.date(2021, 7, 1), "OTRO")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2021040003", datetime.date(2021, 7, 1), "OTRO")
    db_session.commit()

    run(db_session, year=2022)

    assert stored(db_session, "2022040091").egif_wildfire_id is not None
    assert stored(db_session, "2021040003").egif_wildfire_id is None


def test_a_dry_run_writes_nothing(db_session, providers):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()

    bindings = run(db_session, dry_run=True)

    assert bindings[0].is_bound, "the work is done, and then rolled back"
    assert stored(db_session, "2022040091").egif_wildfire_id is None


def test_the_application_writes_no_other_column(db_session, providers):
    """Its whole effect is four columns on rediam_wildfire."""
    rediam_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1),
                      "DALIAS")
    fire = rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1),
                       "DALIAS")
    db_session.commit()
    before = db_session.execute(text(
        "SELECT municipality_name, province_name, part_count, area_ha_scrub, "
        "ignition_id, perimeter_etrs89_utm30n IS NOT NULL AS has_geometry "
        "FROM rediam_wildfire WHERE id = :id"), {"id": fire.id}).one()
    egif_before = db_session.execute(text(
        "SELECT report_number, campaign, municipality_name FROM egif_wildfire "
        "WHERE id = :id"), {"id": parte.id}).one()

    run(db_session)

    after = db_session.execute(text(
        "SELECT municipality_name, province_name, part_count, area_ha_scrub, "
        "ignition_id, perimeter_etrs89_utm30n IS NOT NULL AS has_geometry "
        "FROM rediam_wildfire WHERE id = :id"), {"id": fire.id}).one()
    egif_after = db_session.execute(text(
        "SELECT report_number, campaign, municipality_name FROM egif_wildfire "
        "WHERE id = :id"), {"id": parte.id}).one()
    assert tuple(after) == tuple(before)
    assert tuple(egif_after) == tuple(egif_before)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def test_no_perimeters_is_an_error(db_session, providers):
    _, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()

    with pytest.raises(RuntimeError, match="No Andalusian wildfires"):
        run(db_session)


def test_no_andalusian_partes_is_an_error(db_session, providers):
    rediam_id, _ = providers
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    db_session.commit()

    with pytest.raises(RuntimeError, match="No EGIF partes"):
        run(db_session)


def test_the_csv_reports_the_unbound_as_well_as_the_bound(db_session, providers,
                                                          tmp_path):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "IIFF2025040059", datetime.date(2025, 8, 28),
                "LUBRIN")
    db_session.commit()
    target = tmp_path / "bindings.csv"

    run(db_session, csv_path=target)

    with target.open(encoding="utf-8") as handle:
        rows = {row["code"]: row for row in csv.DictReader(handle)}
    assert list(rows) == ["2022040091", "IIFF2025040059"]
    assert rows["2022040091"]["outcome"] == "bound"
    assert rows["2022040091"]["method"] == MATCH_CODE
    assert rows["2022040091"]["province_name"] == "Almería"
    assert rows["IIFF2025040059"]["outcome"] == "unbound"
    assert rows["IIFF2025040059"]["method"] == ""


def test_the_log_says_which_years_egif_does_not_reach(db_session, providers, caplog):
    """The distinction between a coverage gap and a matching failure."""
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "2022040091", datetime.date(2022, 8, 1), "DALIAS")
    rediam_fire(db_session, rediam_id, "IIFF2025040059", datetime.date(2025, 8, 28),
                "LUBRIN")
    db_session.commit()

    with caplog.at_level(logging.INFO):
        run(db_session)

    assert "which the EGIF exports do not reach" in caplog.text
    assert "2025" in caplog.text


def test_a_run_with_inexact_bindings_says_so(db_session, providers, caplog):
    rediam_id, egif_id = providers
    egif_fire(db_session, egif_id, "2010040999", datetime.date(2010, 5, 27), "NIJAR")
    rediam_fire(db_session, rediam_id, "2010040012", datetime.date(2010, 5, 27), "NIJAR")
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        run(db_session)

    assert "rest on a date and a municipality name" in caplog.text


def test_every_method_has_a_confidence():
    assert set(MATCH_METHODS) == set(MATCH_METHOD_CONFIDENCE)
    assert all(0.0 < value <= 1.0 for value in MATCH_METHOD_CONFIDENCE.values())


def test_the_identifier_boundary_is_where_the_methods_say_it_is():
    """``resolve_contested`` acts on this, so it must not drift from the vocabulary."""
    identifier = {MATCH_CODE, MATCH_CODE_REFORMATTED, MATCH_CODE_DATE_MISMATCH}
    for method in MATCH_METHODS:
        above = MATCH_METHOD_CONFIDENCE[method] >= app.IDENTIFIER_CONFIDENCE
        assert above == (method in identifier), method


def test_the_cascade_has_no_rule_that_matches_on_a_date_alone():
    """The Catalan ``date`` and ``date_name`` cannot be written here — deliberately."""
    assert "date" not in MATCH_METHODS
    assert "date_name" not in MATCH_METHODS
