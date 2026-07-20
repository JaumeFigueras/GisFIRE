#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geographic reference data.

Models in this package are *reference* data rather than observations: they
describe the world GisFIRE's data is located in, and are used to clip datasets
or to attribute an event to a place. They are imported once from an authoritative
source and then change only when that source republishes.

Kept apart from the models in :mod:`src.data_model` proper, which hold the
wildfire domain itself.
"""
