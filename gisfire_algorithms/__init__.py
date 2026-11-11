#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GisFIRE algorithms shared by the command-line applications and the QGIS plugins.

Pure computation on plain data (numpy arrays): it must not import the data model
(SQLAlchemy, GeoAlchemy2, psycopg) nor QGIS. Allowed dependencies are the
standard library, numpy and scikit-learn. Imports inside the package are
relative, so a plugin can ship it vendored under its own namespace.
"""
