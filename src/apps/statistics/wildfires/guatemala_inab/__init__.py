#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Statistics applications for the Guatemalan INAB fire reports.

Two reports over the same fires and the same years, so their ``Country``, ``Year``
and ``Fires`` columns agree row for row:
:mod:`~src.apps.statistics.wildfires.guatemala_inab.wildfire_statistics` counts them,
and :mod:`~src.apps.statistics.wildfires.guatemala_inab.wildfire_classification`
breaks them down by the published vocabularies.

Neither reports a burnt area, and neither reports a cause. INAB publishes thirty-three
attributes and not one of them is either — see
:mod:`src.providers.guatemala_inab`.
"""
