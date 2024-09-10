#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtCore import QTranslator
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QMenu

import qgis.utils
from qgis.core import QgsVectorLayer
from qgis.core import QgsFeature
from qgis.core import QgsGeometry
from qgis.core import QgsVectorDataProvider
from qgis.core import QgsField
from qgis.core import QgsPointXY
from qgis.core import QgsProject
from qgis.gui import QgisInterface

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from ortools. constraint_solver.pywrapcp import RoutingIndexManager
from ortools. constraint_solver.pywrapcp import RoutingModel

from typing import List

from .resources import *  # noqa


class GisFIRETSP:
    """
    GisFIRE TSP QGIS plugin implementation

    TODO: Add attributes information
    """
    iface: QgisInterface

    def __init__(self, iface: QgisInterface):
        """
        Constructor.

        :param iface: An interface instance that will be passed to this class which provides the hook by which you can
        manipulate the QGIS application at run time.
        :type iface: qgis.gui.QgisInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'gisfire_lightnings_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Initialization of UI references
        self._toolbar_actions = dict()
        self._menu_actions = dict()
        self._menu = None
        self._menu_gisfire = None
        self._toolbar = None
        self._dlg = None
        # Initialization of GisFIRE data layers
        self._layers = {}

    # noinspection PyMethodMayBeStatic
    def tr(self, message: str) -> str:
        """
        Get the translation for a string using Qt translation API.

        :param message: String for translation.
        :type message: str
        :returns: Translated version of message.
        :rtype: str
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GisFIRELightnings', message)

    def __add_toolbar_actions(self):
        """
        Creates the toolbar buttons that GisFIRE Lightnings uses as shortcuts.
        """
        # Setup parameters
        action = QAction(
            QIcon(':/gisfire_tsp/routing.png'),
            self.tr('GisFIRE TSP'),
            None
        )
        action.triggered.connect(self.__on_tsp)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE TSP'))
        action.setWhatsThis(self.tr('GisFIRE TSP'))
        self._toolbar.addAction(action)
        self._toolbar_actions['setup'] = action

    def __add_menu_actions(self):
        """
        Creates the menu entries that allow GisFIRE procedures.
        """
        # Setup parameters
        action: QAction = self._menu.addAction(self.tr('TSP'))
        action.setIcon(QIcon(':/gisfire_tsp/routing.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_tsp)
        self._menu_actions['setup'] = action

    def __add_relations(self):
        """
        Creates mutually exclusive relations between toolbar buttons.
        """
        pass

    # noinspection PyPep8Naming
    # noinspection DuplicatedCode
    def initGui(self):
        """
        Initializes the QGIS GUI for the GisFIRE Lightning plugin.
        """
        # Set up the menu
        menu_name = self.tr(u'Gis&FIRE')
        parent_menu = self.iface.mainWindow().menuBar()
        # Search if the menu exists (there are other GisFIRE modules installed)
        for action in parent_menu.actions():
            if action.text() == menu_name:
                self._menu_gisfire = action.menu()
        # Create the menu if it does not exist and add it to the current menubar
        if self._menu_gisfire is None:
            self._menu_gisfire = QMenu(menu_name, parent_menu)
            actions = parent_menu.actions()
            if len(actions) > 0:
                self.iface.mainWindow().menuBar().insertMenu(actions[-1], self._menu_gisfire)
            else:
                self.iface.mainWindow().menuBar().addMenu(self._menu_gisfire)
        # Create TSP menu
        self._menu = QMenu(self.tr(u'TSP'), self._menu_gisfire)
        self._menu.setIcon(QIcon(':/gisfire_tsp/routing.png'))
        self._menu_gisfire.addMenu(self._menu)
        # Set up the toolbar for lightnings plugin
        self._toolbar = self.iface.addToolBar(u'GisFIRE TSP')
        self._toolbar.setObjectName(u'GisFIRE TSP')

        # Add toolbar buttons
        self.__add_toolbar_actions()
        # Add menu entries
        self.__add_menu_actions()
        # Create relations with existing menus and buttons
        self.__add_relations()

    # noinspection DuplicatedCode
    def unload(self):
        """
        Removes the plugin menu item and icon from QGIS GUI.
        """
        # Remove toolbar items
        for action in self._toolbar_actions.values():
            action.triggered.disconnect()
            self.iface.removeToolBarIcon(action)
            action.deleteLater()
        # Remove toolbar
        if not(self._toolbar is None):
            self._toolbar.deleteLater()
        # Remove menu items
        for action in self._menu_actions.values():
            action.triggered.disconnect()
            self._menu.removeAction(action)
            action.deleteLater()
        # Remove menu
        if not(self._menu is None):
            self._menu.deleteLater()
        # Remove the menu_gisfire only if I'm the only GisFIRE module installed
        count = 0
        for name in qgis.utils.active_plugins:
            if name.startswith('gisfire'):
                count += 1
        if count == 1:
            if not(self._menu_gisfire is None):
                self.iface.mainWindow().menuBar().removeAction(self._menu_gisfire.menuAction())
                self._menu_gisfire.menuAction().deleteLater()
                self._menu_gisfire.deleteLater()

    def __on_tsp(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        def distance_callback(from_index, to_index):
            """Returns the distance between the two nodes."""
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        # Generate the distance matrix
        num_points: int = len(features)
        distance_matrix: List[List[int]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                distance_matrix[x][y] = distance
                distance_matrix[y][x] = distance
        # Setup ortools TSP Solver
        manager: RoutingIndexManager = pywrapcp.RoutingIndexManager(num_points, 1, 0)
        routing: RoutingModel = pywrapcp.RoutingModel(manager)
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        # search_parameters.time_limit.seconds = 60
        solution = routing.SolveWithParameters(search_parameters)
        if solution:
            # Create layer
            vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "route", "memory")
            provider: QgsVectorDataProvider = vector_layer.dataProvider()
            # Add fields
            provider.addAttributes([QgsField("fid", QVariant.Int)])
            vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
            index = routing.Start(0)
            points = [manager.IndexToNode(index)]
            while not routing.IsEnd(index):
                index = solution.Value(routing.NextVar(index))
                points.append(manager.IndexToNode(index))
            # Add a feature
            feat: QgsFeature = QgsFeature()
            line: List[QgsPointXY] = list()
            for point in points:
                geom_o: QgsGeometry = features[point].geometry()
                point_o: QgsPointXY = geom_o.asPoint()
                line.append(point_o)
            print(line)
            feat.setGeometry(QgsGeometry.fromPolylineXY(line))
            feat.setAttributes([1])
            provider.addFeatures([feat])
            # update layer's extent when new features have been added
            # because change of extent in provider is not propagated to the layer
            vector_layer.updateExtents()
            current_project: QgsProject = QgsProject()
            current_project.instance().addMapLayer(vector_layer, True)
            vector_layer.setCrs(current_project.instance().crs())
            print(distance_matrix)
            print(solution)
