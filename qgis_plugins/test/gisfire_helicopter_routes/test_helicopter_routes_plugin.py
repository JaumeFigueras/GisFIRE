"""Smoke tests for the GISFire Helicopter Routes plugin."""

import gisfire_helicopter_routes


def test_class_factory_lifecycle(qgis_iface):
    plugin = gisfire_helicopter_routes.classFactory(qgis_iface)
    assert plugin is not None
    plugin.initGui()
    plugin.unload()
