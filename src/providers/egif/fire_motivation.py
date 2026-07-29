#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EGIF fire motivation model.

``idmotivacion`` says *why* an intentional fire was lit — to clear pasture, to
force a change of land use, out of revenge, for the sake of watching it burn. It
is a three-digit code with the same shape as ``idcausa`` and is published on
exactly the fires whose cause is :data:`~src.providers.egif.CAUSE_INTENTIONAL`:
7,117 of the 13,656 fires in the 2022-2023 export, and not one fire outside that
family.

Why this is a second table and not more rows in the first
---------------------------------------------------------

Because the two code spaces overlap and mean different things:

.. code-block:: text

   400  as idcausa       Intencionado
   400  as idmotivacion  Motivación desconocida

They are as unrelated as two enumerations that happen to start counting at the
same place. Put both in one table keyed by code and every query that joins on the
code alone is wrong half the time, silently; keep them apart and the mistake
cannot be expressed. This is the one thing to remember about EGIF's coding, and it
is why :class:`~src.providers.egif.wildfire.EgifWildfire` carries two foreign keys
rather than one.

Everything else about the model — where the labels come from, why the code is not
the key, why :attr:`EgifFireMotivation.label_en` ships empty — is the argument in
:mod:`src.providers.egif.fire_cause`, and is not repeated here.

The catalogue is fully known
----------------------------

Unlike the causes, the motivations were already recoverable from the *Instrucciones
para cumplimentar el parte de incendio forestal*, which prints the complete table.
The Excel export agrees with it: all 28 codes seen in 2022-2023 are in the PDF's
table and none outside it, with ``443``, ``461`` and ``462`` simply unused in those
two campaigns. The two sources corroborating each other is the reason this
catalogue can be trusted where the cause list had to be reconstructed.
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


class EgifFireMotivation(Base):
    """One entry of the EGIF motivation classification (``idmotivacion``).

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key, and what a fire's ``motivation_id``
        points at.
    code : str
        The published ``idmotivacion``, three digits. Indexed and **not** unique,
        and text rather than a number, for the reasons given in
        :class:`~src.providers.egif.fire_cause.EgifFireCause`.

        Do not compare it with a cause code: ``400`` exists in both spaces and
        names different things.
    label : str
        The Spanish label as the Excel export prints it, ``[code]`` prefix
        stripped and runs of spaces collapsed.
    label_en : str or None
        English for :attr:`label`. Always ``None`` as imported.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.
    """

    __tablename__ = "egif_fire_motivation"

    __table_args__ = (
        UniqueConstraint("code", "label", name="uq_egif_fire_motivation_code_label"),
        Index("ix_egif_fire_motivation_code", "code"),
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
        return f"EgifFireMotivation(id={self.id!r}, code={self.code!r})"
