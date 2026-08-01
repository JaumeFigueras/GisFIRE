#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`EgifFireCause` lookup model.

What is pinned down here is the shape the catalogue has to tolerate: a code that
is not the key, a label that is required, and a translation that is not.
"""

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.providers.spain_egif import CAUSE_INTENTIONAL
from src.providers.spain_egif import CAUSE_LIGHTNING
from src.providers.spain_egif import CAUSE_REKINDLE
from src.providers.spain_egif import CAUSE_UNKNOWN
from src.providers.spain_egif.fire_cause import EgifFireCause


def a_cause(**overrides) -> EgifFireCause:
    values = {
        "code": "213",
        "label": "Quema de restos agrícolas (viñas,etc)",
    }
    values.update(overrides)
    return EgifFireCause(**values)


def test_a_cause_is_stored_as_published(db_session):
    db_session.add(a_cause())
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifFireCause))
    assert stored.code == "213"
    assert stored.label == "Quema de restos agrícolas (viñas,etc)"
    assert stored.label_en is None


def test_the_same_classification_cannot_be_stored_twice(db_session):
    db_session.add(a_cause())
    db_session.add(a_cause())
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_one_code_may_name_two_labels(db_session):
    """No EGIF code has changed meaning yet, but the catalogue is versioned.

    The *Instrucciones* are on their ninth update and each has added subcodes. If
    one ever renames a code, both meanings have to be storable or every historical
    fire silently acquires the new label.
    """
    db_session.add(a_cause(code="326", label="Transformadores de la red eléctrica"))
    db_session.add(a_cause(code="326", label="Something a later edition calls it"))
    db_session.commit()

    stored = db_session.scalars(
        select(EgifFireCause).where(EgifFireCause.code == "326")).all()
    assert len(stored) == 2


def test_a_code_keeps_its_leading_zeros(db_session):
    """Stored as text: the code is an identifier, not a quantity."""
    db_session.add(a_cause(code="100"))
    db_session.add(a_cause(code="0100"))
    db_session.commit()

    assert {row.code for row in db_session.scalars(select(EgifFireCause))} == {"100", "0100"}


def test_the_label_is_required(db_session):
    """A code with no label is exactly what an XML-only import must not create."""
    db_session.add(a_cause(label=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_code_is_required(db_session):
    db_session.add(a_cause(code=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_translation_may_be_added_without_touching_the_spanish(db_session):
    db_session.add(a_cause(code="100", label="Rayo", label_en="Lightning"))
    db_session.commit()

    stored = db_session.scalar(select(EgifFireCause).where(EgifFireCause.code == "100"))
    assert stored.label == "Rayo"
    assert stored.label_en == "Lightning"


def test_the_family_codes_are_the_ones_read_off_the_excel_export(db_session):
    """400 is *Intencionado*, not *desconocida*, and 600 exists.

    The paper form lists five families in an order that suggests 400 = unknown and
    500 = rekindle. The Excel export prints the labels, and they do not say that.
    Getting this backwards would misclassify 7,117 intentional fires of 13,656 as
    unknown, so the constants are checked rather than trusted.
    """
    assert (CAUSE_LIGHTNING, CAUSE_INTENTIONAL, CAUSE_UNKNOWN, CAUSE_REKINDLE) == (
        "100", "400", "500", "600")


def test_the_catalogue_holds_every_family_side_by_side(db_session):
    db_session.add_all([
        a_cause(code=CAUSE_LIGHTNING, label="Rayo"),
        a_cause(code=CAUSE_INTENTIONAL, label="Intencionado"),
        a_cause(code=CAUSE_UNKNOWN, label="Desconocida"),
        a_cause(code=CAUSE_REKINDLE, label="Reproducido"),
    ])
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(EgifFireCause)) == 4


def test_repr_before_persist():
    assert repr(a_cause()) == "EgifFireCause(id=None, code='213')"
