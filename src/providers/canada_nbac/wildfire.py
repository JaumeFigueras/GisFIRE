#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NBAC wildfire model.

A burnt area polygon from the Canadian National Burned Area Composite. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the resolved start and end
instants and the perimeter in EPSG:4326; this model adds the published identifiers,
how the burn was mapped and by whom, the four published dates, the cause, the two
published areas, where the fire burnt administratively, the polygon in the CRS it
was published in, and the link to the NFDB fire report for the same fire.

See :mod:`src.providers.canada_nbac` for the dataset itself — the composite and its
sources, the boundary-split polygons, the two date pairs, the three causes and why
the CRS has to be asserted.

The perimeter is stored twice, on purpose
-----------------------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is the reprojection to
EPSG:4326, which is what makes a Canadian fire comparable with a GWIS, GFA, ICNF,
Catalan or Andalusian one and what every cross-provider query uses.
:attr:`NbacWildfire.perimeter_lambert` is the polygon in
:data:`~src.providers.canada_nbac.SOURCE_SRID`, the grid it was published on.

The argument is the ICNF, DARPA and REDIAM one exactly: a projected grid in metres
is what an area or a distance computed on it means something in, and the same
computation on EPSG:4326 is on degrees and means nothing without a geodesic
function. Reprojecting is neither free nor lossless, so a query that needs the grid
needs it stored.

The two are the same geometry: the import dissolves the published polygons, stores
the result, and derives the 4326 one from what it stored with ``ST_Transform``.

One row is one fire, and several polygons
------------------------------------------

The published features are cut at provincial, territorial and national park
boundaries, so a fire that crossed one is published as several polygons sharing a
``GID``. The import dissolves them into one row and records what the union cannot
say by itself:

* :attr:`part_count` — how many published polygons became this row. 1 for 51,360 of
  the 51,818 fires.
* :attr:`crosses_admin` — whether they were in different administrations, which is
  the same question as *is* :attr:`admin_name` *a list*.
* :attr:`admin_name` and :attr:`admin_div` — the administrations, joined with
  :data:`~src.providers.canada_nbac.ADMIN_SEPARATOR` when there is more than one.
* :attr:`area_ha_polygon` and :attr:`area_ha_adjusted` — **summed** over the parts,
  because each published piece carries the area of its own piece.

The joined names are a string and not a related table, which is a deliberate
departure from how this project usually models a set. Three reasons: the set has at
most a handful of members and 99.1% of fires have exactly one; the members are
codes from a closed published vocabulary, not entities with attributes of their
own; and nothing in GisFIRE will ever join on them — a query that wants "fires in
Alberta" wants :attr:`~src.data_model.wildfire.Wildfire.admin_boundary_id`, which
is resolved from the geometry against real boundaries. A join table would be three
hundred rows of ceremony for a label.

.. warning::

   :attr:`admin_name` is therefore **not** a key and must not be compared with
   ``=`` to a province code. ``"AB"`` and ``"AB; SK"`` are both fires that burnt in
   Alberta. Test :attr:`crosses_admin` first, or use the resolved boundary.

Which date the fire starts on
------------------------------

The dataset publishes two independent date pairs and, for some fires, neither. The
import resolves :attr:`~src.data_model.wildfire.Wildfire.start_date_time` in a
fixed order and records both what it used and how much of it is real:

===================  ===================================  =========================
:attr:`date_source`  From                                 :attr:`date_time_precision`
===================  ===================================  =========================
``agency``           ``AG_SDATE``, the agency's date      ``day``
``hotspot``          ``HS_SDATE``, the first hotspot      ``day``
``year``             1 January of the published ``YEAR``  ``year``
===================  ===================================  =========================

All four published dates are kept as published — :attr:`hotspot_start_date`,
:attr:`hotspot_end_date`, :attr:`agency_start_date`, :attr:`agency_end_date` — so
the resolution can be checked rather than merely trusted, and so the *other*
observation stays available to whoever wants it. A fire whose agency start and
whose first hotspot are three weeks apart is telling you something about one of
them.

The end is :attr:`agency_end_date` where there is one and ``NULL`` otherwise, and
it is ``NULL`` far more often than not: 939 of 2023's 2,244 fires publish no agency
end date. The last hotspot is deliberately **not** used to fill it — a hotspot is
the last time the fire was hot enough for a satellite to see through cloud, which
is not the same event as an agency declaring a fire out, and mixing the two into
one column would make the burning duration a mixture of two definitions.

There is no minute, ever
^^^^^^^^^^^^^^^^^^^^^^^^

Every date this dataset publishes is a bare date, so
:data:`~src.providers.canada_nbac.PRECISION_DAY` is the best it gets and
:mod:`src.providers.portugal_icnf`'s ``minute`` has no counterpart here. The stored
instant is local midnight, resolved against the zone of the fire's own geometry.

The NFDB relation
-----------------

:attr:`nfdb_wildfire_id` is the link to the agency fire report for the same fire,
and the import **never fills it in**. See :mod:`src.providers.canada_nbac`: it
exists so that the application which eventually matches the two Canadian datasets
is an ``UPDATE`` rather than another migration, and the three columns that account
for it come with it.

Unlike Catalonia and Andalusia, there is **no published identifier the two datasets
share** — no code here that is secretly the other's key. That was written as a
prediction and has since been checked: NBAC publishes nineteen fields, identical in
every one of its fifty-three yearly archives, and not one of them is an agency fire
number. :attr:`nfireid` is NBAC's own within-year sequence and :attr:`gid` is the
year and that sequence run together.

So the binding rests on **place, date and agency** instead, and
:mod:`src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires` is what writes it.
:data:`MATCH_METHODS` is the vocabulary that came out of working those rules out, and
it is now constrained — the revision that model docstring asked for.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.wildfire import Wildfire
from src.providers.canada_nbac import DATE_SOURCES
from src.providers.canada_nbac import DATE_TIME_PRECISIONS
from src.providers.canada_nbac import FIRE_CAUSES
from src.providers.canada_nbac import SOURCE_SRID
from src.providers.canada_nfdb.wildfire import NfdbWildfire

#: The NFDB point falls **inside** this perimeter, was filed by the agency that
#: mapped it, and its ``REP_DATE`` is the perimeter's ``AG_SDATE``. The strongest
#: claim this pair of datasets can support.
#:
#: All three agree far more often than chance: on the perimeters that contain a
#: point, the agency matches 178 times in 181 (1985) and 128 in 128 (1986), and the
#: dates agree on 157 of 177 dated pairs. That is not luck — NBAC's agency dates come
#: from the same agency records NFDB publishes — which is what makes ``(agency, day)``
#: the pseudo-identifier this binding otherwise has none of.
MATCH_INSIDE_AGENCY_DAY = "inside_agency_day"

#: Inside, same agency, and **NBAC publishes no agency date to check**. 9,941 of the
#: 51,818 perimeters carry no date at all, and 105 of 1986's 364 alone, so this is a
#: silence rather than a disagreement — the date neither confirms nor contradicts.
MATCH_INSIDE_AGENCY_UNDATED = "inside_agency_undated"

#: Inside, same agency, and the two published dates **disagree**. Still a match,
#: because a point inside a polygon mapped by the same agency is strong evidence, but
#: kept apart in the way :data:`~src.providers.catalonia_darpa.wildfire.
#: MATCH_CODE_DATE_MISMATCH` is: a fire whose two sources disagree about when it burnt
#: is worth being able to find.
MATCH_INSIDE_AGENCY_DATE_MISMATCH = "inside_agency_date_mismatch"

#: Inside, and the agency does not match or is not published. Rare — 0 to 2 fires a
#: year — and worth having because NBAC's ``ADMIN_NAME`` is where the polygon was
#: *mapped*, which for a fire crossing a boundary need not be who *filed* it.
MATCH_INSIDE = "inside"

#: The point is **outside** the perimeter but within
#: :data:`DEFAULT_MATCH_DISTANCE_M` of it, filed by the same agency on the same day.
#:
#: The workhorse of the 1980s and 1990s — about half of every year's bindings — and
#: the weakest rule here by some distance. See
#: :data:`MATCH_METHOD_CONFIDENCE` for the measured risk it carries.
MATCH_NEAR_AGENCY_DAY = "near_agency_day"

#: Every value :attr:`NbacWildfire.match_method` may take, strongest first.
MATCH_METHODS = (
    MATCH_INSIDE_AGENCY_DAY,
    MATCH_INSIDE_AGENCY_UNDATED,
    MATCH_INSIDE_AGENCY_DATE_MISMATCH,
    MATCH_INSIDE,
    MATCH_NEAR_AGENCY_DAY,
)

#: How far outside a perimeter a point may be and still be considered, in metres.
#:
#: Measured rather than chosen. Over 1985-1995, taking the 1,359 perimeters that have
#: a known-good contained partner and asking how often a **wrong** point is also
#: nearby with the same agency and day:
#:
#: ======================  ==================  ============
#: tolerance               bindings it yields  decoy density
#: ======================  ==================  ============
#: 500 m                   1,034               3.7%
#: 1 km                    1,478               5.7%
#: **2 km**                **1,685**           **7.5%**
#: 5 km                    1,730               13.0%
#: ======================  ==================  ============
#:
#: There is a knee at 2 km: going on to 5 km buys 45 more bindings, 2.7%, and nearly
#: doubles the chance that the point a fire is bound to is the wrong one.
DEFAULT_MATCH_DISTANCE_M = 2000.0

#: The confidence stored for each method.
#:
#: Fixed per method rather than computed per fire, and **an ordering rather than a
#: probability** — see :attr:`NbacWildfire.match_confidence`.
#:
#: .. warning::
#:
#:    **Nothing here reaches 1.00, and that is the point.** The Catalan and Andalusian
#:    binders open at 1.00 because a published identifier says the two records are the
#:    same fire. NBAC and NFDB **share no identifier at all** — NBAC publishes 19
#:    fields in every one of its 53 yearly archives and not one of them is an agency
#:    fire number — so every binding here is an inference from place, date and agency,
#:    and the strongest of them is still an inference.
#:
#:    A ``--min-confidence 0.9`` that means "identifier matches only" in Spain
#:    therefore means "the point is inside the polygon and both agree on the agency and
#:    the day" here, which is the nearest equivalent and is not the same claim.
#:
#: The gap that matters is between the four containment methods and
#: :data:`MATCH_NEAR_AGENCY_DAY`: the first four rest on the point being *in* the burnt
#: area, and the last rests on it being near one, which 7.5% of the time is a
#: coincidence available to some other fire as well.
MATCH_METHOD_CONFIDENCE = {
    MATCH_INSIDE_AGENCY_DAY: 0.95,
    MATCH_INSIDE_AGENCY_UNDATED: 0.85,
    MATCH_INSIDE_AGENCY_DATE_MISMATCH: 0.80,
    MATCH_INSIDE: 0.70,
    MATCH_NEAR_AGENCY_DAY: 0.60,
}


class NbacWildfire(Wildfire):
    """A Canadian burned area composite fire event.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the Canadian ones are stored here, in
    ``nbac_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE
        identifier, shared with the parent row.
    gid : str
        The published ``GID`` — the fire year and ``NFIREID`` run together — and the
        natural key of the archive. **Unique**: it is what the published metadata
        offers for "selecting unique fire records merged by year", and after the
        dissolve there is exactly one row per value.
    nfireid : int
        The published ``NFIREID``, which identifies a fire event within one year and
        repeats across years. Kept because it is what the service's own change logs
        refer to — *"C2C fire polygon nfireid 1 in year 1990 replaced with agency
        polygon"* — and indexed with :attr:`year` for exactly that lookup.
    year : int
        The published ``YEAR``, the fire year. ``NOT NULL`` and indexed: it is how a
        year is re-imported and what every report groups on.
    part_count : int
        How many published polygons were dissolved into this row. 1 for 51,360 of
        the 51,818 fires; the rest are fires cut at an administrative boundary.
    crosses_admin : bool
        Whether those polygons lay in more than one administration — and therefore
        whether :attr:`admin_name` is a
        :data:`~src.providers.canada_nbac.ADMIN_SEPARATOR`-joined list.

        It is stored rather than derived from the string because searching a text
        column for a separator is not a question the database should have to be
        asked, and because a single administration whose name one day contains a
        semicolon would make the derivation wrong.
    admin_name : str or None
        Where the perimeter was mapped: a province or territory code (``AB``,
        ``BC``, ``NT``, …), ``PC`` for Parks Canada or ``DND`` for the Department of
        National Defence. Joined with
        :data:`~src.providers.canada_nbac.ADMIN_SEPARATOR` when
        :attr:`crosses_admin`, so ``"AB; SK"`` is one fire in two provinces.

        **Not a key.** See the module docstring.
    admin_div : str or None
        The national park, historic site or military base the perimeter was mapped
        in, where ``admin_name`` is ``PC`` or ``DND`` — ``WB`` for Wood Buffalo,
        ``JA`` for Jasper. Joined the same way and ``None`` for a fire outside both.
    fire_cause : str or None
        ``FIRECAUS``: :data:`~src.providers.canada_nbac.CAUSE_NATURAL`,
        :data:`~src.providers.canada_nbac.CAUSE_HUMAN` or
        :data:`~src.providers.canada_nbac.CAUSE_UNDETERMINED`, constrained to those
        three and indexed.

        ``Natural`` is the nearest thing to lightning this dataset has and is not a
        lightning category — see :data:`~src.providers.canada_nbac.CAUSE_NATURAL`.
    ba_source : str or None
        ``BASRC``, which burned area product the polygon came from: ``MAFiMS``,
        ``C2C``, ``TFMS`` or ``Agency``. Not constrained — the composite gains a
        source whenever one is built.
    detection_source : str or None
        ``FIREMAPS``, what the burn was identified from: ``Landsat``, ``Sentinel-2``,
        ``MODIS``, ``Satellite hotspots``, ``Aerial survey``, ``Ground survey``,
        ``Drone (UAV)``, ``Undefined``, …
    mapping_method : str or None
        ``FIREMAPM``, how the polygon was delineated: ``Processed imagery``,
        ``Manually delineated``, ``Direct from GPS``, ``Buffered points`` or
        ``Undefined``.

        Worth reading before trusting a shape. ``Buffered points`` is a circle drawn
        round a coordinate — 176 of 2023's fires — and its perimeter is an area
        estimate wearing the costume of a mapped boundary.
    hotspot_start_date, hotspot_end_date : datetime.date or None
        ``HS_SDATE`` and ``HS_EDATE``: the first and last satellite hotspot detected
        inside the fire's extent. AVHRR for 1989-2000, MODIS from 2001, and ``None``
        for every fire before 1989 and about half of the recent ones.
    agency_start_date, agency_end_date : datetime.date or None
        ``AG_SDATE`` and ``AG_EDATE``, as the agency reported them. For a fire that
        crossed a border NBAC keeps the earliest start and the latest end of the
        agencies involved.
    capture_date : datetime.date or None
        ``CAPDATE``, when the source data was acquired — the date of the GPS survey,
        the air photo or the satellite image. Provenance of the *mapping*, not of
        the fire.
    date_source : str
        Which published date :attr:`~src.data_model.wildfire.Wildfire.
        start_date_time` was resolved from: one of
        :data:`~src.providers.canada_nbac.DATE_SOURCES`. Constrained.
    date_time_precision : str
        How much of that instant the provider actually published:
        :data:`~src.providers.canada_nbac.PRECISION_DAY` or
        :data:`~src.providers.canada_nbac.PRECISION_YEAR`. Constrained.
    area_ha_polygon : float or None
        ``POLY_HA``, the mapped area in hectares as the service computes it — on the
        Canada Albers Equal Area Conic projection, per the published metadata, which
        is neither of the two CRSs stored here. **Summed** over the dissolved parts.

        Kept as published and not reconciled with the geometry. It is the service's
        own measurement of its own polygon; a measurement taken here would be a
        different number arrived at a different way, and a report that mixed them
        would be comparing two things in one column.
    area_ha_adjusted : float or None
        ``ADJ_HA``, an adjusted area burned from the models of
        `doi:10.1088/1748-9326/abfb2c <https://doi.org/10.1088/1748-9326/abfb2c>`_,
        which estimate what the mapped polygon missed. Also summed over the parts.
    area_adjusted : bool
        ``ADJ_FLAG``, whether an adjustment model was applied — that is, whether
        :attr:`area_ha_adjusted` is a model output or simply a copy of the mapped
        area. Without it the adjusted column cannot be interpreted at all.
    prescribed : bool
        ``PRESCRIBED``, whether the agency reported this as a prescribed burn. A
        deliberate fire, and not a wildfire: 12 of 2005's fires, 7 of 2023's.
        Anything counting wildfires should exclude them.
    version : str or None
        ``VERSION``, the annual dataset version the row came from. Provenance, and
        what tells two imports of the same year apart.
    nfdb_wildfire_id : int or None
        Foreign key to the :class:`~src.providers.canada_nfdb.wildfire.NfdbWildfire`
        for the same fire. **Written by nothing yet** — see the module docstring.
    nfdb_wildfire : NfdbWildfire or None
        The agency fire report this perimeter was matched to.
    match_method : str or None
        Which rule produced the link, one of :data:`MATCH_METHODS`. ``NULL`` exactly
        when :attr:`nfdb_wildfire_id` is, and constrained to the vocabulary — both
        enforced by check constraints.
    match_confidence : float or None
        How much the rule is worth, 0 to 1, from :data:`MATCH_METHOD_CONFIDENCE`.

        **An ordering, not a probability**, and unlike the Catalan and Andalusian
        models nothing here reaches 1.00: those two have a published identifier to
        rest on and this one has none.
    matched_at : datetime.datetime or None
        When the binding was made, so a re-run can be told from an old result.
    perimeter_lambert : geoalchemy2.elements.WKBElement or None
        The dissolved perimeter as published, in
        :data:`~src.providers.canada_nbac.SOURCE_SRID` (NAD83 / Canada Atlas
        Lambert). The parent's
        :attr:`~src.data_model.wildfire.Wildfire.perimeter` is this reprojected to
        EPSG:4326.

    Notes
    -----
    ``gid`` is unique and ``(year, nfireid)`` is unique too — the second is what the
    first is built from — and both constraints are stated. The pair is what the
    service's own change logs address a fire by, and a unique constraint is the
    cheapest possible statement that the dissolve worked.
    """

    __tablename__ = "nbac_wildfire"

    __table_args__ = (
        UniqueConstraint("gid", name="uq_nbac_wildfire_gid"),
        UniqueConstraint("year", "nfireid", name="uq_nbac_wildfire_year_nfireid"),
        CheckConstraint(
            "fire_cause IS NULL OR fire_cause IN ("
            + ", ".join(f"'{cause}'" for cause in FIRE_CAUSES)
            + ")",
            name="ck_nbac_wildfire_fire_cause",
        ),
        CheckConstraint(
            "date_source IN ("
            + ", ".join(f"'{source}'" for source in DATE_SOURCES)
            + ")",
            name="ck_nbac_wildfire_date_source",
        ),
        CheckConstraint(
            "date_time_precision IN ("
            + ", ".join(f"'{precision}'" for precision in DATE_TIME_PRECISIONS)
            + ")",
            name="ck_nbac_wildfire_date_time_precision",
        ),
        CheckConstraint(
            "(nfdb_wildfire_id IS NULL) = (match_method IS NULL)",
            name="ck_nbac_wildfire_match_method_with_link",
        ),
        CheckConstraint(
            "match_method IS NULL OR match_method IN ("
            + ", ".join(f"'{method}'" for method in MATCH_METHODS)
            + ")",
            name="ck_nbac_wildfire_match_method",
        ),
        CheckConstraint("part_count >= 1", name="ck_nbac_wildfire_part_count"),
        Index("ix_nbac_wildfire_year", "year"),
        Index("ix_nbac_wildfire_fire_cause", "fire_cause"),
        Index("ix_nbac_wildfire_nfdb_wildfire_id", "nfdb_wildfire_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    gid: Mapped[str] = mapped_column(String, nullable=False)
    nfireid: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    crosses_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    admin_name: Mapped[str | None] = mapped_column(String, nullable=True)
    admin_div: Mapped[str | None] = mapped_column(String, nullable=True)

    fire_cause: Mapped[str | None] = mapped_column(String, nullable=True)
    ba_source: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_source: Mapped[str | None] = mapped_column(String, nullable=True)
    mapping_method: Mapped[str | None] = mapped_column(String, nullable=True)

    hotspot_start_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    hotspot_end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    agency_start_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    agency_end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    capture_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    date_source: Mapped[str] = mapped_column(String, nullable=False)
    date_time_precision: Mapped[str] = mapped_column(String, nullable=False)

    area_ha_polygon: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_adjusted: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prescribed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[str | None] = mapped_column(String, nullable=True)

    nfdb_wildfire_id: Mapped[int | None] = mapped_column(
        ForeignKey(NfdbWildfire.id), nullable=True
    )
    match_method: Mapped[str | None] = mapped_column(String, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    perimeter_lambert: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID), nullable=True
    )

    nfdb_wildfire: Mapped[NfdbWildfire | None] = relationship(
        foreign_keys=[nfdb_wildfire_id]
    )

    __mapper_args__ = {
        "polymorphic_identity": "nbac_wildfire",
    }

    def __repr__(self) -> str:
        return (f"NbacWildfire(id={self.id!r}, gid={self.gid!r}, "
                f"year={self.year!r})")
