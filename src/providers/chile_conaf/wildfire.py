#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAF wildfire model (Chile).

A fire report from CONAF's seasonal archive. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the resolved start and end
instants; this model adds the season it was filed in, the office's own number and
name, who filed it, where it burnt administratively, where and in what it started,
its cause, the fourteen published areas, and the link to the point it was filed at.

See :mod:`src.providers.chile_conaf` for the dataset itself — the season, the
missing dates, the coordinate triple, the two cause taxonomies and the dirt.

The perimeter is always ``NULL``
---------------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every one of
these rows and always will be. CONAF publishes the report as a point; the polygons
are a different product, they are
:class:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire`, and
writing one onto a row whose ``data_provider_id`` names the report archive would
make the provenance a lie.

The two are related instead by
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.conaf_wildfire_id`,
which the binder fills in — the direction
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id` and
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id`
also point in: perimeter to report, because the perimeter archive is the sparse
one.

Which instant the fire starts at
---------------------------------

There is one published start, not NBAC's two, and for half the archive there is
none at all. :attr:`date_time_precision` records how much of the stored instant is
real:

:data:`~src.providers.chile_conaf.PRECISION_MINUTE`
    ``start_date_time`` is the published instant.
:data:`~src.providers.chile_conaf.PRECISION_DAY`
    ``start_date_time`` is local midnight of the published day.
:data:`~src.providers.chile_conaf.PRECISION_SEASON`
    ``start_date_time`` is 1 July of :attr:`season_start_year`, local — a placeholder,
    because nothing was published.

.. warning::

   49,470 of the 95,868 fires are :data:`~src.providers.chile_conaf.
   PRECISION_SEASON`, which means their start is a placeholder and their
   ``start_date_time`` is 1 July at midnight. Filtering on it, grouping by month,
   or subtracting it from an end date gives an answer for the other half of the
   archive and nonsense for this one.

Fourteen areas, in three groups and a total
---------------------------------------------

CONAF reports burnt area by what burnt, and the published columns nest:

.. code-block:: text

   area_ha_pine_0_10 + area_ha_pine_11_17 + area_ha_pine_18_plus
     + area_ha_eucalyptus + area_ha_other_plantation   = area_ha_plantation
   area_ha_native_forest + area_ha_scrub + area_ha_grassland
                                                       = area_ha_vegetation
   area_ha_agricultural + area_ha_debris               = area_ha_other
   area_ha_plantation + area_ha_vegetation + area_ha_other = area_ha_total

The pine bands are **stand ages in years**, not tree sizes: 0-10, 11-17 and 18 or
more. The split exists because a young *Pinus radiata* plantation and a mature one
are different fuels and different money, and CONAF has reported them apart since
the archive begins.

The arithmetic holds on 90,128 of the 95,831 readable rows and drifts on the rest,
almost all of them in 2010-2011, 2011-2012 and 2015-2016.
:attr:`area_totals_agree` records which is which, so a report can say how much of
its total it is standing on rather than discovering the gap by subtraction.

Every column is stored **as published**, drift included. Nothing is recomputed from
the parts: :attr:`area_ha_total` is the office's own figure for the fire, and where
it disagrees with its own components that disagreement is the datum.

Nothing here is a key
----------------------

:attr:`number` is the office's running number and repeats within a season, even
inside one región. :attr:`name` is a place name and repeats freely. Neither is
constrained, and neither should be joined on outside the binder, which uses them
together with the season and corroborates them spatially.
"""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.wildfire import Wildfire
from src.providers.chile_conaf import DATE_TIME_PRECISIONS
from src.providers.chile_conaf import REPORTERS
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.ignition import ConafIgnition


class ConafWildfire(Wildfire):
    """A Chilean fire as CONAF's seasonal archive reports it.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the Chilean ones are stored here, in
    ``conaf_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE identifier,
        shared with the parent row.
    ignition_id : int
        Foreign key to the :class:`~src.providers.chile_conaf.ignition.ConafIgnition`
        this report was filed at. ``NOT NULL``, unlike
        :attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.ignition_id`,
        because every one of the 95,868 published features carries a geometry —
        checked, with no exceptions. It is a constraint the data supports, so it is
        stated.
    ignition : ConafIgnition
        The point this report was filed at.
    season : str
        The published ``TEMPORADA``, as published: ``"2010-2011"``. ``NOT NULL``.
        Seven features publish something else — six blanks and one ``"2023-2025"``
        — and get the season their archive is for, which the import counts.
    season_start_year : int
        First year of :attr:`season`, ``2010`` for ``"2010-2011"``. ``NOT NULL`` and
        indexed: the unit the archives, the imports and the reports are all
        organised by.
    number : int or None
        The published ``NUMERO_REG``. **Not a key** — see the module docstring.
    name : str or None
        The published ``NOM_INCEN``, the name the office gave the fire, usually the
        *fundo* or the place it started at.
    reporter : str or None
        The published ``AMBITO``, folded to
        :data:`~src.providers.chile_conaf.REPORTER_CONAF` or
        :data:`~src.providers.chile_conaf.REPORTER_COMPANY` and constrained to
        those two. Who filed the report, not who owned the land. Indexed, because
        a count by it is a count of two different reporting systems.
    region, province, commune : str or None
        The published ``REGION``, ``PROVINCIA`` and ``COMUNA``, as published.
        ``None`` on every fire of six of the fifteen mainland seasons, which
        publish the codes and not the names.
    region_code, province_code, commune_code : str or None
        The published ``CODREG``, ``CODPROV`` and ``CODCOM``, zero-padded to two,
        three and five digits by
        :func:`~src.providers.chile_conaf.admin_code`. The codes nest, so a
        comuna's first three digits are its provincia and its first two its región.

        These are CONAF's own administrative fields and are **not** the resolved
        :attr:`~src.data_model.wildfire.Wildfire.admin_boundary_id`, which comes
        from a spatial join against real boundaries and is what a cross-provider
        query uses.
    start_place : str or None
        The published ``INICIO_C``, where the fire started: *camino principal*,
        *sendero*, *casa o refugio*. As published, and dirty — 425 distinct
        strings, case and accents varying by season.
    fuel : str or None
        The published ``COMBUS_I``, what was burning when it started: *pastizal*,
        *matorral*, *desechos*. As published; 42 distinct strings.
    cause_id : int or None
        Foreign key to :class:`~src.providers.chile_conaf.fire_cause.ConafFireCause`
        — the ``(CAUSA_GENE, CAUSA_ESPE)`` pair this fire published. Indexed.

        ``None`` for the 840 fires that publish neither half.
    cause : ConafFireCause or None
        The fire's cause classification. **Group by its ``cause_normalised``**, not
        by its code; see :mod:`src.providers.chile_conaf.fire_cause`.
    date_time_precision : str
        How much of :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is
        real: one of
        :data:`~src.providers.chile_conaf.DATE_TIME_PRECISIONS`. ``NOT NULL``,
        constrained and indexed — a report that does not filter on it is
        reporting on 1 July.
    area_ha_pine_0_10 : decimal.Decimal or None
        Published ``PINO_00_10``: pine plantation aged 0 to 10 years, in hectares.
    area_ha_pine_11_17 : decimal.Decimal or None
        Published ``PINO_11_17``: pine plantation aged 11 to 17 years.
    area_ha_pine_18_plus : decimal.Decimal or None
        Published ``PINO18_MAS``: pine plantation aged 18 years or more.
    area_ha_eucalyptus : decimal.Decimal or None
        Published ``EUCALIPTO``.
    area_ha_other_plantation : decimal.Decimal or None
        Published ``OTRAS_PLAN``: plantation that is neither pine nor eucalyptus.
    area_ha_plantation : decimal.Decimal or None
        Published ``TOTAL_PLAN``, the office's own subtotal of the five above.
    area_ha_native_forest : decimal.Decimal or None
        Published ``ARBOLADO``: native forest.
    area_ha_scrub : decimal.Decimal or None
        Published ``MATORRAL``.
    area_ha_grassland : decimal.Decimal or None
        Published ``PASTIZAL``. The largest single category in the archive.
    area_ha_vegetation : decimal.Decimal or None
        Published ``TOTAL_VEG``, the subtotal of the three above — the natural
        vegetation, as against the plantations.
    area_ha_agricultural : decimal.Decimal or None
        Published ``AGRICOLA``: crops.
    area_ha_debris : decimal.Decimal or None
        Published ``DESECHOS``: slash, logging debris and rubbish.
    area_ha_other : decimal.Decimal or None
        Published ``TOTAL_OTRA``, the subtotal of the two above.
    area_ha_total : decimal.Decimal or None
        Published ``SUPERFICIE``, the office's figure for the whole fire. Stored as
        published; see :attr:`area_totals_agree`.

        Not the same measurement as
        :attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.area_ha_mapped`,
        which is traced from a polygon.
    area_totals_agree : bool
        Whether :attr:`area_ha_plantation`, :attr:`area_ha_vegetation` and
        :attr:`area_ha_other` sum to :attr:`area_ha_total`, to within a hundredth
        of a hectare. ``True`` on 90,128 of the 95,831 readable rows.

        Stored rather than derived because deriving it means summing four nullable
        numerics in every query that cares, and because it is the cheapest possible
        answer to "how much of this total can I stand on".
    created_at, updated_at : datetime.datetime
        Inherited from :class:`~src.data_model.wildfire.Wildfire`.

    Notes
    -----
    There is no unique constraint and no natural key. See the module docstring.
    """

    __tablename__ = "conaf_wildfire"

    __table_args__ = (
        CheckConstraint(
            "reporter IS NULL OR reporter IN ("
            + ", ".join(f"'{value}'" for value in REPORTERS) + ")",
            name="ck_conaf_wildfire_reporter",
        ),
        CheckConstraint(
            "date_time_precision IN ("
            + ", ".join(f"'{value}'" for value in DATE_TIME_PRECISIONS) + ")",
            name="ck_conaf_wildfire_date_time_precision",
        ),
        CheckConstraint("area_ha_total IS NULL OR area_ha_total >= 0",
                        name="ck_conaf_wildfire_area_ha_total"),
        Index("ix_conaf_wildfire_season_start_year", "season_start_year"),
        Index("ix_conaf_wildfire_number", "number"),
        Index("ix_conaf_wildfire_reporter", "reporter"),
        Index("ix_conaf_wildfire_cause_id", "cause_id"),
        Index("ix_conaf_wildfire_date_time_precision", "date_time_precision"),
        Index("ix_conaf_wildfire_ignition_id", "ignition_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    ignition_id: Mapped[int] = mapped_column(ForeignKey(ConafIgnition.id), nullable=False)
    season: Mapped[str] = mapped_column(String, nullable=False)
    season_start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    reporter: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    province: Mapped[str | None] = mapped_column(String, nullable=True)
    commune: Mapped[str | None] = mapped_column(String, nullable=True)
    region_code: Mapped[str | None] = mapped_column(String, nullable=True)
    province_code: Mapped[str | None] = mapped_column(String, nullable=True)
    commune_code: Mapped[str | None] = mapped_column(String, nullable=True)
    start_place: Mapped[str | None] = mapped_column(String, nullable=True)
    fuel: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_id: Mapped[int | None] = mapped_column(
        ForeignKey(ConafFireCause.id), nullable=True
    )
    date_time_precision: Mapped[str] = mapped_column(String, nullable=False)
    area_ha_pine_0_10: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_pine_11_17: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_pine_18_plus: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_eucalyptus: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_other_plantation: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_plantation: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_native_forest: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_scrub: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_grassland: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_vegetation: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_agricultural: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_debris: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_other: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_total: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_totals_agree: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    ignition: Mapped[ConafIgnition] = relationship(foreign_keys=[ignition_id])
    cause: Mapped[ConafFireCause | None] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "conaf_wildfire",
    }

    def __repr__(self) -> str:
        return (f"ConafWildfire(id={self.id!r}, season={self.season!r}, "
                f"number={self.number!r}, name={self.name!r})")
