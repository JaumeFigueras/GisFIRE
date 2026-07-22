#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFA — Global Fire Atlas.

Data model for the products published by the Global Fire Atlas, which derives
individual fire events from the MODIS MCD64A1 burnt area product: for each fire
an ignition point, a perimeter, and a set of measurements of how it spread.

Two products come out of it, published as separate sets of shapefiles — the
perimeters and the ignition points. Only the perimeters are modelled so far, and
they carry the ignition coordinate as an attribute, so
:class:`~src.providers.gfa.wildfire.GfaWildfire` already holds the ignition
point.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: GFA wildfire hangs off, kept beside the model for the same reason as GWIS's
#: (see :mod:`src.providers.gwis`).
PROVIDER_NAME = "GFA"
PROVIDER_FULL_NAME = "Global Fire Atlas"
PROVIDER_PRODUCT = "Fire Atlas"
PROVIDER_URL = "https://zenodo.org/records/17669692"
