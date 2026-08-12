#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NBAC — National Burned Area Composite.

Data model for the Canadian national burned area cartography, published by Natural
Resources Canada through the Canadian Wildland Fire Information System as one
zipped shapefile per year.

GisFIRE's first source outside Europe, and its largest perimeter dataset after
GWIS and GFA: **52,276 polygons over 1973-2025**, dissolving to **51,818 fire
events** and 132.7 million hectares of mapped burn.

It is a *composite*, not an agency archive
-------------------------------------------

NBAC is compiled by the FireMARS system from two kinds of source — Natural
Resources Canada's own satellite products and the provincial, territorial and
Parks Canada agencies' own mapping — and a rule-based process picks the best
available polygon for each fire. :attr:`~src.providers.canada_nbac.wildfire.
NbacWildfire.ba_source` records which won, and it matters: a MAFiMS polygon
derived from Landsat and an agency polygon digitised from a GPS track are not
observations of equal precision.

That also makes NBAC a different kind of thing from
:mod:`src.providers.canada_nfdb`, which is the agencies' own fire *reports*
unaltered. The two cover the same country and the same fires and disagree on the
total by 34 million hectares, because one measures burn from imagery and the other
records what an agency filed. Neither corrects the other; see *The NFDB relation*.

A fire is a GID, not a polygon
-------------------------------

``NFIREID`` identifies a fire event within one year, and ``GID`` — the year and
the ``NFIREID`` run together — identifies it across the archive. The published
metadata says so outright: *GID is useful for selecting unique fire records merged
by year*.

The published polygons are **cut at provincial, territorial and national park
boundaries**, so one fire that crossed a border is published as several features
sharing a ``GID``. 458 of the 52,276 polygons are such pieces, affecting a little
under one percent of the archive.

The import dissolves them: one row per ``GID``, the geometry unioned, ``POLY_HA``
and ``ADJ_HA`` summed over the parts, and the count kept in
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.part_count`. What the
pieces carried and the union cannot is *where* each piece was, so
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.admin_name` becomes a
:data:`ADMIN_SEPARATOR`-joined list of the administrations the fire burnt in, and
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.crosses_admin` says that
it is one. See that module for why the list is a string and not a table.

Two date pairs, and sometimes neither
--------------------------------------

The service publishes the fire's dates twice over, from two independent
observations:

``HS_SDATE`` / ``HS_EDATE``
    First and last satellite hotspot inside the fire's extent — AVHRR for
    1989-2000, MODIS from 2001. ``NULL`` where no hotspot was detected, which is
    every fire before 1989 and about half of the recent ones.
``AG_SDATE`` / ``AG_EDATE``
    The dates the agency reported. ``NULL`` where the agency provided none.

:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is ``NOT NULL``, so the
import resolves one from the other in a fixed order — the agency's date, then the
hotspot's, then 1 January of the published ``YEAR`` — and records which it got
in :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.date_time_precision`,
exactly as :mod:`src.providers.portugal_icnf` does. **Some fires publish no date
at all**: 102 of 1980's 530, 125 of 2005's 961, 39 of 2023's 2,244.

All four published dates are stored as published, so the resolution is visible
rather than merely trusted.

The cause is three categories, and one of them is nearly lightning
-------------------------------------------------------------------

``FIRECAUS`` takes exactly three values, which the published metadata defines:
:data:`CAUSE_NATURAL`, :data:`CAUSE_HUMAN` and :data:`CAUSE_UNDETERMINED`. Over
the archive they split 50.8% / 25.3% / 24.8%.

.. warning::

   ``Natural`` is **not** a lightning category. The metadata glosses it *"Ignition
   source by natural cause. Most often lightning."* — which is the same
   relationship :mod:`src.providers.portugal_icnf`'s ``Natural`` has to lightning
   and emphatically not the relationship EGIF's ``100 — Rayo`` has to it.

   Anything counting lightning fires here is counting natural-cause fires and
   should say so. See :data:`CAUSE_NATURAL`.

The catalogue is three constants and not a table, unlike
:class:`~src.providers.portugal_icnf.fire_cause.IcnfFireCause`: three values with
no codes, no hierarchy and no labels to translate do not need a row each, and a
``CHECK`` states the vocabulary where a foreign key would only imply it.

The CRS is EPSG:3978, and the file does not say so
----------------------------------------------------

The published ``.prj`` is a bare ``Canada_Lambert_Conformal_Conic`` — NAD83, two
standard parallels at 49° and 77°, false origin at 49°N 95°W — with **no EPSG
identifier attached**. Those are precisely the parameters of EPSG:3978, NAD83 /
Canada Atlas Lambert, and the dataset's own metadata names ``EPSG:3978`` as its
reference system. The sibling NFDB shapefile declares it properly.

So :data:`SOURCE_SRID` is asserted by the import rather than read from the file,
the same guard :mod:`src.providers.andalusia_rediam` needs for the opposite
reason. A projection GDAL cannot name is one PROJ may later decide to interpret
differently.

1972 is not here
----------------

The published metadata describes a 1972-2025 series of 52,610 features. The
service distributes no 1972 archive, and the 53 yearly files available run
1973-2025 and hold 52,276. The missing 334 features are that year.

Nothing in the model depends on the first year, and no lightning analysis reaches
back that far in any case.

The NFDB relation
-----------------

:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id` links a
perimeter to the agency fire report for the same fire, and **nothing fills it in
yet** — exactly as
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id`
was created empty for a later binding application to write.

The direction is the Catalan one: the perimeter points at the report, because the
report is the record the fire is filed under and the perimeter is the shape
somebody mapped afterwards. The three columns that account for the link —
``match_method``, ``match_confidence``, ``matched_at`` — come with it, because a
binding that does not say how it was made is unusable.

No ``CHECK`` lists the methods. The Canadian rules have not been worked out, and
the two datasets share **no published identifier at all** — there is no ``CODIGO``
here that is secretly a report number — so a binding will rest on date, place and
geometry, and inventing its vocabulary now would freeze a guess into the schema.
:mod:`src.providers.andalusia_rediam.wildfire` took the constraint in a revision
of its own once the rules were known; this should do the same.
"""

from __future__ import annotations

#: Name of the provider, shared with :mod:`src.providers.canada_nfdb`: one agency,
#: two products, which is exactly what
#: :class:`~src.data_model.data_provider.DataProvider`'s ``(name, product)``
#: uniqueness is for.
PROVIDER_NAME = "Canada Government - Natural Resources"

#: The agency, in full.
PROVIDER_FULL_NAME = "Natural Resources Canada, Canadian Forest Service"

#: The published product.
PROVIDER_PRODUCT = "National Burned Area Composite"

#: Where the yearly archives are published.
PROVIDER_URL = ("https://cwfis.cfs.nrcan.gc.ca/en/catalogue/results/"
                "537a1fd0-698e-4a7b-85a1-e02581ae78b2")

#: The CRS the perimeters are published in: NAD83 / Canada Atlas Lambert.
#:
#: Kept unchanged on
#: :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.perimeter_lambert`
#: alongside the EPSG:4326 reprojection on the generic model, for the reason set out
#: in :mod:`src.providers.portugal_icnf.wildfire`: a national grid in metres is what
#: an area or a distance means something in, and reprojecting is neither free nor
#: lossless.
#:
#: **Asserted, not read.** The published ``.prj`` carries these parameters with no
#: EPSG identifier; see the module docstring.
SOURCE_SRID = 3978

#: Zone the published dates are resolved against.
#:
#: A fallback rather than a rule, unlike Greece's: Canada spans six time zones, so
#: the importer resolves the zone from the fire's own geometry and uses this only
#: when no time zone areas are imported. Every published date is a bare date in any
#: case, so the zone decides which instant local midnight is and nothing more.
DEFAULT_TIME_ZONE = "America/Edmonton"

#: First year the service distributes. See the module docstring: the metadata
#: describes a series starting in 1972 and no 1972 archive is published.
FIRST_YEAR = 1973

#: ``FIRECAUS``, as the published metadata defines it.
#:
#: *"Ignition source by natural cause. Most often lightning."* — the nearest thing
#: this dataset has to a lightning category, and **not** a lightning category. The
#: same proxy :data:`~src.providers.portugal_icnf.CAUSE_NATURAL` is, and not the
#: named ``Rayo`` of :data:`~src.providers.spain_egif.CAUSE_LIGHTNING`. 26,311 fire
#: events, 50.8% of the archive.
CAUSE_NATURAL = "Natural"

#: *"Ignition source by human cause. Examples include non-industrial activity,
#: industrial activity, prescribed burn, arson, and miscellaneous activity."*
#: 13,115 fire events, 25.3%.
CAUSE_HUMAN = "Human"

#: *"Ignition source undetermined."* 12,850 fire events, 24.8% — and it is not
#: evenly spread: 1976 and 1977 are 80% undetermined, 2017 and 2018 barely 2%.
CAUSE_UNDETERMINED = "Undetermined"

#: Every value ``FIRECAUS`` takes. Constrained on the column: three values, defined
#: in the published metadata and stable since the v20240228 reclassification, is a
#: vocabulary worth stating in the schema rather than a sample worth leaving open.
FIRE_CAUSES = (CAUSE_NATURAL, CAUSE_HUMAN, CAUSE_UNDETERMINED)

#: How the resolved start date was arrived at, and therefore how much of it to
#: believe. Same three-valued scheme as
#: :data:`~src.providers.portugal_icnf.DATE_TIME_PRECISIONS`, and the same column
#: name, so a query over both archives is one query.
#:
#: The whole date is the published ``YEAR`` and nothing else: no agency date and no
#: hotspot was published, so the stored instant is 1 January and means *this fire
#: burnt in this year*.
PRECISION_YEAR = "year"

#: The published date is a day, from ``AG_SDATE`` or ``HS_SDATE``. Every date this
#: dataset publishes is a bare date, so this is the best it ever gets — there is no
#: ``minute`` here, unlike ICNF.
PRECISION_DAY = "day"

#: Every value :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.
#: date_time_precision` takes.
DATE_TIME_PRECISIONS = (PRECISION_YEAR, PRECISION_DAY)

#: Which published date the resolved start came from, recorded beside the
#: precision because the two answer different questions: the precision says how
#: much of the date is real, this says who observed it.
SOURCE_AGENCY = "agency"

#: The start came from ``HS_SDATE``, the first satellite hotspot — no agency date
#: was published. A detection rather than a report, and never earlier than 1989.
SOURCE_HOTSPOT = "hotspot"

#: Neither was published and the start is 1 January of the published ``YEAR``.
#: Always accompanies :data:`PRECISION_YEAR`.
SOURCE_YEAR = "year"

#: Every value :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.
#: date_source` takes, in the order the import prefers them.
DATE_SOURCES = (SOURCE_AGENCY, SOURCE_HOTSPOT, SOURCE_YEAR)

#: What joins the administrations of a fire that crossed a boundary.
#:
#: ``"AB; SK"`` is one fire that burnt in Alberta and Saskatchewan, published as two
#: polygons and stored as one row. See
#: :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.admin_name`, and
#: :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.crosses_admin`, which is
#: what tells a reader to expect a list rather than having to look for a separator.
ADMIN_SEPARATOR = "; "

#: The burned area products a perimeter can come from (``BASRC``), in the order the
#: published metadata lists them. Not constrained: the composite gains a source
#: whenever the Canadian Forest Service builds one — ``TFMS`` arrived with the 2024
#: publication — and a ``CHECK`` here would reject the next.
BA_SOURCES = ("MAFiMS", "C2C", "TFMS", "Agency")
