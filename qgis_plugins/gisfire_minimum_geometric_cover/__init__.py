"""GISFire Minimum Geometric Cover QGIS plugin.

Runs inside QGIS's Python (Qt6/PyQt6). Talks to the GisFIRE backend over HTTP
(requests) only — must not import the server / data-model packages.
"""


def classFactory(iface):  # pragma: no cover - QGIS entry point
    """QGIS plugin entry point.

    :param iface: a QgisInterface instance provided by QGIS at load time.
    """
    from .plugin import GisFireMinimumGeometricCoverPlugin
    return GisFireMinimumGeometricCoverPlugin(iface)
