#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# noinspection PyPep8Naming
def classFactory(iface):
    """
    Loads the GisFIRELightnings class.

    :param iface: A QGIS interface instance.
    :type iface: qgis.gui.QgisInterface
    """
    from .gisfire_lightnings import GisFIRELightnings
    return GisFIRELightnings(iface)
