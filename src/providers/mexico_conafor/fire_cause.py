#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAFOR fire cause model.

CONAFOR classifies why every fire started, in two published attributes: ``CAUSA``,
the cause, in all fourteen layers, and ``CAUSAESP``, the *causa específica*, in
2010 and 2012-2019. The published files contain 179 distinct pairs of the two,
which become **141 stored classifications** once the null tokens in either half
are folded to ``NULL`` (see :func:`~src.providers.mexico_conafor.is_missing`) —
141 rows for 45,914 fires, one classification repeated on every fire that shares
it, which is what makes this a lookup table rather than two more columns on the
fire, on the same argument as :mod:`src.providers.portugal_icnf.fire_cause`.

Here there is a second reason, and it is the stronger one.

There is no code, and the text does not hold still
---------------------------------------------------

The ICNF publishes ``Causa_Cod`` beside its two names. CONAFOR publishes **no code
at all**: the cause is a typed string, and over fourteen years it is typed
sixty-four different ways for what is perhaps twenty real causes.

.. code-block:: text

   Fogatas · fogatas · Fogata · Fogatas\\n · Fogatas de paseantes ·
   Fogatas De Paseantes
   Desconocidas · DESCONOCIDAS · Desconocida · Desconocidos ·
   No Determinadas · Desconocidas\\n
   Actividades Agropecuarias · Actividad Agropecuaria, · Actividad Agropecuario ·
   Actividad Agropecuarias · Agropecuario ·
   Actividad Agropecuaria, Chamuzca de Nopal.
   Tormenta Electrica · Tormenta Electrica. · Tormenta Elcetrica ·
   Descargas Electricas · Descargas electricas · Naturales

Case- and accent-folding through
:func:`~src.providers.mexico_conafor.normalise` gets 64 down to 43 and stops
there. ``Fogatas`` and ``Fogata`` are still two strings; so are ``Desconocidas``
and ``No Determinadas``, and *Tormenta Eléctrica* and *Naturales*, which are the
same natural cause under two administrative names a decade apart.

**Without this table, every query that groups by cause has to redo that
reconciliation, and every analyst will do it slightly differently.** With it, the
reconciliation is done once, is written down where it can be argued with, and a
fourteen-year time series of ignition causes is a ``GROUP BY`` on one column.

Which is what the columns are for
----------------------------------

Four, in two pairs, and the distinction between them is the whole design:

:attr:`ConaforFireCause.cause` and :attr:`ConaforFireCause.specific_cause`
    The provider's own strings, byte for byte, trailing newlines and mojibake
    included. Together they are the natural key: a row exists for every pair the
    published files actually contain, so a fire always links to the classification
    *its own layer printed*, and any row can be checked against the file it came
    from.

:attr:`ConaforFireCause.cause_normalised`
    The canonical Spanish. Many published strings share one — this is the column
    that puts ``Fogatas``, ``fogatas``, ``Fogata`` and ``Fogatas\\n`` together —
    and it is **not unique**, deliberately: it is the grouping key, not an
    identity.

:attr:`ConaforFireCause.cause_en` and :attr:`ConaforFireCause.specific_cause_en`
    English beside the Spanish, never instead of it. From
    :data:`CAUSE_TRANSLATIONS` and :data:`SPECIFIC_CAUSE_TRANSLATIONS`, applied by
    the importer, and ``None`` for a string not in those tables — which is what a
    category a later release invents should look like, rather than a guess.

The tables below are fixed rather than computed for the reason ICNF's are: these
are terms of art in Mexican forestry administration, and a wrong guess would be
indistinguishable from a right one to a reader who does not speak Spanish.
*Chamuzca de nopal* is the singeing of prickly pear to burn the spines off before
feeding it to cattle; nothing derives that from the string.

The specific cause is not a sub-category of the cause
------------------------------------------------------

It looks like one and mostly behaves like one, but the pairing is not a
hierarchy: ``Quema para preparacion de siembra`` appears under
``Actividades Agropecuarias``, ``Actividades Agricolas`` and ``Agropecuario``, and
``Ninguna / No aplica`` — 4,242 rows, the most common specific cause of all —
appears under nearly every cause there is. Read the pair, and do not reconstruct
either half from the other.

``CAUSAESP`` is also gone from 2020 onwards. 27,624 of the 45,914 fires, three in
five, have a cause and no specific cause, and their rows in this table have
:attr:`ConaforFireCause.specific_cause` ``NULL``. That ``NULL`` is part of the
natural key, which is why the uniqueness is enforced by a partial index rather
than a plain ``UNIQUE`` constraint — see :attr:`ConaforFireCause.__table_args__`.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy import text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model import Base

#: Canonical Spanish for each ``CAUSA`` CONAFOR publishes, keyed by the
#: :func:`~src.providers.mexico_conafor.normalise` d published string.
#:
#: Sixty-four published spellings fold to forty-three normalised ones and those
#: map onto the twenty causes below. Every judgement in this table is a judgement,
#: and the three worth defending:
#:
#: * *Tormenta eléctrica* and *descargas eléctricas* map to **Naturales**. They
#:   are the only natural cause the archive names, they are what CONAFOR itself
#:   calls *naturales* from 2012 on, and the fourteen rows that use the older
#:   wording are all in 2011.
#: * *No determinadas*, *desconocida* and *desconocidos* map to **Desconocidas**.
#:   One state of knowledge, three ways of writing it.
#: * *Fogatas de paseantes* — hikers' campfires — maps to **Fogatas** here and
#:   survives in full in :data:`SPECIFIC_CAUSE_TRANSLATIONS`, where it is also a
#:   published ``CAUSAESP``. Twenty-six rows write it in the ``CAUSA`` column
#:   instead; folding it into *Fogatas* is what keeps those twenty-six with the
#:   3,763 they belong to.
#:
#: What this table does **not** do is reconcile categories CONAFOR *renamed*. Two
#: pairs are the same act under two administrative names in different years, and
#: both are kept apart:
#:
#: * *Intencional* (2013-2019 and 2023) and *Actividades ilícitas* (2020-2022,
#:   and no other year). The second is the broader phrase — it can cover fires set
#:   to clear illicit crops, which the archive files separately as *Cultivos
#:   ilícitos* — so merging them on a guess would be a worse error than reporting
#:   them apart. The consequence is that a fourteen-year series of either has a
#:   three-year hole of exact zeros in it; see
#:   :mod:`src.apps.statistics.wildfires.mexico_conafor.wildfire_causes`.
#: * *Actividades agropecuarias* (to 2017), which becomes *Actividades agrícolas*
#:   and *Actividades pecuarias* from 2018. A split rather than a rename, and
#:   collapsing the two back would throw away a distinction the provider started
#:   making.
#:
#: A published string not in this table gets no canonical form and is reported, on
#: the same argument as an untranslated ICNF cause.
CAUSE_NORMALISATIONS = {
    "fogatas": "Fogatas",
    "fogata": "Fogatas",
    "fogatas de paseantes": "Fogatas",
    "fumadores": "Fumadores",
    "intencional": "Intencional",
    "rencillas": "Intencional",
    "litigios": "Intencional",
    "actividades ilicitas": "Actividades ilícitas",
    "cultivos ilicitos": "Cultivos ilícitos",
    "actividades agricolas": "Actividades agrícolas",
    "actividades pecuarias": "Actividades pecuarias",
    "actividades agropecuarias": "Actividades agropecuarias",
    "agropecuario": "Actividades agropecuarias",
    "actividad agropecuario": "Actividades agropecuarias",
    "actividad agropecuarias": "Actividades agropecuarias",
    "actividad agropecuaria,": "Actividades agropecuarias",
    "actividad agropecuaria, chamuzca de nopal.": "Actividades agropecuarias",
    "actividades forestales": "Residuos de aprovechamiento forestal",
    "residuos de aprovechamiento forestal": "Residuos de aprovechamiento forestal",
    "quema de basureros": "Quema de basureros",
    "quema de basurero irregular": "Quema de basureros",
    "cazadores": "Cazadores",
    "cazadores furtivos": "Cazadores",
    "naturales": "Naturales",
    "descargas electricas": "Naturales",
    "tormenta electrica": "Naturales",
    "tormenta electrica.": "Naturales",
    "tormenta elcetrica": "Naturales",
    "transportes": "Transportes",
    "limpias de derecho de via": "Limpias de derecho de vía",
    "limpia de derechos de via": "Limpias de derecho de vía",
    # The 2021 layer writes this one mojibake — 'Limpias de derecho de vÃƒÂ­a' —
    # and the fold cannot undo that, deliberately (see the module docstring of
    # src.providers.mexico_conafor). A corrupted spelling is still a published
    # spelling, and this table's job is to map published spellings onto canonical
    # ones, so it gets an entry like any other rather than losing its fire out of
    # the series. One row.
    "limpias de derecho de vaƒa\xada": "Limpias de derecho de vía",
    "festividades y rituales": "Festividades y rituales",
    "otras actividades productivas": "Otras actividades productivas",
    "otras actividades productivas (ind., maq., etc.)": "Otras actividades productivas",
    "otras causas": "Otras causas",
    "desconocidas": "Desconocidas",
    "desconocida": "Desconocidas",
    "desconocidos": "Desconocidas",
    "no determinadas": "Desconocidas",
}

#: English for each canonical cause in :data:`CAUSE_NORMALISATIONS`, keyed by the
#: canonical Spanish rather than by any published string.
#:
#: Two are worth spelling out. *Limpias de derecho de vía* is the clearing of a
#: right of way — roadside, railway or power-line verges — by burning, which is a
#: distinct administrative category from general land clearance and not the same
#: thing as *Transportes*, a fire started by a vehicle. And *Cazadores* is
#: hunters, whose fires are set to drive game rather than by accident, which is
#: why the English says hunting and not *hunters' negligence*.
CAUSE_TRANSLATIONS = {
    "Fogatas": "Campfires",
    "Fumadores": "Smokers",
    "Intencional": "Intentional",
    "Actividades ilícitas": "Illicit activities",
    "Cultivos ilícitos": "Illicit crops",
    "Actividades agrícolas": "Agricultural activities",
    "Actividades pecuarias": "Livestock activities",
    "Actividades agropecuarias": "Agricultural and livestock activities",
    "Residuos de aprovechamiento forestal": "Forest harvesting residues",
    "Quema de basureros": "Rubbish dump burning",
    "Cazadores": "Hunting",
    "Naturales": "Natural",
    "Transportes": "Transport",
    "Limpias de derecho de vía": "Right-of-way clearing",
    "Festividades y rituales": "Festivities and rituals",
    "Otras actividades productivas": "Other productive activities",
    "Otras causas": "Other causes",
    "Desconocidas": "Unknown",
}

#: English for each ``CAUSAESP`` the archive publishes, keyed by the
#: :func:`~src.providers.mexico_conafor.normalise` d published string.
#:
#: Fifty-four published spellings, on 17,185 fires of 2010 and 2012-2019 and on no
#: fire after that. Kept keyed on the normalised string rather than on a canonical
#: Spanish, because the specific cause needs no reconciliation: its variation is
#: case and accents, which the fold already removes, and there is no synonymy left
#: after it.
#:
#: *Chamuzca de nopal* — singeing prickly pear to burn the spines off before
#: feeding it to cattle — is not in here: it appears only inside a ``CAUSA``
#: string, ``'Actividad Agropecuaria, Chamuzca de Nopal.'``, which is one fire.
SPECIFIC_CAUSE_TRANSLATIONS = {
    "ninguna / no aplica": "None / not applicable",
    "ninguna/ no aplica": "None / not applicable",
    "no aplica": "None / not applicable",
    "quema para preparacion de siembra": "Burning to prepare for sowing",
    "quema para pastoreo": "Burning for grazing",
    "quema para desmontar": "Burning to clear land",
    "quema de canaveral": "Sugar cane field burning",
    "quema de desechos forestales": "Forest waste burning",
    "cambio de uso de suelo": "Change of land use",
    "vandalismo": "Vandalism",
    "rencillas": "Feuds",
    "litigios": "Land disputes",
    "problemas ejidales": "Ejido disputes",
    "fogatas de paseantes": "Campfires of day trippers",
    "rayos": "Lightning",
    "descargas electricas": "Lightning",
    "erupciones volcanicas": "Volcanic eruptions",
    "lineas electricas": "Power lines",
    "uso de lineas electricas": "Power lines",
    "ferrocarril": "Railway",
    "accidente automovilistico": "Road accident",
    "industria": "Industry",
    "mineria (extraccion de materiales)": "Mining (extraction of materials)",
    "hornos de carbon": "Charcoal kilns",
    "horno de carbon": "Charcoal kilns",
    "carboneros": "Charcoal burners",
    "actividades apicolas": "Beekeeping",
    "agricultura": "Agriculture",
    "ganadero": "Livestock",
    "caza furtiva": "Poaching",
    "cultivos desconocidos": "Unidentified crops",
    "desarrollo turistico": "Tourist development",
    "urbanizacion": "Urbanisation",
    "similares": "Similar",
    "otras": "Other",
    "otros": "Other",
    "desconocidas": "Unknown",
}


class ConaforFireCause(Base):
    """One entry of the CONAFOR fire cause classification.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key, and what a fire's ``cause_id`` points
        at. A surrogate rather than the natural key because the natural key is the
        whole ``(cause, specific_cause)`` pair, one half of which is ``NULL`` on
        three fires in five, and repeating both strings on 45,914 fires to avoid a
        join would be a poor trade.
    cause : str
        The published ``CAUSA``, in Spanish, **as published**. Sixty-four values
        across the fourteen layers, trailing newlines and mojibake included: this
        is the string a file actually contains, and a row has to be checkable
        against it. See :attr:`cause_normalised` for the one to group by.
    cause_normalised : str or None
        The canonical Spanish for :attr:`cause`, from
        :data:`CAUSE_NORMALISATIONS`. **Not unique** — putting the sixty-four
        spellings onto twenty causes is the entire point of it — and indexed,
        because grouping by it is what this table exists for. ``None`` for a
        published string not in that table, which means CONAFOR has typed
        something new.
    cause_en : str or None
        English for :attr:`cause_normalised`, from :data:`CAUSE_TRANSLATIONS`.
        ``None`` under the same circumstances, and also whenever
        :attr:`cause_normalised` is ``None``: there is nothing to translate from.
    specific_cause : str or None
        The published ``CAUSAESP`` (``CAUSA_ESPE`` in 2012), in Spanish, as
        published. ``None`` for the 27,624 fires of 2011 and 2020-2023, whose
        layers do not publish the attribute at all.
    specific_cause_en : str or None
        English for :attr:`specific_cause`, from
        :data:`SPECIFIC_CAUSE_TRANSLATIONS`, looked up on the normalised form.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    The table has no ``data_provider_id``. Every other model in the project carries
    one because the same real-world thing is published by several agencies; this
    classification is CONAFOR's own and is meaningless outside it, which the table
    name already says. :mod:`src.providers.portugal_icnf.fire_cause` and
    :mod:`src.providers.spain_egif.fire_cause` are the same shape for the same
    reason.

    The rows are not seeded from a fixed list. The importer inserts whatever
    ``(cause, specific_cause)`` pairs the layer it is reading actually contains —
    176 of them across the published archive — so a cause CONAFOR invents appears
    the first time a fire uses it, with no canonical form and no English and with a
    warning, until the tables above are extended.
    """

    __tablename__ = "conafor_fire_cause"

    #: Uniqueness of the ``(cause, specific_cause)`` pair, enforced by **two
    #: partial unique indexes** rather than one ``UNIQUE`` constraint.
    #:
    #: A plain ``UNIQUE (cause, specific_cause)`` would not do the job. In SQL two
    #: ``NULL``\s are not equal, so it would happily admit ``('Fogatas', NULL)``
    #: twice — and ``NULL`` is not an edge case here, it is what 2011 and 2020-2023
    #: publish, three fires in five. ``uq_conafor_fire_cause_pair`` covers the
    #: pairs that have both halves and ``uq_conafor_fire_cause_cause_only`` the
    #: ones that have only a cause, and between them every row is covered exactly
    #: once.
    #:
    #: PostgreSQL 15 could express this as ``UNIQUE NULLS NOT DISTINCT``. Two
    #: partial indexes say the same thing, are what SQLAlchemy can render without a
    #: dialect-specific construct, and do not tie the schema to a server version.
    __table_args__ = (
        Index("uq_conafor_fire_cause_pair", "cause", "specific_cause", unique=True,
              postgresql_where=text("specific_cause IS NOT NULL")),
        Index("uq_conafor_fire_cause_cause_only", "cause", unique=True,
              postgresql_where=text("specific_cause IS NULL")),
        Index("ix_conafor_fire_cause_cause_normalised", "cause_normalised"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cause: Mapped[str] = mapped_column(String, nullable=False)
    cause_normalised: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_en: Mapped[str | None] = mapped_column(String, nullable=True)
    specific_cause: Mapped[str | None] = mapped_column(String, nullable=True)
    specific_cause_en: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (f"ConaforFireCause(id={self.id!r}, cause={self.cause!r}, "
                f"specific_cause={self.specific_cause!r})")
