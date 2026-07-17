"""Smoke tests for the GISFire Thunderstorm plugin."""

import gisfire_thunderstorm


def test_class_factory_lifecycle(qgis_iface):
    plugin = gisfire_thunderstorm.classFactory(qgis_iface)
    assert plugin is not None
    plugin.initGui()
    plugin.unload()
