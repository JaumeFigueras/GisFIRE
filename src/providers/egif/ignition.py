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
``("REGCAN95", 28)`` is EPSG:4083. Both are constrained to the values the exports
actually use, which is what turns a transcription error into a failed insert: one
fire in the 2022 export (``2022470051``, Valladolid) is published with
``Huso 3``, a typo for 30 that the coordinates themselves disambiguate.
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
from src.providers.egif import UTM_ZONES


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
        The UTM zone the published coordinate is in (``huso``), constrained to
        :data:`~src.providers.egif.UTM_ZONES`.
    utm_x : float
        Published easting, in metres. Stored as published.
    utm_y : float
        Published northing, in metres. Stored as published.
    datum : str
        The geodetic datum the coordinate is on, constrained to
        :data:`~src.providers.egif.DATUMS`. With :attr:`utm_zone` it names the
        CRS: see :data:`~src.providers.egif.SOURCE_SRIDS`.
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
            "utm_zone IN (" + ", ".join(str(zone) for zone in UTM_ZONES) + ")",
            name="ck_egif_ignition_utm_zone",
        ),
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
    datum: Mapped[str] = mapped_column(String, nullable=False)
    start_point_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mtn_sheet: Mapped[str | None] = mapped_column(String, nullable=True)
    mtn_grid: Mapped[str | None] = mapped_column(String, nullable=True)
    place_name: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "egif_ignition",
    }

    def __repr__(self) -> str:
        return f"EgifIgnition(id={self.id!r}, report_number={self.report_number!r})"
