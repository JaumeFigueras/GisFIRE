#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import applications for time zone areas.

One subpackage per source, following the layout of the other import packages,
though in practice there is only one usable source: the IANA time zone database
defines zones by *place names*, not by geometry, so the polygons have to come
from somewhere that has drawn them.
"""
