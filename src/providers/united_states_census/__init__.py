#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US Census Bureau — Cartographic Boundary Files.

Data model for the *Cartographic Boundary Files* the United States Census Bureau
publishes every year: generalised extracts of its MAF/TIGER database, at 1:500,000,
1:5,000,000 and 1:20,000,000. GisFIRE imports two of the 1:500,000 layers as
:class:`~src.providers.united_states_census.admin_boundary.CensusAdminBoundary`
rows:

==========================  ==================================  ==========================
Level                       File (2025 edition)                 Count (50 states and DC)
==========================  ==================================  ==========================
State (and DC)              ``cb_2025_us_state_500k.zip``       51
County (and equivalents)    ``cb_2025_us_county_500k.zip``      3 144
==========================  ==================================  ==========================

Published at
https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html,
the files of an edition under ``https://www2.census.gov/geo/tiger/GENZ<edition>/shp/``.
A work of the US federal government, so in the public domain.

Land boundaries, not TIGER/Line's
---------------------------------

The cartographic files are **clipped to the shoreline**, while TIGER/Line, the
Census's full-detail product, runs the state boundaries into the sea out to the
3-mile limit and into the Great Lakes. Clipped is what GisFIRE wants: a boundary
is the land, as for the OCHA countries. The price is the generalisation to
1:500,000, which moves a boundary by a few hundred metres at most.

The GEOID nests
---------------

``GEOID`` is the FIPS code: two digits for a state (``02`` Alaska), the state's
two plus three for a county (``02020`` Anchorage). A county's parent is therefore
the state whose ``GEOID`` is the first two digits of its own, and the tree is built
from the codes rather than by a spatial test. The two lengths differ, so a state's
and a county's code never collide within the provider.

``LSAD`` (*legal/statistical area description*) says what kind of entity a row is,
as a two-character code. In the 2025 county file, over the 50 states and DC:

======  ====================================  =====
LSAD    Description                           Count
======  ====================================  =====
``06``  County                                2 999
``15``  Parish (Louisiana)                    64
``25``  city (an independent city)            40
``04``  Borough (Alaska)                      13
``05``  Census Area (Alaska)                  11
``PL``  Planning Region (Connecticut)         9
``03``  City and Borough (Alaska)             4
``12``  Municipality (Alaska)                 2
``00``  none: the District of Columbia and    2
        Carson City
======  ====================================  =====

Every state is ``00``. Connecticut's planning regions replaced its counties in
2022. The code is what tells apart two entities of one name in one state:
Baltimore County (``24005``, ``06``) and the city of Baltimore (``24510``,
``25``).

What is left out
----------------

The state file also holds the five inhabited territories — American Samoa (FIPS
60), Guam (66), the Northern Mariana Islands (69), Puerto Rico (72) and the US
Virgin Islands (78) — and the county file their 91 county equivalents. They are
**not imported**: OCHA, which GisFIRE already imports at level 0, has each of them
as a country of its own, so keeping them here would put them under the United
States as well. The 50 states and DC are FIPS 01 to 56 (:data:`LAST_STATE_FIPS`).

Alaska crosses the antimeridian
-------------------------------

Alaska's western Aleutians lie east of 180°. The file publishes them as parts of
their own at positive longitudes (to 179.78° E), beside the rest of the state at
negative ones, so in EPSG:4326 Alaska's bounding box spans the whole globe. In a
projected CRS (EPSG:3338, Alaska Albers) the parts sit side by side, whole.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: Census boundary hangs off, kept beside the model for the same reason as OCHA's
#: (see :mod:`src.providers.ocha`). The product carries the **edition**: counties
#: and their codes change (Connecticut's in 2022), so each year's files are a
#: provider of their own.
PROVIDER_NAME = "US Census Bureau"
PROVIDER_FULL_NAME = "United States Census Bureau"
PROVIDER_PRODUCT_TEMPLATE = "Cartographic Boundary Files {edition}, 1:500,000"
PROVIDER_URL = ("https://www.census.gov/geographies/mapping-files/time-series/geo/"
                "cartographic-boundary.html")

#: Edition imported when none is given. The file names carry it
#: (``cb_2025_us_state_500k.zip``), so the import looks for the files of the
#: edition it is told and cannot mix two up.
DEFAULT_EDITION = "2025"

#: A state, or the District of Columbia: level 1.
KIND_STATE = "state"

#: A county or county equivalent (borough, census area, parish, independent city,
#: planning region, ...): level 2.
KIND_COUNTY = "county"

#: Every value :attr:`~src.providers.united_states_census.admin_boundary.CensusAdminBoundary.kind`
#: may take, from the largest division down.
KINDS = (KIND_STATE, KIND_COUNTY)

#: The administrative level each kind is stored at. Level 0 is the country, which
#: these files do not publish at 1:500,000 — see :data:`COUNTRY_ISO_3`.
LEVELS = {KIND_STATE: 1, KIND_COUNTY: 2}

#: The layer name each kind's file carries: ``cb_<edition>_us_<layer>_500k``.
LAYERS = {KIND_STATE: "state", KIND_COUNTY: "county"}

#: How many digits of a ``GEOID`` identify a state; a county's begins with them.
STATE_CODE_LENGTH = 2

#: The largest state FIPS code: the 50 states and DC are 01 to 56, the territories
#: 60 and above. Codes are compared as text, which orders two-digit codes as
#: numbers.
LAST_STATE_FIPS = "56"

#: ISO 3166-1 alpha-3 code of the country the states are parented to, used to
#: find the OCHA boundary that becomes their parent.
COUNTRY_ISO_3 = "USA"


def provider_product(edition: str) -> str:
    """Return the ``DataProvider.product`` naming one edition.

    Parameters
    ----------
    edition : str
        The edition's year, e.g. ``"2025"``.

    Returns
    -------
    str
        The product string, e.g. ``"Cartographic Boundary Files 2025, 1:500,000"``.
    """
    return PROVIDER_PRODUCT_TEMPLATE.format(edition=edition)


def file_name(edition: str, kind: str) -> str:
    """Return the base name, without extension, of one kind's file in one edition.

    Parameters
    ----------
    edition : str
        The edition's year, e.g. ``"2025"``.
    kind : str
        :data:`KIND_STATE` or :data:`KIND_COUNTY`.

    Returns
    -------
    str
        E.g. ``"cb_2025_us_county_500k"``, which is also the shapefile's layer name.
    """
    return f"cb_{edition}_us_{LAYERS[kind]}_500k"
