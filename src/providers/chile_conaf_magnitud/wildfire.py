#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAF *incendio de magnitud* wildfire model (Chile).

A mapped burnt-area polygon from CONAF's large-fire archive. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the resolved start and end
instants and the perimeter in EPSG:4326; this model adds the season, the office's
number and name, where it burnt administratively, the published cause, the two
areas, the polygon in the CRS it was published in, and the link to the report for
the same fire.

See :mod:`src.providers.chile_conaf_magnitud` for the dataset — the 200-hectare
threshold, the dissolve, the invalid geometries and the binding evidence.

The perimeter is stored twice, on purpose
------------------------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is the reprojection to
EPSG:4326, which is what makes a Chilean fire comparable with a GWIS, ICNF,
Canadian or Mexican one and what every cross-provider query uses.
:attr:`perimeter_utm19s` and :attr:`perimeter_utm12s` are the polygon on the grid
it was published on.

The argument is the ICNF, DARPA, REDIAM and NBAC one exactly: a projected grid in
metres is what an area or a distance computed on it means something in, and the
same computation on EPSG:4326 is on degrees and means nothing without a geodesic
function. Reprojecting is neither free nor lossless, so a query that needs the grid
needs it stored.

There are two of them rather than one because Chile has no single national
projected CRS — the reason
:class:`~src.providers.chile_conaf.ignition.ConafIgnition` has two point columns.
:attr:`perimeter_utm19s` holds 742 fires and :attr:`perimeter_utm12s` holds the one
Easter Island fire, and a ``CHECK`` requires exactly one.

One row is one fire, and several polygons
------------------------------------------

There is no ``GID`` here, and a fire mapped in pieces is published as several
features sharing a season and a name. The import dissolves them and records what
the union cannot say by itself:

* :attr:`part_count` — how many published features became this row. 1 for 724 of
  the 743 fires; ``668 - CANIHUAL VII`` of 2018-2019 is 13.
* :attr:`area_ha_mapped` — the area of the **dissolved** geometry.
* :attr:`area_ha_published` — the sum of the parts' own ``SUPERFICIE``.

The two differ whenever the parts overlap, and they do overlap: ``37_TIL TIL`` of
2016-2017 is six features each declaring the same 327.50 ha. Summing gives 1,965
hectares for a 328-hectare fire, which is why the mapped area comes from the union
and the published sum is kept beside it rather than instead of it.

.. warning::

   Neither is the fire's *reported* burnt area. That is
   :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_ha_total` on the
   report this row binds to — a different measurement, filed by an office counting
   affected vegetation by type rather than traced from a map. They routinely
   disagree, and neither corrects the other.

Which instant the fire starts at
---------------------------------

The same three-valued :attr:`date_time_precision` the reports use, for the same
reason: three archives — 2015-2016, 2017-2018 and 2019-2020, 116 features — publish
no ``FECHA_INI``, and 313 features publish no end.

Binding to the report
----------------------

:attr:`conaf_wildfire_id` points at the
:class:`~src.providers.chile_conaf.wildfire.ConafWildfire` for the same fire, and
:attr:`match_method` says which rule found it. Both are ``NULL`` until
:mod:`src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires` has
run, and a ``CHECK`` keeps them ``NULL`` or filled together — an unexplained link
is not a link this project will store.

The direction is perimeter to report, matching
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id`: the
perimeter archive is the sparse one, so it is the one that carries the pointer.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Float
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
from src.providers.chile_conaf import SOURCE_SRID_EASTER
from src.providers.chile_conaf import SOURCE_SRID_MAINLAND
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.wildfire import ConafWildfire
from src.providers.chile_conaf_magnitud import MATCH_METHODS


class ConafMagnitudWildfire(Wildfire):
    """A Chilean fire as CONAF's large-fire archive maps it.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the ones specific to this archive are stored here,
    in ``conaf_magnitud_wildfire``, whose primary key is also a foreign key to the
    parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`.
    season : str
        The published ``TEMPORADA``, as published. One feature publishes
        ``"2023-2025"``, which is a typing error and gets its archive's season.
    season_start_year : int
        First year of :attr:`season`. ``NOT NULL`` and indexed.
    number : int or None
        The office's running number for the fire, from the published
        ``NUMERO_REG`` where the archive has that column and from the ``'402 - '``
        prefix on ``NOM_INCEN`` where it does not — see
        :func:`~src.providers.chile_conaf_magnitud.published_number`. 596 of the
        781 published features carry one.

        The strongest thing the binder has, and still **not a key**.
    name : str or None
        The published ``NOM_INCEN`` with any number prefix removed, so that this
        and :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.name` are the
        same string for the same fire.
    region, province, commune : str or None
        The published ``REGION``, ``PROVINCIA`` and ``COMUNA``, as published, and
        often blank in this archive.
    region_code, province_code, commune_code : str or None
        The published codes, zero-padded by
        :func:`~src.providers.chile_conaf.admin_code`.
    cause_published : str or None
        The published ``CAUSA``, byte for byte.

        One column where the reports have two, used inconsistently: sometimes a
        *causa específica* with its code, sometimes a *causa general* in prose,
        sometimes the null token ``'0'``. 180 distinct strings over 781 features.
        Kept as published because it is what the file says.
    cause_id : int or None
        Foreign key to :class:`~src.providers.chile_conaf.fire_cause.ConafFireCause`,
        resolved from :attr:`cause_published` where that string matches one the
        report archive also uses. ``None`` where it does not — in which case the
        bound report's cause is the one to use.
    area_ha_mapped : decimal.Decimal or None
        Area of the **dissolved** polygon, in hectares. See the module docstring.
    area_ha_published : decimal.Decimal or None
        Sum of the published ``SUPERFICIE`` of the features that were dissolved
        into this row. Equal to :attr:`area_ha_mapped` for the 724 single-feature
        fires and larger wherever the parts overlapped.
    part_count : int
        How many published features were dissolved into this row. ``CHECK >= 1``.
    perimeter_utm19s : geoalchemy2.elements.WKBElement or None
        The dissolved polygon on
        :data:`~src.providers.chile_conaf.SOURCE_SRID_MAINLAND`, for a mainland
        fire. 742 rows.
    perimeter_utm12s : geoalchemy2.elements.WKBElement or None
        The dissolved polygon on
        :data:`~src.providers.chile_conaf.SOURCE_SRID_EASTER`. One row.
    date_time_precision : str
        How much of :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is
        real: one of
        :data:`~src.providers.chile_conaf.DATE_TIME_PRECISIONS`.
    conaf_wildfire_id : int or None
        Foreign key to the
        :class:`~src.providers.chile_conaf.wildfire.ConafWildfire` report for the
        same fire, or ``None`` while unbound. Indexed.
    conaf_wildfire : ConafWildfire or None
        The report for the same fire.
    match_method : str or None
        Which rule bound it: one of
        :data:`~src.providers.chile_conaf_magnitud.MATCH_METHODS`. ``NULL`` exactly
        when :attr:`conaf_wildfire_id` is, enforced by a ``CHECK``.

        The vocabulary itself is constrained by a migration of its own, added once
        the binder existed.
    match_confidence : float or None
        :data:`~src.providers.chile_conaf_magnitud.MATCH_METHOD_CONFIDENCE` for
        :attr:`match_method`. Ordinal, not a probability.
    matched_at : datetime.datetime or None
        When the binding was made. Timezone-aware.
    created_at, updated_at : datetime.datetime
        Inherited from :class:`~src.data_model.wildfire.Wildfire`.

    Notes
    -----
    No unique constraint on :attr:`number`, :attr:`name` or the pair. This archive
    has no key either, and after the dissolve the ``(season_start_year, name)``
    grouping is a decision the import made rather than one CONAF published.

    :attr:`conaf_wildfire_id` is **not** unique, deliberately, even though the
    binder refuses to bind two perimeters to one report. A unique constraint would
    make a future archive that genuinely re-maps a fire in two products fail the
    import rather than be reported; the binder's own refusal is where that rule
    belongs, because it can explain itself.
    """

    __tablename__ = "conaf_magnitud_wildfire"

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(perimeter_utm19s, perimeter_utm12s) = 1",
            name="ck_conaf_magnitud_wildfire_one_grid",
        ),
        CheckConstraint(
            "date_time_precision IN ("
            + ", ".join(f"'{value}'" for value in DATE_TIME_PRECISIONS) + ")",
            name="ck_conaf_magnitud_wildfire_date_time_precision",
        ),
        CheckConstraint("part_count >= 1",
                        name="ck_conaf_magnitud_wildfire_part_count"),
        CheckConstraint("area_ha_mapped IS NULL OR area_ha_mapped >= 0",
                        name="ck_conaf_magnitud_wildfire_area_ha_mapped"),
        #: A link and its explanation arrive together or not at all. The binder is
        #: the only thing that writes either, and a row that says which fire it is
        #: without saying how it knows is not evidence of anything.
        CheckConstraint(
            "(conaf_wildfire_id IS NULL) = (match_method IS NULL)",
            name="ck_conaf_magnitud_wildfire_match_method_with_link",
        ),
        #: The vocabulary itself, added to the schema by a revision of its own once
        #: the binder existed — see ``2c9f4e7b81a6``. The literal list lives there
        #: too; this is the model's copy, and the two are kept in step by
        #: ``test_the_match_method_constraint_accepts_every_conaf_method``.
        CheckConstraint(
            "match_method IS NULL OR match_method IN ("
            + ", ".join(f"'{method}'" for method in MATCH_METHODS) + ")",
            name="ck_conaf_magnitud_wildfire_match_method",
        ),
        Index("ix_conaf_magnitud_wildfire_season_start_year", "season_start_year"),
        Index("ix_conaf_magnitud_wildfire_number", "number"),
        Index("ix_conaf_magnitud_wildfire_cause_id", "cause_id"),
        Index("ix_conaf_magnitud_wildfire_conaf_wildfire_id", "conaf_wildfire_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    season: Mapped[str] = mapped_column(String, nullable=False)
    season_start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    province: Mapped[str | None] = mapped_column(String, nullable=True)
    commune: Mapped[str | None] = mapped_column(String, nullable=True)
    region_code: Mapped[str | None] = mapped_column(String, nullable=True)
    province_code: Mapped[str | None] = mapped_column(String, nullable=True)
    commune_code: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_published: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_id: Mapped[int | None] = mapped_column(
        ForeignKey(ConafFireCause.id), nullable=True
    )
    area_ha_mapped: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    area_ha_published: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    date_time_precision: Mapped[str] = mapped_column(String, nullable=False)
    perimeter_utm19s: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID_MAINLAND), nullable=True
    )
    perimeter_utm12s: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID_EASTER), nullable=True
    )
    conaf_wildfire_id: Mapped[int | None] = mapped_column(
        ForeignKey(ConafWildfire.id), nullable=True
    )
    match_method: Mapped[str | None] = mapped_column(String, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    conaf_wildfire: Mapped[ConafWildfire | None] = relationship(
        foreign_keys=[conaf_wildfire_id]
    )
    cause: Mapped[ConafFireCause | None] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "conaf_magnitud_wildfire",
    }

    def __repr__(self) -> str:
        return (f"ConafMagnitudWildfire(id={self.id!r}, season={self.season!r}, "
                f"number={self.number!r}, name={self.name!r})")
