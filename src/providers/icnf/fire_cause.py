#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICNF fire cause model.

The ICNF classifies the cause of every fire it dates, publishing three attributes
per feature: a numeric code (``Causa_Cod``), a broad type (``Causa_Tipo``) and a
description (``Causa_Desc``), the last two in Portuguese. Across the twelve years
that carry a cause — 18,955 classified fires in 2014-2025 — there are 5 types and
24 descriptions, and one classification is repeated on every fire that shares it.

That repetition is what makes this a lookup table rather than three columns on
every fire: a classification is a thing in its own right, not a property of one
fire.

The code is not the key
-----------------------

It would be the obvious one, and it does not work: the ICNF **has reused a code
for a different cause**. Four of them changed meaning in the 2025 layer, all in
the same direction — what used to be one description was split into a family:

.. code-block:: text

   126  2014-2024  Queimadas de sobrantes florestais ou agrícolas
        2025       Queimadas extensivas - Penetração em áreas de caça e margens dos rios_
   127  2014-2024  Queimadas de sobrantes florestais ou agrícolas
        2025       Queimadas extensivas - Limpeza de caminhos, acessos e instalações_
   128  2014-2023  Queimadas de sobrantes florestais ou agrícolas
        2025       Queimadas extensivas - Protecção contra incêndios_
   129  2014-2024  Queimadas de sobrantes florestais ou agrícolas
        2025       Queimadas extensivas - Outras_

So there are 97 codes but **101 classifications**, and the key is the whole triple.
A code with two meanings gets two rows, and a fire links to the one its own layer
published — which is the only way a 2019 fire and a 2025 fire with ``Causa_Cod``
127 can both be right.

Treating the code as unique would silently attach every 2025 fire in those four
codes to the 2014-2024 meaning. The published trailing underscores are kept, as
everything else is: they are in the data.

The Portuguese is stored as published
-------------------------------------

:attr:`IcnfFireCause.type` and :attr:`IcnfFireCause.description` are the
provider's own words, byte for byte. The English in :attr:`IcnfFireCause.type_en`
and :attr:`IcnfFireCause.description_en` is a translation *added* beside them,
never a replacement — a row can always be checked against the published file, and
a query can read either language.

The translations live in :data:`TYPE_TRANSLATIONS` and
:data:`DESCRIPTION_TRANSLATIONS` below and are applied by the importer. They are
a fixed table rather than anything computed: there are twenty-five strings in
total, they are terms of art in Portuguese forest-fire administration, and a
wrong guess would be indistinguishable from a right one to a reader who does not
speak the language. A string that is not in the table is stored with no
translation and reported, which is the only honest thing to do with a category a
later release invents.

The code is not a hierarchy you can parse either
------------------------------------------------

The codes look hierarchical — ``1xx`` negligent, ``2xx`` accidental, ``3xx`` and
``4xx`` intentional — and mostly are, but not reliably: ``312`` is published as
*Negligente* / *Acidentais - Outros*, in the middle of the intentional range. Nor
are they a fixed width: they are one to three digits through 2024 and the 2025
layer adds five-digit ones (``11001``, ``32115``, ``43102``). Read the type and
the description; do not derive them from the digits, and do not assume a shape.
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

#: English for each ``Causa_Tipo`` the ICNF publishes. Five values across
#: 2014-2025. ``Reacendimento`` is a fire that started again from an area already
#: burnt and declared out, which English fire services call a *rekindle*; it is a
#: cause in its own right here rather than a state of an earlier fire.
TYPE_TRANSLATIONS = {
    "Negligente": "Negligent",
    "Intencional": "Intentional",
    "Desconhecida": "Unknown",
    "Reacendimento": "Rekindle",
    "Natural": "Natural",
}

#: English for each ``Causa_Desc`` the ICNF publishes. Twenty-four values across
#: 2014-2025, each belonging to exactly one type. The last four arrived with the
#: 2025 layer, trailing underscores and all — those are in the published data and
#: are kept, because the key has to match what a file actually says.
#:
#: Two pairs are close enough to be worth spelling out. *Queimada* and *queima*
#: are different acts under Portuguese forest law, needing different permits —
#: the second is of material gathered into heaps, which is what *amontoados*
#: says and what the English keeps; translating both as plain "burning" would
#: merge two categories that between them account for 2,705 fires. *Imputáveis*
#: and *inimputáveis* are the legal distinction between an arsonist who can be
#: held criminally responsible and one who cannot, which is why the English says
#: so rather than reaching for a shorter word.
DESCRIPTION_TRANSLATIONS = {
    "Uso do fogo - Queima de lixo": "Use of fire - Rubbish burning",
    "Uso do fogo - Lançamento Foguetes": "Use of fire - Firework rockets",
    "Uso do fogo - Fogueiras": "Use of fire - Campfires",
    "Uso do fogo - Fumar": "Use of fire - Smoking",
    "Uso do fogo - Outros": "Use of fire - Other",
    "Queimadas de sobrantes florestais ou agrícolas":
        "Burning of forest or agricultural residues",
    "Queimas amontoados de sobrantes florestais ou agrícolas":
        "Burning of piled forest or agricultural residues",
    "Queimadas para gestão de pasto para gado": "Burning for livestock pasture management",
    "Acidentais - Transportes e Comunicações": "Accidental - Transport and communications",
    "Acidentais - Maquinaria": "Accidental - Machinery",
    "Acidentais - Outros": "Accidental - Other",
    "Estruturais - Caça e vida selvagem": "Structural - Hunting and wildlife",
    "Estruturais - Uso do solo": "Structural - Land use",
    "Estruturais - Outras": "Structural - Other",
    "Incendiarismo - Sem motivação conhecida": "Arson - No known motive",
    "Incendiarismo - Imputáveis": "Arson - Criminally responsible",
    "Incendiarismo - Inimputáveis": "Arson - Not criminally responsible",
    "Naturais": "Natural",
    "Indeterminadas": "Undetermined",
    "Reacendimentos": "Rekindles",
    "Queimadas extensivas - Limpeza de caminhos, acessos e instalações_":
        "Extensive burning - Clearing of paths, accesses and installations",
    "Queimadas extensivas - Penetração em áreas de caça e margens dos rios_":
        "Extensive burning - Access into hunting grounds and river banks",
    "Queimadas extensivas - Protecção contra incêndios_":
        "Extensive burning - Fire protection",
    "Queimadas extensivas - Outras_": "Extensive burning - Other",
}


class IcnfFireCause(Base):
    """One entry of the ICNF fire cause classification.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key, and what a fire's ``cause_id``
        points at. A surrogate rather than the natural key because the natural
        key is the whole ``(code, type, description)`` triple — see the module
        docstring — and repeating a hundred-character description on every one of
        18,955 fires to avoid a join would be a poor trade.
    code : str
        The published ``Causa_Cod``. **Not unique**: four codes name two different
        causes each. Indexed, because looking a classification up by the code the
        file printed is still the normal thing to do — just expect two rows for
        ``126``, ``127``, ``128`` and ``129``.

        Text, not a number: it is one to five digits, it is an identifier rather
        than a quantity, and nothing is gained by making ``60`` and ``060`` the
        same value.
    type : str
        The published ``Causa_Tipo``, in Portuguese, as published — one of
        ``Negligente``, ``Intencional``, ``Desconhecida``, ``Reacendimento`` or
        ``Natural``.
    type_en : str or None
        English for :attr:`type`, from :data:`TYPE_TRANSLATIONS`. ``None`` for a
        type not in that table, which means the provider has published a category
        that postdates it.
    description : str
        The published ``Causa_Desc``, in Portuguese, as published.
    description_en : str or None
        English for :attr:`description`, from :data:`DESCRIPTION_TRANSLATIONS`.
        ``None`` under the same circumstances as :attr:`type_en`.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    The table has no ``data_provider_id``. Every other model in the project
    carries one because the same real-world thing is published by several
    agencies; this classification is the ICNF's own and is meaningless outside
    it, which the table name already says.

    The rows are not seeded from a fixed list. The importer inserts whatever
    ``(code, type, description)`` triples the layer it is reading actually
    contains, so a classification the ICNF adds — a new code, or a new meaning
    for an old one — appears the first time a fire uses it, with no English and
    with a warning, until a translation is added above.
    """

    __tablename__ = "icnf_fire_cause"

    __table_args__ = (
        UniqueConstraint("code", "type", "description",
                         name="uq_icnf_fire_cause_code_type_description"),
        Index("ix_icnf_fire_cause_code", "code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    type_en: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    description_en: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"IcnfFireCause(id={self.id!r}, code={self.code!r}, type={self.type!r})"
