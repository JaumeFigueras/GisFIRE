#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCHA — UN Office for the Coordination of Humanitarian Affairs.

Data model for the products published by OCHA. Currently only *Global
International Boundaries (OSM)*, a worldwide layer of country outlines built from
OpenStreetMap data, which GisFIRE imports as administrative level 0.

Published on HDX at
https://data.humdata.org/dataset/global-international-boundaries-osm
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: OCHA boundary hangs off. Kept here rather than in the import application
#: because more than one application needs it: the boundary importer creates the
#: row, and the wildfire importers look it up to know which boundaries to
#: attribute their fires to. A ``(name, product)`` pair identifies it — OCHA
#: publishes several datasets and each is its own row.
PROVIDER_NAME = "OCHA"
PROVIDER_FULL_NAME = "United Nations Office for the Coordination of Humanitarian Affairs"
PROVIDER_PRODUCT = "Global International Boundaries - OSM"
PROVIDER_URL = "https://data.humdata.org/dataset/global-international-boundaries-osm"
