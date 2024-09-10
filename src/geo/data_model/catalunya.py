#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from src.data_model import Base

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from geoalchemy2 import Geometry


class Catalunya(Base):
    __tablename__ = "catalunya"
    id: Mapped[int] = mapped_column('fid', Integer, primary_key=True, autoincrement=True)
    geometry_4326: Mapped[Geometry] = mapped_column('geometry_4326', Geometry(geometry_type='MULTIPOLYGON', srid=4326), nullable=True)
    geometry_4258: Mapped[Geometry] = mapped_column('geometry_4258', Geometry(geometry_type='MULTIPOLYGON', srid=4258), nullable=True)
    geometry_25831: Mapped[Geometry] = mapped_column('geometry_25831', Geometry(geometry_type='MULTIPOLYGON', srid=25831), nullable=True)
