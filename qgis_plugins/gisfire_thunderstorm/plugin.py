"""GISFire Thunderstorm plugin implementation.

Minimal skeleton: holds the QGIS interface and implements the plugin lifecycle
(``initGui`` / ``unload``). GUI wiring and API calls are added as the plugin is
built out.
"""


class GisFireThunderstormPlugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):  # noqa: N802 - QGIS-required method name
        # TODO: register actions / menus / toolbars.
        pass

    def unload(self):
        # TODO: remove actions / menus / toolbars registered in initGui.
        pass
