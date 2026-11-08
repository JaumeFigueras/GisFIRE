#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import applications for lightning strokes.

One subpackage per provider: every detection network publishes its strokes in its
own format with its own location-quality measures, but they all land in the same
:class:`~src.data_model.lightning.Lightning` model.
"""
