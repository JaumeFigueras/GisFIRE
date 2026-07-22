#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provider-specific data models.

Each data provider gets a subpackage holding the models for the data it
supplies. They subclass the generic models in :mod:`src.data_model` rather than
duplicating them, adding only the columns particular to the provider (its own
identifier, above all).

Importing this package registers every provider table on
:attr:`src.data_model.Base.metadata`, which is what lets
``Base.metadata.create_all()`` and Alembic autogenerate see them. Anything that
needs the full schema — ``alembic/env.py``, the test fixtures — must therefore
import :mod:`src.providers`, not just :mod:`src.data_model`.
"""

# Imported for the side effect of registering the tables; kept at the bottom of
# the module for the same reason as in src/data_model/__init__.py.
from src.providers.gfa.wildfire import GfaWildfire  # noqa: E402,F401
from src.providers.gwis.wildfire import GwisWildfire  # noqa: E402,F401
from src.providers.ocha.admin_boundary import OchaAdminBoundary  # noqa: E402,F401
