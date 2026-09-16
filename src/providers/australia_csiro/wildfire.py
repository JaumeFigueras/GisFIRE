#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSIRO wildfire model.

A mapped burnt area from the Australian historical bushfire extents. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the resolved start and end
instants and the perimeter in EPSG:4326; this model adds which feature class the row
came from, the published identifiers, where it burnt administratively, what kind of
fire it was, what caused it, how it was mapped, the three published dates and the two
published measurements.

See :mod:`src.providers.australia_csiro` for the dataset itself — the two feature
classes, the 48% that is deliberate burning, the sentinel identifiers, the 1 January
cluster and why there is no second geometry column.

One row is one published polygon
---------------------------------

**Nothing is merged.** Each of the 347,834 published features becomes one row, keyed
by ``(source_layer, object_id)``, and every stored value is that feature's own: its
geometry as published, its ``area_ha``, its ``perim_km``, its attributes.

This is a decision and not an oversight, and it was taken after trying the
alternative. A burn really is published as many patches — Victoria's 705270 is 3,566
features of one day — and grouping them on
``(source_layer, state_code, fire_id, ignition_date)`` looks obvious until the result
is measured:

* **23.4% of the merged groups spanned more than 10 km**, 15.8% more than 25 km and
  6.6% more than 100 km;
* the worst joined two Western Australian features **2,403 km apart**, sharing the
  ``fire_id`` ``23`` on 2010-11-24;
* the widest groups are all Western Australian and all carry small numbers — ``23``,
  ``21``, ``001``, ``1``, ``4`` — which are district sequence numbers reused across
  the state, placeholders as surely as the ``'999'`` in
  :data:`~src.providers.australia_csiro.FIRE_ID_SENTINELS` but harder to spot.

A fire can of course have several fronts; it cannot have one on either side of
Western Australia. Since no published field distinguishes a real fire number from a
reused one, **the published unit of publication is the only unit this table can
honestly store**, and reassembling fires is left to whoever can bring a rule to it —
which is a query, or another application, over data that has not already been merged.
Merging is the one operation an import cannot undo.

What follows from that
-----------------------

* :attr:`fire_id` is **not a key** and there is no unique constraint on it in any
  combination. Fires do share it, legitimately and illegitimately.
* :attr:`area_ha` and :attr:`perim_km` are the published figures for **this polygon**,
  unsummed and unreconciled — a fire published as fifty patches has fifty rows, each
  carrying its own fiftieth.
* A count of rows is a count of **mapped polygons**, not of fires. There are more
  rows than there were fires in Australia, and no column in this table says by how
  many.

Nothing here is a wildfire by default
--------------------------------------

:attr:`fire_type` separates the 85,336 bushfires from the 166,048 prescribed burns
and the 93,960 unknowns. It is ``NOT NULL`` and constrained, and it is the column
every cross-provider query has to remember — see the warning in
:mod:`src.providers.australia_csiro`. ``v_csiro_bushfire`` is the view that has
already applied it.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.wildfire import Wildfire
from src.providers.australia_csiro import DATE_SOURCES
from src.providers.australia_csiro import DATE_TIME_PRECISIONS
from src.providers.australia_csiro import FIRE_CAUSES
from src.providers.australia_csiro import FIRE_TYPES
from src.providers.australia_csiro import SOURCE_LAYERS
from src.providers.australia_csiro import STATE_CODES


class CsiroWildfire(Wildfire):
    """An Australian mapped burnt area.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the Australian ones are stored here, in
    ``csiro_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE identifier,
        shared with the parent row.
    source_layer : str
        Which feature class of the geodatabase this row came from, one of
        :data:`~src.providers.australia_csiro.SOURCE_LAYERS`. Constrained and
        indexed: it is what an import replaces, the two classes being published and
        versioned separately.
    object_id : int
        The feature's published ``OBJECTID``, and the row's identity. Unique with
        :attr:`source_layer`, one row being one published feature.

        It is provenance and a replacement key, not a fire number — the agencies
        never see it. For the fire number, such as it is, see :attr:`fire_id`.
    year : int
        The calendar year of
        :attr:`~src.data_model.wildfire.Wildfire.start_date_time` as the import
        resolved it — not a published attribute, the geodatabase having no year
        column.

        ``NOT NULL`` and indexed because it is **what an import replaces**: the
        archive arrives as one 860 MB geodatabase and is read a year at a time, one
        transaction each, so a year is the unit that is deleted and rewritten. The
        same job :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.year` does
        for Canada, where the archive is published a year at a time to begin with.

    fire_id : str or None
        The published ``fire_id``, verbatim, sentinels included.

        **Not unique and not a key**, in any combination of columns. 145,694 Western
        Australian features publish ``'999'``, every Queensland feature publishes
        nothing, and 10.5% of the national class is null. Indexed, because a lookup
        by agency fire number is worth having where the number is real.

        .. warning::

           Grouping by it does not give fires. Checking
           :attr:`fire_id_is_sentinel` first is necessary and **not sufficient**:
           the numbers that survive that test include Western Australian district
           sequence numbers reused across the state, which put fires 2,400 km apart
           under one value. See the module docstring.
    fire_id_is_sentinel : bool
        Whether :attr:`fire_id` is a placeholder — null, blank or one of
        :data:`~src.providers.australia_csiro.FIRE_ID_SENTINELS` — rather than an
        identifier. True for 186,632 of the 345,345 national features (145,694
        published as ``'999'``, 4,592 as ``'0'``, 36,341 with nothing at all and a
        handful blank) and for none of the Northern Territory ones.

        Stored rather than derived, for the reason
        :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.crosses_admin` is:
        the test involves a vocabulary that can change, and a query should not have
        to know it.
    fire_name : str or None
        The published ``fire_name``. Absent on half the national class; in the
        Northern Territory class it is a street address.
    state_published : str
        The ``state`` attribute exactly as published, in whichever of the two
        classes' spellings — ``WA (Western Australia)`` or ``WA``.
    state_code : str
        The normalised state or territory, one of
        :data:`~src.providers.australia_csiro.STATE_CODES`. Constrained and indexed:
        it is the fallback the time zone is resolved against, and what every report
        groups on.
    agency : str or None
        The agency credited with the mapping, as published: 23 of them in the
        national class, 5 in the Northern Territory one. Not normalised and not
        constrained — it is a list of organisations, and organisations are renamed.
    fire_type_published : str or None
        The ``fire_type`` attribute as published, both spellings of *prescribed
        burn* preserved.
    fire_type : str
        The normalised type, one of
        :data:`~src.providers.australia_csiro.FIRE_TYPES`. Constrained, indexed and
        ``NOT NULL``.

        **The most important column in this table.** Half of this dataset is
        deliberate burning; see the module docstring and
        :mod:`src.providers.australia_csiro`.
    cause_published : str or None
        The ``ignition_cause`` attribute as published, including the 274
        ``NOT DETERMINED``, the 57 ``OTHER`` and the one ``WF - unknown``.
    cause : str or None
        The normalised cause, one of
        :data:`~src.providers.australia_csiro.FIRE_CAUSES`, or ``None``.
        Constrained.

        ``None`` means either that no cause was published — 78.2% of the national
        class — or that the published one has no canonical form here, which is
        ``OTHER`` and nothing else. The two are told apart by looking at
        :attr:`cause_published`, which is why it is kept.
    capture_method_published : str or None
        The ``capt_method`` attribute as published.
    capture_method : str or None
        The normalised sensor or method the polygon was drawn from — the analogue of
        :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.ba_source`.
        Deliberately **not** constrained: see
        :data:`~src.providers.australia_csiro.CAPTURE_METHODS`.
    ignition_date : datetime.date or None
        The published ``ignition_date``, as published — epoch sentinels, 1898 and
        all. ``None`` for the 331 features that publish none.
    extinguish_date : datetime.date or None
        The published ``extinguish_date``, as published, including the ones in the
        year 200 and the year 2525. ``None`` for 85% of the national class.
    capture_date : datetime.date or None
        When the imagery or the survey behind the polygon was taken. Provenance of
        the *mapping*, not of the fire, exactly as
        :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.capture_date` is.

        Published as ``YYYYMMDD`` text by the national class — and by only 1,976 of
        its features, all in New South Wales and the ACT — and as a date column by
        the Northern Territory class, where it is 2025-09-17 for every row and is
        the date the class was compiled rather than a per-fire observation.
    date_source : str
        Which published date
        :attr:`~src.data_model.wildfire.Wildfire.start_date_time` was resolved from,
        one of :data:`~src.providers.australia_csiro.DATE_SOURCES`. Constrained.
    date_time_precision : str
        How much of that instant the provider published:
        :data:`~src.providers.australia_csiro.PRECISION_DAY`, always. Constrained,
        and kept as a column so that a query across this archive and the Portuguese,
        Canadian or Chilean ones is one query.
    dates_plausible : bool
        Whether the published dates survive
        :func:`~src.providers.australia_csiro.dates_are_plausible` — no epoch
        sentinel, nothing outside 1900-2100, no end before its start. False on 514
        of the published features, 0.15%.

        A flag and not a fix: the dates are stored as published either way. Filter
        on it before computing anything about durations or trends, in the same way
        :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_totals_agree`
        is filtered on.
    area_ha : float or None
        The published ``area_ha`` of **this polygon**, in whole hectares as
        published. Nothing is summed and nothing is reconciled with the geometry:
        it is the agency's measurement of its own patch, and 77,069 features are 0
        because their patch rounded to nothing.
    perim_km : float or None
        The published ``perim_km`` of this polygon, on the same terms.

    Notes
    -----
    There is no second geometry column. The published CRS is EPSG:4283, geographic
    degrees 1.8 m from the EPSG:4326 the parent row stores, so the copy the
    Portuguese, Canadian, Catalan and Andalusian models keep would cost gigabytes
    over 155.8 million vertices and answer no question the parent cannot. See
    :data:`~src.providers.australia_csiro.SOURCE_SRID`.

    There is no ignition either. This dataset publishes polygons and no ignition
    points, so there is no ``csiro_ignition`` and
    :attr:`~src.data_model.wildfire.Wildfire.perimeter` is never ``NULL``.
    """

    __tablename__ = "csiro_wildfire"

    __table_args__ = (
        UniqueConstraint("source_layer", "object_id",
                         name="uq_csiro_wildfire_source_layer_object_id"),
        CheckConstraint(
            "source_layer IN ("
            + ", ".join(f"'{layer}'" for layer in SOURCE_LAYERS)
            + ")",
            name="ck_csiro_wildfire_source_layer",
        ),
        CheckConstraint(
            "state_code IN ("
            + ", ".join(f"'{code}'" for code in STATE_CODES)
            + ")",
            name="ck_csiro_wildfire_state_code",
        ),
        CheckConstraint(
            "fire_type IN ("
            + ", ".join(f"'{fire_type}'" for fire_type in FIRE_TYPES)
            + ")",
            name="ck_csiro_wildfire_fire_type",
        ),
        CheckConstraint(
            "cause IS NULL OR cause IN ("
            + ", ".join(f"'{cause}'" for cause in FIRE_CAUSES)
            + ")",
            name="ck_csiro_wildfire_cause",
        ),
        CheckConstraint(
            "date_source IN ("
            + ", ".join(f"'{source}'" for source in DATE_SOURCES)
            + ")",
            name="ck_csiro_wildfire_date_source",
        ),
        CheckConstraint(
            "date_time_precision IN ("
            + ", ".join(f"'{precision}'" for precision in DATE_TIME_PRECISIONS)
            + ")",
            name="ck_csiro_wildfire_date_time_precision",
        ),
        # A missing fire number is a missing fire number: whatever else counts as a
        # placeholder, NULL always does.
        CheckConstraint(
            "fire_id IS NOT NULL OR fire_id_is_sentinel",
            name="ck_csiro_wildfire_null_fire_id_is_sentinel",
        ),
        # There is deliberately **no** unique constraint over (source_layer,
        # state_code, fire_id, ignition_date). An earlier revision had one, to state
        # that those four columns identify a fire; they do not. See the module
        # docstring: the numbers that pass the sentinel test include Western
        # Australian district sequence numbers reused across the state, and the
        # constraint would have to reject features the archive really publishes.
        Index("ix_csiro_wildfire_year", "year"),
        Index("ix_csiro_wildfire_fire_id", "fire_id"),
        Index("ix_csiro_wildfire_state_code", "state_code"),
        Index("ix_csiro_wildfire_fire_type", "fire_type"),
        Index("ix_csiro_wildfire_source_layer", "source_layer"),
        Index("ix_csiro_wildfire_ignition_date", "ignition_date"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)

    source_layer: Mapped[str] = mapped_column(String, nullable=False)
    object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    fire_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fire_id_is_sentinel: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                      default=False)
    fire_name: Mapped[str | None] = mapped_column(String, nullable=True)

    state_published: Mapped[str] = mapped_column(String, nullable=False)
    state_code: Mapped[str] = mapped_column(String, nullable=False)
    agency: Mapped[str | None] = mapped_column(String, nullable=True)

    fire_type_published: Mapped[str | None] = mapped_column(String, nullable=True)
    fire_type: Mapped[str] = mapped_column(String, nullable=False)

    cause_published: Mapped[str | None] = mapped_column(String, nullable=True)
    cause: Mapped[str | None] = mapped_column(String, nullable=True)

    capture_method_published: Mapped[str | None] = mapped_column(String, nullable=True)
    capture_method: Mapped[str | None] = mapped_column(String, nullable=True)

    ignition_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    extinguish_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    capture_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    date_source: Mapped[str] = mapped_column(String, nullable=False)
    date_time_precision: Mapped[str] = mapped_column(String, nullable=False)
    dates_plausible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    perim_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "csiro_wildfire",
    }

    def __repr__(self) -> str:
        return (f"CsiroWildfire(id={self.id!r}, source_layer={self.source_layer!r}, "
                f"object_id={self.object_id!r}, fire_type={self.fire_type!r})")
