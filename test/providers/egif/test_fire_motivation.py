#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`EgifFireMotivation` lookup model.

The point of this module is the one in the model's docstring: motivations are a
*separate code space* from causes, and the schema has to let ``400`` mean two
different things at once.
"""

import pytest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.providers.egif.fire_cause import EgifFireCause
from src.providers.egif.fire_motivation import EgifFireMotivation


def a_motivation(**overrides) -> EgifFireMotivation:
    values = {
        "code": "482",
        "label": "Incendios provocados por vandalismo (gamberradas,etc)",
    }
    values.update(overrides)
    return EgifFireMotivation(**values)


def test_a_motivation_is_stored_as_published(db_session):
    db_session.add(a_motivation())
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifFireMotivation))
    assert stored.code == "482"
    assert stored.label == "Incendios provocados por vandalismo (gamberradas,etc)"
    assert stored.label_en is None


def test_code_400_means_different_things_in_the_two_catalogues(db_session):
    """The reason there are two tables and not one.

    As a cause, 400 is *Intencionado*. As a motivation, it is *Motivación
    desconocida*. Both have to be storable at once, and a join on the code alone
    has to be impossible to express.
    """
    db_session.add(EgifFireCause(code="400", label="Intencionado"))
    db_session.add(a_motivation(code="400", label="Motivación desconocida"))
    db_session.commit()

    cause = db_session.scalar(select(EgifFireCause).where(EgifFireCause.code == "400"))
    motivation = db_session.scalar(
        select(EgifFireMotivation).where(EgifFireMotivation.code == "400"))
    assert cause.label == "Intencionado"
    assert motivation.label == "Motivación desconocida"
    assert cause.label != motivation.label


def test_the_same_motivation_cannot_be_stored_twice(db_session):
    db_session.add(a_motivation())
    db_session.add(a_motivation())
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_code_may_name_two_labels(db_session):
    db_session.add(a_motivation(code="499", label="Otras motivaciones (conocidas)"))
    db_session.add(a_motivation(code="499", label="Something a later edition calls it"))
    db_session.commit()

    stored = db_session.scalars(
        select(EgifFireMotivation).where(EgifFireMotivation.code == "499")).all()
    assert len(stored) == 2


def test_the_label_is_required(db_session):
    db_session.add(a_motivation(label=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_code_is_required(db_session):
    db_session.add(a_motivation(code=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist():
    assert repr(a_motivation()) == "EgifFireMotivation(id=None, code='482')"
