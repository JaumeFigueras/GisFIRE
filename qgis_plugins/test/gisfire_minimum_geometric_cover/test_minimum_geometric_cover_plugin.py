"""Smoke tests for the GISFire Minimum Geometric Cover plugin."""

import gisfire_minimum_geometric_cover


def test_class_factory_lifecycle(qgis_iface):
    plugin = gisfire_minimum_geometric_cover.classFactory(qgis_iface)
    assert plugin is not None
    plugin.initGui()
    plugin.unload()
