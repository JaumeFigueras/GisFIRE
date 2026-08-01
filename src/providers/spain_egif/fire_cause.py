#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EGIF fire cause model.

The cause of an EGIF fire is a three-digit code, ``idcausa``, and the whole
catalogue is a lookup table for the same reason the ICNF's is: one classification
is shared by every fire that carries it, and a classification is a thing in its
own right rather than a property of one fire.

Where the labels come from
--------------------------

Nowhere in the published documentation. The instructions PDF gives the cause
*hierarchy* in prose and no numbers at all, and the search service's own
``Search/getCausasIncendio`` endpoint — which would return exactly this table as
JSON — redirects to a login.

What does publish them is the **Excel export**, which prints code and label
together, ``[213]  Quema de restos agrícolas (viñas,etc)``. The 87 codes present
across the 2022 and 2023 campaigns were read off it; the seed for this table is
``NOTES_EGIF_codes.csv`` at the root of the repository.

That is why the import order in :mod:`src.providers.spain_egif` is not negotiable. The
XML publishes ``<idcausa>231</idcausa>`` and nothing else, so an XML import into a
database whose catalogue was never seeded produces fires whose cause is an integer
with no meaning attached.

The code is not the key, for the ICNF's reason
----------------------------------------------

No EGIF code has been observed to change meaning — unlike the ICNF, which reused
four — but the catalogue is versioned: the *Instrucciones para cumplimentar el
parte de incendio forestal* are at v3.6, *9ª actualización*, and each revision has
added subcodes. ``327`` *Aerogenerador* and ``328`` *Huerto solar/placas solares*
are plainly recent additions to a list that once ended at ``326``.

So the key is ``(code, label)`` and the code is indexed but **not unique**,
exactly as in :class:`~src.providers.portugal_icnf.fire_cause.IcnfFireCause`. If an edition
ever renames a code, both meanings are storable and a fire links to the one its
own export published, instead of every historical fire silently acquiring the new
label.

There is no translation table
-----------------------------

:attr:`EgifFireCause.label_en` exists and is left ``None`` by the import. The ICNF
model ships translations because its catalogue is 24 short category names; this
one is 87 causes and 28 motivations of running Spanish prose — *"Incendios
provocados para mantener libre de vegetación el monte, bajo un concepto
tradicional del paisaje, sin pretender otro beneficio"* — which are terms of art
in Spanish forest-fire administration and where a wrong guess would read exactly
like a right one. The column is there for translations added deliberately, one at
a time; it is not there to be filled by a bulk pass.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model import Base


class EgifFireCause(Base):
    """One entry of the EGIF cause classification (``idcausa``).

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key, and what a fire's ``cause_id``
        points at. A surrogate rather than the code itself because the natural
        key is the ``(code, label)`` pair — see the module docstring.
    code : str
        The published ``idcausa``, three digits. Indexed and **not** unique.

        Text, not a number: it is an identifier rather than a quantity, its first
        digit is a family (see :mod:`src.providers.spain_egif`), and nothing is gained
        by making ``100`` and ``0100`` the same value.
    label : str
        The Spanish label as the Excel export prints it, with the ``[code]``
        prefix stripped and the run of spaces collapsed — ``"Quema de restos
        agrícolas (viñas,etc)"``. Stored as published otherwise, punctuation and
        missing spaces included.
    label_en : str or None
        English for :attr:`label`. Always ``None`` as imported; see the module
        docstring for why no translation table ships with the model.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    The table has no ``data_provider_id``. This classification is the EGIF's own
    and means nothing outside it, which the table name already says — the same
    argument as for :class:`~src.providers.portugal_icnf.fire_cause.IcnfFireCause`.

    Nor are the rows seeded from a list frozen in the source. The importer inserts
    whatever ``(code, label)`` pairs the export it is reading actually contains,
    so a code a later edition adds appears the first time a fire uses it.
    """

    __tablename__ = "egif_fire_cause"

    __table_args__ = (
        UniqueConstraint("code", "label", name="uq_egif_fire_cause_code_label"),
        Index("ix_egif_fire_cause_code", "code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    label_en: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"EgifFireCause(id={self.id!r}, code={self.code!r})"
