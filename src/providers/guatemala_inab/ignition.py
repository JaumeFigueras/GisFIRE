#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INAB ignition model.

Where a Guatemalan fire was reported to be. The generic
:class:`~src.data_model.ignition.Ignition` already holds the point and the
instant; this model adds the report's identifier, the coordinates as the operator
typed them, and the altitude.

See :mod:`src.providers.guatemala_inab` for the dataset and
:class:`~src.providers.guatemala_inab.wildfire.InabWildfire` for the report the
point belongs to.

Every record has a point
-------------------------

All 4,615 published records carry a geometry, which makes this the best-located
administrative fire statistic in the project: :mod:`src.providers.greece_ffa`
publishes a coordinate for one record in five and :mod:`src.providers.spain_egif`
publishes one that has to be reconstructed from a UTM zone and a datum code. Here
it arrives as EPSG:4326 longitude and latitude, ready to use.

Three of those points are not in Guatemala, and all three belong to records the
provider has already flagged ``falso``. See
:func:`~src.providers.guatemala_inab.is_in_guatemala` for why they are stored
rather than repaired.

The typed coordinates are a second, worse reading
---------------------------------------------------

The reporting form has fields for the coordinates *and* a map to tap, and both
end up in the record. The map is the one to trust.

:attr:`InabIgnition.reported_x` and :attr:`InabIgnition.reported_y` are the typed
pair, and they are kept for the same reason
:attr:`~src.providers.spain_egif.ignition.EgifIgnition.utm_x` is: they are what
the provider published, and a stored original is what makes the geometry
checkable. They are **not** a location to use:

* only **440 of the 4,615** records have them at all, against 4,615 with a point;
* **12 have the axes swapped**, latitude typed into ``coordenada_x``;
* **15 more are out of range entirely** — one easting reads 15,801,966;
* where they are usable, they disagree with the point by a median of 130 m,
  because they are an independent reading rather than a copy of it.

:attr:`InabIgnition.reported_crs` says which grid the pair is on —
:data:`~src.providers.guatemala_inab.CRS_GTM` on 389 records and
:data:`~src.providers.guatemala_inab.CRS_UTM` on 102 — and GTM is the one with no
EPSG code, whose definition and verification are in
:data:`~src.providers.guatemala_inab.GTM_PROJ`.

Nothing here reprojects them. Turning a typed easting into a longitude would
produce a second opinion about a location that already has a good one, and would
have to decide what to do about the twelve with the axes swapped — which is
exactly the kind of guess that puts plausible wrong coordinates into a database.
"""

from __future__ import annotations

from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition


class InabIgnition(Ignition):
    """The point at which a Guatemalan fire was reported.

    Uses joined table inheritance: the columns shared by every ignition live in
    the ``ignition`` table and only the INAB-specific ones are stored here, in
    ``inab_ignition``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE
        identifier, shared with the parent row.
    global_id : str
        The report's ``GlobalID``, a braced UUID —
        ``'{49585C0C-4FE2-45A3-A50C-405E6C4EF418}'``. **Unique**, and the same
        value as :attr:`~src.providers.guatemala_inab.wildfire.InabWildfire.
        global_id` on the report this point belongs to, because a report has
        exactly one location.

        Stored on both rather than reached through the foreign key so that a
        point can be matched back to a published record without a join, which is
        what re-importing a revised publication needs.
    reported_x : float or None
        ``coordenada_x`` as typed into the form. See the module docstring before
        using it — it is present on one record in ten and wrong on several dozen
        of those.
    reported_y : float or None
        ``coordenada_y``, likewise.
    reported_crs : str or None
        ``sistema_proyeccion``, which grid the typed pair is on: ``'GTM'`` or
        ``'UTM'``. ``None`` on the 4,124 records that typed no coordinates, and —
        worth knowing — on 21 that typed a pair without saying what it was.
    utm_zone : int or None
        ``zona``, the UTM zone of the typed pair. 15 or 16, and filled on 84
        records. Meaningless unless :attr:`reported_crs` is ``'UTM'``, and absent
        from 18 of the 102 records that say it is.
    altitude_m : float or None
        ``altitud``, metres above sea level, on 226 records. As published, and
        never derived from the point.

    Notes
    -----
    There are no coordinate columns for the *stored* location, unlike
    :class:`~src.providers.spain_egif.ignition.EgifIgnition`, which keeps the
    published UTM pair the point was built from. INAB publishes the point itself,
    in the CRS the project stores, so there is nothing to keep beside
    :attr:`~src.data_model.ignition.Ignition.geometry`: the typed columns above
    are a *different* observation, not the same one in another form.
    """

    __tablename__ = "inab_ignition"

    __table_args__ = (
        Index("ix_inab_ignition_reported_crs", "reported_crs"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    global_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    reported_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_crs: Mapped[str | None] = mapped_column(String, nullable=True)
    utm_zone: Mapped[int | None] = mapped_column(Integer, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "inab_ignition",
    }

    def __repr__(self) -> str:
        return f"InabIgnition(id={self.id!r}, global_id={self.global_id!r})"
