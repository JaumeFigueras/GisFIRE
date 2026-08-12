#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`ConafFireCause` lookup model and its reconciliation tables.

CONAF renumbered its cause taxonomy in 2023-2024 **and reused the numbers**, so the
thing this module has to get right is not spelling but arithmetic on a moving
vocabulary: ``4.1`` names two different causes on the two sides of the break, and
the 2016-2017 layer publishes nothing but the number. Most of what follows pins
that — that a code is never read without a scheme, that the scheme is settled
before the cause is named, and that the ten renamed categories stay apart.

The rest pins the shape of the natural key. Either half of ``(cause,
specific_cause)`` can be ``NULL`` here — one more case than
:mod:`src.providers.mexico_conafor.fire_cause` has to cover — which is why there
are three partial unique indexes and a ``CHECK`` where CONAFOR needs two and none.
"""

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.providers.chile_conaf import normalise
from src.providers.chile_conaf.fire_cause import CAUSE_NORMALISATIONS
from src.providers.chile_conaf.fire_cause import CAUSE_TRANSLATIONS
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.fire_cause import POST_2023_CODE_NAMES
from src.providers.chile_conaf.fire_cause import PRE_2023_CODE_NAMES
from src.providers.chile_conaf.fire_cause import SCHEME_POST_2023
from src.providers.chile_conaf.fire_cause import SCHEME_PRE_2023
from src.providers.chile_conaf.fire_cause import SCHEME_SUCCESSORS
from src.providers.chile_conaf.fire_cause import SCHEMES
from src.providers.chile_conaf.fire_cause import resolve_cause
from src.providers.chile_conaf.fire_cause import resolve_published_cause
from src.providers.chile_conaf.fire_cause import split_code


def a_cause(**overrides) -> ConafFireCause:
    values = {
        "cause": "1.7. Tránsito de personas, vehículos o aeronaves",
        "cause_code": "1.7",
        "cause_normalised": "Tránsito de personas, vehículos o aeronaves",
        "cause_en": "Movement of people, vehicles or aircraft",
        "specific_cause": "1.7.1. Uso de fuego por transeúntes",
        "specific_cause_code": "1.7.1",
        "scheme": SCHEME_PRE_2023,
    }
    values.update(overrides)
    return ConafFireCause(**values)


# --------------------------------------------------------------------------
# The reconciliation table
# --------------------------------------------------------------------------

def test_every_key_of_the_normalisation_table_is_already_normalised():
    """It is looked up with normalise(); a key that is not folded can never match."""
    for key in CAUSE_NORMALISATIONS:
        assert key == normalise(key)


def test_looking_a_canonical_cause_up_gives_it_back():
    """Folding a canonical form and looking it up is a no-op, not a ``KeyError``.

    Three canonical forms carry commas the published spelling drops —
    *Actividades al aire libre (camping, excursiones, …)* is published without any
    of them — so both spellings are keys. That makes the table idempotent under
    fold-and-look-up, and it means a season that starts punctuating properly
    reconciles on the day it appears rather than the day somebody notices.
    """
    for canonical in set(CAUSE_NORMALISATIONS.values()):
        assert CAUSE_NORMALISATIONS[normalise(canonical)] == canonical


def test_the_two_spellings_of_transito_reconcile_to_one():
    """The comma appears in some seasons and not others; the fold does not remove it."""
    assert (CAUSE_NORMALISATIONS[normalise("Tránsito de personas, vehículos o aeronaves")]
            == CAUSE_NORMALISATIONS[normalise("TRANSITO DE PERSONAS VEHICULOS O AERONAVES")]
            == "Tránsito de personas, vehículos o aeronaves")


def test_the_four_unchanged_causes_keep_one_name_across_the_break():
    """CONAF kept the name, so this table keeps one canonical form. Only these four."""
    for published in ("Faenas forestales", "Faenas agrícolas y pecuarias",
                      "Incendios intencionales", "Incendios naturales"):
        canonical = CAUSE_NORMALISATIONS[normalise(published)]
        assert canonical not in SCHEME_SUCCESSORS, \
            f"{canonical} is bridged, so it is not one of the unchanged four"


@pytest.mark.parametrize("before, after", [
    ("Quema de desechos", "Otras quemas"),
    ("Accidentes eléctricos", "Líneas eléctricas"),
    ("Actividades recreativas",
     "Actividades al aire libre (camping, excursiones, caza, pesca, otros)"),
    ("Tránsito de personas, vehículos o aeronaves",
     "Originados por desplazamiento de personas, vehículos o aeronaves"),
])
def test_a_renamed_category_stays_apart_from_its_successor(before, after):
    """*Quema de desechos* is burning rubbish; *Otras quemas* is any other burning.

    They are different sizes, so merging them would invent a continuity CONAF did
    not publish. The consequence — a break at 2023-2024 in any series of these ten
    — is the datum, and :data:`SCHEME_SUCCESSORS` is the deliberate way across it.
    """
    assert CAUSE_NORMALISATIONS[normalise(before)] == before
    assert CAUSE_NORMALISATIONS[normalise(after)] == after
    assert before != after
    assert SCHEME_SUCCESSORS[before] == after


def test_the_bridge_only_ever_points_forwards():
    """Keys are pre-2023 canonical forms, values post-2023 ones, and never the same.

    A self-entry would be an assertion that a category was renamed to itself, which
    would put it in this table instead of among the unchanged four where it belongs.
    """
    canonical = set(CAUSE_NORMALISATIONS.values())
    for before, after in SCHEME_SUCCESSORS.items():
        assert before in canonical and after in canonical
        assert before != after
        assert before in PRE_2023_CODE_NAMES.values()
        assert after in POST_2023_CODE_NAMES.values()


def test_the_invented_category_has_no_predecessor():
    """642 fires, and nothing before 2023-2024 to join them to."""
    invented = ("Parcelaciones, edificaciones residenciales, industriales u otras en "
                "zonas rurales o de interfaz")
    assert invented in POST_2023_CODE_NAMES.values()
    assert invented not in SCHEME_SUCCESSORS.values()


def test_the_perimeter_archives_prose_spellings_reconcile():
    """The magnitud files write the cause by hand, in the singular and with clauses.

    Eleven of the 781 perimeters publish a *causa general* this way. Left out of the
    table they would be eleven unreconciled catalogue entries **and**, worse, would
    fall through to being read as specific causes — see
    :func:`resolve_published_cause`.
    """
    assert CAUSE_NORMALISATIONS[normalise("Incendio Intencional")] == "Incendios intencionales"
    assert CAUSE_NORMALISATIONS[normalise("Causa desconocida")] == "Incendios de causa desconocida"
    assert (CAUSE_NORMALISATIONS[normalise("Caída de rayo- Incendios naturales")]
            == "Incendios naturales")


# --------------------------------------------------------------------------
# The code tables
# --------------------------------------------------------------------------

def test_the_reused_codes_name_different_causes():
    """The whole reason ``scheme`` exists, stated as an assertion.

    ``4.1`` is *incendios de causa desconocida* before the break and *faenas
    forestales* after it. A fifteen-season series grouped on the code alone merges
    every fire whose cause was unknown with every fire started by forestry work.
    """
    assert PRE_2023_CODE_NAMES["4.1"] == "Incendios de causa desconocida"
    assert POST_2023_CODE_NAMES["4.1"] == "Faenas forestales"

    reused = {code for code in PRE_2023_CODE_NAMES
              if PRE_2023_CODE_NAMES[code] != POST_2023_CODE_NAMES.get(code)}
    assert reused == {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "4.1"}


def test_the_two_numberings_of_the_late_layers_name_the_same_cause():
    """2023-2024 and 2024-2025 publish ``1.1`` and ``4.1`` for one cause: 83 fires and 492.

    The group number wobbles inside a single published file, which is why the name
    and not the number is what :data:`CAUSE_NORMALISATIONS` is keyed on.
    """
    for tens, forties in (("1.1", "4.1"), ("1.8", "4.8"), ("1.9", "4.9"),
                          ("1.10", "4.10")):
        assert POST_2023_CODE_NAMES[tens] == POST_2023_CODE_NAMES[forties]


def test_every_code_names_a_cause_the_normalisation_table_knows():
    """Otherwise a bare code would resolve to a name nothing else in the schema uses."""
    canonical = set(CAUSE_NORMALISATIONS.values())
    for table in (PRE_2023_CODE_NAMES, POST_2023_CODE_NAMES):
        assert set(table.values()) <= canonical


def test_every_canonical_cause_is_translated():
    """A canonical form with no English is a column that is NULL for no good reason."""
    assert set(CAUSE_NORMALISATIONS.values()) == set(CAUSE_TRANSLATIONS)
    assert all(spanish and english for spanish, english in CAUSE_TRANSLATIONS.items())


def test_the_two_ways_of_not_knowing_are_translated_apart():
    """*Desconocida* is investigated and not established; *indeterminada* is not.

    They are the pre- and post-2023 forms of the same slot and CONAF chose different
    words for them; so does the English.
    """
    assert (CAUSE_TRANSLATIONS["Incendios de causa desconocida"]
            != CAUSE_TRANSLATIONS["Incendios de causa indeterminada"])


def test_faenas_is_not_translated_as_tasks():
    """Work in the field — forestry and farm operations — which is what CONAF means."""
    assert CAUSE_TRANSLATIONS["Faenas forestales"] == "Forestry operations"


# --------------------------------------------------------------------------
# Splitting a published string
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published, expected", [
    ("1.7. Tránsito de personas, vehículos o aeronaves",
     ("1.7", "transito de personas, vehiculos o aeronaves")),
    # 2023-2024 separates with a hyphen instead of a full stop.
    ("4.1 - Faenas forestales", ("4.1", "faenas forestales")),
    # 2016-2017 publishes the code and nothing else.
    ("01.07", ("1.7", "")),
    ("1.7.1. Uso de fuego por transeúntes", ("1.7.1", "uso de fuego por transeuntes")),
    ("Incendios Intencionales", (None, "incendios intencionales")),
    ("", (None, "")),
    (None, (None, "")),
])
def test_a_published_cause_splits_into_a_code_and_a_name(published, expected):
    assert split_code(published) == expected


def test_the_zeros_are_stripped_component_by_component():
    """``'01.10'`` is *otras actividades*; ``'1.1'`` is *faenas forestales*.

    Stripping the zeros from the string as a whole rather than from each component
    would silently move one into the other — 2016-2017 publishes 573 fires as
    ``'01.10'``.
    """
    assert split_code("01.10")[0] == "1.10"
    assert PRE_2023_CODE_NAMES["1.10"] != PRE_2023_CODE_NAMES["1.1"]


# --------------------------------------------------------------------------
# Resolving a published pair
# --------------------------------------------------------------------------

def test_the_bare_code_of_2016_2017_is_read_in_the_scheme_of_its_own_decade():
    """The headline: ``'04.01'`` is *causa desconocida*, and must not become *faenas*.

    2016-2017 is nine seasons before the renumbering and publishes 220 fires as
    ``'04.01'``. Naming the cause before settling the scheme would resolve every one
    of them into forestry work — a category they have nothing to do with — and it
    would look right, because *faenas forestales* is a plausible cause.
    """
    resolved = resolve_cause("04.01", "4.1.1. Sin información")
    assert resolved["cause_code"] == "4.1"
    assert resolved["scheme"] == SCHEME_PRE_2023
    assert resolved["cause_normalised"] == "Incendios de causa desconocida"
    assert resolved["cause_normalised"] != POST_2023_CODE_NAMES["4.1"]


def test_the_published_string_is_kept_byte_for_byte():
    """The row has to be checkable against the file it came from."""
    resolved = resolve_cause("01.07", "1.7.1.")
    assert resolved["cause"] == "01.07"
    assert resolved["specific_cause"] == "1.7.1."


def test_a_code_whose_name_is_published_settles_the_scheme_by_the_name():
    """``4.1`` beside *faenas forestales* can only be the post-2023 numbering."""
    resolved = resolve_cause("4.1 - Faenas forestales", None)
    assert resolved["scheme"] == SCHEME_POST_2023
    assert resolved["cause_normalised"] == "Faenas forestales"


def test_a_code_that_means_the_same_in_both_numberings_leaves_the_scheme_unset():
    """``1.1`` is *faenas forestales* either way, so the pair does not settle it.

    ``None`` here is the honest answer and it is harmless: the cause is the same
    whichever numbering the file was written in.
    """
    resolved = resolve_cause("1.1. Faenas forestales", None)
    assert resolved["scheme"] is None
    assert resolved["cause_normalised"] == "Faenas forestales"


def test_an_uncoded_cause_has_no_scheme_and_still_has_a_name():
    """Most seasons before 2019-2020 publish the name alone."""
    resolved = resolve_cause("Incendios Intencionales", None)
    assert (resolved["cause_code"], resolved["scheme"]) == (None, None)
    assert resolved["cause_normalised"] == "Incendios intencionales"
    assert resolved["cause_en"] == "Intentional fires"


def test_mojibake_is_stored_unreconciled_rather_than_guessed_at():
    """``'TRANSEONTES'`` lost a letter to a bad decode and cannot be guessed back.

    Storing it with no canonical form keeps the published string, keeps the fire,
    and makes the gap visible — which is what the import reports on.
    """
    resolved = resolve_cause("TRANSEONTES", None)
    assert resolved["cause"] == "TRANSEONTES"
    assert resolved["cause_normalised"] is None
    assert resolved["cause_en"] is None


@pytest.mark.parametrize("published", ["", "0", "S/I", "(en blanco)", None])
def test_a_null_token_is_no_cause_at_all(published):
    """``'0'`` included: it is a spreadsheet's empty cell, not a cause coded zero."""
    resolved = resolve_cause(published, published)
    assert resolved["cause"] is None and resolved["specific_cause"] is None
    assert resolved["cause_normalised"] is None


def test_the_scheme_is_only_ever_one_of_the_constrained_values():
    """The column carries a CHECK; a third string would be accepted here and refused there."""
    for cause in ("04.01", "4.1 - Faenas forestales", "1.1. Faenas forestales",
                  "Incendios Intencionales", "TRANSEONTES", None):
        assert resolve_cause(cause, None)["scheme"] in (*SCHEMES, None)


# --------------------------------------------------------------------------
# The perimeter archive's single CAUSA column
# --------------------------------------------------------------------------

def test_a_three_part_code_is_a_specific_cause():
    """730 of the 781 perimeters are settled exactly by the shape of their code."""
    resolved = resolve_published_cause("2.1.11. Otros intencionales no clasificados")
    assert resolved["cause"] is None
    assert resolved["specific_cause"] == "2.1.11. Otros intencionales no clasificados"
    assert resolved["specific_cause_code"] == "2.1.11"


def test_a_two_part_code_is_a_general_cause():
    resolved = resolve_published_cause("2.1. Incendios intencionales")
    assert resolved["cause"] == "2.1. Incendios intencionales"
    assert resolved["cause_normalised"] == "Incendios intencionales"
    assert resolved["specific_cause"] is None


def test_an_uncoded_string_the_table_knows_is_a_general_cause():
    """Eleven perimeters. The general causes are a closed list of twenty-three terms."""
    resolved = resolve_published_cause("Incendio Intencional")
    assert resolved["cause"] == "Incendio Intencional"
    assert resolved["cause_normalised"] == "Incendios intencionales"
    assert resolved["specific_cause"] is None


@pytest.mark.parametrize("published", [
    # causa específica 1.7.1, in the report archive's own words, 19,276 times.
    "Uso de fuego por transeúntes",
    "Rebrote de incendio anterior",          # 1.6.1
    "Niños jugando con fuego",               # 1.4.5
    "Elaboración de carbón",                 # 1.3.1
    "Chispa de maquinaria en faena agrícola",
    "Quema ilegal de desechos de cosecha forestal",
])
def test_an_uncoded_string_the_table_does_not_know_is_a_specific_cause(published):
    """Forty of the 781 perimeters write a *causa específica* without its number.

    Reading them as general causes — which an earlier version of this function did —
    filed forty sentences in the ``cause`` column, where a query grouping general
    causes counts them beside *Incendios intencionales* as though they were peers.

    Defaulting to *specific* is the rule that stays right as CONAF writes new
    sentences, which it does in every archive: the general causes are twenty-three
    terms and are recognised, the specific ones are five hundred and are not.
    """
    resolved = resolve_published_cause(published)
    assert resolved["cause"] is None
    assert resolved["specific_cause"] == published


def test_a_perimeter_with_no_published_cause_gets_no_row():
    """Eighteen of them, thirteen of which publish the ``'0'`` token."""
    assert resolve_published_cause("0") is None
    assert resolve_published_cause("") is None
    assert resolve_published_cause(None) is None


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_a_classification_round_trips(db_session):
    db_session.add(a_cause())
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(ConafFireCause))
    assert stored.cause_code == "1.7"
    assert stored.cause_normalised == "Tránsito de personas, vehículos o aeronaves"
    assert stored.cause_en == "Movement of people, vehicles or aircraft"
    assert stored.specific_cause_code == "1.7.1"
    assert stored.scheme == SCHEME_PRE_2023


def test_there_is_no_english_for_the_specific_cause(db_session):
    """Five hundred descriptive sentences, and nothing in GisFIRE would group by them.

    Deliberate, and a departure from CONAFOR, whose ``CAUSAESP`` is a vocabulary of
    fifty-four short terms. The code in front is what a query can use, and it is
    stored parsed out for exactly that.
    """
    assert "specific_cause_en" not in ConafFireCause.__table__.columns
    assert "specific_cause_code" in ConafFireCause.__table__.columns


def test_the_published_pair_cannot_be_stored_twice(db_session):
    db_session.add(a_cause())
    db_session.add(a_cause())
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_general_cause_on_its_own_cannot_be_stored_twice(db_session):
    """7,061 fires publish no ``CAUSA_ESPE``; so do most of the perimeters.

    In SQL two ``NULL``\\s are not equal, so a plain ``UNIQUE (cause,
    specific_cause)`` would let the catalogue grow a duplicate on every import.
    """
    db_session.add(a_cause(specific_cause=None, specific_cause_code=None))
    db_session.add(a_cause(specific_cause=None, specific_cause_code=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_specific_cause_on_its_own_cannot_be_stored_twice_either(db_session):
    """The shape a perimeter's classification takes — the third partial index.

    :class:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause` never needs
    this one: CONAFOR publishes the specific cause only beside a general one.
    """
    db_session.add(a_cause(cause=None, cause_code=None, cause_normalised=None,
                           cause_en=None))
    db_session.add(a_cause(cause=None, cause_code=None, cause_normalised=None,
                           cause_en=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_general_and_a_specific_cause_of_the_same_string_are_two_rows(db_session):
    """A perimeter's half-row is not a half-built version of a report's pair.

    The pair says which general cause a specific one was filed under; the perimeter
    archive does not say. Merging them would invent that.
    """
    db_session.add(a_cause(specific_cause=None, specific_cause_code=None))
    db_session.add(a_cause(cause=None, cause_code=None, cause_normalised=None,
                           cause_en=None))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(ConafFireCause)) == 2


def test_a_classification_that_classifies_nothing_is_refused(db_session):
    """The fourth combination, which no partial index can constrain.

    Such a fire carries ``cause_id IS NULL`` instead — the absence of a row, not a
    row recording an absence.
    """
    db_session.add(a_cause(cause=None, cause_code=None, cause_normalised=None,
                           cause_en=None, specific_cause=None,
                           specific_cause_code=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("scheme", [*SCHEMES, None])
def test_every_documented_scheme_is_accepted(db_session, scheme):
    db_session.add(a_cause(scheme=scheme))
    db_session.commit()

    assert db_session.scalar(select(ConafFireCause)).scheme == scheme


def test_a_scheme_outside_the_two_numberings_is_refused(db_session):
    db_session.add(a_cause(scheme="2016"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_many_classifications_may_share_a_canonical_cause(db_session):
    """cause_normalised is the grouping key, not an identity.

    110 published spellings onto twenty-three causes is the whole point of it.
    """
    for published in ("1.7. Tránsito de personas, vehículos o aeronaves",
                      "TRANSITO DE PERSONAS VEHICULOS O AERONAVES",
                      "Tránsi\xadto de personas, vehículos o aeronaves"):
        db_session.add(a_cause(cause=published, specific_cause=None,
                               specific_cause_code=None))
    db_session.commit()

    grouped = db_session.scalars(select(ConafFireCause).where(
        ConafFireCause.cause_normalised
        == "Tránsito de personas, vehículos o aeronaves")).all()
    assert len(grouped) == 3


def test_a_cause_conaf_invents_is_stored_unreconciled(db_session):
    """Refusing it would drop a fire; storing it without a canonical form is recoverable."""
    db_session.add(a_cause(cause="6.1. Drones", cause_code="6.1",
                           cause_normalised=None, cause_en=None,
                           specific_cause=None, specific_cause_code=None,
                           scheme=None))
    db_session.commit()

    stored = db_session.scalar(
        select(ConafFireCause).where(ConafFireCause.cause == "6.1. Drones"))
    assert stored.cause_code == "6.1"
    assert stored.cause_normalised is None


def test_the_table_belongs_to_conaf_and_says_so_by_its_name(db_session):
    """No ``data_provider_id``: the classification is CONAF's own and both products share it."""
    assert "data_provider_id" not in ConafFireCause.__table__.columns
    assert ConafFireCause.__tablename__ == "conaf_fire_cause"


def test_repr_before_persist():
    assert repr(a_cause()) == (
        "ConafFireCause(id=None, "
        "cause='1.7. Tránsito de personas, vehículos o aeronaves', "
        "specific_cause='1.7.1. Uso de fuego por transeúntes')")
