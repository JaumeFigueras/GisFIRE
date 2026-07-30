#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EGIF ignition model.

EGIF publishes a coordinate for the point the fire started at — the *punto de
inicio* — which is exactly what the generic
:class:`~src.data_model.ignition.Ignition` holds. This model adds the report
number that identifies the fire, the coordinate as published, and the two
locators that describe the point rather than the fire.

That the point really is an ignition and not, say, a centroid, is not an
assumption: the report carries ``puntosinicioincendio``, a count of the fire's
ignition points, which only means anything if the coordinate is one of them.
See :attr:`EgifIgnition.start_point_count`.

Why the published coordinate is kept as numbers and not as a geometry
---------------------------------------------------------------------

:class:`~src.providers.icnf.wildfire.IcnfWildfire` keeps its polygon twice, in
EPSG:4326 and in the national grid it was published in, because an area computed
on a projected grid in metres is the number Portuguese forestry works in and
reprojecting is neither free nor lossless.

None of that applies here. A point has no area and no length, so there is nothing
to compute on a projected grid, and the published easting and northing are kept
losslessly as :attr:`utm_x` and :attr:`utm_y` — they *are* the original numbers,
not a reprojection of them. A geometry column in the source CRS would buy only
QGIS convenience, and it would cost more than it looks: EGIF has no single source
CRS. The datum and zone vary by row, a geometry column carries one SRID in its
type modifier, and a view has to select a geometry straight from its table to stay
detectable in QGIS — so "the published CRS" would mean four nullable geometry
columns and four more views, growing with every datum an older campaign turns out
to use.

The single EPSG:4326 point on the parent, plus the four scalars here, says
everything those columns would and can be reprojected on demand.

Which CRS the numbers are in
----------------------------

:attr:`utm_zone` and :attr:`datum` together name it, through
:data:`~src.providers.egif.SOURCE_SRIDS` — ``("ETRS89", 31)`` is EPSG:25831,
``("REGCAN95", 28)`` is EPSG:4083.

Neither is guaranteed, and the importer, not a ``CHECK``, is what resolves them:

* **The datum is missing for most of the archive.** ``iddatum`` does not appear in
  the XML before the 2014-2016 campaigns; 2004-2013 publish coordinates with no
  datum at all. So :attr:`datum` is nullable and the mainland default has to be
  assumed for those years. See :data:`~src.providers.egif.DATUM_CODES`.
* **The published zone is sometimes wrong, and so is the published lat/lon.**
  Sixteen fires in the archive carry a ``huso`` outside 28-31 — ``3``, ``27``,
  ``32``, ``33``, ``39``, ``50``, ``63``, ``71`` — and the service's own
  ``latitud``/``longitud`` are computed *from* that bad zone, so they land in the
  Pacific (``2011331154``: ``lon -117.24``) or central Asia (``2011260019``:
  ``lon 117.27``). The published geographic coordinate is therefore **derived, not
  independent**, and cannot be used to check the projected one.

  :attr:`utm_zone` consequently has no ``CHECK``: it holds the published number
  whatever it is, and the importer derives the zone to reproject from — from the
  province, which is right in all sixteen cases — rather than trusting it. A
  constraint here would only reject real published records.

There is one fire per coordinate, or none
-----------------------------------------

:attr:`utm_x` and :attr:`utm_y` stay ``NOT NULL``: an ``egif_ignition`` row means
"this fire has a published point". **293,710 of the 586,157 fires in the 1982-2023
archive have no coordinate at all** — every fire before 1998, and a diminishing
share after it until 2017, when the last of them gets one.

Those fires get no ignition row and a ``NULL``
:attr:`~src.providers.egif.wildfire.EgifWildfire.ignition_id`, rather than an
ignition with a hole where the point should be.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition
from src.providers.egif import DATUMS


class EgifIgnition(Ignition):
    """The point an EGIF fire started at, as published in the *parte*.

    Uses joined table inheritance: the columns shared by every ignition live in
    the ``ignition`` table — the EPSG:4326 point above all — and only the
    EGIF-specific ones are stored here, in ``egif_ignition``, whose primary key is
    also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE
        identifier, shared with the parent row.
    report_number : str
        The fire's ``numeroparte``, **unique**, and the same value carried by the
        matching :attr:`~src.providers.egif.wildfire.EgifWildfire.report_number`.
        This is what ties an ignition to its report, the way ``gfa_id`` ties a
        GFA ignition to its perimeter.

        Ten characters: the campaign year, the two-digit INE province code and a
        four-digit sequence — ``2020080001`` is the first fire of 2020 in
        Barcelona. Text, because the province field has a leading zero for the
        first nine provinces.
    utm_zone : int
        The UTM zone the published coordinate is in (``huso``), stored **as
        published and unconstrained**. Normally one of
        :data:`~src.providers.egif.UTM_ZONES`; sixteen fires in the archive carry
        something else, and the module docstring explains why that is kept rather
        than rejected.
    utm_x : float
        Published easting, in metres. Stored as published.
    utm_y : float
        Published northing, in metres. Stored as published.
    datum : str or None
        The geodetic datum the coordinate is on, constrained to
        :data:`~src.providers.egif.DATUMS` where present. With :attr:`utm_zone` it
        names the CRS: see :data:`~src.providers.egif.SOURCE_SRIDS`.

        ``None`` for every campaign before 2014 and most of 2014-2016, where the
        XML publishes no ``iddatum``, and for the three records whose ``iddatum``
        is the unmappable ``3``.
    datum_code : str or None
        The raw ``iddatum`` as published, kept so that resolving it stays lossless.
        ``3`` occurs on three records in the whole archive and maps to no
        known datum, so those keep the code beside a ``NULL`` :attr:`datum` instead
        of being rounded to the common case. ``None`` for a fire read from an Excel
        export, which publishes the datum as a label and never as a code.
    start_point_count : int or None
        How many points the fire was started at (``puntosinicioincendio``).

        Worth checking before treating this ignition as *the* origin: 888 fires of
        the 13,656 in the 2022-2023 export have more than one, up to fifteen, and
        the report publishes a coordinate for only one of them. Where this is
        greater than 1 the stored point is one ignition among several, which for
        an arson case is exactly the interesting part.
    mtn_sheet : str or None
        Sheet of the *Mapa Topográfico Nacional* 1:50,000 the point falls on
        (``hoja``), four characters. A locator the report publishes beside the
        coordinate, kept because it is how the fire is filed on paper.
    mtn_grid : str or None
        Cell within that sheet (``cuadricula``), a letter and two digits.
    place_name : str or None
        The *paraje*: free text naming the spot, ``"Riu Anoia"``. Published in the
        XML only — the Excel export drops it.

    Notes
    -----
    There is no unique constraint on the coordinate, and there should not be: the
    same ground can burn twice. 74 ``(zone, x, y)`` triples in the 2022-2023
    export are shared by 149 different fires.
    """

    __tablename__ = "egif_ignition"

    __table_args__ = (
        CheckConstraint(
            "datum IN (" + ", ".join(f"'{datum}'" for datum in DATUMS) + ")",
            name="ck_egif_ignition_datum",
        ),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    report_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    utm_zone: Mapped[int] = mapped_column(Integer, nullable=False)
    utm_x: Mapped[float] = mapped_column(Float, nullable=False)
    utm_y: Mapped[float] = mapped_column(Float, nullable=False)
    datum: Mapped[str | None] = mapped_column(String, nullable=True)
    datum_code: Mapped[str | None] = mapped_column(String, nullable=True)
    start_point_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mtn_sheet: Mapped[str | None] = mapped_column(String, nullable=True)
    mtn_grid: Mapped[str | None] = mapped_column(String, nullable=True)
    place_name: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "egif_ignition",
    }

    def __repr__(self) -> str:
        return f"EgifIgnition(id={self.id!r}, report_number={self.report_number!r})"
