#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DARPA wildfire model.

A burnt area polygon from the Catalan cartography. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the start instant and the
perimeter; this model adds the published code, the published date, where the fire
is filed municipally, how many polygons it was published as, the polygon in the
CRS it was published in, and the link to the EGIF *parte* for the same fire.

See :mod:`src.providers.catalonia_darpa` for the dataset itself — the two encodings,
the three shattered years, the six formats of code and why ``GRID_CODE`` is not an
attribute of the fire.

The perimeter is stored twice, on purpose
-----------------------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is the reprojection to
EPSG:4326, which is what makes a Catalan fire comparable with a GWIS, GFA or ICNF
one and what every cross-provider query uses.
:attr:`DarpaWildfire.perimeter_etrs89_utm31n` is the polygon in EPSG:25831, the
grid it was published on.

The argument is the ICNF one exactly (see
:mod:`src.providers.portugal_icnf.wildfire`): ETRS89 / UTM 31N is a projected grid
in metres, so an area or a distance computed on it is a number in metres, and the
same computation on EPSG:4326 is on degrees and means nothing without a geodesic
function. Reprojecting is neither free nor lossless, so a query that needs the
grid needs it stored.

The two are the same geometry: the import dissolves and repairs the published
polygons, stores the result, and derives the 4326 one from what it stored with
``ST_Transform``.

There is no burnt area, and there never will be
------------------------------------------------

This dataset publishes ``CODI_FINAL``, ``DATA_INCEN``, ``MUNICIPI`` and
``GRID_CODE``, and no hectares in any layer of any year. That is not an omission
to be filled in later from the polygon: an area measured off a perimeter and an
area written on a report form are different quantities, and GisFIRE keeps
published numbers rather than manufacturing them.

The hectares for a Catalan fire live on the EGIF *parte* for the same fire —
five of them, split by land type, on
:class:`~src.providers.spain_egif.wildfire.EgifWildfire` — which is a large part of
why :attr:`DarpaWildfire.egif_wildfire_id` is worth having. What EGIF cannot give
is the shape, and what this gives is nothing else.

There is no ignition either
----------------------------

Unlike a GFA or an EGIF fire, a Catalan one has no
:class:`~src.data_model.ignition.Ignition`. The layers publish a perimeter and a
municipality and **no ignition coordinate**, so there would be no point to put in
one. EGIF does publish a point for the Spanish fire, which is one more thing the
relation makes reachable.

The code is stored as published
--------------------------------

:attr:`DarpaWildfire.code` is ``CODI_FINAL`` verbatim, in whichever of its six
historical forms the layer used, with nothing split off it. See
:mod:`src.providers.catalonia_darpa`: parsing it would bake a matching rule into
the model, and the matching rule is exactly what has not been agreed yet.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
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
from src.providers.catalonia_darpa import SOURCE_SRID
from src.providers.spain_egif.wildfire import EgifWildfire

#: The published ``CODI_FINAL`` is the EGIF ``report_number``, and the two agree on
#: the date as well. 480 of the 860 fires, all of them 1997 or later. Certain.
MATCH_CODE = "code"

#: The code is the ``report_number`` but the two published dates disagree — 9 of
#: those 480, by anything from a day to eight weeks. Still a match, because the
#: report number is a national identifier and not a guess; kept apart because a
#: fire whose two sources disagree about *when* it burnt is worth being able to
#: find.
MATCH_CODE_DATE_MISMATCH = "code_date_mismatch"

#: The published code is the ``report_number`` **rearranged** — the older Catalan
#: formats carry the same year, province and sequence in a different order and
#: width, and :func:`~src.providers.catalonia_darpa.egif_report_number` puts them
#: back. 122 of the 860 fires, all of them 1986-1996.
#:
#: Below :data:`MATCH_CODE` because it rests on a reading of the format rather than
#: on string equality, and above everything else because it is still an identifier:
#: a decode is accepted only when the two published dates also agree, and on the
#: real archive all 122 do — a cleaner record than the undecoded form, which
#: disagrees on nine of its 480.
MATCH_CODE_REFORMATTED = "code_reformatted"

#: Exactly one EGIF fire in the whole of Catalonia on that date.
MATCH_DATE = "date"

#: Exactly one in that province on that date, the province read off the code.
MATCH_DATE_PROVINCE = "date_province"

#: Exactly one on that date whose municipality name matches, with no province to
#: narrow by first — the 1994-1996 codes encode none.
MATCH_DATE_NAME = "date_name"

#: Exactly one on that date, in that province, in that municipality. The workhorse
#: of the pre-1997 era.
MATCH_DATE_PROVINCE_NAME = "date_province_name"

#: Exactly one candidate left after testing which EGIF ignition points fall inside
#: the Catalan perimeter. Strong evidence, and almost never available: EGIF
#: publishes no coordinate at all before 1998, which is where nearly every
#: unresolved fire is.
MATCH_GEOMETRY = "geometry"

#: Every value :attr:`DarpaWildfire.match_method` may take, strongest first.
MATCH_METHODS = (
    MATCH_CODE,
    MATCH_CODE_REFORMATTED,
    MATCH_CODE_DATE_MISMATCH,
    MATCH_GEOMETRY,
    MATCH_DATE_PROVINCE_NAME,
    MATCH_DATE_NAME,
    MATCH_DATE_PROVINCE,
    MATCH_DATE,
)

#: The confidence stored for each method.
#:
#: Fixed per method rather than computed per fire, and **an ordering rather than a
#: probability** — see :attr:`DarpaWildfire.match_confidence`. The gap between
#: :data:`MATCH_CODE` and everything else is the one that matters and is the reason
#: the numbers exist at all: an identifier match and a name match are different
#: kinds of claim, not the same claim held less firmly.
MATCH_METHOD_CONFIDENCE = {
    MATCH_CODE: 1.00,
    MATCH_CODE_REFORMATTED: 0.95,
    MATCH_CODE_DATE_MISMATCH: 0.90,
    MATCH_GEOMETRY: 0.85,
    MATCH_DATE_PROVINCE_NAME: 0.75,
    MATCH_DATE_NAME: 0.65,
    MATCH_DATE_PROVINCE: 0.60,
    MATCH_DATE: 0.50,
}


class DarpaWildfire(Wildfire):
    """A Catalan forest fire perimeter.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the Catalan ones are stored here, in
    ``darpa_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE
        identifier, shared with the parent row.
    source_layer : str
        The published year the fire was read from, canonically named:
        ``incendis`` plus four digits, from
        :func:`~src.providers.catalonia_darpa.source_layer_name`.

        Canonical rather than as-found, because the department ships one year under
        up to four names — ``incendis2022.shp``, ``incendis22.zip``, and a GDAL
        layer called plainly ``incendis`` inside that zip; 2010 adds ``incendis10``.
        Storing the name as found would put the same fires under two different
        values depending on which copy was to hand, and the import's
        replace-the-year rule keys on exactly this column.

        Indexed: it is how a republished year is replaced, and it is the provenance
        of a row in a table that gathers thirty-nine files.
    code : str
        The published ``CODI_FINAL``, **exactly as published**, in whichever of its
        six historical forms — ``178600064``, ``G0870016``, ``L89004001``,
        ``894496``, ``2013080287``, ``303/22N``. Never parsed or normalised; see
        the module docstring.

        Indexed through :attr:`fire_date`'s unique constraint rather than on its
        own, because it is **not unique**: ``303/22N`` names two different fires.
    fire_date : datetime.date
        The published ``DATA_INCEN``, as a date. ``NOT NULL``, and it really is
        published for every fire this model stores — the features with no date are
        all background polygons and are not fires (see
        :data:`~src.providers.catalonia_darpa.GRID_CODE_BURNT`).

        Stored beside :attr:`~src.data_model.wildfire.Wildfire.start_date_time`
        rather than derived from it because the two are different kinds of thing:
        the parent holds an *instant*, local midnight in
        :attr:`~src.data_model.wildfire.Wildfire.time_zone`, and this holds the
        *date* the department wrote down. Recovering the second from the first
        needs the zone applied back, and the whole reason a fire has no time here
        is that the source never gave one.

        It is also half the natural key: ``(code, fire_date)`` is unique across the
        archive and ``code`` alone is not.
    year : int
        The year of the published layer, which is also the year of
        :attr:`fire_date` — checked at import on every fire rather than assumed,
        and true of all 4,533 of them. Indexed, because grouping by year is what
        every statistics report over this dataset does, and an expression on
        :attr:`fire_date` could not use an index.
    municipality_name : str
        ``MUNICIPI``, as published: the municipality the fire is filed under. The
        case is the source's and varies by era — ``Sant Cugat del Vallès`` in the
        older layers, ``BELLPRAT`` in the newer — and is not normalised, for the
        same reason the code is not.

        ``NOT NULL``: every burnt feature in the archive has one. It is a *name*
        and not a code — there is no INE municipal code in this dataset — so
        turning it into an
        :class:`~src.providers.spain_ign.admin_boundary.IgnAdminBoundary` is a name
        match, and is not attempted here.

        A fire that burnt in several municipalities is filed under one of them:
        this is where the fire is *recorded*, not the whole of where it burnt. The
        perimeter is the answer to the second question.
    part_count : int
        How many published polygons were dissolved into this fire's perimeter.

        ``1`` for most of the archive, and very much not for three years: the 1991,
        1993 and 1994 layers were vectorised from a raster and never dissolved, and
        one 1994 fire is published as **1,309 separate features**. Stored so that
        the shattering stays visible — a perimeter assembled from 1,309 fragments
        is a different kind of evidence from one digitised as a single ring, and
        nothing else in the row would say so.
    egif_wildfire_id : int or None
        Foreign key to the :class:`~src.providers.spain_egif.wildfire.EgifWildfire`
        *parte* for the same fire.

        **Always ``None`` as imported**: the import does not attempt the match. It
        is filled in afterwards by
        :mod:`~src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires`,
        which is the only thing that writes it or the three columns below.
    egif_wildfire : EgifWildfire or None
        The Spanish *parte* for the same fire, once something has bound them.
    match_method : str or None
        **How** the binding was arrived at, one of :data:`MATCH_METHODS`. ``None``
        exactly when :attr:`egif_wildfire_id` is, which a check constraint
        enforces.

        This column is the reason the binding is usable at all. Roughly 56% of the
        links come from an exact identifier — the published code *is* the EGIF
        ``report_number`` from 1997 on — and the rest from a date, a province and a
        municipality name, which is a good rule and not a certainty. An analysis
        that treats the two alike is claiming a precision the second kind does not
        have, and without this column there is no way to tell them apart.
    match_confidence : float or None
        A number between 0 and 1, fixed per method by
        :data:`MATCH_METHOD_CONFIDENCE`.

        **An ordering, not a probability.** Nothing here has been calibrated
        against ground truth — there is no independent answer key for a 1989 fire —
        so it says "trust this more than that" and nothing arithmetical. It exists
        because ``WHERE match_confidence >= 0.9`` is the query people actually
        write, and spelling out the method names each time is worse.
    matched_at : datetime.datetime or None
        When the binding was computed. Not
        :attr:`~src.data_model.wildfire.Wildfire.updated_at`, which moves for any
        edit: a binding older than the last EGIF import was computed against data
        that has since changed, and this is what says so.
    perimeter_etrs89_utm31n : str or None
        The burnt area polygon in EPSG:25831, the grid the department publishes on.
        See the module docstring on why it is kept as well as the EPSG:4326 one on
        the parent row.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL`` on every
    row and will stay so: the dataset publishes one date per fire and does not say
    whether it is the detection, the ignition or the day the perimeter was flown.
    Storing it as an end as well would be an invention.
    """

    __tablename__ = "darpa_wildfire"

    __table_args__ = (
        # The published natural key. Not ``code`` alone: 303/22N names a fire in
        # Lleida on 19 June 2022 and another in Figueres on 7 July, and a unique
        # constraint on the code would have forced them into one polygon.
        UniqueConstraint("code", "fire_date", name="uq_darpa_wildfire_code_fire_date"),
        CheckConstraint(
            "match_method IN ("
            + ", ".join(f"'{method}'" for method in MATCH_METHODS)
            + ")",
            name="ck_darpa_wildfire_match_method",
        ),
        # A binding is the link *and* the account of how it was made. Either both
        # are there or neither is: a link with no method would be unattributable,
        # and a method with no link would be a claim about nothing.
        CheckConstraint(
            "(egif_wildfire_id IS NULL) = (match_method IS NULL)",
            name="ck_darpa_wildfire_match_method_with_link",
        ),
        Index("ix_darpa_wildfire_source_layer", "source_layer"),
        Index("ix_darpa_wildfire_year", "year"),
        Index("ix_darpa_wildfire_egif_wildfire_id", "egif_wildfire_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    source_layer: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    fire_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    municipality_name: Mapped[str] = mapped_column(String, nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False)
    egif_wildfire_id: Mapped[int | None] = mapped_column(
        ForeignKey(EgifWildfire.id), nullable=True
    )
    match_method: Mapped[str | None] = mapped_column(String, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    perimeter_etrs89_utm31n: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID), nullable=True
    )

    egif_wildfire: Mapped[EgifWildfire | None] = relationship(
        foreign_keys=[egif_wildfire_id]
    )

    __mapper_args__ = {
        "polymorphic_identity": "darpa_wildfire",
    }

    def __repr__(self) -> str:
        return (f"DarpaWildfire(id={self.id!r}, code={self.code!r}, "
                f"fire_date={self.fire_date!r})")
