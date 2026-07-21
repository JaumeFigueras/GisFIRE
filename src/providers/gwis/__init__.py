#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GWIS — Global Wildfire Information System.

Data model for the products published by GWIS. Currently only the *Global
Wildfire Database* product, which supplies wildfire perimeters.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: GWIS wildfire hangs off, kept beside the model for the same reason as OCHA's
#: (see :mod:`src.providers.ocha`). The product carries the version because
#: GlobFire v3 and a future v4 are different datasets with different fire
#: identifiers, and must not share a provider row.
PROVIDER_NAME = "GWIS"
PROVIDER_FULL_NAME = "Global Wildfire Information System"
PROVIDER_PRODUCT = "Global Wildfire Database v3"
PROVIDER_URL = "https://doi.pangaea.de/10.1594/PANGAEA.943975"
