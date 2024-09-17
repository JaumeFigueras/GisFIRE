#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path
import math
import copy
import itertools
import time
import random

from networkx.algorithms.approximation import max_clique
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

from ortools.linear_solver import pywraplp
from ortools.linear_solver.pywraplp import Solver

import networkx as nx
from networkx.classes.graph import Graph
from networkx.algorithms import approximation as approx

from typing import List
from typing import Dict
from typing import Any
from typing import Tuple
from typing import Optional

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
        action.triggered.connect(self.__on_step_5)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 5'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 5'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step5'] = action
        # Step 6
        action = QAction(
            QIcon(':/gisfire_dudcs/disks.png'),
            self.tr('GisFIRE Step 6'),
            None
        )
        action.triggered.connect(self.__on_step_6)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 6'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 6'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step6'] = action
        # Step 7
        action = QAction(
            QIcon(':/gisfire_dudcs/disks.png'),
            self.tr('GisFIRE Step 7'),
            None
        )
        action.triggered.connect(self.__on_step_7)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover - Step 7'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover - Step 7'))
        self._toolbar.addAction(action)
        self._toolbar_actions['dudcs_step7'] = action

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
        action: QAction = self._menu.addAction(self.tr('Step 5'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_5)
        self._menu_actions['dudcs_step5'] = action
        # Step 6
        action: QAction = self._menu.addAction(self.tr('Step 6'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_6)
        self._menu_actions['dudcs_step6'] = action
        # Step 7
        action: QAction = self._menu.addAction(self.tr('Step 7'))
        action.setIcon(QIcon(':/gisfire_dudcs/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_step_7)
        self._menu_actions['dudcs_step7'] = action

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

    def __on_step_5(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        num_points: int = len(features)
        point_id = 0
        clique_id = 0
        points: List[Tuple[float, float, int, int]] = list()
        # Remove same locations point
        remove = set()
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: float = geom_a.distance(geom_b)
                if distance < 0.5:
                    remove.add(x)
        for i in sorted(list(remove), reverse=True):
            del features[i]
        # Build the graph
        num_points: int = len(features)
        graph: Graph = nx.Graph()
        for feature_index in range(num_points):
            node = dict()
            geom: QgsGeometry = features[feature_index].geometry()
            point: QgsPointXY = geom.asPoint()
            node['feature'] = features[feature_index]
            node['feature_index'] = feature_index
            node['geometry'] = geom
            node['x'] = point.x()
            node['y'] = point.y()
            graph.add_node(feature_index, **node)
        distance_matrix: List[List[float]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for node_a_index in range(num_points):
            node_a_attrs = graph.nodes[node_a_index]
            for node_b_index in range(node_a_index + 1, num_points):
                node_b_attrs = graph.nodes[node_b_index]
                distance: float = node_a_attrs['geometry'].distance(node_b_attrs['geometry'])
                distance_matrix[node_a_index][node_b_index] = distance
                distance_matrix[node_b_index][node_a_index] = distance
                if distance < self.radius * 2:
                    graph.add_edge(node_a_index, node_b_index, weight=distance)
        # Create the subgraphs
        print(num_points)
        connected_subgraphs: List[Graph] = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
        print(sum([len(g) for g in connected_subgraphs]))
        # Remove subgraphs with cardinality 1 or 2 and add them to the disks list
        remove = list()
        disks: List[Tuple[float, float, int]] = list()
        for i in range(len(connected_subgraphs)):
            if len(connected_subgraphs[i]) == 1:
                nodes = connected_subgraphs[i].nodes.items()
                for node_id, node_attribs in nodes:
                    disks.append((node_attribs['x'], node_attribs['y'], clique_id))
                    points.append((node_attribs['x'], node_attribs['y'], point_id, clique_id))
                    point_id += 1
                    clique_id += 1
                    remove.append(node_attribs['feature_index'])
            elif len(connected_subgraphs[i]) == 2:
                nodes = connected_subgraphs[i].nodes.items()
                nodes_attribs = [node_attribs for node_id, node_attribs in nodes]
                disks.append(((nodes_attribs[0]['x'] + nodes_attribs[1]['x']) / 2, (nodes_attribs[0]['y'] + nodes_attribs[1]['y']) / 2, clique_id))
                points.append((nodes_attribs[0]['x'], nodes_attribs[0]['y'], point_id, clique_id))
                point_id += 1
                points.append((nodes_attribs[1]['x'], nodes_attribs[1]['y'], point_id, clique_id))
                point_id += 1
                clique_id += 1
                remove.append(nodes_attribs[0]['feature_index'])
                remove.append(nodes_attribs[1]['feature_index'])
        for i in sorted(remove, reverse=True):
            del features[i]

        num_points: int = len(features)
        graph: Graph = nx.Graph()
        for feature_index in range(num_points):
            node = dict()
            geom: QgsGeometry = features[feature_index].geometry()
            point: QgsPointXY = geom.asPoint()
            node['feature'] = features[feature_index]
            node['feature_index'] = feature_index
            node['geometry'] = geom
            node['x'] = point.x()
            node['y'] = point.y()
            graph.add_node(feature_index, **node)
        distance_matrix: List[List[float]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for node_a_index in range(num_points):
            node_a_attrs = graph.nodes[node_a_index]
            for node_b_index in range(node_a_index + 1, num_points):
                node_b_attrs = graph.nodes[node_b_index]
                distance: float = node_a_attrs['geometry'].distance(node_b_attrs['geometry'])
                distance_matrix[node_a_index][node_b_index] = distance
                distance_matrix[node_b_index][node_a_index] = distance
                if distance < self.radius * math.sqrt(3):
                    graph.add_edge(node_a_index, node_b_index, weight=distance)
        # Create the subgraphs
        connected_subgraphs: List[Graph] = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
        print("Subgraphs: ", len(connected_subgraphs))
        # Find cliques for all connected subgraphs
        subgraph_id = 0
        for subgraph in connected_subgraphs:
            # Find all cliques and store them in reverse order (max len to min)
            print("Subgraph: ", subgraph_id)
            covered_nodes = set()
            len_subgraph = len(subgraph)
            # max_independent = approx.maximum_independent_set(subgraph)
            count = 0
            while len_subgraph != len(covered_nodes):
                print("Subgraph nodes ", len(subgraph), " Covered nodes ", len(covered_nodes))
                cliques = list(nx.enumerate_all_cliques(subgraph))[::-1]
                print("Number of cliques: ", len(cliques))
                max_cliques = list(nx.find_cliques(subgraph))
                max_cliques_lengths = [len(clique) for clique in max_cliques]
                print("max clique ", max(max_cliques_lengths))
                max_size = len(cliques[0])
                max_size_cliques = list()
                for clique in cliques:
                    if len(clique) == max_size:
                        max_size_cliques.append(clique)
                print("cliques of size ", max_size, ":", len(max_size_cliques))
                for clique in max_size_cliques:
                    clique_set = set(clique)
                    if clique_set.isdisjoint(covered_nodes):
                        print("found no intersect subset")
                        xs = list()
                        ys = list()
                        for node in clique:
                            node_attribs = subgraph.nodes[node]
                            xs.append(node_attribs['x'])
                            ys.append(node_attribs['y'])
                            points.append((node_attribs['x'], node_attribs['y'], point_id, clique_id))
                            point_id += 1
                        min_x = min(xs)
                        max_x = max(xs)
                        min_y = min(ys)
                        max_y = max(ys)
                        # Compute the center of the bounding box
                        center_x = (min_x + max_x) / 2
                        center_y = (min_y + max_y) / 2
                        disks.append((center_x, center_y, clique_id))
                        covered_nodes |= clique_set
                        clique_id += 1
                        count += 1
                subgraph.remove_nodes_from(covered_nodes)
            subgraph_id += 1
            # print("Max independent = ", len(max_independent), " - Found = ", count)

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "disks", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("clique", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for disk in disks:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(self.__interpolate_circle(QgsPointXY(disk[0], disk[1]), self.radius)))
            feat.setAttributes([fid, disk[2]])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

        vector_layer: QgsVectorLayer = QgsVectorLayer("point", "points", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("point", QVariant.Int), QgsField("clique", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for point in points:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point[0], point[1])))
            feat.setAttributes([fid, point[2], point[3]])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

    def __on_step_6(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        num_points: int = len(features)
        point_id = 0
        clique_id = 0
        points: List[Tuple[float, float, int, int]] = list()
        # Remove same locations point
        remove = set()
        for x in range(num_points):
            for y in range(x + 1, num_points):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: float = geom_a.distance(geom_b)
                if distance < 0.5:
                    remove.add(x)
        for i in sorted(list(remove), reverse=True):
            del features[i]
        # Build the graph
        num_points: int = len(features)
        graph: Graph = nx.Graph()
        for feature_index in range(num_points):
            node = dict()
            geom: QgsGeometry = features[feature_index].geometry()
            point: QgsPointXY = geom.asPoint()
            node['feature'] = features[feature_index]
            node['feature_index'] = feature_index
            node['geometry'] = geom
            node['x'] = point.x()
            node['y'] = point.y()
            graph.add_node(feature_index, **node)
        distance_matrix: List[List[float]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for node_a_index in range(num_points):
            node_a_attrs = graph.nodes[node_a_index]
            for node_b_index in range(node_a_index + 1, num_points):
                node_b_attrs = graph.nodes[node_b_index]
                distance: float = node_a_attrs['geometry'].distance(node_b_attrs['geometry'])
                distance_matrix[node_a_index][node_b_index] = distance
                distance_matrix[node_b_index][node_a_index] = distance
                if distance < self.radius * 2:
                    graph.add_edge(node_a_index, node_b_index, weight=distance)
        # Create the subgraphs
        print(num_points)
        connected_subgraphs: List[Graph] = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
        print(sum([len(g) for g in connected_subgraphs]))
        # Remove subgraphs with cardinality 1 or 2 and add them to the disks list
        remove = list()
        disks: List[Tuple[float, float, int]] = list()
        for i in range(len(connected_subgraphs)):
            if len(connected_subgraphs[i]) == 1:
                nodes = connected_subgraphs[i].nodes.items()
                for node_id, node_attribs in nodes:
                    disks.append((node_attribs['x'], node_attribs['y'], clique_id))
                    points.append((node_attribs['x'], node_attribs['y'], point_id, clique_id))
                    point_id += 1
                    clique_id += 1
                    remove.append(node_attribs['feature_index'])
            elif len(connected_subgraphs[i]) == 2:
                nodes = connected_subgraphs[i].nodes.items()
                nodes_attribs = [node_attribs for node_id, node_attribs in nodes]
                disks.append(((nodes_attribs[0]['x'] + nodes_attribs[1]['x']) / 2, (nodes_attribs[0]['y'] + nodes_attribs[1]['y']) / 2, clique_id))
                points.append((nodes_attribs[0]['x'], nodes_attribs[0]['y'], point_id, clique_id))
                point_id += 1
                points.append((nodes_attribs[1]['x'], nodes_attribs[1]['y'], point_id, clique_id))
                point_id += 1
                clique_id += 1
                remove.append(nodes_attribs[0]['feature_index'])
                remove.append(nodes_attribs[1]['feature_index'])
        for i in sorted(remove, reverse=True):
            del features[i]

        num_points: int = len(features)
        graph: Graph = nx.Graph()
        for feature_index in range(num_points):
            node = dict()
            geom: QgsGeometry = features[feature_index].geometry()
            point: QgsPointXY = geom.asPoint()
            node['feature'] = features[feature_index]
            node['feature_index'] = feature_index
            node['geometry'] = geom
            node['x'] = point.x()
            node['y'] = point.y()
            graph.add_node(feature_index, **node)
        distance_matrix: List[List[float]] = [[0 for x in range(num_points)] for y in range(num_points)]
        for node_a_index in range(num_points):
            node_a_attrs = graph.nodes[node_a_index]
            for node_b_index in range(node_a_index + 1, num_points):
                node_b_attrs = graph.nodes[node_b_index]
                distance: float = node_a_attrs['geometry'].distance(node_b_attrs['geometry'])
                distance_matrix[node_a_index][node_b_index] = distance
                distance_matrix[node_b_index][node_a_index] = distance
                if distance < self.radius * math.sqrt(3):
                    graph.add_edge(node_a_index, node_b_index, weight=distance)
        # Create the subgraphs
        connected_subgraphs: List[Graph] = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
        print("Subgraphs: ", len(connected_subgraphs))
        # Find cliques for all connected subgraphs
        subgraph_id = 0
        lines: List[Tuple[float, float, float, float, int]] = list()
        clique_id = 0
        for subgraph in connected_subgraphs:
            # Find all cliques and store them in reverse order (max len to min)
            print("Subgraph: ", subgraph_id)
            covered_nodes = set()
            len_subgraph = len(subgraph)
            # print("Subgraph nodes: ", [node for node, attrs in subgraph.nodes.items()])
            # print("Fids: ", [attrs['feature'].attributes()[0] for node, attrs in subgraph.nodes.items()])
            max_independent = approx.maximum_independent_set(subgraph)
            print("independent ", max_independent)
            all_cliques = list()
            for independent in max_independent:
                cliques = list(nx.find_cliques(subgraph, [independent]))
                all_cliques.extend(cliques)
                # print("find_cliques returned ", len(cliques), " cliques")
                # print("cliques: ", cliques)
                for clique in cliques:
                    for i in range(len(clique)):
                        x_i = subgraph.nodes[clique[i]]['x']
                        y_i = subgraph.nodes[clique[i]]['y']
                        for j in range(len(clique)):
                            if i != j:
                                x_j = subgraph.nodes[clique[j]]['x']
                                y_j = subgraph.nodes[clique[j]]['y']
                                lines.append((x_i, y_i, x_j, y_j, clique_id))
                    clique_id += 1
            for node in subgraph.nodes:
                found = False
                for clique in all_cliques:
                    if node in clique:
                        found = True
                        break
                if not found:
                    cliques = list(nx.find_cliques(subgraph, [node]))
                    all_cliques.extend(cliques)
                    # print("find_cliques returned ", len(cliques), " cliques")
                    # print("cliques: ", cliques)
                    for clique in cliques:
                        for i in range(len(clique)):
                            x_i = subgraph.nodes[clique[i]]['x']
                            y_i = subgraph.nodes[clique[i]]['y']
                            for j in range(len(clique)):
                                if i != j:
                                    x_j = subgraph.nodes[clique[j]]['x']
                                    y_j = subgraph.nodes[clique[j]]['y']
                                    lines.append((x_i, y_i, x_j, y_j, clique_id))
                        clique_id += 1
            num_rows = len_subgraph
            num_columns = len(all_cliques)
            graph_node_to_or_id: Dict[int, int] = dict()
            or_id_to_graph_node: Dict[int, int] = dict()
            node_id = 0
            for clique in all_cliques:
                for node in clique:
                    if node not in graph_node_to_or_id:
                        or_id_to_graph_node[node_id] = node
                        graph_node_to_or_id[node] = node_id
                        node_id += 1
            # print(graph_node_to_or_id)
            # print(or_id_to_graph_node)
            problem_matrix: List[List[int]] = [[0 for x in range(num_columns)] for y in range(num_rows)]
            # print(problem_matrix)
            for column_index in range(len(all_cliques)):
                for node in all_cliques[column_index]:
                    # print(column_index, graph_node_to_or_id[node])
                    problem_matrix[graph_node_to_or_id[node]][column_index] = 1
                    # print(problem_matrix)
            print(problem_matrix)
            solver = pywraplp.Solver.CreateSolver("SCIP")
            if not solver:
                return
            selected_columns = [None for x in range(num_columns)]
            for i in range(num_columns):
                selected_columns[i] = solver.IntVar(0, 1, "")
            for i in range(num_rows):
                solver.Add(solver.Sum(selected_columns[j] * problem_matrix[i][j] for j in range(num_columns)) >= 1)
            objective = []
            for i in range(num_columns):
                objective.append(selected_columns[i] * 1)
            solver.Minimize(solver.Sum(selected_columns))
            status = solver.Solve()
            if status == pywraplp.Solver.OPTIMAL:
                print("Optimal solution found: ", [col.solution_value() for col in selected_columns])
            elif status == pywraplp.Solver.FEASIBLE:
                print("Feasible solution found: ", [col.solution_value() for col in selected_columns])
            else:
                print("Solution not found")
            for i in range(num_columns):
                if selected_columns[i].solution_value() == 1:
                    clique = all_cliques[i]
                    xs = list()
                    ys = list()
                    for node in clique:
                        node_attribs = subgraph.nodes[node]
                        xs.append(node_attribs['x'])
                        ys.append(node_attribs['y'])
                        points.append((node_attribs['x'], node_attribs['y'], point_id, clique_id))
                        point_id += 1
                    min_x = min(xs)
                    max_x = max(xs)
                    min_y = min(ys)
                    max_y = max(ys)
                    # Compute the center of the bounding box
                    center_x = (min_x + max_x) / 2
                    center_y = (min_y + max_y) / 2
                    disks.append((center_x, center_y, clique_id))
                    clique_id += 1

            subgraph_id += 1

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "cliques", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("clique_id", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for line in lines:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(line[0], line[1]), QgsPointXY(line[2], line[3])]))
            feat.setAttributes([fid, line[4]])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "disks", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("clique", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for disk in disks:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(self.__interpolate_circle(QgsPointXY(disk[0], disk[1]), self.radius)))
            feat.setAttributes([fid, disk[2]])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

    def __on_step_7(self) -> None:
        """
        TODO: Describe

        :return: None
        """
        # Get current layer
        layer: QgsVectorLayer = self.iface.activeLayer()
        # Get the features
        features: List[QgsFeature] = list(layer.getFeatures())
        point_id = 0
        clique_id = 0
        points: List[Tuple[float, float, int, int]] = list()
        disks: List[Tuple[float, float, int]] = list()
        # Remove same locations point
        remove = list()
        for x in range(len(features)):
            for y in range(x + 1, len(features)):
                geom_a: QgsGeometry = features[x].geometry()
                geom_b: QgsGeometry = features[y].geometry()
                distance: float = geom_a.distance(geom_b)
                if distance < 0.5:
                    remove.append(x)
        for i in sorted(list(remove), reverse=True):
            del features[i]
        # Build the graph
        graph: Graph = nx.Graph()
        for feature_index in range(len(features)):
            node = dict()
            geom: QgsGeometry = features[feature_index].geometry()
            point: QgsPointXY = geom.asPoint()
            node['feature'] = features[feature_index]
            node['feature_id'] = features[feature_index].attribute('id')
            node['geometry'] = geom
            node['x'] = point.x()
            node['y'] = point.y()
            graph.add_node(feature_index, **node)
        for node_a_index in range(len(features)):
            node_a_attrs = graph.nodes[node_a_index]
            for node_b_index in range(node_a_index + 1, len(features)):
                node_b_attrs = graph.nodes[node_b_index]
                distance: float = node_a_attrs['geometry'].distance(node_b_attrs['geometry'])
                if distance < self.radius * 2:
                    graph.add_edge(node_a_index, node_b_index, weight=distance)
        # Create the subgraphs
        connected_subgraphs: List[Graph] = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
        # Remove subgraphs with cardinality 1 or 2 and add them to the disks list
        remove = list()
        for i in range(len(connected_subgraphs)):
            if len(connected_subgraphs[i]) == 1:
                nodes = connected_subgraphs[i].nodes.items()
                for node_id, node_attribs in nodes:
                    disks.append((node_attribs['x'], node_attribs['y'], clique_id))
                    points.append((node_attribs['x'], node_attribs['y'], point_id, clique_id))
                    point_id += 1
                    clique_id += 1
                    remove.append(node_attribs['feature_id'])
            elif len(connected_subgraphs[i]) == 2:
                nodes = connected_subgraphs[i].nodes.items()
                nodes_attribs = [node_attribs for node_id, node_attribs in nodes]
                disks.append(((nodes_attribs[0]['x'] + nodes_attribs[1]['x']) / 2, (nodes_attribs[0]['y'] + nodes_attribs[1]['y']) / 2, clique_id))
                points.append((nodes_attribs[0]['x'], nodes_attribs[0]['y'], point_id, clique_id))
                point_id += 1
                points.append((nodes_attribs[1]['x'], nodes_attribs[1]['y'], point_id, clique_id))
                point_id += 1
                clique_id += 1
                remove.append(nodes_attribs[0]['feature_id'])
                remove.append(nodes_attribs[1]['feature_id'])

        graph: Graph = nx.Graph()
        for feature_index in range(len(features)):
            if features[feature_index].attribute('id') not in remove:
                node = dict()
                geom: QgsGeometry = features[feature_index].geometry()
                point: QgsPointXY = geom.asPoint()
                node['feature'] = features[feature_index]
                node['feature_id'] = features[feature_index].attribute('id')
                node['geometry'] = geom
                node['x'] = point.x()
                node['y'] = point.y()
                graph.add_node(feature_index, **node)
        distance_limit: float = self.radius * math.sqrt(3)
        node_list = list(graph.nodes)
        for node_a_index in range(len(node_list)):
            node_a_attrs = graph.nodes[node_list[node_a_index]]
            for node_b_index in range(node_a_index + 1, len(node_list)):
                node_b_attrs = graph.nodes[node_list[node_b_index]]
                distance: float = node_a_attrs['geometry'].distance(node_b_attrs['geometry'])
                if distance < distance_limit:
                    graph.add_edge(node_list[node_a_index], node_list[node_b_index], weight=distance)
        # Create the subgraphs
        connected_subgraphs: List[Graph] = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
        # Find cliques for all connected subgraphs
        for subgraph in connected_subgraphs:
            max_cliques = list()
            for node in subgraph.nodes:
                cliques = list(nx.find_cliques(subgraph, [node]))
                max_cliques.extend(cliques)
            num_rows = len(subgraph)
            num_columns = len(max_cliques)
            graph_node_to_or_id: Dict[int, int] = dict()
            or_id_to_graph_node: Dict[int, int] = dict()
            node_id = 0
            for clique in max_cliques:
                for node in clique:
                    if node not in graph_node_to_or_id:
                        or_id_to_graph_node[node_id] = node
                        graph_node_to_or_id[node] = node_id
                        node_id += 1
            coverage_matrix: List[List[int]] = [[0 for x in range(num_columns)] for y in range(num_rows)]
            decision_variables = [None for x in range(num_columns)]
            for column_index in range(len(max_cliques)):
                for node in max_cliques[column_index]:
                    coverage_matrix[graph_node_to_or_id[node]][column_index] = 1
            solver: Solver = pywraplp.Solver.CreateSolver("SCIP")
            if not solver:
                return
            for i in range(num_columns):
                decision_variables[i] = solver.IntVar(0, 1, "")
            for i in range(num_rows):
                solver.Add(solver.Sum(decision_variables[j] * coverage_matrix[i][j] for j in range(num_columns)) >= 1)
            solver.Minimize(solver.Sum(decision_variables))
            status = solver.Solve()
            if status == pywraplp.Solver.OPTIMAL:
                print("Optimal solution found: ", [col.solution_value() for col in decision_variables])
            elif status == pywraplp.Solver.FEASIBLE:
                print("Feasible solution found: ", [col.solution_value() for col in decision_variables])
            else:
                print("Solution not found")
            for i in range(num_columns):
                if decision_variables[i].solution_value() == 1:
                    clique = max_cliques[i]
                    points_to_find_circle: List[Tuple[float, float]] = list()
                    for node in clique:
                        node_attribs = subgraph.nodes[node]
                        points_to_find_circle.append((node_attribs['x'], node_attribs['y']))
                        points.append((node_attribs['x'], node_attribs['y'], point_id, clique_id))
                        point_id += 1
                    center = GisFIREDiskCover._compute_center(points_to_find_circle)
                    disks.append((center[0], center[1], clique_id))
                    clique_id += 1

        vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "disks", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("clique", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for disk in disks:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(self.__interpolate_circle(QgsPointXY(disk[0], disk[1]), self.radius)))
            feat.setAttributes([fid, disk[2]])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

        vector_layer: QgsVectorLayer = QgsVectorLayer("point", "points", "memory")
        provider: QgsVectorDataProvider = vector_layer.dataProvider()
        provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("point", QVariant.Int), QgsField("clique", QVariant.Int)])
        vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
        fid = 1
        for point in points:
            feat: QgsFeature = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point[0], point[1])))
            feat.setAttributes([fid, point[2], point[3]])
            fid += 1
            provider.addFeatures([feat])
        vector_layer.updateExtents()
        current_project: QgsProject = QgsProject()
        vector_layer.setCrs(current_project.instance().crs())
        current_project.instance().addMapLayer(vector_layer, True)

    @staticmethod
    def _compute_center(points: List[Tuple[float, float]]) -> Tuple[float, float]:
        random.shuffle(points)
        circle = GisFIREDiskCover.__mec(points, len(points), [(0,0), (0, 0), (0, 0)], 0)
        return circle[0], circle[1]

    @staticmethod
    def __point_inside_circle(circle: Tuple[float, float, float], point: Tuple[float, float]) -> bool:
        return math.sqrt((point[0] - circle[0]) ** 2 + (point[1] - circle[1]) ** 2) < circle[2]

    @staticmethod
    def __compute_circle(a: Tuple[float, float], b: Optional[Tuple[float, float]] = None, c: Tuple[float, float] = None) -> Tuple[float, float, float]:
        if b is not None and c is not None:
            aa = b[0] - a[0]
            bb = b[1] - a[1]
            cc = c[0] - a[0]
            dd = c[1] - a[1]
            ee = aa * (b[0] + a[0]) * 0.5 + bb * (b[1] + a[1]) * 0.5
            ff = cc * (c[0] + a[0]) * 0.5 + dd * (c[1] + a[1]) * 0.5
            det = aa * dd - bb * cc
            cx = (dd * ee - bb * ff) / det
            cy = (-cc * ee + aa * ff) / det
            return cx, cy, math.sqrt((a[0] - cx) ** 2 + (a[1] - cy) ** 2)
        elif b is not None and c is None:
            return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) / 2
        else:
            return a[0], a[1], 0

    @staticmethod
    def __mec(points: List[Tuple[float, float]], n: int, boundary: List[Tuple[float, float]], b: int) -> Tuple[float, float, float]:
        circle: Tuple[float, float, float]
        if b == 3:
            circle = GisFIREDiskCover.__compute_circle(boundary[0], boundary[1], boundary[2])
        elif n == 1 and b == 0:
            circle = GisFIREDiskCover.__compute_circle(points[0])
        elif n == 0 and b == 2:
            circle = GisFIREDiskCover.__compute_circle(boundary[0], boundary[1])
        elif n == 1 and b == 1:
            circle = GisFIREDiskCover.__compute_circle(boundary[0], points[0])
        else:
            circle = GisFIREDiskCover.__mec(points, n - 1, boundary, b)
            if not GisFIREDiskCover.__point_inside_circle(circle, points[n-1]):
                boundary[b] = points[n-1]
                b += 1
                circle = GisFIREDiskCover.__mec(points, n - 1, boundary, b)
        return circle