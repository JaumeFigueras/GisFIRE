#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import applications for wildfires.

One subpackage per provider: every agency publishes fire perimeters in its own
format with its own identifiers, but they all land in the same
:class:`~src.data_model.wildfire.Wildfire` model.
"""
