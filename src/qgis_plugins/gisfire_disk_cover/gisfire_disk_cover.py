#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path
import math
import copy
import itertools
import time

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
from typing import Dict
from typing import Any

from .resources import *  # noqa


class GisFIREDiskCover:
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

        # Create algorithm members
        self.radius = 1000
        self.initial_array_input_points: List[Dict[str, Any]] = list()
        self.array_of_active_input_points: List[Dict[str, Any]] = list()

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
            QIcon(':/gisfire_dudcs/disks.png'),
            self.tr('GisFIRE Step 1'),
            None
        )
        action.triggered.connect(self.__on_step_1)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 1'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 1'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step1'] = action
        # Step 2
        action = QAction(
            QIcon(':/gisfire_dudcs/disks.png'),
            self.tr('GisFIRE Step 2'),
            None
        )
        action.triggered.connect(self.__on_step_2)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 2'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 2'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step2'] = action
        # Step 3
        action = QAction(
            QIcon(':/gisfire_dudcs/disks.png'),
            self.tr('GisFIRE Step 3'),
            None
        )
        action.triggered.connect(self.__on_step_3)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 3'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 3'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step3'] = action
        # Step 3
        action = QAction(
            QIcon(':/gisfire_dudcs/disks.png'),
            self.tr('GisFIRE Step 4'),
            None
        )
        action.triggered.connect(self.__on_step_4)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 4'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 4'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step4'] = action

    def __add_menu_actions(self):
        """
        Creates the menu entries that allow GisFIRE procedures.
        """
        # Setup parameters
        action: QAction = self._menu.addAction(self.tr('Step 1'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_1)
        self._menu_actions['dudcs_step1'] = action
        # Step 2
        action: QAction = self._menu.addAction(self.tr('Step 2'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_2)
        self._menu_actions['dudcs_step2'] = action
        # Step 3
        action: QAction = self._menu.addAction(self.tr('Step 3'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_3)
        self._menu_actions['dudcs_step3'] = action
        # Step 4
        action: QAction = self._menu.addAction(self.tr('Step 4'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_4)
        self._menu_actions['dudcs_step4'] = action

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
        self._menu = QMenu(self.tr(u'Disk Cover'), self._menu_gisfire)
        self._menu.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        self._menu_gisfire.addMenu(self._menu)
        # Set up the toolbar for lightnings plugin
        self._toolbar = self.iface.addToolBar(u'GisFIRE Disk Cover')
        self._toolbar.setObjectName(u'GisFIRE Disk Cover')

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

    @staticmethod
    def __interpolate_circle(point: QgsPointXY, radius: float, num_points: int = 100) -> List[QgsPointXY]:
        """
        Interpolates a circle with center in point with radius and sampled with num_points
        :param point:
        :param radius:
        :return:
        """
        angles = [2 * math.pi * (i / num_points) for i in range(num_points)]
        points = [QgsPointXY(radius * math.cos(angle) + point.x(), radius * math.sin(angle) + point.y()) for angle in angles]
        points.append(points[0])
        return points

    def __on_step_1(self) -> None:
        """
        TODO: Describe

        :return: None
        """
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

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "circles", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for feature in features:
            feat: QgsFeature = QgsFeature()
            point: QgsPointXY = feature.geometry().asPoint()
            feat.setGeometry(QgsGeometry.fromPolylineXY(self.__interpolate_circle(point, self.radius)))
            feat.setAttributes([fid])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

    def __on_step_2(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        num_points: int = len(features)
        remove = set()
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                if 0 <= distance <= 1:
                    remove.add(x)
        print(len(features))
        for i in sorted(list(remove), reverse=True):
            del features[i]
        print(len(features))

        # Generate the distance matrix
        num_points: int = len(features)
        ids: dict[int, Dict[str, Any]] = {}
        for x in range(num_points):
            ids[x] = {
                'id': features[x].attributes()[features[x].fieldNameIndex('id')],
                'feature': features[x]
            }

        distance_matrix: List[List[int]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                distance_matrix[x][y] = distance
                distance_matrix[y][x] = distance

        adjacency_matrix: List[List[int]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for x in range(num_points):
            for y in range(x + 1, num_points):
                adjacency_matrix[x][y] = int(distance_matrix[x][y] <= (self.radius * 2))
                adjacency_matrix[y][x] = adjacency_matrix[x][y]

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "graph", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        idx_fid = 1
        for x in range(num_points):
            point_1: QgsPointXY = ids[x]['feature'].geometry().asPoint()
            for y in range(x + 1, num_points):
                if adjacency_matrix[x][y] == 1:
                    point_2: QgsPointXY = ids[y]['feature'].geometry().asPoint()
                    feat: QgsFeature = QgsFeature()
                    feat.setGeometry(QgsGeometry.fromPolylineXY([point_1, point_2]))
                    feat.setAttributes([idx_fid])
                    idx_fid += 1
                    provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

        adjacencies: List[int] = [0 for x in range(num_points)]
        for x in range(num_points):
            adjacencies[x] = sum(adjacency_matrix[x])

        count: List[int] = [0 for x in range(max(adjacencies) + 1)]
        for x in range(num_points):
            if adjacencies[x] >= 14:
                count[14] += 1
            else:
                count[adjacencies[x]] += 1

        labels: List[int] = [-1 for x in range(num_points)]
        label = 0
        for x in range(num_points):
            if labels[x] == -1:
                labels[x] = label
                for y in range(x + 1, num_points):
                    if adjacency_matrix[x][y] != 0:
                        if labels[y] == -1:
                            labels[y] = labels[x]
                label += 1
            else:
                for y in range(x + 1, num_points):
                    if adjacency_matrix[x][y] == 1:
                        if labels[y] == -1:
                            labels[y] = labels[x]

        sizes = [0 for x in range(label)]
        for x in range(len(labels)):
            sizes[labels[x]] += 1

        frequencies = [0 for x in range(max(sizes) + 1)]
        for x in range(len(sizes)):
            frequencies[sizes[x]] += 1
        print(sum(frequencies), sum(frequencies[:2]), "{:2.2f}".format((sum(frequencies[:2])/sum(frequencies))*100))

    def __on_step_3(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        num_points: int = len(features)
        remove = set()
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                if 0 <= distance <= 1:
                    remove.add(x)
        for i in sorted(list(remove), reverse=True):
            del features[i]
        num_points: int = len(features)
        distance_matrix: List[List[int]] = [[0 for x in range(num_points)] for y in range(num_points)]
        points = list()
        for x in range(num_points):
            geom_a: QgsGeometry = features[x].geometry()
            point = geom_a.asPoint()
            points.append([point.x(), point.y()])
            for y in range(x + 1, num_points):
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                distance_matrix[x][y] = distance
                distance_matrix[y][x] = distance

        disks = list()
        explored_points = list()
        for x in range(num_points):
            if x not in explored_points:
                current_points = [x]
                for y in range(x +1, num_points):
                    if y not in explored_points:
                        if distance_matrix[x][y] <= self.radius:
                            current_points.append(y)
                x_components = [points[current_point][0] for current_point in current_points]
                y_components = [points[current_point][1] for current_point in current_points]
                disks.append([sum(x_components) / len(x_components), sum(y_components) / len(y_components)])
                explored_points = explored_points + current_points

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "disks", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for disk in disks:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(self.__interpolate_circle(QgsPointXY(disk[0], disk[1]), self.radius)))
            feat.setAttributes([fid])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)


    def __on_step_4(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        num_points: int = len(features)
        remove = set()
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                if 0 <= distance <= 1:
                    remove.add(x)
        for i in sorted(list(remove), reverse=True):
            del features[i]
        num_points: int = len(features)
        distance_matrix: List[List[int]] = [[0 for x in range(num_points)] for y in range(num_points)]
        points_x = list()
        points_y = list()
        for x in range(num_points):
            geom_a: QgsGeometry = features[x].geometry()
            point = geom_a.asPoint()
            points_x.append(point.x())
            points_y.append(point.y())
            for y in range(x + 1, num_points):
                geom_b: QgsGeometry = features[y].geometry()
                distance: int = int(geom_a.distance(geom_b))
                distance_matrix[x][y] = distance
                distance_matrix[y][x] = distance

        min_x = min(points_x)
        max_x = max(points_x)
        min_y = min(points_y)
        max_y = max(points_y)
        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "surfaces", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        current_x = min_x
        surfaces = list()
        while current_x <= max_x:
            current_y = min_y
            while current_y <= max_y:
                feat: QgsFeature = QgsFeature()
                surface_points = [
                    QgsPointXY(current_x, current_y),
                    QgsPointXY(current_x, current_y + self.radius * 4),
                    QgsPointXY(current_x + self.radius * 4, current_y + self.radius * 4),
                    QgsPointXY(current_x + self.radius * 4, current_y),
                    QgsPointXY(current_x, current_y)
                ]
                surfaces.append(surface_points)
                feat.setGeometry(QgsGeometry.fromPolylineXY(surface_points))
                feat.setAttributes([fid])
                fid += 1
                provider.addFeatures([feat])
                current_y += self.radius * 4
            current_x += self.radius * 4
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

        disks = list()
        surface_idx = 0
        for surface in surfaces:
            # Find points in surface
            print("Find points in surface #{}".format(surface_idx))
            features_in_surface: List[int] = list()
            for x in range(num_points):
                top = surface[2].y()
                left = surface[0].x()
                bottom = surface[0].y()
                right = surface[2].x()
                geom_a: QgsGeometry = features[x].geometry()
                point = geom_a.asPoint()
                if left <= point.x() < right and bottom <= point.y() < top:
                    features_in_surface.append(x)
            print("Find points in surface #{} has {} points".format(surface_idx, len(features_in_surface)))
            # Build distance matrix
            print("Compute distance matrix for surface #{}".format(surface_idx))
            distance_matrix: List[List[int]] = [[0 for x in range(len(features_in_surface))] for y in range(len(features_in_surface))]
            for x in range(len(features_in_surface)):
                geom_a: QgsGeometry = features[features_in_surface[x]].geometry()
                point = geom_a.asPoint()
                points_x.append(point.x())
                points_y.append(point.y())
                for y in range(x + 1, len(features_in_surface)):
                    geom_b: QgsGeometry = features[features_in_surface[y]].geometry()
                    distance: int = int(geom_a.distance(geom_b))
                    distance_matrix[x][y] = distance
                    distance_matrix[y][x] = distance
            # Fins adjacency matrix
            print("Compute adjacency matrix for surface #{}".format(surface_idx))
            adjacency_matrix: List[List[int]] = [[0 for x in range(len(features_in_surface))] for y in range(len(features_in_surface))]
            for x in range(len(features_in_surface)):
                for y in range(x + 1, len(features_in_surface)):
                    adjacency_matrix[x][y] = int(distance_matrix[x][y] <= (self.radius * 2))
                    adjacency_matrix[y][x] = adjacency_matrix[x][y]
            print("Label sub-graphs for surface #{}".format(surface_idx))
            labels: List[int] = [-1 for x in range(len(features_in_surface))]
            label = 0
            for x in range(len(features_in_surface)):
                if labels[x] == -1:
                    labels[x] = label
                    for y in range(x + 1, len(features_in_surface)):
                        if adjacency_matrix[x][y] != 0:
                            if labels[y] == -1:
                                labels[y] = labels[x]
                    label += 1
                else:
                    for y in range(x + 1, len(features_in_surface)):
                        if adjacency_matrix[x][y] == 1:
                            if labels[y] == -1:
                                labels[y] = labels[x]
            print("Compute sub-graphs cardinality for surface #{}".format(surface_idx))
            sizes = [0 for x in range(label)]
            for x in range(len(labels)):
                sizes[labels[x]] += 1
            print(sizes)
            print("Find disks of cardinality 1 and 2 for surface #{}".format(surface_idx))
            delete = list()
            for x in range(len(sizes)):
                if sizes[x] == 1:
                    idx = labels.index(x)
                    delete.append(idx)
                    feature = features[features_in_surface[idx]]
                    geom: QgsGeometry = feature.geometry()
                    point = geom.asPoint()
                    disks.append([point.x(), point.y()])
                if sizes[x] == 2:
                    idx = labels.index(x)
                    delete.append(idx)
                    feature_a = features[features_in_surface[idx]]
                    idx = labels.index(x, idx + 1)
                    delete.append(idx)
                    feature_b = features[features_in_surface[idx]]
                    geom_a = feature_a.geometry()
                    geom_b = feature_b.geometry()
                    point_a = geom_a.asPoint()
                    point_b = geom_b.asPoint()
                    disks.append([(point_a.x() + point_b.x()) / 2, (point_a.y() + point_b.y()) / 2])
            print(delete, len(delete))
            for i in sorted(delete, reverse=True):
                del features_in_surface[i]
            print(len(features_in_surface))
            if len(features_in_surface) > 0:
                combination_level = len(features_in_surface)
                found = False
                found_combination = None
                while not found: # for i in range(3, len(features_in_surface)):
                    combinations = itertools.combinations(list(range(len(features_in_surface))), combination_level)
                    print("Analyzing level {} combinations for surface #{}".format(combination_level, surface_idx))
                    for combination in combinations:
                        print(combination)
                        points_x = list()
                        points_y = list()
                        disks_to_explore = list()
                        for x in combination:
                            geom: QgsGeometry = features[x].geometry()
                            point = geom.asPoint()
                            points_x.append(point.x())
                            points_y.append(point.y())
                        disks_to_explore.append(QgsGeometry.fromPointXY(QgsPointXY(sum(points_x) / len(points_x), sum(points_y) / len(points_y))))
                        inside_disks = [0 for x in range(len(features_in_surface))]
                        for x in range(len(features_in_surface)):
                            feature = features[features_in_surface[x]]
                            geom: QgsGeometry = feature.geometry()
                            for disk in disks_to_explore:
                                if disk.distance(geom) <= self.radius:
                                    inside_disks[x] = 1
                                    break
                        if sum(inside_disks) == len(features_in_surface):
                            found = True
                            found_combination = combination
                            break
                    combination_level -= 1
                    if combination_level == 0:
                        print("No Solution found", found_combination)
                        found = True
                print("Solution found", found_combination)
                if found_combination is not None:
                    for elem in found_combination:
                        features_in_disk = list()
                        for x in range(len(adjacency_matrix[elem])):
                            if adjacency_matrix[elem][x] == 1:
                                features_in_disk.append(features_in_surface[x])
                        points_x = list()
                        points_y = list()
                        for x in features_in_disk:
                            geom: QgsGeometry = features[x].geometry()
                            point = geom.asPoint()
                            points_x.append(point.x())
                            points_y.append(point.y())
                        disks.append([sum(points_x) / len(points_x), sum(points_y) / len(points_y)])
            else:
                print("All discs already found for surface #{}".format(surface_idx))
            surface_idx += 1

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "disks", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for disk in disks:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(self.__interpolate_circle(QgsPointXY(disk[0], disk[1]), self.radius)))
            feat.setAttributes([fid])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)


level = 5
while level > 0:
    c = itertools.combinations(list(range(5)), level)
    for elem in c:
        print(elem)
    level -= 1
