#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`IcnfFireCause` lookup model and its translations."""

import pytest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.providers.portugal_icnf.fire_cause import DESCRIPTION_TRANSLATIONS
from src.providers.portugal_icnf.fire_cause import IcnfFireCause
from src.providers.portugal_icnf.fire_cause import TYPE_TRANSLATIONS


def a_cause(**overrides) -> IcnfFireCause:
    values = {
        "code": "125",
        "type": "Negligente",
        "type_en": "Negligent",
        "description": "Queimadas para gestão de pasto para gado",
        "description_en": "Burning for livestock pasture management",
    }
    values.update(overrides)
    return IcnfFireCause(**values)


# --------------------------------------------------------------------------
# The translation tables
# --------------------------------------------------------------------------

def test_every_published_cause_type_is_translated():
    """The five values Causa_Tipo takes across 2014-2024, all of them."""
    assert set(TYPE_TRANSLATIONS) == {
        "Negligente", "Intencional", "Desconhecida", "Reacendimento", "Natural",
    }


def test_every_published_cause_description_is_translated():
    """Twenty-four distinct Causa_Desc values across 2014-2025."""
    assert len(DESCRIPTION_TRANSLATIONS) == 24


def test_the_2025_descriptions_keep_their_published_trailing_underscore():
    """The key has to match what the file says, typo and all, or the lookup misses."""
    assert "Queimadas extensivas - Outras_" in DESCRIPTION_TRANSLATIONS
    assert "Queimadas extensivas - Outras" not in DESCRIPTION_TRANSLATIONS


def test_no_translation_is_left_empty():
    for table in (TYPE_TRANSLATIONS, DESCRIPTION_TRANSLATIONS):
        assert all(portuguese and english for portuguese, english in table.items())


def test_queimada_and_queima_are_not_translated_to_the_same_thing():
    """Two different acts under Portuguese forest law; merging them loses a category."""
    spread = DESCRIPTION_TRANSLATIONS["Queimadas de sobrantes florestais ou agrícolas"]
    piled = DESCRIPTION_TRANSLATIONS["Queimas amontoados de sobrantes florestais ou agrícolas"]
    assert spread != piled
    assert "piled" in piled


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_a_cause_is_stored_with_both_languages(db_session):
    db_session.add(a_cause())
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(IcnfFireCause))
    assert stored.code == "125"
    assert stored.type == "Negligente"
    assert stored.type_en == "Negligent"
    assert stored.description == "Queimadas para gestão de pasto para gado"
    assert stored.description_en == "Burning for livestock pasture management"


def test_the_same_classification_cannot_be_stored_twice(db_session):
    db_session.add(a_cause())
    db_session.add(a_cause())
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_code_may_name_two_classifications(db_session):
    """The ICNF reused 126-129 in 2025, so the code alone cannot be the key.

    Both meanings have to be storable, or every 2025 fire in those codes is
    attached to a description that stopped applying to it.
    """
    db_session.add(a_cause(
        code="127", description="Queimadas de sobrantes florestais ou agrícolas",
        description_en="Burning of forest or agricultural residues"))
    db_session.add(a_cause(
        code="127",
        description="Queimadas extensivas - Limpeza de caminhos, acessos e instalações_",
        description_en="Extensive burning - Clearing of paths, accesses and installations"))
    db_session.commit()

    stored = db_session.scalars(
        select(IcnfFireCause).where(IcnfFireCause.code == "127")).all()
    assert len(stored) == 2
    assert len({row.description for row in stored}) == 2


def test_a_code_keeps_its_leading_zeros(db_session):
    """Stored as text: 60 and 060 are different codes, not the same number."""
    db_session.add(a_cause(code="60"))
    db_session.add(a_cause(code="060"))
    db_session.commit()

    assert {row.code for row in db_session.scalars(select(IcnfFireCause))} == {"60", "060"}


def test_the_portuguese_is_required_and_the_english_is_not(db_session):
    """A category a later release invents is stored untranslated rather than refused."""
    db_session.add(a_cause(code="999", type_en=None, description_en=None))
    db_session.commit()

    stored = db_session.scalar(select(IcnfFireCause).where(IcnfFireCause.code == "999"))
    assert stored.type_en is None
    assert stored.description_en is None


def test_the_published_type_is_required(db_session):
    db_session.add(a_cause(type=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist():
    assert repr(a_cause()) == "IcnfFireCause(id=None, code='125', type='Negligente')"
