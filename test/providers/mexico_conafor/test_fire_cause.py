#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`ConaforFireCause` lookup model and its tables.

Two things are worth pinning down here. The reconciliation tables have to reach
every published spelling — a cause they miss is a hole in a fourteen-year time
series — and the ``NULL`` half of the natural key has to be constrained, because
three fires in five have one.
"""

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.providers.mexico_conafor import normalise
from src.providers.mexico_conafor.fire_cause import CAUSE_NORMALISATIONS
from src.providers.mexico_conafor.fire_cause import CAUSE_TRANSLATIONS
from src.providers.mexico_conafor.fire_cause import ConaforFireCause
from src.providers.mexico_conafor.fire_cause import SPECIFIC_CAUSE_TRANSLATIONS


def a_cause(**overrides) -> ConaforFireCause:
    values = {
        "cause": "Fogatas",
        "cause_normalised": "Fogatas",
        "cause_en": "Campfires",
        "specific_cause": "Fogatas de paseantes",
        "specific_cause_en": "Campfires of day trippers",
    }
    values.update(overrides)
    return ConaforFireCause(**values)


# --------------------------------------------------------------------------
# The reconciliation table
# --------------------------------------------------------------------------

def test_every_key_of_the_normalisation_table_is_already_normalised():
    """It is looked up with normalise(); a key that is not folded can never match."""
    for key in CAUSE_NORMALISATIONS:
        assert key == normalise(key)


def test_the_four_spellings_of_fogatas_reconcile_to_one():
    assert {CAUSE_NORMALISATIONS[normalise(published)]
            for published in ("Fogatas", "fogatas", "Fogata", "Fogatas\n")} == {"Fogatas"}


def test_the_electrical_storms_of_2011_are_the_naturales_of_2012_onwards():
    """One natural cause under two administrative names a decade apart."""
    for published in ("Tormenta Electrica", "Tormenta Electrica.", "Tormenta Elcetrica",
                      "Descargas Electricas", "Descargas electricas", "Naturales"):
        assert CAUSE_NORMALISATIONS[normalise(published)] == "Naturales"


def test_the_three_ways_of_not_knowing_reconcile_to_one():
    for published in ("Desconocidas", "DESCONOCIDAS", "Desconocida", "Desconocidos",
                      "No Determinadas"):
        assert CAUSE_NORMALISATIONS[normalise(published)] == "Desconocidas"


def test_the_agropecuario_typos_reconcile_to_one():
    """Six spellings, one of which carries a stray clause about singeing nopal."""
    for published in ("Actividades Agropecuarias", "Agropecuario",
                      "Actividad Agropecuario", "Actividad Agropecuarias",
                      "Actividad Agropecuaria,",
                      "Actividad Agropecuaria, Chamuzca de Nopal."):
        assert CAUSE_NORMALISATIONS[normalise(published)] == "Actividades agropecuarias"


def test_agricolas_and_pecuarias_stay_apart():
    """The 2018-2022 layers split what the earlier ones lumped; do not re-merge them."""
    agricultural = CAUSE_NORMALISATIONS[normalise("Actividades Agricolas")]
    livestock = CAUSE_NORMALISATIONS[normalise("Actividades Pecuarias")]
    combined = CAUSE_NORMALISATIONS[normalise("Actividades Agropecuarias")]
    assert len({agricultural, livestock, combined}) == 3


def test_intencional_and_desconocidas_stay_apart():
    """The largest two causes in the archive; merging them would say nothing at all."""
    assert (CAUSE_NORMALISATIONS[normalise("Intencional")]
            != CAUSE_NORMALISATIONS[normalise("Desconocidas")])


# --------------------------------------------------------------------------
# The translation tables
# --------------------------------------------------------------------------

def test_every_canonical_cause_is_translated():
    """A canonical form with no English is a column that is NULL for no good reason."""
    assert set(CAUSE_NORMALISATIONS.values()) == set(CAUSE_TRANSLATIONS)


def test_the_translations_are_keyed_on_the_canonical_form_not_the_published_one():
    """One English string per cause, not one per spelling."""
    assert "Fogatas" in CAUSE_TRANSLATIONS
    assert "fogatas" not in CAUSE_TRANSLATIONS


def test_every_specific_cause_key_is_normalised():
    for key in SPECIFIC_CAUSE_TRANSLATIONS:
        assert key == normalise(key)


def test_no_translation_is_left_empty():
    for table in (CAUSE_TRANSLATIONS, SPECIFIC_CAUSE_TRANSLATIONS):
        assert all(spanish and english for spanish, english in table.items())


def test_the_right_of_way_clearing_is_not_translated_as_transport():
    """Two published causes, two administrative categories; merging loses one."""
    assert (CAUSE_TRANSLATIONS["Limpias de derecho de vía"]
            != CAUSE_TRANSLATIONS["Transportes"])


def test_rayos_and_descargas_electricas_are_the_same_specific_cause():
    """Both are lightning, in the one column where that question can be asked."""
    assert (SPECIFIC_CAUSE_TRANSLATIONS["rayos"]
            == SPECIFIC_CAUSE_TRANSLATIONS["descargas electricas"] == "Lightning")


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_a_classification_is_stored_with_both_languages(db_session):
    db_session.add(a_cause())
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(ConaforFireCause))
    assert stored.cause == "Fogatas"
    assert stored.cause_normalised == "Fogatas"
    assert stored.cause_en == "Campfires"
    assert stored.specific_cause == "Fogatas de paseantes"
    assert stored.specific_cause_en == "Campfires of day trippers"


def test_the_published_cause_is_required(db_session):
    db_session.add(a_cause(cause=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_cause_a_later_release_invents_is_stored_untranslated(db_session):
    """Refusing it would drop a fire; storing it unreconciled is recoverable."""
    db_session.add(a_cause(cause="Drones", cause_normalised=None, cause_en=None,
                           specific_cause=None, specific_cause_en=None))
    db_session.commit()

    stored = db_session.scalar(
        select(ConaforFireCause).where(ConaforFireCause.cause == "Drones"))
    assert stored.cause_normalised is None
    assert stored.cause_en is None


def test_the_published_pair_cannot_be_stored_twice(db_session):
    db_session.add(a_cause())
    db_session.add(a_cause())
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_cause_with_no_specific_cause_cannot_be_stored_twice_either(db_session):
    """The reason for the partial indexes: in SQL two NULLs are not equal.

    ``CAUSAESP`` is absent from 2011 and from every year from 2020, so this is
    the shape of the classifications covering three fires in five. A plain
    ``UNIQUE (cause, specific_cause)`` would let the catalogue grow a duplicate
    every time one of those layers was imported.
    """
    db_session.add(a_cause(specific_cause=None, specific_cause_en=None))
    db_session.add(a_cause(specific_cause=None, specific_cause_en=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_cause_may_carry_many_specific_causes(db_session):
    """CAUSA and CAUSAESP pair 179 ways over 45,914 fires."""
    db_session.add(a_cause(specific_cause="Fogatas de paseantes"))
    db_session.add(a_cause(specific_cause="Otras", specific_cause_en="Other"))
    db_session.add(a_cause(specific_cause=None, specific_cause_en=None))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(ConaforFireCause)) == 3


def test_many_classifications_may_share_a_canonical_cause(db_session):
    """cause_normalised is the grouping key, not an identity — see the module docstring."""
    db_session.add(a_cause(cause="Fogatas", specific_cause=None, specific_cause_en=None))
    db_session.add(a_cause(cause="fogatas", specific_cause=None, specific_cause_en=None))
    db_session.add(a_cause(cause="Fogata", specific_cause=None, specific_cause_en=None))
    db_session.commit()

    grouped = db_session.scalars(
        select(ConaforFireCause).where(ConaforFireCause.cause_normalised == "Fogatas")).all()
    assert len(grouped) == 3
    assert {row.cause for row in grouped} == {"Fogatas", "fogatas", "Fogata"}


def test_the_published_trailing_newline_is_kept(db_session):
    """It is in the file. The canonical form beside it is what a query groups by."""
    db_session.add(a_cause(cause="Fogatas\n", specific_cause=None, specific_cause_en=None))
    db_session.commit()

    stored = db_session.scalar(
        select(ConaforFireCause).where(ConaforFireCause.cause_normalised == "Fogatas"))
    assert stored.cause == "Fogatas\n"


def test_repr_before_persist():
    assert repr(a_cause()) == (
        "ConaforFireCause(id=None, cause='Fogatas', "
        "specific_cause='Fogatas de paseantes')")
