#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GisFIRE generic data model.

Defines the declarative :class:`Base` that every ORM model inherits from,
using the fully declarative SQLAlchemy 2.0 style (``DeclarativeBase`` +
``Mapped`` / ``mapped_column``).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for all GisFIRE ORM models.

    Every table's ``MetaData`` is collected on ``Base.metadata``, so importing
    the model modules (done below) is enough for ``Base.metadata.create_all()``
    to know about them.
    """


# Import models so their tables register on ``Base.metadata`` when the package
# is imported. Kept at the bottom to avoid a circular import (the models import
# ``Base`` from this module).
from src.data_model.data_provider import DataProvider  # noqa: E402,F401
from src.data_model.geography.admin_boundary import AdminBoundary  # noqa: E402,F401
from src.data_model.geography.time_zone import TimeZone  # noqa: E402,F401
from src.data_model.ignition import Ignition  # noqa: E402,F401
from src.data_model.wildfire import Wildfire  # noqa: E402,F401
