#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path
import math
import copy
import itertools
import time
import random

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtCore import QTranslator
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QMenu
from qgis.PyQt.QtWidgets import QDialog

import qgis.utils
from qgis.core import QgsMapLayer
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
from typing import Union

from .resources import *  # noqa
from .ui.dialogs.disk_cover_algorithm import DlgDiskCoverAlgorithm
from .algorithms.helpers import order_x
from .algorithms.helpers import remove_duplicates
from .algorithms.set_cover import export_to_ampl_all_cliques_incremental_segmented
from .algorithms.set_cover import isolated
from .algorithms.set_cover import naive
from .algorithms.set_cover import greedy_naive
from .algorithms.set_cover import greedy_cliques
from .algorithms.set_cover import max_cliques_ortools_scip
from .algorithms.set_cover import max_cliques_ampl
from .algorithms.set_cover import ip_complete_cliques
from .algorithms.set_cover import aprox_hochbaum_mass
from .algorithms.set_cover import aprox_biniaz_et_al
from .algorithms.set_cover_multiprocessing import multics
from .helpers.geometry import interpolate_circle

bases_bombers_cat = [
    ["Sabadell",425257,4597293],
    ["Olot",456606,4671049],
    ["Manresa",404564,4621746],
    ["Girona",483939,4645337],
    ["Lleida",300438,4610849],
    ["Ullastrell",414179,4597526],
    ["Tarragona",347859,4555183],
    ["Calaf",377521,4620906],
    ["Orriols",492075,4664450],
    ["Maçanet",479414,4625308],
    ["Balaguer",317693,4629868],
    ["Tiurana",355626,4648365],
    ["Dosrius",453859,4607609],
    ["Òdena",387651,4604814],
    ["Montmell",380126,4579833],
    ["Garraf",409134,4569740],
    ["Móra d'Ebre",300924,4551070],
]

class GisFIRELightnings:
    """
    GisFIRE Lightnings QGIS plugin implementation

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

        # Create algorithm members
        self._default_radius = 1000

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
        # Disk Cover
        action = QAction(
            QIcon(':/gisfire_lightnings/disks.png'),
            self.tr('GisFIRE Disk Cover'),
            None
        )
        action.triggered.connect(self.__on_disk_cover)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Disk Cover'))
        action.setWhatsThis(self.tr('GisFIRE Disk Cover'))
        self._toolbar.addAction(action)
        self._toolbar_actions['disk_cover'] = action
        # Storms
        action = QAction(
            QIcon(':/gisfire_lightnings/storms.png'),
            self.tr('GisFIRE Storms'),
            None
        )
        action.triggered.connect(self.__on_storms)
        action.setEnabled(True)
        action.setCheckable(False)
        action.setStatusTip(self.tr('GisFIRE Storms'))
        action.setWhatsThis(self.tr('GisFIRE Storms'))
        self._toolbar.addAction(action)
        self._toolbar_actions['storms'] = action

    def __add_menu_actions(self):
        """
        Creates the menu entries that allow GisFIRE procedures.
        """
        # Disk Cover
        action: QAction = self._menu.addAction(self.tr('Disk Cover'))
        action.setIcon(QIcon(':/gisfire_lightnings/disks.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_disk_cover)
        self._menu_actions['disk_cover'] = action
        # Storms
        action: QAction = self._menu.addAction(self.tr('Storms'))
        action.setIcon(QIcon(':/gisfire_lightnings/storms.png'))
        action.setIconVisibleInMenu(True)
        action.triggered.connect(self.__on_storms)
        self._menu_actions['storma'] = action

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
        # Create lightning menu
        self._menu = QMenu(self.tr(u'Lightnings'), self._menu_gisfire)
        self._menu.setIcon(QIcon(':/gisfire_lightnings/disks.png'))
        self._menu_gisfire.addMenu(self._menu)
        # Set up the toolbar for lightnings plugin
        self._toolbar = self.iface.addToolBar(u'GisFIRE Lightnings')
        self._toolbar.setObjectName(u'GisFIRE Lightnings')

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

    def __on_disk_cover(self):
        """
        """
        dlg = DlgDiskCoverAlgorithm(self.iface.mainWindow())
        result = dlg.exec_()
        if result == QDialog.Accepted:
            # Get current layer
            layer: Union[QgsMapLayer, QgsVectorLayer] = self.iface.activeLayer()
            # Get the features
            points: List[Dict[str, Any]] = list()
            features: List[QgsFeature] = list(layer.getFeatures())
            for i, feature in enumerate(features):
                geom: QgsGeometry = feature.geometry()
                pt: QgsPointXY = geom.asPoint()
                point = {
                    'fid': feature.id(),
                    'id': i,
                    'x': pt.x(),
                    'y': pt.y()
                }
                points.append(point)
            points, _ = order_x(points)
            points, _, _ = remove_duplicates(points)
            selected_algorithm = dlg.algorithm
            if selected_algorithm == 0: # Remove isolated lightnings
                disks, covered_points, _ = isolated(points, self._default_radius)
            elif selected_algorithm == 1: # Naive
                disks, covered_points, _ = naive(points, self._default_radius)
            elif selected_algorithm == 2: # Greedy Naive
                disks, covered_points, _ = greedy_naive(points, self._default_radius)
            elif selected_algorithm == 3: # Greedy Cliques
                disks, covered_points, _ = greedy_cliques(points, self._default_radius)
            elif selected_algorithm == 4:  # IP Max Cliques
                disks, covered_points, _ = max_cliques_ortools_scip(points, self._default_radius)
            elif selected_algorithm == 5:  # IP All Cliques
                disks, covered_points, _ = ip_complete_cliques(points, self._default_radius)
            elif selected_algorithm == 6:  # Hochbaumm Mass
                squares, disks, covered_points, _ = aprox_hochbaum_mass(points, self._default_radius * 2, 2)
                vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "surfaces", "memory")
                provider: QgsVectorDataProvider = vector_layer.dataProvider()
                provider.addAttributes([QgsField("fid", QVariant.Int)])
                vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
                fid = 1
                for square in squares:
                    feat: QgsFeature = QgsFeature()
                    surface_points = [
                        QgsPointXY(square['top_left_x'], square['top_left_y']),
                        QgsPointXY(square['top_left_x'], square['bottom_right_y']),
                        QgsPointXY(square['bottom_right_x'], square['bottom_right_y']),
                        QgsPointXY(square['bottom_right_x'], square['top_left_y']),
                        QgsPointXY(square['top_left_x'], square['top_left_y'])
                    ]
                    feat.setGeometry(QgsGeometry.fromPolylineXY(surface_points))
                    feat.setAttributes([fid])
                    fid += 1
                    provider.addFeatures([feat])
                vector_layer.updateExtents()
                current_project: QgsProject = QgsProject()
                vector_layer.setCrs(current_project.instance().crs())
                current_project.instance().addMapLayer(vector_layer, True)
            elif selected_algorithm == 7:  # IP All Cliques
                disks, covered_points, _ = aprox_biniaz_et_al(points, self._default_radius)
            elif selected_algorithm == 8:  # Max Cliques using AMPL + CPLEX
                disks, covered_points, _ = max_cliques_ampl(points, self._default_radius)
            elif selected_algorithm == 9: # Export AMPL
                squares, covered_points, _ = export_to_ampl_all_cliques_incremental_segmented(points, self._default_radius, bases_bombers_cat)
                vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "surfaces", "memory")
                provider: QgsVectorDataProvider = vector_layer.dataProvider()
                provider.addAttributes([QgsField("fid", QVariant.Int)])
                vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
                fid = 1
                for square in squares:
                    feat: QgsFeature = QgsFeature()
                    surface_points = [
                        QgsPointXY(square['top_left_x'], square['top_left_y']),
                        QgsPointXY(square['top_left_x'], square['bottom_right_y']),
                        QgsPointXY(square['bottom_right_x'], square['bottom_right_y']),
                        QgsPointXY(square['bottom_right_x'], square['top_left_y']),
                        QgsPointXY(square['top_left_x'], square['top_left_y'])
                    ]
                    feat.setGeometry(QgsGeometry.fromPolylineXY(surface_points))
                    feat.setAttributes([fid])
                    fid += 1
                    provider.addFeatures([feat])
                vector_layer.updateExtents()
                current_project: QgsProject = QgsProject()
                vector_layer.setCrs(current_project.instance().crs())
                current_project.instance().addMapLayer(vector_layer, True)
            vector_layer: QgsVectorLayer = QgsVectorLayer("linestring", "disks", "memory")
            provider: QgsVectorDataProvider = vector_layer.dataProvider()
            provider.addAttributes([QgsField("fid", QVariant.Int), QgsField("covers", QVariant.String)])
            vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
            print(len(disks))
            for disk in disks:
                feat: QgsFeature = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPolylineXY(interpolate_circle(QgsPointXY(disk['x'], disk['y']), self._default_radius)))
                feat.setAttributes([disk['id'], ','.join(map(str, disk['covers'].keys()))])
                provider.addFeatures([feat])
            vector_layer.updateExtents()
            current_project: QgsProject = QgsProject()
            vector_layer.setCrs(current_project.instance().crs())
            current_project.instance().addMapLayer(vector_layer, True)

            vector_layer: QgsVectorLayer = QgsVectorLayer("point", "points", "memory")
            provider: QgsVectorDataProvider = vector_layer.dataProvider()
            provider.addAttributes(
                [QgsField("fid", QVariant.Int), QgsField("point", QVariant.Int), QgsField("covered_by", QVariant.String)])
            vector_layer.updateFields()  # tell the vector layer to fetch changes from the provider
            fid = 1
            for point in covered_points:
                feat: QgsFeature = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point['x'], point['y'])))
                feat.setAttributes([fid, point['id'], ','.join(map(str, point['covered_by'].keys()))])
                fid += 1
                provider.addFeatures([feat])
            vector_layer.updateExtents()
            current_project: QgsProject = QgsProject()
            vector_layer.setCrs(current_project.instance().crs())
            current_project.instance().addMapLayer(vector_layer, True)


    def __on_storms(self) -> None:
        """

        Returns
        -------

        """
        dlg = DlgDiskCoverAlgorithm(self.iface.mainWindow())
        result = dlg.exec_()