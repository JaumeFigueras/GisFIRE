#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAF fire cause model (Chile).

CONAF classifies why every fire started in two published attributes: ``CAUSA_GENE``,
the *causa general*, and ``CAUSA_ESPE``, the *causa específica*, both present in
every one of the twenty-three report layers. The published files contain 110 and
500 distinct strings, which become a few hundred stored classifications once the
null tokens are folded to ``NULL`` — one row for each ``(cause, specific_cause)``
pair the archive really contains, on the same argument as
:mod:`src.providers.mexico_conafor.fire_cause`.

Here there is a second reason, and it is much stronger than CONAFOR's.

The taxonomy was renumbered, and the codes were reused
--------------------------------------------------------

CONAF publishes a code with the name — ``'1.7. Tránsito de personas, vehículos o
aeronaves'`` — and **changed what the codes mean in 2023-2024**. Reading the same
code across the break gives two different causes:

.. code-block:: text

   code   to 2022-2023                          from 2023-2024
   ----   -----------------------------------   -----------------------------------
   1.1    Faenas forestales                     Faenas forestales
   1.2    Faenas agrícolas y pecuarias          Faenas agrícolas y pecuarias
   1.3    Confección/extracción productos …     Actividades al aire libre …
   1.4    Actividades recreativas               Vías férreas
   1.5    Operaciones en vías férreas           Actividades de control y extinción …
   1.6    Actividades extinción incendios …     Parcelaciones, edificaciones …
   1.7    Tránsito de personas, vehículos …     Originados por desplazamiento …
   1.8    Quema de desechos                     Otras quemas
   1.9    Accidentes eléctricos                 Líneas eléctricas
   1.10   Otras actividades                     Otras causas
   4.1    Incendios de causa desconocida        Faenas forestales
   5.1    —                                     Incendios de causa indeterminada

.. danger::

   **Never group on the code alone.** ``4.1`` is *incendios de causa desconocida*
   before the break and *faenas forestales* after it: a fifteen-season series
   grouped on it silently merges every fire whose cause was unknown with every fire
   started by forestry work.

   Group on :attr:`ConafFireCause.cause_normalised`. If a query really needs the
   code, it must pair it with :attr:`ConafFireCause.scheme`, which is what says
   which numbering the code belongs to.

Worse, the 2023-2024 and 2024-2025 layers write **both** numberings. ``1.1`` and
``4.1`` in those files are the same cause — *faenas forestales*, 83 fires and 492 —
and so are ``1.8`` and ``4.8``, ``1.9`` and ``4.9``, and every other pair. The
group number wobbles inside a single published file; only the name holds still. So
the name is what this table reconciles on, and
:data:`CAUSE_NORMALISATIONS` is keyed on it.

The 2016-2017 layer publishes only the code
---------------------------------------------

``CAUSA_GENE`` is ``'01.07'``, ``'02.01'``, ``'04.01'`` — a zero-padded code and no
name at all, on all 5,234 fires. They are resolved here rather than left blank,
because the resolution is checkable: the layer's own ``CAUSA_ESPE`` still carries
the old-scheme ``'1.7.1.'``-style codes, and the two agree feature for feature —
1,962 fires with ``'01.07'`` and 1,962 with a ``1.7.x`` specific cause, 1,687 with
``'02.01'`` and 1,687 with ``2.1.x``, and so on for every code in the layer.

:data:`PRE_2023_CODE_NAMES` is that resolution, and it is applied to the pre-2023
numbering only — the layer is nine seasons before the break.

The specific cause is stored, not translated
----------------------------------------------

:attr:`ConafFireCause.specific_cause` keeps the published string and
:attr:`ConafFireCause.specific_cause_code` the code in front of it, and there is no
English for it, which is a departure from
:mod:`src.providers.mexico_conafor.fire_cause` and needs saying.

CONAFOR's ``CAUSAESP`` is a vocabulary: fifty-four short terms, each naming a thing,
each translatable in three words. CONAF's is not. It is five hundred descriptive
sentences — *'1.9.2. Contacto de material vegetal (ej. Corteza de eucalipto) o no
vegetal (ej. Pizarreños), desprendido y desplazado por acción del viento, con el
tendido eléctrico'* — which are prose written to be read, not labels to be joined
on. Hand-translating five hundred of those would be five hundred opportunities to
put a wrong English sentence beside a right Spanish one, and nothing in GisFIRE
would group by the result.

The code in front is what a query can use, and it is stored parsed out for exactly
that. The English stops at the general cause, where there are twenty-three terms and
they really are terms.

The strings are dirty, and the fold does not finish the job
-------------------------------------------------------------

:func:`~src.providers.chile_conaf.normalise` gets ``CAUSA_GENE`` from 110 published
spellings to 43 normalised ones, which is most of the case, accent and soft-hyphen
variation. What it leaves is the mojibake — ``'TRANSEONTES'``, ``'CALDA DE RAYO'``,
``'ELACTRICO'``, ``'PIRAMANO'`` — where a letter was lost in a bad decode and
cannot be guessed back by rule.

Those are reconciled by name in :data:`CAUSE_NORMALISATIONS`, one entry each, for
the reason CONAFOR's table gives: a corrupted spelling is still a published
spelling, and this table's job is to map published spellings onto canonical ones.
"""

from __future__ import annotations

import datetime
import re

from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy import text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model import Base
from src.providers.chile_conaf import is_missing
from src.providers.chile_conaf import normalise

#: The published code belongs to the numbering CONAF used to 2022-2023.
SCHEME_PRE_2023 = "pre_2023"

#: The published code belongs to the numbering CONAF adopted in 2023-2024.
SCHEME_POST_2023 = "post_2023"

#: Every value :attr:`ConafFireCause.scheme` takes. Constrained on the column.
#:
#: ``NULL`` is the third state and is not in here: it means *the published pair does
#: not settle which numbering this is*, which is the honest answer for a row with no
#: code at all and for the four causes whose name is the same in both numberings.
SCHEMES = (SCHEME_PRE_2023, SCHEME_POST_2023)

#: Canonical Spanish for each *causa general* CONAF publishes, keyed by the
#: :func:`~src.providers.chile_conaf.normalise` d published string with any leading
#: code stripped.
#:
#: 110 published spellings fold to 43 normalised ones and those map onto the
#: twenty-three causes below. Most entries are pure spelling: a comma that appears
#: in some seasons and not others, or one of the mis-decoded forms the archive is
#: littered with.
#:
#: What this table does **not** do is reconcile the categories CONAF *renamed* at
#: the 2023-2024 break. Ten pairs are a pre-2023 cause and its post-2023 successor,
#: and every one of them is kept apart, because in most of the ten the successor is
#: visibly a different size:
#:
#: * *Accidentes eléctricos* (any electrical accident) becomes *Líneas eléctricas*
#:   (the power line only) — narrower.
#: * *Quema de desechos* (burning rubbish) becomes *Otras quemas* (any other
#:   burning) — broader.
#: * *Actividades extinción incendios forestales, incendios estructurales u otros*
#:   becomes *Actividades de control y extinción de incendios forestales*, dropping
#:   structural fires — narrower.
#: * *Confección y/o extracción productos secundarios del bosque* becomes
#:   *Producción y/o extracción de productos y/o derivados del bosque* and moves
#:   from slot 1.3 to slot 4.11.
#:
#: Merging those on a guess would be a worse error than reporting them apart, which
#: is the judgement :mod:`src.providers.mexico_conafor.fire_cause` makes for
#: *Intencional* and *Actividades ilícitas*. The consequence is the same: a series
#: of any one of the ten has a break at 2023-2024. :data:`SCHEME_SUCCESSORS` is the
#: bridge for a reader who wants to cross it deliberately.
#:
#: The four causes that really are unchanged — *faenas forestales*, *faenas
#: agrícolas y pecuarias*, *incendios intencionales* and *incendios naturales* —
#: keep one canonical name across the whole archive, because CONAF kept one name.
CAUSE_NORMALISATIONS = {
    # ── Stable across the break ────────────────────────────────────────────────
    "incendios intencionales": "Incendios intencionales",
    "faenas forestales": "Faenas forestales",
    "faenas agricolas y pecuarias": "Faenas agrícolas y pecuarias",
    "incendios naturales": "Incendios naturales",

    # ── Pre-2023 numbering ─────────────────────────────────────────────────────
    "transito de personas vehiculos o aeronaves":
        "Tránsito de personas, vehículos o aeronaves",
    "transito de personas, vehiculos o aeronaves":
        "Tránsito de personas, vehículos o aeronaves",
    "quema de desechos": "Quema de desechos",
    "actividades recreativas": "Actividades recreativas",
    "accidentes electricos": "Accidentes eléctricos",
    "confeccion y/o extraccion productos secundarios del bosque":
        "Confección y/o extracción productos secundarios del bosque",
    "actividades extincion incendios forestales incendios estructurales u otros":
        "Actividades extinción incendios forestales, incendios estructurales u otros",
    "actividades extincion incendios forestales, incendios estructurales u otros":
        "Actividades extinción incendios forestales, incendios estructurales u otros",
    "operaciones en vias ferreas": "Operaciones en vías férreas",
    "otras actividades": "Otras actividades",
    "incendios de causa desconocida": "Incendios de causa desconocida",

    # ── Post-2023 numbering ────────────────────────────────────────────────────
    # The published spelling of these three drops the commas that the canonical
    # form — which is CONAF's own, from the taxonomy rather than from a data file —
    # carries. Both are keys, so that folding a canonical form and looking it up
    # gives it back rather than raising, and so that a season that starts writing
    # the commas reconciles on the day it appears.
    "originados por desplazamiento de personas vehiculos o aeronaves":
        "Originados por desplazamiento de personas, vehículos o aeronaves",
    "originados por desplazamiento de personas, vehiculos o aeronaves":
        "Originados por desplazamiento de personas, vehículos o aeronaves",
    "otras quemas": "Otras quemas",
    "actividades al aire libre (camping excursiones caza pesca otros)":
        "Actividades al aire libre (camping, excursiones, caza, pesca, otros)",
    "actividades al aire libre (camping, excursiones, caza, pesca, otros)":
        "Actividades al aire libre (camping, excursiones, caza, pesca, otros)",
    "lineas electricas": "Líneas eléctricas",
    "produccion y/o extraccion de productos y/o derivados del bosque":
        "Producción y/o extracción de productos y/o derivados del bosque",
    "actividades de control y extincion de incendios forestales":
        "Actividades de control y extinción de incendios forestales",
    "vias ferreas": "Vías férreas",
    "parcelaciones edificaciones residenciales industriales u otras en zonas rurales o de interfaz":
        "Parcelaciones, edificaciones residenciales, industriales u otras en zonas "
        "rurales o de interfaz",
    "parcelaciones, edificaciones residenciales, industriales u otras en zonas rurales o de interfaz":
        "Parcelaciones, edificaciones residenciales, industriales u otras en zonas "
        "rurales o de interfaz",
    "otras causas": "Otras causas",
    "incendios de causa indeterminada": "Incendios de causa indeterminada",

    # ── Prose spellings only the perimeter archive publishes ───────────────────
    # :mod:`src.providers.chile_conaf_magnitud` writes its cause by hand rather
    # than picking it from the taxonomy, so these arrive in the singular, or with
    # the specific cause bolted on after a dash. They are here rather than in a
    # table of their own because they are what they look like: further published
    # spellings of causes this table already knows, which is exactly what it is
    # for. They also settle which half of the taxonomy an uncoded string is —
    # see :func:`resolve_published_cause`.
    "incendio intencional": "Incendios intencionales",
    "incendios intencionales - conflictos territoriales": "Incendios intencionales",
    "incendio de causa desconocida": "Incendios de causa desconocida",
    "causa desconocida": "Incendios de causa desconocida",
    "caida de rayo- incendios naturales": "Incendios naturales",
}

#: The pre-2023 *causa general* each code named, for the 2016-2017 layer, which
#: publishes ``'01.07'`` and no name.
#:
#: Keyed on the code with its leading zeros stripped, so ``'01.07'`` and ``'1.7'``
#: are one entry. Applied **only** where :attr:`ConafFireCause.scheme` is
#: :data:`SCHEME_PRE_2023`; applying it to a post-2023 code would produce exactly
#: the error the module docstring warns about.
#:
#: The mapping is read off the seasons that publish both a code and a name, and it
#: is corroborated by 2016-2017's own ``CAUSA_ESPE``, which still carries the
#: matching ``1.7.x``-style specific codes on the same features.
PRE_2023_CODE_NAMES = {
    "1.1": "Faenas forestales",
    "1.2": "Faenas agrícolas y pecuarias",
    "1.3": "Confección y/o extracción productos secundarios del bosque",
    "1.4": "Actividades recreativas",
    "1.5": "Operaciones en vías férreas",
    "1.6": "Actividades extinción incendios forestales, incendios estructurales u otros",
    "1.7": "Tránsito de personas, vehículos o aeronaves",
    "1.8": "Quema de desechos",
    "1.9": "Accidentes eléctricos",
    "1.10": "Otras actividades",
    "2.1": "Incendios intencionales",
    "3.1": "Incendios naturales",
    "4.1": "Incendios de causa desconocida",
}

#: The post-2023 *causa general* each code names, in both of the numberings the
#: 2023-2024 and 2024-2025 layers use.
#:
#: ``1.x`` and ``4.x`` are the same list because those layers really do publish the
#: same cause under both — see the module docstring. Used to settle
#: :attr:`ConafFireCause.scheme` for a coded row, not to invent a name for one that
#: has none: every post-2023 row publishes its name.
POST_2023_CODE_NAMES = {
    "1.1": "Faenas forestales",
    "1.2": "Faenas agrícolas y pecuarias",
    "1.3": "Actividades al aire libre (camping, excursiones, caza, pesca, otros)",
    "1.4": "Vías férreas",
    "1.5": "Actividades de control y extinción de incendios forestales",
    "1.6": "Parcelaciones, edificaciones residenciales, industriales u otras en zonas "
           "rurales o de interfaz",
    "1.7": "Originados por desplazamiento de personas, vehículos o aeronaves",
    "1.8": "Otras quemas",
    "1.9": "Líneas eléctricas",
    "1.10": "Otras causas",
    "2.1": "Incendios intencionales",
    "3.1": "Incendios naturales",
    "4.1": "Faenas forestales",
    "4.2": "Faenas agrícolas y pecuarias",
    "4.3": "Actividades al aire libre (camping, excursiones, caza, pesca, otros)",
    "4.4": "Vías férreas",
    "4.5": "Actividades de control y extinción de incendios forestales",
    "4.6": "Parcelaciones, edificaciones residenciales, industriales u otras en zonas "
           "rurales o de interfaz",
    "4.7": "Originados por desplazamiento de personas, vehículos o aeronaves",
    "4.8": "Otras quemas",
    "4.9": "Líneas eléctricas",
    "4.10": "Otras causas",
    "4.11": "Producción y/o extracción de productos y/o derivados del bosque",
    "5.1": "Incendios de causa indeterminada",
}

#: Which post-2023 canonical cause took over each pre-2023 one's slot in the
#: taxonomy.
#:
#: **This is a bridge, not an equality.** The two sides are not the same category —
#: that is exactly why :data:`CAUSE_NORMALISATIONS` keeps them apart — and joining a
#: series across one of these pairs asserts a continuity CONAF did not publish. It
#: is here so that a report which wants to draw the fifteen seasons as one line can
#: do so *deliberately*, saying which bridge it used, rather than by accidentally
#: grouping on a reused code.
#:
#: :mod:`src.apps.statistics.wildfires.chile_conaf.wildfire_causes` offers it behind
#: an explicit option and reports the break either way.
#:
#: *Parcelaciones, edificaciones residenciales…* has no entry: it is a category the
#: post-2023 taxonomy invented, with 642 fires and no predecessor.
SCHEME_SUCCESSORS = {
    "Tránsito de personas, vehículos o aeronaves":
        "Originados por desplazamiento de personas, vehículos o aeronaves",
    "Quema de desechos": "Otras quemas",
    "Actividades recreativas":
        "Actividades al aire libre (camping, excursiones, caza, pesca, otros)",
    "Accidentes eléctricos": "Líneas eléctricas",
    "Confección y/o extracción productos secundarios del bosque":
        "Producción y/o extracción de productos y/o derivados del bosque",
    "Actividades extinción incendios forestales, incendios estructurales u otros":
        "Actividades de control y extinción de incendios forestales",
    "Operaciones en vías férreas": "Vías férreas",
    "Otras actividades": "Otras causas",
    "Incendios de causa desconocida": "Incendios de causa indeterminada",
}

#: English for each canonical cause in :data:`CAUSE_NORMALISATIONS`, keyed by the
#: canonical Spanish rather than by any published string.
#:
#: Three are worth spelling out. *Faenas* is work in the field — forestry or farm
#: operations — and not *tasks*. *Parcelaciones* is the subdivision of rural land
#: into smallholdings and second homes, which in Chile is the wildland-urban
#: interface problem under its administrative name, so the English says so rather
#: than saying *parcelling*. And *Tránsito de personas, vehículos o aeronaves* is
#: fire caused by people simply passing through — its dominant specific cause is
#: *uso de fuego por transeúntes*, 11,278 fires — not fire caused by traffic
#: accidents.
CAUSE_TRANSLATIONS = {
    "Incendios intencionales": "Intentional fires",
    "Faenas forestales": "Forestry operations",
    "Faenas agrícolas y pecuarias": "Agricultural and livestock operations",
    "Incendios naturales": "Natural fires",
    "Tránsito de personas, vehículos o aeronaves":
        "Movement of people, vehicles or aircraft",
    "Quema de desechos": "Burning of waste",
    "Actividades recreativas": "Recreational activities",
    "Accidentes eléctricos": "Electrical accidents",
    "Confección y/o extracción productos secundarios del bosque":
        "Gathering and processing of non-timber forest products",
    "Actividades extinción incendios forestales, incendios estructurales u otros":
        "Wildfire, structural and other fire suppression activities",
    "Operaciones en vías férreas": "Railway operations",
    "Otras actividades": "Other activities",
    "Incendios de causa desconocida": "Fires of unknown cause",
    "Originados por desplazamiento de personas, vehículos o aeronaves":
        "Caused by the movement of people, vehicles or aircraft",
    "Otras quemas": "Other burning",
    "Actividades al aire libre (camping, excursiones, caza, pesca, otros)":
        "Outdoor activities (camping, hiking, hunting, fishing, other)",
    "Líneas eléctricas": "Power lines",
    "Producción y/o extracción de productos y/o derivados del bosque":
        "Production and extraction of forest products and by-products",
    "Actividades de control y extinción de incendios forestales":
        "Wildfire control and suppression activities",
    "Vías férreas": "Railways",
    "Parcelaciones, edificaciones residenciales, industriales u otras en zonas "
    "rurales o de interfaz":
        "Rural subdivisions, residential, industrial and other building in rural or "
        "interface areas",
    "Otras causas": "Other causes",
    "Incendios de causa indeterminada": "Fires of indeterminate cause",
}


class ConafFireCause(Base):
    """One entry of the CONAF fire cause classification (Chile).

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key, and what a fire's ``cause_id`` points
        at. A surrogate rather than the natural key because the natural key is the
        whole ``(cause, specific_cause)`` pair, either half of which can be
        ``NULL``.
    cause : str
        The published ``CAUSA_GENE``, in Spanish, **as published** — leading code,
        doubled spaces, mojibake and all. This is the string a file actually
        contains and a row has to be checkable against it. See
        :attr:`cause_normalised` for the one to group by.
    cause_code : str or None
        The code in front of :attr:`cause`, leading zeros stripped: ``'1.7'`` for
        both ``'1.7. Tránsito…'`` and 2016-2017's bare ``'01.07'``. ``None`` where
        the published string carries no code, which is most seasons before
        2019-2020.

        .. danger::

           Meaningless without :attr:`scheme`. See the module docstring.
    cause_normalised : str or None
        The canonical Spanish for :attr:`cause`, from
        :data:`CAUSE_NORMALISATIONS` — or, for a row that publishes only a code,
        from :data:`PRE_2023_CODE_NAMES`. **Not unique**: putting 110 published
        spellings onto twenty-three causes is the whole point of it, and it is
        indexed because grouping by it is what this table exists for.

        ``None`` where CONAF has published something this table does not know,
        which the import reports rather than guessing at.
    cause_en : str or None
        English for :attr:`cause_normalised`, from :data:`CAUSE_TRANSLATIONS`.
        ``None`` whenever :attr:`cause_normalised` is: there is nothing to
        translate from.
    specific_cause : str or None
        The published ``CAUSA_ESPE``, in Spanish, as published. Five hundred
        distinct descriptive sentences; see the module docstring for why there is
        no English beside it.
    specific_cause_code : str or None
        The code in front of it — ``'1.7.1'``, ``'4.8.2'`` — leading zeros
        stripped. The part of the specific cause a query can group on. Indexed, and
        subject to the same :attr:`scheme` caveat as :attr:`cause_code`.
    scheme : str or None
        Which numbering :attr:`cause_code` and :attr:`specific_cause_code` belong
        to: :data:`SCHEME_PRE_2023`, :data:`SCHEME_POST_2023`, or ``None``.

        ``None`` means the published pair does not settle it — either the row
        carries no code, or its name is one of the four that CONAF kept unchanged
        across the break, in which case the code is ambiguous but harmless because
        the cause is the same either way.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    The table has no ``data_provider_id``, for the reason
    :class:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause` has none:
    this classification is CONAF's own and is meaningless outside it, which the
    table name already says.

    Both published products share it.
    :mod:`src.providers.chile_conaf_magnitud` publishes a single ``CAUSA`` column
    that sometimes holds a *causa específica* and sometimes a *causa general*, and
    its rows point here wherever the string matches one the reports use — see
    :attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.cause_id`.

    The rows are not seeded from a fixed list. The importer inserts whatever
    ``(cause, specific_cause)`` pairs the layer it is reading actually contains, so
    a cause CONAF invents appears the first time a fire uses it — with no canonical
    form, no English and a warning — until the tables above are extended.
    """

    __tablename__ = "conaf_fire_cause"

    #: Uniqueness of the ``(cause, specific_cause)`` pair, enforced by **three
    #: partial unique indexes** rather than one ``UNIQUE`` constraint.
    #:
    #: In SQL two ``NULL``\s are not equal, so a plain ``UNIQUE (cause,
    #: specific_cause)`` would happily admit the same pair twice whenever either
    #: half is ``NULL`` — and both halves really are ``NULL`` sometimes here, which
    #: is one more case than
    #: :class:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause` has to
    #: cover: 7,061 fires publish no ``CAUSA_GENE`` and 4,727 no ``CAUSA_ESPE``,
    #: and the two sets overlap.
    #:
    #: Three partial indexes cover the four combinations — both present, cause
    #: only, specific cause only — and between them every row is covered exactly
    #: once. The row with both ``NULL`` cannot be constrained by an index at all
    #: and is prevented by the ``CHECK`` instead: a classification that classifies
    #: nothing is not a row, it is the absence of one, and such a fire carries
    #: ``cause_id IS NULL``.
    __table_args__ = (
        Index("uq_conaf_fire_cause_pair", "cause", "specific_cause", unique=True,
              postgresql_where=text("cause IS NOT NULL AND specific_cause IS NOT NULL")),
        Index("uq_conaf_fire_cause_cause_only", "cause", unique=True,
              postgresql_where=text("cause IS NOT NULL AND specific_cause IS NULL")),
        Index("uq_conaf_fire_cause_specific_only", "specific_cause", unique=True,
              postgresql_where=text("cause IS NULL AND specific_cause IS NOT NULL")),
        Index("ix_conaf_fire_cause_cause_normalised", "cause_normalised"),
        Index("ix_conaf_fire_cause_specific_cause_code", "specific_cause_code"),
        CheckConstraint("cause IS NOT NULL OR specific_cause IS NOT NULL",
                        name="ck_conaf_fire_cause_not_empty"),
        CheckConstraint("scheme IS NULL OR scheme IN ('pre_2023', 'post_2023')",
                        name="ck_conaf_fire_cause_scheme"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cause: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_code: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_normalised: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_en: Mapped[str | None] = mapped_column(String, nullable=True)
    specific_cause: Mapped[str | None] = mapped_column(String, nullable=True)
    specific_cause_code: Mapped[str | None] = mapped_column(String, nullable=True)
    scheme: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return (f"ConafFireCause(id={self.id!r}, cause={self.cause!r}, "
                f"specific_cause={self.specific_cause!r})")


#: A published cause: an optional dotted code, then optionally a name.
#:
#: The separator between them is a full stop in most seasons (``'1.7. Tránsito…'``)
#: and a hyphen from 2023-2024 (``'4.1 - Faenas forestales'``). 2016-2017 publishes
#: the code with nothing after it.
_CODE_THEN_NAME = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\s*[.\-]?\s*(.*)$")


def split_code(published: str | None) -> tuple[str | None, str]:
    """Split a published cause string into its code and its name.

    Parameters
    ----------
    published : str or None
        A published ``CAUSA_GENE``, ``CAUSA_ESPE`` or ``CAUSA`` cell, as read.

    Returns
    -------
    tuple
        ``(code, name)``. *code* has its leading zeros stripped — ``'01.07'`` and
        ``'1.7.'`` both give ``'1.7'`` — or is ``None`` when the string does not
        start with one. *name* is the
        :func:`~src.providers.chile_conaf.normalise` d remainder, and is ``""``
        when there is nothing after the code.

    Notes
    -----
    Zero-stripping per component rather than on the whole string, so that
    2016-2017's ``'01.10'`` becomes ``'1.10'`` and not ``'1.1'`` — which would
    silently move *otras actividades* into *faenas forestales*.
    """
    text = normalise(published)
    if not text:
        return (None, "")
    match = _CODE_THEN_NAME.match(text)
    if match is None:
        return (None, text)
    code = ".".join(part.lstrip("0") or "0" for part in match.group(1).split("."))
    return (code, match.group(2).strip())


def resolve_cause(cause: str | None, specific_cause: str | None) -> dict[str, str | None]:
    """Turn a published ``(CAUSA_GENE, CAUSA_ESPE)`` pair into a stored row.

    Parameters
    ----------
    cause : str or None
        The published *causa general*, as read.
    specific_cause : str or None
        The published *causa específica*, as read.

    Returns
    -------
    dict
        The column values for a :class:`ConafFireCause`: ``cause``, ``cause_code``,
        ``cause_normalised``, ``cause_en``, ``specific_cause``,
        ``specific_cause_code`` and ``scheme``. The two published strings come back
        unchanged, or ``None`` where
        :func:`~src.providers.chile_conaf.is_missing` says the cell is empty.

    Notes
    -----
    The order the three unknowns are settled in matters, and it is:

    1. **Split** each half into a code and a name.
    2. **Decide the scheme** from the pair. A code whose post-2023 name is what was
       published is :data:`SCHEME_POST_2023`; a code whose pre-2023 name was
       published is :data:`SCHEME_PRE_2023`; a code with no name at all is
       pre-2023, because 2016-2017 is the only layer that publishes one and it is
       nine seasons before the break. A name that means the same in both leaves the
       scheme ``None`` — see :attr:`ConafFireCause.scheme`.
    3. **Name it.** From :data:`CAUSE_NORMALISATIONS` where a name was published;
       from :data:`PRE_2023_CODE_NAMES` where only a pre-2023 code was.

    Deciding the scheme before naming the cause is what stops 2016-2017's
    ``'04.01'`` being read as *faenas forestales*. Doing it the other way round
    would resolve every one of that layer's 220 unknown-cause fires into the wrong
    category.
    """
    published_cause = None if is_missing(cause) else cause
    published_specific = None if is_missing(specific_cause) else specific_cause

    cause_code, cause_name = split_code(published_cause)
    specific_code, _ = split_code(published_specific)

    scheme: str | None = None
    if cause_code is not None:
        if not cause_name:
            # A bare code, which only 2016-2017 publishes.
            scheme = SCHEME_PRE_2023
        else:
            canonical_here = CAUSE_NORMALISATIONS.get(cause_name)
            post = POST_2023_CODE_NAMES.get(cause_code)
            pre = PRE_2023_CODE_NAMES.get(cause_code)
            if canonical_here is not None and post == pre:
                # The code names the same cause in both numberings; the pair says
                # nothing about which one this is, and nothing depends on it.
                scheme = None
            elif canonical_here is not None and canonical_here == post:
                scheme = SCHEME_POST_2023
            elif canonical_here is not None and canonical_here == pre:
                scheme = SCHEME_PRE_2023

    canonical = CAUSE_NORMALISATIONS.get(cause_name) if cause_name else None
    if canonical is None and cause_code is not None and not cause_name:
        if scheme == SCHEME_PRE_2023:
            canonical = PRE_2023_CODE_NAMES.get(cause_code)

    return {
        "cause": published_cause,
        "cause_code": cause_code,
        "cause_normalised": canonical,
        "cause_en": CAUSE_TRANSLATIONS.get(canonical) if canonical else None,
        "specific_cause": published_specific,
        "specific_cause_code": specific_code,
        "scheme": scheme,
    }


def resolve_published_cause(published: str | None) -> dict[str, str | None] | None:
    """Turn the perimeter archive's single ``CAUSA`` into a stored row.

    Parameters
    ----------
    published : str or None
        The published ``CAUSA`` of an *incendio de magnitud*, as read.

    Returns
    -------
    dict or None
        Column values for a :class:`ConafFireCause`, or ``None`` where the cell is
        empty — including the null token ``'0'``, which thirteen perimeters publish.

    Notes
    -----
    :mod:`src.providers.chile_conaf_magnitud` publishes **one** cause column where
    the reports publish two, and uses it for both: ``'2.1.11. Otros intencionales no
    clasificados'`` is a *causa específica*, ``'Incendio Intencional'`` is a *causa
    general*, and both appear in the same archive.

    Which half a string is has to be decided before it can be stored, because the
    two go in different columns, and the code is what decides it: three components
    (``2.1.11``) is a specific cause and two (``2.1``) is a general one, which is how
    the taxonomy is built and how the report archive's own two columns are numbered.
    That settles 730 of the 781 published perimeters exactly.

    The other 51 publish **no code at all**, and there the rule is:
    :data:`CAUSE_NORMALISATIONS` recognises it, so it is a general cause; otherwise
    it is a specific one.

    That is the right way round, and measurably so. Of the 51, nineteen are
    ``'Uso de fuego por transeúntes'`` — which is *causa específica* ``1.7.1``, in
    the report archive's own words, 19,276 times — and the rest are
    ``'Rebrote de incendio anterior'`` (``1.6.1``), ``'Niños jugando con fuego'``
    (``1.4.5``), ``'Elaboración de carbón'`` (``1.3.1``) and a dozen more of the same
    shape. Only eleven are a general cause, and they are the eleven this table knows.

    Reading them all as general causes — which is what an earlier version of this
    function did — filed 44 specific causes in the ``cause`` column, where a query
    grouping general causes would count them beside *Incendios intencionales* as
    though they were peers of it.

    The reason the fallback can lean on :data:`CAUSE_NORMALISATIONS` at all is that
    the general causes are a closed vocabulary of twenty-three terms while the
    specific ones are five hundred sentences: recognising the short list and
    defaulting to the long one is a rule that stays right as CONAF writes new
    sentences, which it does in every archive.

    The resulting row has one half ``NULL``, which is what
    ``uq_conaf_fire_cause_cause_only`` and ``uq_conaf_fire_cause_specific_only``
    exist for: a perimeter's classification is a genuine entry in the catalogue and
    not a half-built version of a report's pair, and it must not be silently merged
    with one.
    """
    if is_missing(published):
        return None

    code, name = split_code(published)
    if code is not None:
        is_specific = code.count(".") == 2
    else:
        is_specific = name not in CAUSE_NORMALISATIONS
    if is_specific:
        return resolve_cause(None, published)
    return resolve_cause(published, None)
