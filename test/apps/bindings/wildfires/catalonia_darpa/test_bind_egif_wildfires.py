#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the DARPA <-> EGIF binding application.

The binding is inference rather than transcription, so what has to be pinned down
is not only that it finds the right *parte* but that it **refuses** to find one
when the evidence does not single one out. Most of what follows is about the
refusals.

The fixture is built around the four things that decide the outcome: a code that
is an EGIF ``report_number`` (1997 on), a date shared by several *partes*, a
municipality name the two agencies spell differently, and an ignition point that
exists only from 1998.
"""

import csv
import datetime
import logging

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.bindings.wildfires.catalonia_darpa import bind_egif_wildfires as app
from src.data_model.data_provider import DataProvider
from src.providers import catalonia_darpa
from src.providers import spain_egif
from src.providers.catalonia_darpa.wildfire import MATCH_CODE
from src.providers.catalonia_darpa.wildfire import MATCH_CODE_DATE_MISMATCH
from src.providers.catalonia_darpa.wildfire import MATCH_CODE_REFORMATTED
from src.providers.catalonia_darpa.wildfire import MATCH_DATE
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_NAME
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_PROVINCE
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_PROVINCE_NAME
from src.providers.catalonia_darpa.wildfire import MATCH_GEOMETRY
from src.providers.catalonia_darpa.wildfire import MATCH_METHODS
from src.providers.catalonia_darpa.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.catalonia_darpa.wildfire import DarpaWildfire
from src.providers.spain_egif.ignition import EgifIgnition
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc

logger = logging.getLogger("test-darpa-egif-bind")


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
            time_zone=spain_egif.DEFAULT_TIME_ZONE, utm_zone=31,
            utm_x=400000.0, utm_y=4600000.0, datum=spain_egif.DATUM_ETRS89,
            start_point_count=1)
        session.add(ignition)
        session.flush()
        ignition_id = ignition.id
    fire = EgifWildfire(
        data_provider_id=provider_id, report_number=report_number,
        campaign=date.year, province_ine_code=province or report_number[4:6],
        municipality_name=municipality, ignition_id=ignition_id,
        # Local noon, so the local date is unambiguously the published one whatever
        # the offset — a midnight instant would land on the previous day in summer.
        start_date_time=datetime.datetime(date.year, date.month, date.day, 12,
                                          tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE)
    session.add(fire)
    session.flush()
    return fire


def darpa_fire(session, provider_id, code, date, municipality, year=None,
               geometry=None) -> DarpaWildfire:
    """One Catalan perimeter."""
    year = year or date.year
    fire = DarpaWildfire(
        data_provider_id=provider_id, source_layer=f"incendis{year}", code=code,
        fire_date=date, year=year, municipality_name=municipality, part_count=1,
        start_date_time=datetime.datetime(date.year, date.month, date.day,
                                          tzinfo=UTC),
        time_zone=catalonia_darpa.DEFAULT_TIME_ZONE,
        perimeter=geometry or perimeter(1.80, 41.80))
    session.add(fire)
    session.flush()
    return fire


@pytest.fixture
def providers(db_session):
    darpa = DataProvider(name=catalonia_darpa.PROVIDER_NAME,
                         product=catalonia_darpa.PROVIDER_PRODUCT,
                         full_name=catalonia_darpa.PROVIDER_FULL_NAME)
    egif = DataProvider(name=spain_egif.PROVIDER_NAME,
                        product=spain_egif.PROVIDER_PRODUCT,
                        full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add_all([darpa, egif])
    db_session.commit()
    return darpa.id, egif.id


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


def stored(session, code):
    return session.scalar(select(DarpaWildfire).where(DarpaWildfire.code == code))


# --------------------------------------------------------------------------
# Name normalisation
# --------------------------------------------------------------------------

def test_the_catalan_article_is_un_inverted():
    """EGIF writes the article at the end, DARPA at the front. The one rule that pays."""
    assert app.normalise_name("La Vall de Boí") == app.normalise_name("VALL DE BOI, LA")
    assert app.normalise_name("L'Albiol") == app.normalise_name("ALBIOL, L'")


def test_accents_and_punctuation_are_folded():
    assert app.normalise_name("Sant Vicenç de Castellet") == "SANT VICENC DE CASTELLET"
    assert app.normalise_name("Sant Cugat del Vallès") == "SANT CUGAT DEL VALLES"


def test_a_geminate_l_joins_rather_than_splits():
    """``Vil·la`` is one word; the interpunct and the dot the exports use for it go."""
    assert app.normalise_name("Vil·la") == "VILLA"
    assert app.normalise_name("Vil.la") == "VILLA"


def test_a_municipality_that_is_only_an_article_survives():
    """Les, in the Val d'Aran, is a real municipality whose whole name is the word.

    Stripping it would leave the empty string, which matches nothing — a rule meant
    to save bindings would have lost one.
    """
    assert app.normalise_name("Les") == "LES"
    assert app.same_municipality("Les", "LES")


def test_an_absent_name_never_matches():
    """Two blanks are not agreement, they are two absences."""
    assert not app.same_municipality(None, None)
    assert not app.same_municipality("", "")
    assert not app.same_municipality(None, "OLOT")


def test_genuinely_different_names_stay_different():
    """A merger and a rename must not be smoothed over — see the module docstring."""
    assert not app.same_municipality("Montagut", "MONTAGUT I OIX")
    assert not app.same_municipality("Santa Coloma de Gramenet", "SANTA COLOMA DE GRAMANET")


# --------------------------------------------------------------------------
# Stage 1: the code
# --------------------------------------------------------------------------

def test_a_code_that_is_a_report_number_is_the_match(db_session, providers):
    darpa_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24),
                      "SANT MATEU DE BAGES")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24),
               "Sant Mateu de Bages")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2013080287")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_CODE
    assert fire.match_confidence == 1.0
    assert fire.matched_at is not None


def test_the_code_wins_even_when_the_dates_disagree(db_session, providers):
    """The report number is a national identifier, not a guess.

    Nine of the 480 real code matches disagree about the date, by up to eight
    weeks. They are still the same fire; the method says the sources differ.
    """
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 9, 19),
              "SANT MATEU DE BAGES")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24),
               "Sant Mateu de Bages")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2013080287")
    assert fire.match_method == MATCH_CODE_DATE_MISMATCH
    assert fire.match_confidence == MATCH_METHOD_CONFIDENCE[MATCH_CODE_DATE_MISMATCH]


def test_the_code_wins_even_when_the_municipality_disagrees(db_session, providers):
    """The identifier is not up for review by a name spelled thirty years apart."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24),
              "CASSÀ DE LA SELVA")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24),
               "Llagostera")
    db_session.commit()

    run(db_session)

    assert stored(db_session, "2013080287").match_method == MATCH_CODE


# --------------------------------------------------------------------------
# Stage 2: the date, narrowed
# --------------------------------------------------------------------------

def test_a_unique_date_is_a_match(db_session, providers):
    """The only EGIF fire in Catalonia that day. Bound, and labelled as thin."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1994080123", datetime.date(1994, 8, 11), "SUBIRATS")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11),
               "Sant Cugat del Vallès")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "894496")
    assert fire.match_method == MATCH_DATE
    assert fire.match_confidence == MATCH_METHOD_CONFIDENCE[MATCH_DATE]


def test_the_province_from_the_code_narrows_the_date(db_session, providers):
    """``L89004001`` is Lleida; the Barcelona fire of the same day is not a candidate."""
    darpa_id, egif_id = providers
    lleida = egif_fire(db_session, egif_id, "1989250001", datetime.date(1989, 1, 27),
                       "EL PONT DE BAR")
    egif_fire(db_session, egif_id, "1989080001", datetime.date(1989, 1, 27), "OLESA")
    darpa_fire(db_session, darpa_id, "L89004001", datetime.date(1989, 1, 27),
               "Un altre nom", year=1989)
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "L89004001")
    assert fire.egif_wildfire_id == lleida.id
    assert fire.match_method == MATCH_DATE_PROVINCE


def test_the_municipality_narrows_what_the_province_could_not(db_session, providers):
    darpa_id, egif_id = providers
    wanted = egif_fire(db_session, egif_id, "1989250001", datetime.date(1989, 1, 27),
                       "PONT DE BAR, EL")
    egif_fire(db_session, egif_id, "1989250002", datetime.date(1989, 1, 27), "TOSES")
    darpa_fire(db_session, darpa_id, "L89004001", datetime.date(1989, 1, 27),
               "El Pont de Bar", year=1989)
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "L89004001")
    assert fire.egif_wildfire_id == wanted.id
    assert fire.match_method == MATCH_DATE_PROVINCE_NAME


def test_the_municipality_alone_narrows_a_code_with_no_province(db_session, providers):
    """An internal reference encodes nothing at all; the name is all there is."""
    darpa_id, egif_id = providers
    wanted = egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11),
                       "SANT CUGAT DEL VALLES")
    egif_fire(db_session, egif_id, "1994170001", datetime.date(1994, 8, 11), "OLOT")
    darpa_fire(db_session, darpa_id, "303/94N", datetime.date(1994, 8, 11),
               "Sant Cugat del Vallès", year=1994)
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "303/94N")
    assert fire.egif_wildfire_id == wanted.id
    assert fire.match_method == MATCH_DATE_NAME


def test_the_perimeter_narrows_what_the_name_could_not(db_session, providers):
    """The last resort, and the only stage that uses the thing DARPA exists for."""
    darpa_id, egif_id = providers
    inside = egif_fire(db_session, egif_id, "2005080001", datetime.date(2005, 7, 1),
                       "UN NOM", point=(1.805, 41.805))
    egif_fire(db_session, egif_id, "2005080002", datetime.date(2005, 7, 1),
              "UN NOM", point=(2.500, 42.500))
    darpa_fire(db_session, darpa_id, "303/05N", datetime.date(2005, 7, 1),
               "Un altre nom", year=2005, geometry=perimeter(1.80, 41.80))
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "303/05N")
    assert fire.egif_wildfire_id == inside.id
    assert fire.match_method == MATCH_GEOMETRY


def test_a_province_that_excludes_everything_does_not_narrow(db_session, providers):
    """A code and a parte disagreeing about the province is not a filter.

    Applied as one it would empty the candidate set and lose a fire the name would
    have matched perfectly well.
    """
    darpa_id, egif_id = providers
    wanted = egif_fire(db_session, egif_id, "1989170001", datetime.date(1989, 1, 27),
                       "TOSES")
    egif_fire(db_session, egif_id, "1989170002", datetime.date(1989, 1, 27), "OLOT")
    # L is Lleida (25); both partes are filed in Girona (17).
    darpa_fire(db_session, darpa_id, "L89004001", datetime.date(1989, 1, 27),
               "Toses", year=1989)
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "L89004001")
    assert fire.egif_wildfire_id == wanted.id
    assert fire.match_method == MATCH_DATE_NAME, "narrowed by name, not by province"


# --------------------------------------------------------------------------
# The refusals
# --------------------------------------------------------------------------

def test_no_candidate_leaves_the_fire_unbound(db_session, providers):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11), "SUBIRATS")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 3, 2), "Subirats")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "894496").egif_wildfire_id is None
    assert bindings[0].reason == app.UNBOUND_NO_CANDIDATE


def test_several_candidates_leave_the_fire_unbound(db_session, providers):
    """The whole conservative half of the design.

    A wrong binding attaches another fire's cause and burnt area to this perimeter
    and nothing downstream could detect it. A missing one is in the first report.
    """
    darpa_id, egif_id = providers
    for sequence in range(3):
        egif_fire(db_session, egif_id, f"199408000{sequence}",
                  datetime.date(1994, 8, 11), "SANT CUGAT DEL VALLES")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11),
               "Sant Cugat del Vallès")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "894496").egif_wildfire_id is None
    assert bindings[0].reason == app.UNBOUND_AMBIGUOUS
    assert bindings[0].candidates == 3


def test_one_parte_claimed_by_two_perimeters_binds_neither(db_session, providers):
    """Enforced in the application, and reported by name."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11), "SUBIRATS")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Subirats")
    darpa_fire(db_session, darpa_id, "894497", datetime.date(1994, 8, 11), "Subirats")
    db_session.commit()

    bindings = run(db_session)

    assert all(binding.egif is None for binding in bindings)
    assert {binding.reason for binding in bindings} == {app.UNBOUND_PARTE_CONTESTED}
    assert db_session.scalar(select(func.count()).select_from(DarpaWildfire.__table__)
                             .where(DarpaWildfire.egif_wildfire_id.is_not(None))) == 0


def test_a_contested_parte_is_named_in_the_log(db_session, providers, caplog):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11), "SUBIRATS")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Subirats")
    darpa_fire(db_session, darpa_id, "894497", datetime.date(1994, 8, 11), "Subirats")
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        run(db_session)

    assert "1994080001" in caplog.text
    assert "claimed by 2 perimeters" in caplog.text


def test_a_parte_outside_catalonia_is_never_a_candidate(db_session, providers):
    """The candidate side is the four Catalan provinces and nothing else.

    An Asturian *parte* on the right day with the right municipality name would
    otherwise be a perfect stage-2 match. The Catalan fire on another date is only
    there so the run has some Catalan *parte* at all, which it refuses to run
    without.
    """
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1994330001", datetime.date(1994, 8, 11),
              "SANT CUGAT DEL VALLES", province="33")
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 3, 2), "OLESA")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11),
               "Sant Cugat del Vallès")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "894496").egif_wildfire_id is None
    assert bindings[0].reason == app.UNBOUND_NO_CANDIDATE


# --------------------------------------------------------------------------
# What the run writes, and what it leaves alone
# --------------------------------------------------------------------------

def test_the_link_and_the_method_are_all_or_nothing(db_session, providers):
    """A check constraint, so nothing can ever store one without the other."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Y")
    db_session.commit()

    run(db_session)

    assert db_session.scalar(text(
        "SELECT count(*) FROM darpa_wildfire "
        "WHERE (egif_wildfire_id IS NULL) <> (match_method IS NULL)")) == 0


def test_every_method_it_can_write_is_a_known_one(db_session, providers):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.commit()

    run(db_session)

    methods = set(db_session.scalars(select(DarpaWildfire.match_method)))
    assert methods <= set(MATCH_METHODS) | {None}


def test_a_re_run_is_idempotent(db_session, providers):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.commit()

    run(db_session)
    first = stored(db_session, "2013080287").egif_wildfire_id
    run(db_session)

    assert stored(db_session, "2013080287").egif_wildfire_id == first


def test_a_re_run_clears_a_binding_that_no_longer_holds(db_session, providers):
    """The reason the run recomputes rather than accumulates.

    Without the clear, a *parte* deleted from EGIF would leave its link behind
    forever and no re-run could correct it.
    """
    darpa_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.commit()
    run(db_session)
    assert stored(db_session, "2013080287").egif_wildfire_id is not None

    db_session.execute(text("UPDATE darpa_wildfire SET egif_wildfire_id = NULL, "
                            "match_method = NULL, match_confidence = NULL"))
    db_session.execute(text("DELETE FROM egif_wildfire WHERE id = :id"), {"id": parte.id})
    db_session.execute(text("DELETE FROM wildfire WHERE id = :id"), {"id": parte.id})
    egif_fire(db_session, egif_id, "2013080999", datetime.date(2013, 7, 24), "X")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "2013080287")
    assert fire.egif_wildfire_id is not None, "rebound to the only fire that day"
    assert fire.match_method == MATCH_DATE


def test_only_unbound_leaves_an_existing_link_alone(db_session, providers):
    """For a binding made by hand, which this application must not overwrite."""
    darpa_id, egif_id = providers
    kept = egif_fire(db_session, egif_id, "2013080999", datetime.date(2013, 7, 24), "X")
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    fire = darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.execute(text(
        "UPDATE darpa_wildfire SET egif_wildfire_id = :egif, match_method = 'date', "
        "match_confidence = 0.5 WHERE id = :id"), {"egif": kept.id, "id": fire.id})
    db_session.commit()

    run(db_session, only_unbound=True)

    assert stored(db_session, "2013080287").egif_wildfire_id == kept.id


def test_without_only_unbound_the_binding_is_recomputed(db_session, providers):
    """The same fixture, the other way: the code match must win on a full run."""
    darpa_id, egif_id = providers
    other = egif_fire(db_session, egif_id, "2013080999", datetime.date(2013, 7, 24), "X")
    parte = egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    fire = darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.execute(text(
        "UPDATE darpa_wildfire SET egif_wildfire_id = :egif, match_method = 'date', "
        "match_confidence = 0.5 WHERE id = :id"), {"egif": other.id, "id": fire.id})
    db_session.commit()

    run(db_session)

    stored_fire = stored(db_session, "2013080287")
    assert stored_fire.egif_wildfire_id == parte.id
    assert stored_fire.match_method == MATCH_CODE


def test_a_year_restricts_the_perimeters_but_not_the_partes(db_session, providers):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11), "Y")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Y")
    db_session.commit()

    run(db_session, year=2013)

    assert stored(db_session, "2013080287").egif_wildfire_id is not None
    assert stored(db_session, "894496").egif_wildfire_id is None


def test_a_dry_run_writes_nothing(db_session, providers):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.commit()

    bindings = run(db_session, dry_run=True)

    assert bindings[0].is_bound, "it still works out what it would have done"
    assert stored(db_session, "2013080287").egif_wildfire_id is None


def test_the_application_writes_no_other_column(db_session, providers):
    """It is a binding, not an import: nothing of either dataset is edited."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24),
               "Sant Mateu")
    db_session.commit()
    before = db_session.execute(text(
        "SELECT code, fire_date, year, municipality_name, part_count, source_layer "
        "FROM darpa_wildfire")).all()
    egif_before = db_session.execute(text(
        "SELECT report_number, campaign, municipality_name FROM egif_wildfire")).all()

    run(db_session)

    assert db_session.execute(text(
        "SELECT code, fire_date, year, municipality_name, part_count, source_layer "
        "FROM darpa_wildfire")).all() == before
    assert db_session.execute(text(
        "SELECT report_number, campaign, municipality_name FROM egif_wildfire")).all() \
        == egif_before


# --------------------------------------------------------------------------
# Failures and reporting
# --------------------------------------------------------------------------

def test_no_perimeters_is_an_error(db_session, providers):
    _, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.commit()

    with pytest.raises(RuntimeError, match="No Catalan wildfires in scope"):
        run(db_session)


def test_no_catalan_partes_is_an_error(db_session, providers):
    darpa_id, _ = providers
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    db_session.commit()

    with pytest.raises(RuntimeError, match="no EGIF partes|nothing to bind to"):
        run(db_session)


def test_the_csv_reports_the_unbound_as_well_as_the_bound(db_session, providers, tmp_path):
    """A report of the successes says nothing about whether the rules are right."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Y")
    db_session.commit()
    target = tmp_path / "bindings.csv"

    run(db_session, csv_path=target)

    with target.open(encoding="utf-8") as handle:
        rows = {line["code"]: line for line in csv.DictReader(handle)}

    assert list(rows) == ["894496", "2013080287"]
    assert rows["2013080287"]["outcome"] == "bound"
    assert rows["2013080287"]["method"] == MATCH_CODE
    assert rows["2013080287"]["egif_report_number"] == "2013080287"
    assert rows["894496"]["outcome"] == "unbound"
    assert rows["894496"]["method"] == ""


def test_the_log_breaks_the_bindings_down_by_method(db_session, providers, caplog):
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "2013080287", datetime.date(2013, 7, 24), "X")
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11), "Y")
    darpa_fire(db_session, darpa_id, "2013080287", datetime.date(2013, 7, 24), "X")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Y")
    db_session.commit()

    with caplog.at_level(logging.INFO):
        run(db_session)

    assert "Bound 2 of 2" in caplog.text
    assert MATCH_CODE in caplog.text
    assert MATCH_DATE in caplog.text


def test_a_run_with_inexact_bindings_says_so(db_session, providers, caplog):
    """The warning that stops a name match being read as an identifier match."""
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1994080001", datetime.date(1994, 8, 11), "Y")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11), "Y")
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        run(db_session)

    assert "match_confidence >= 0.9" in caplog.text


def test_every_method_has_a_confidence():
    assert set(MATCH_METHODS) == set(MATCH_METHOD_CONFIDENCE)
    assert MATCH_METHOD_CONFIDENCE[MATCH_CODE] == 1.0
    # The gap that matters: an identifier match is not the same kind of claim as a
    # name match held slightly less firmly.
    assert min(MATCH_METHOD_CONFIDENCE[m] for m in (MATCH_CODE, MATCH_CODE_DATE_MISMATCH)) \
        > max(MATCH_METHOD_CONFIDENCE[m] for m in
              (MATCH_GEOMETRY, MATCH_DATE_PROVINCE_NAME, MATCH_DATE_NAME,
               MATCH_DATE_PROVINCE, MATCH_DATE))


# --------------------------------------------------------------------------
# Stage 1b: the code rearranged
# --------------------------------------------------------------------------

def test_an_older_code_is_the_report_number_rearranged(db_session, providers):
    """``920800034`` in 1992 is ``1992080034``: year, province and sequence reordered.

    Four of the six published formats are the EGIF identifier in a different layout,
    which is what turns a third of this dataset from a name guess into an identity.
    """
    darpa_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "1992080034", datetime.date(1992, 4, 14),
                      "GAVÀ")
    # Another parte that day, so nothing could have matched by date alone.
    egif_fire(db_session, egif_id, "1992080099", datetime.date(1992, 4, 14), "GAVÀ")
    darpa_fire(db_session, darpa_id, "920800034", datetime.date(1992, 4, 14), "Gavà")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "920800034")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_CODE_REFORMATTED


def test_the_1986_and_1992_layouts_are_told_apart_by_the_year(db_session, providers):
    """The nine-digit form is ``PPYY`` in 1986 and ``YYPP`` in 1992.

    Only one reading of each puts the fire in the year of its own layer, which is
    what disambiguates them — ``920800034`` is province 92 of 1908 the other way,
    and there is no such thing.
    """
    darpa_id, egif_id = providers
    older = egif_fire(db_session, egif_id, "1986170064", datetime.date(1986, 7, 19),
                      "JONQUERA, LA")
    newer = egif_fire(db_session, egif_id, "1992250018", datetime.date(1992, 2, 23),
                      "GUINGUETA D' ANEU, LA")
    darpa_fire(db_session, darpa_id, "178600064", datetime.date(1986, 7, 19),
               "La Jonquera", year=1986)
    darpa_fire(db_session, darpa_id, "922500018", datetime.date(1992, 2, 23),
               "La Guingueta d'Àneu", year=1992)
    db_session.commit()

    run(db_session)

    assert stored(db_session, "178600064").egif_wildfire_id == older.id
    assert stored(db_session, "922500018").egif_wildfire_id == newer.id
    assert {stored(db_session, code).match_method
            for code in ("178600064", "922500018")} == {MATCH_CODE_REFORMATTED}


def test_a_six_digit_code_carries_a_one_digit_province(db_session, providers):
    """``894496`` in 1994 is province 08, year 94, fire 496."""
    darpa_id, egif_id = providers
    parte = egif_fire(db_session, egif_id, "1994080496", datetime.date(1994, 8, 11),
                      "SANT CUGAT DEL VALLES")
    egif_fire(db_session, egif_id, "1994080497", datetime.date(1994, 8, 11), "OLESA")
    darpa_fire(db_session, darpa_id, "894496", datetime.date(1994, 8, 11),
               "Sant Cugat del Vallès")
    db_session.commit()

    run(db_session)

    fire = stored(db_session, "894496")
    assert fire.egif_wildfire_id == parte.id
    assert fire.match_method == MATCH_CODE_REFORMATTED


def test_a_decode_the_date_contradicts_is_not_believed(db_session, providers):
    """The guard that makes the decode safe.

    A rearranged code is a reading of a format rather than string equality, so it
    has to be confirmed. On the real archive all 122 decodes agree on the date; one
    that did not would be a coincidence of digits, not an identifier.
    """
    darpa_id, egif_id = providers
    egif_fire(db_session, egif_id, "1992080034", datetime.date(1992, 9, 30), "GAVÀ")
    darpa_fire(db_session, darpa_id, "920800034", datetime.date(1992, 4, 14), "Gavà")
    db_session.commit()

    bindings = run(db_session)

    assert stored(db_session, "920800034").egif_wildfire_id is None
    assert bindings[0].reason == app.UNBOUND_NO_CANDIDATE


def test_a_decode_that_is_not_catalan_is_refused():
    """A code of some other kind with the right number of digits is not a report number."""
    assert catalonia_darpa.egif_report_number("999900123", 1999) is None
    assert catalonia_darpa.egif_report_number("339400123", 1994) is None, "province 33"


def test_the_letter_formats_are_not_decoded():
    """1987-1991 carry six digits where a report number has four; no reading fits.

    Asserted so the omission stays deliberate. Their province is still read off the
    leading letter, which is the only thing narrowing those 97 fires.
    """
    for code, year in (("G0870016", 1987), ("L89004001", 1989), ("T91030011", 1991)):
        assert catalonia_darpa.egif_report_number(code, year) is None
    assert catalonia_darpa.province_ine_code("L89004001", 1989) == "25"
    assert catalonia_darpa.province_ine_code("G0870016", 1987) == "17"


def test_a_reformatted_code_ranks_below_a_literal_one_and_above_the_rest():
    assert MATCH_METHOD_CONFIDENCE[MATCH_CODE] > \
        MATCH_METHOD_CONFIDENCE[MATCH_CODE_REFORMATTED] > \
        MATCH_METHOD_CONFIDENCE[MATCH_DATE_PROVINCE_NAME]
