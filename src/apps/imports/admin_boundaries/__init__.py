#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import applications for administrative boundaries.

One subpackage per source: the boundaries of different levels come from
different providers (countries from OCHA, subdivisions from OSM), each with its
own format and quirks, but they all land in the same
:class:`~src.data_model.geography.admin_boundary.AdminBoundary` model.
"""
