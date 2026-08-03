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
from src.providers.caop.admin_boundary import CaopAdminBoundary  # noqa: E402,F401
from src.providers.spain_egif.fire_cause import EgifFireCause  # noqa: E402,F401
# DarpaWildfire imports EgifWildfire (its egif_wildfire_id points at it), so it
# has to come after the EGIF models below rather than in alphabetical order.
from src.providers.spain_egif.fire_motivation import EgifFireMotivation  # noqa: E402,F401
from src.providers.spain_egif.ignition import EgifIgnition  # noqa: E402,F401
from src.providers.spain_egif.wildfire import EgifWildfire  # noqa: E402,F401
from src.providers.spain_egif.wildfire_report import EgifWildfireReport  # noqa: E402,F401
from src.providers.catalonia_darpa.wildfire import DarpaWildfire  # noqa: E402,F401
# Likewise RediamWildfire, which points at EgifWildfire as well.
from src.providers.andalusia_rediam.ignition import RediamIgnition  # noqa: E402,F401
from src.providers.andalusia_rediam.wildfire import RediamWildfire  # noqa: E402,F401
from src.providers.gfa.ignition import GfaIgnition  # noqa: E402,F401
from src.providers.gfa.wildfire import GfaWildfire  # noqa: E402,F401
from src.providers.gwis.wildfire import GwisWildfire  # noqa: E402,F401
from src.providers.portugal_icnf.fire_cause import IcnfFireCause  # noqa: E402,F401
from src.providers.spain_ign.admin_boundary import IgnAdminBoundary  # noqa: E402,F401
from src.providers.portugal_icnf.wildfire import IcnfWildfire  # noqa: E402,F401
from src.providers.ocha.admin_boundary import OchaAdminBoundary  # noqa: E402,F401
