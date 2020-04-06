from qgis.core import QgsFeature
from qgis.core import QgsPointXY
from qgis.core import QgsGeometry
from qgis.core import QgsSpatialIndex
from qgis.core import QgsFeatureRequest
from qgis.core import QgsProcessingFeedback
from qgis.core import QgsApplication
from qgis.core import QgsVectorLayer
from qgis.core import QgsProject
from qgis.core import QgsExpressionContextUtils
from qgis.core import QgsExpressionContextScope
from qgis.core import QgsField
from qgis.core import QgsVectorFileWriter
from qgis.analysis import QgsNativeAlgorithms
from processing.core.Processing import Processing
import processing

from PyQt5.QtCore import QVariant

from .ROS import ros
from .Ellipse import Alexander

from ..Helper.Layers import CreateLayer
from ..Helper.Layers import LayerToGeoPackage
from ..Helper.Layers import LoadLayer


from datetime import datetime
from datetime import timedelta
from numpy import arange
import numpy
from math import sin, cos, atan
from math import sqrt
from itertools import product
import random

Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

def ceilToTimeStep(dt, delta):
    return dt + (datetime.min - dt) % timedelta(seconds=delta)

class IgnitionPoint:

    def __init__(self, feat, x, y, dt):
        self._feat = feat
        self._x = x
        self._y = y
        self._dt = dt
        self._windSpeed = 0
        self._windDirection = 0
        self._fuelModel = '1'
        self._slope = 0
        self._aspect = 0

    def __lt__(self, other):
        return self._dt < other._dt

    def __gt__(self, other):
        return self._dt > other._dt

    def __le__(self, other):
        return self._dt <= other._dt

    def __ge__(self, other):
        return self._dt >= other._dt

    @property
    def feature(self):
        return self._feat

    @feature.setter
    def feature(self, value):
        self._feat = value

    @feature.deleter
    def feature(self):
        del self._feat

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        self._x = value

    @x.deleter
    def x(self):
        del self._x

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        self._y = value

    @y.deleter
    def y(self):
        del self._y

    @property
    def dt(self):
        return self._dt

    @dt.setter
    def dt(self, value):
        self._dt = value

    @dt.deleter
    def dt(self):
        del self._dt

    @property
    def fuelModel(self):
        return self._fuelModel

    @fuelModel.setter
    def fuelModel(self, value):
        self._fuelModel = value

    @fuelModel.deleter
    def fuelModel(self):
        del self._fuelModel


class SpreadSimulator:

    def __init__(self):
        self._timeStep = 30
        self._initialSampling = 100
        self._ignition_layer = None
        self._perimeter_layer = None
        self._fuel_layer = None
        self._tnow = datetime.now()

    @property
    def timeStep(self):
        return self._timeStep

    @timeStep.setter
    def timeStep(self, value):
        self._timeStep = value

    @timeStep.deleter
    def timeStep(self):
        del self._timeStep

    @property
    def ignitionLayer(self):
        return self._ignition_layer

    @ignitionLayer.setter
    def ignitionLayer(self, value):
        self._ignition_layer = value

    @ignitionLayer.deleter
    def ignitionLayer(self):
        del self._ignition_layer

    @property
    def perimeterLayer(self):
        return self._perimeter_layer

    @perimeterLayer.setter
    def perimeterLayer(self, value):
        self._perimeter_layer = value

    @perimeterLayer.deleter
    def perimeterLayer(self):
        del self._perimeter_layer

    @property
    def fuelLayer(self):
        return self._fuel_layer

    @fuelLayer.setter
    def fuelLayer(self, value):
        self._fuel_layer = value

    @fuelLayer.deleter
    def fuelLayer(self):
        del self._fuel_layer

    def initilizeSimulation(self):
        """Initialize the internal variables to perform a simulation and
        normalize the ignition layer points time to ceilling to the next time
        step modifying the layer values."""
        # get points from layer
        if self._ignition_layer.startEditing():
            for feat in self._ignition_layer.getFeatures():
                dt = ceilToTimeStep(datetime.strptime(feat.attributes()[1], '%Y-%m-%dT%H:%M:%S'), self._timeStep)
                self._ignition_layer.changeAttributeValue(feat.id(), 1, dt.strftime('%Y-%m-%dT%H:%M:%S'))
            #end for
            self._ignition_layer.commitChanges()
        #end if
        # Convert points to Ignition Point, sort and calculate starting simulation time
        points = [IgnitionPoint(feat, feat.geometry().asPoint().x(), feat.geometry().asPoint().y(), datetime.strptime(feat.attributes()[1], '%Y-%m-%dT%H:%M:%S')) for feat in self._ignition_layer.getFeatures()]
        points.sort()
        self._tnow = points[0].dt

    def _assignFuel(self, points):
        index = QgsSpatialIndex()
        for feat in self._fuel_layer.getFeatures():
            index.addFeature(feat)
        intersecting_fuels = dict()
        intersecting_points = list()
        for pt in points:
            pt.fuelModel = '1'
            geom = pt.feature.geometry()
            intersects = index.intersects(geom.boundingBox())
            if len(intersects) > 0:
                request = QgsFeatureRequest()
                request.setFilterFids([intersects[0]])
                fuels = [f for f in self._fuel_layer.getFeatures(request)]
                for fuel in fuels:
                    if not fuel.id() in intersecting_fuels:
                        intersecting_fuels[fuel.id()] = fuel
                intersecting_points.append(pt)
        if len(intersecting_fuels) > 0:
            for pt in intersecting_points:
                for k, feat in intersecting_fuels.items():
                    if feat.geometry().contains(pt.feature.geometry()):
                        pt.fuelModel = feat.attributes()[1]
                        break

    def _ignitePoints(self, layer):
        # get ignition points to ignite now and udtae list
        points = [IgnitionPoint(feat, feat.geometry().asPoint().x(), feat.geometry().asPoint().y(), datetime.strptime(feat.attributes()[1], '%Y-%m-%dT%H:%M:%S')) for feat in self._ignition_layer.getFeatures()]
        points_to_ignite = [pt for pt in points if pt.dt == self._tnow]
        self._assignFuel(points_to_ignite)
        for pt in points_to_ignite:
            perimeter_outer = self._computeElipseFromPoint(pt)
            if len(perimeter_outer) > 0:
                points_outer = [QgsPointXY(pt[0], pt[1]) for pt in perimeter_outer]
                new_perimeter = [points_outer]
                self._addPerimeterToLayer(layer, new_perimeter)

    def _addPerimeterToLayer(self, layer, perimeter):
        feat = QgsFeature()
        geom = QgsGeometry.fromPolygonXY(perimeter)
        feat.setGeometry(geom)
        (res, outFeats) = layer.dataProvider().addFeatures([feat])

    def _computeElipseFromPoint(self, pt):
        if pt.fuelModel == '0':
            return list()
        (rate, alpha, Ue) = ros(pt.fuelModel, [[0.03,0.03,0.03],[0.45,0.82]], [1, numpy.radians(-30)], 0)
        (a, b, c) = Alexander(rate / 60, Ue)
        dt = self._timeStep
        ds = (2 * numpy.pi) / self._initialSampling
        ids = arange(0, 2 * numpy.pi, ds)
        points = [(dt * a * cos(ids), dt * b * sin(ids) + dt * c) for ids in arange(0, 2 * numpy.pi, ds)]
        points = [(p[0] * cos(alpha) - p[1] * sin(alpha), p[0] * sin(alpha) + p[1] * cos(alpha)) for p in points]
        points = [(p[0] + pt.x, p[1] + pt.y) for p in points]
        return points

    def _ignitePerimeters(self, layer):
        perimeters = self._perimeter_layer.getFeatures()
        perimeters_features = [f for f in perimeters if f.attributes()[1] == self._tnow.strftime('%Y-%m-%dT%H:%M:%S')]
        perimeters = list()
        for perimeter_feature in perimeters_features:
            new_perimeter = list()
            geom = perimeter_feature.geometry().asPolygon()
            points = list()
            for pt in geom[0]:
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
                ip = IgnitionPoint(feat, pt.x(), pt.y(), self._tnow.strftime('%Y-%m-%dT%H:%M:%S'))
                points.append(ip)
            self._assignFuel(points)
            new_points = self._propagatePerimeter(points[-2::-1])
            new_perimeter.append([QgsPointXY(pt[0], pt[1]) for pt in new_points])
            if len(geom) > 1:
                for i in range(1, len(geom)):
                    points = list()
                    for pt in geom[i]:
                        feat = QgsFeature()
                        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
                        ip = IgnitionPoint(feat, pt.x(), pt.y(), self._tnow.strftime('%Y-%m-%dT%H:%M:%S'))
                        points.append(ip)
                    self._assignFuel(points)
                    new_points = self._propagatePerimeter(points[-2::-1])
                    new_perimeter.append([[QgsPointXY(pt[0], pt[1]) for pt in new_points], geom[i]])
            perimeters.append(new_perimeter)
        for perimeter in perimeters:
            # Create a line layer to calculate rings
            layer_in = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'outer_perimeter')
            self._addPerimeterToLayer(layer_in, [perimeter[0]])
            params = {'INPUT': layer_in, 'OUTPUT': 'memory:'}
            feedback = QgsProcessingFeedback()
            result = processing.run('native:fixgeometries', params, feedback=feedback, is_child_algorithm=False)
            fixed_layer = result['OUTPUT']
            params = {'INPUT': fixed_layer, 'OUTPUT': 'memory:'}
            feedback = QgsProcessingFeedback()
            result = processing.run('native:polygonstolines', params, feedback=feedback, is_child_algorithm=False)
            line_layer = result['OUTPUT']
            params = {'INPUT': line_layer, 'LINES': line_layer, 'OUTPUT': 'memory:'}
            feedback = QgsProcessingFeedback()
            result = processing.run('native:splitwithlines', params, feedback=feedback, is_child_algorithm=False)
            split_layer = result['OUTPUT']
            params = {'INPUT': split_layer, 'OUTPUT': 'memory:'}
            feedback = QgsProcessingFeedback()
            result = processing.run('qgis:linestopolygons', params, feedback=feedback, is_child_algorithm=False)
            polygon_layer = result['OUTPUT']
            params = {'INPUT': polygon_layer, 'OUTPUT': 'memory:'}
            feedback = QgsProcessingFeedback()
            result = processing.run('native:multiparttosingleparts', params, feedback=feedback, is_child_algorithm=False)
            correct_plygons = result['OUTPUT']
            island_layer = None
            if correct_plygons.featureCount() > 1:
                island_layer = self._findRing(correct_plygons)
            #params = {'INPUT': polygon_layer, 'OUTPUT': 'memory:'}
            #feedback = QgsProcessingFeedback()
            #result = processing.run('native:dissolve', params, feedback=feedback, is_child_algorithm=False)
            #dissolved_layer = result['OUTPUT']
            #if island_layer is None:
            #    params = {'INPUT': polygon_layer, 'OUTPUT': 'memory:'}
            #else:
            #    params = {'INPUT': island_layer, 'OUTPUT': 'memory:'}
            #feedback = QgsProcessingFeedback()
            #result = processing.run('native:multiparttosingleparts', params, feedback=feedback, is_child_algorithm=False)
            #correct_plygons = result['OUTPUT']
            if island_layer is None:
                rings_layer = correct_plygons
            else:
                rings_layer = island_layer
            feats = [f for f in rings_layer.getFeatures()]
            elements = feats[0].geometry().asPolygon()
            new_perimeter = list()
            for element in elements:
                new_perimeter.append([QgsPointXY(pt.x(), pt.y()) for pt in element])
            del(layer_in)
            del(fixed_layer)
            del(line_layer)
            del(split_layer)
            del(polygon_layer)
            if not (island_layer is None):
                del(island_layer)
            del(correct_plygons)
            if len(perimeter) > 1:
                for i in range(1, len(perimeter)):
                    # Create layer fromprevious perimeter
                    geom = perimeter[i][1]
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPolygonXY([geom]))
                    previous_ring = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'previous_ring')
                    previous_ring.dataProvider().addFeatures([feature])
                    actual_ring = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'actual_ring')
                    self._addPerimeterToLayer(actual_ring, [perimeter[i][0]])
                    params = {'INPUT': actual_ring, 'OUTPUT': 'memory:'}
                    feedback = QgsProcessingFeedback()
                    result = processing.run('native:fixgeometries', params, feedback=feedback, is_child_algorithm=False)
                    fixed_layer = result['OUTPUT']
                    params = {'INPUT': fixed_layer, 'OUTPUT': 'memory:'}
                    feedback = QgsProcessingFeedback()
                    result = processing.run('native:polygonstolines', params, feedback=feedback, is_child_algorithm=False)
                    line_layer = result['OUTPUT']
                    params = {'INPUT': line_layer, 'LINES': line_layer, 'OUTPUT': 'memory:'}
                    feedback = QgsProcessingFeedback()
                    result = processing.run('native:splitwithlines', params, feedback=feedback, is_child_algorithm=False)
                    split_layer = result['OUTPUT']
                    params = {'INPUT': split_layer, 'OUTPUT': 'memory:'}
                    feedback = QgsProcessingFeedback()
                    result = processing.run('qgis:linestopolygons', params, feedback=feedback, is_child_algorithm=False)
                    polygon_layer = result['OUTPUT']
                    params = {'INPUT': polygon_layer, 'PREDICATE': [6], 'INTERSECT': previous_ring, 'OUTPUT': 'memory:'}
                    feedback = QgsProcessingFeedback()
                    result = processing.run('native:extractbylocation', params, feedback=feedback, is_child_algorithm=False)
                    rings_inside = result['OUTPUT']
                    params = {'INPUT': rings_inside, 'OUTPUT': 'memory:'}
                    feedback = QgsProcessingFeedback()
                    result = processing.run('native:multiparttosingleparts', params, feedback=feedback, is_child_algorithm=False)
                    correct_rings = result['OUTPUT']
                    for feature in correct_rings.getFeatures():
                        geom = feature.geometry().asPolygon()
                        for elem in geom:
                            new_perimeter.append([QgsPointXY(pt.x(), pt.y()) for pt in elem])
                    del(previous_ring)
                    del(actual_ring)
                    del(fixed_layer)
                    del(line_layer)
                    del(split_layer)
                    del(rings_inside)
                    del(correct_rings)
            self._addPerimeterToLayer(layer, new_perimeter)

    def _findRing(self, layer):
        #find largest area polygon
        features = layer.getFeatures()
        max = 0
        max_feature = -1
        for feature in features:
            area = feature.geometry().area()
            if area > max:
                max = area
                max_feature = feature
        features = layer.getFeatures()
        max_geom = max_feature.geometry().asPolygon()
        rings = list()
        for feature in features:
            if feature.id() != max_feature.id():
                geom = feature.geometry().asPolygon()
                is_island = True
                for elem in list(product(max_geom[0], geom[0])):
                    if elem[0].x() == elem[1].x() and elem[0].y() == elem[1].y():
                        is_island = False
                        break
                if is_island:
                    rings.append(feature)
        new_layer = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'polygon_island')
        perimeter = list()
        for ring in rings:
            geom = ring.geometry().asPolygon()
            perimeter.append([QgsPointXY(pt.x(), pt.y()) for pt in geom[0]])
        perimeter.insert(0, [QgsPointXY(pt.x(), pt.y()) for pt in max_geom[0]])
        self._addPerimeterToLayer(new_layer, perimeter)
        return new_layer

    def _propagatePerimeter(self, perimeter):
        ds = (2 * numpy.pi) / len(perimeter)
        dt = self._timeStep
        dxij = list()
        dyij = list()
        xijp1_bar = list()
        yijp1_bar = list()
        for i in range(0, len(perimeter)):
            if perimeter[i].fuelModel != '0':
                (rate, alpha, Ue) = ros(int(perimeter[i].fuelModel), [[0.03,0.03,0.03],[0.45,0.82]], [1, numpy.radians(-30)], 0)
                alpha = -alpha
                (a, b, c) = Alexander(rate / 60, Ue)
                xij = perimeter[i].x
                yij = perimeter[i].y
                xs = (perimeter[(i+1)%len(perimeter)].x - perimeter[i-1].x) / (2 * ds)
                ys = (perimeter[(i+1)%len(perimeter)].y - perimeter[i-1].y) / (2 * ds)
                (xt, yt) = self.__FG(xs, ys, (a, b, c), alpha)
                dxij.append(dt * xt)
                dyij.append(dt * yt)
                xijp1_bar.append(xij + dt * xt)
                yijp1_bar.append(yij + dt * yt)
            else:
                dxij.append(0)
                dyij.append(0)
                xijp1_bar.append(perimeter[i].x)
                yijp1_bar.append(perimeter[i].y)
        dxij_bar = list()
        dyij_bar = list()
        new_perimeter = list()
        for i in range(0, len(perimeter)):
            if perimeter[i].fuelModel != '0':
                (rate, alpha, Ue) = ros(int(perimeter[i].fuelModel), [[0.03,0.03,0.03],[0.45,0.82]], [1, numpy.radians(-30)], 0)
                alpha = -alpha
                (a, b, c) = Alexander(rate / 60, Ue)
                xij = perimeter[i].x
                yij = perimeter[i].y
                xs = (xijp1_bar[(i+1)%len(perimeter)] - xijp1_bar[i-1]) / (2 * ds)
                ys = (yijp1_bar[(i+1)%len(perimeter)] - yijp1_bar[i-1]) / (2 * ds)
                if xs != 0 or ys != 0:
                    (xt, yt) = self.__FG(xs, ys, (a, b, c), alpha)
                    dxij_bar.append(dt * xt)
                    dyij_bar.append(dt * yt)
                    xijp1 = xij + 0.5 * (dxij[i] + dt * xt)
                    yijp1 = yij + 0.5 * (dyij[i] + dt * yt)
                    new_perimeter.append((xijp1, yijp1))
                else:
                    print("ERROR")
            else:
                dxij_bar.append(0)
                dyij_bar.append(0)
                new_perimeter.append((perimeter[i].x, perimeter[i].y))
        return new_perimeter

    def __FG(self, xs, ys, elipse, theta):
        (a, b, c) = elipse
        part1 = (a ** 2) * (cos(theta)) * (xs * sin(theta) + ys * cos(theta))
        part2 = (b ** 2) * (sin(theta)) * (xs * cos(theta) - ys * sin(theta))
        part3 = (b ** 2) * ((xs * cos(theta) - ys * sin(theta)) ** 2)
        part4 = (a ** 2) * ((xs * sin(theta) + ys * cos(theta)) ** 2)
        part5 = c * sin(theta)
        part6 = sqrt(part3 + part4)
        xt = ((part1 - part2) / (part6)) + part5
        part1 = (a ** 2) * (sin(theta)) * (xs * sin(theta) + ys * cos(theta))
        part2 = (b ** 2) * (cos(theta)) * (xs * cos(theta) - ys * sin(theta))
        part5 = c * cos(theta)
        yt = ((-part1 - part2) / (part6)) + part5
        return (xt, yt)

    #def _propagateInnerPerimeter(self, geometry):
    #    pass

    def _pointGeometryOperations(self, layer_in, layer_out):
        # Fix fixgeometries
        params = {'INPUT': layer_in, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:fixgeometries', params, feedback=feedback, is_child_algorithm=False)
        fixed_layer = result['OUTPUT']
        params = {'INPUT': fixed_layer, 'OUTPUT': 'memory:', 'FIELD': None}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:dissolve', params, feedback=feedback, is_child_algorithm=False)
        dissolved_layer = result['OUTPUT']
        params = {'INPUT': dissolved_layer, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:multiparttosingleparts', params, feedback=feedback, is_child_algorithm=False)
        singlepart_layer = result['OUTPUT']
        params = {'INPUT': singlepart_layer, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:forcerhr', params, feedback=feedback, is_child_algorithm=False)
        del(fixed_layer)
        del(dissolved_layer)
        del(singlepart_layer)
        self._deepCopyPolygonFeatures(result['OUTPUT'], layer_out)
        del(result['OUTPUT'])

    def _deepCopyPolygonFeatures(self, layer_in, layer_out):
        if layer_out.startEditing():
            feats = list()
            for f in layer_in.getFeatures():
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPolygonXY(f.geometry().asPolygon()))
                feats.append(feat)
            (res, outFeats) = layer_out.dataProvider().addFeatures(feats)
            layer_out.commitChanges()

    def _perimeterGeometryOperations(self, layer_in, layer_out):
        # Fix fixgeometries
        params = {'INPUT': layer_in, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:fixgeometries', params, feedback=feedback, is_child_algorithm=False)
        fixed_layer = result['OUTPUT']
        params = {'INPUT': fixed_layer, 'OUTPUT': 'memory:', 'FIELD': None}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:dissolve', params, feedback=feedback, is_child_algorithm=False)
        dissolved_layer = result['OUTPUT']
        params = {'INPUT': dissolved_layer, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:multiparttosingleparts', params, feedback=feedback, is_child_algorithm=False)
        singlepart_layer = result['OUTPUT']
        params = {'INPUT': singlepart_layer, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:forcerhr', params, feedback=feedback, is_child_algorithm=False)
        del(fixed_layer)
        del(dissolved_layer)
        del(singlepart_layer)
        self._deepCopyPolygonFeatures(result['OUTPUT'], layer_out)
        del(result['OUTPUT'])

    def _createMemoryLayer(self, type, crs_authid, name):
        return QgsVectorLayer(type + '?crs=' + crs_authid, name, 'memory')

    def resamplePerimeters(self, perimeters_to_update_layer):
        pass

    def _updatePerimeterLayer(self, layer_in):
        if self._perimeter_layer.startEditing():
            feats = list()
            for f in layer_in.getFeatures():
                feat = QgsFeature(self._perimeter_layer.fields())
                feat.setAttribute('date', (self._tnow + timedelta(seconds=self._timeStep)).strftime('%Y-%m-%dT%H:%M:%S'))
                feat.setGeometry(QgsGeometry.fromPolygonXY(f.geometry().asPolygon()))
                feats.append(feat)
            (res, outFeats) = self._perimeter_layer.dataProvider().addFeatures(feats)
            self._perimeter_layer.triggerRepaint()
            self._perimeter_layer.commitChanges()
            self._perimeter_layer.updateExtents()


    def _mergePerimeters(self, layer_1, layer_2):
        # Fix fixgeometries
        params = {'LAYERS': [layer_1, layer_2], 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:mergevectorlayers', params, feedback=feedback, is_child_algorithm=False)
        merged_layer = result['OUTPUT']
        params = {'INPUT': merged_layer, 'OUTPUT': 'memory:'}
        feedback = QgsProcessingFeedback()
        result = processing.run('native:multiparttosingleparts', params, feedback=feedback, is_child_algorithm=False)
        del(merged_layer)
        return result['OUTPUT']

    def _regridPerimeters(self, layer):
        T = 1
        layer_out = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'regridded')
        for feature in layer.getFeatures():
            new_feature = QgsFeature()
            new_geom = list()
            for geom in feature.geometry().asPolygon():
                geom = geom[:-1]
                while True:
                    new_geometry = list()
                    added = False
                    for i in range(0, len(geom)):
                        segments = list()
                        points = [geom[i - 2], geom[i - 1], geom[i], geom[(i + 1) % len(geom)]]
                        segments = [[points[0], points[1]], [points[1], points[2]], [points[2], points[3]]]
                        lk = sqrt(((points[1].x() - points[2].x()) ** 2) + ((points[1].y() - points[2].y()) ** 2))
                        theta_aux = list()
                        for k in range(0, 3):
                            if points[k].x() - points[k+1].x() != 0:
                                theta_aux.append(atan((points[k].y() - points[k+1].y()) / (points[k].x() - points[k+1].x())))
                            else:
                                theta_aux.append(numpy.pi / 2)
                        theta = list()
                        theta.append(theta_aux[1] - theta_aux[0])
                        theta.append(theta_aux[2] - theta_aux[1])
                        if (max(cos(theta[0] / 2), cos(theta[1] / 2)) > ((T / lk) ** 2)):
                            new_geometry.append(QgsPointXY((geom[i - 1].x() + geom[i].x()) / 2,(geom[i - 1].y() + geom[i].y()) / 2))
                            added = True
                        new_geometry.append(geom[i])
                    geom = new_geometry
                    if not added:
                        break
                new_geom.append(new_geometry)
            self._addPerimeterToLayer(layer_out, new_geom)
        return layer_out

    def step(self):
        # Ignite the points and store the new fire perimeters in a new layer
        point_perimeters = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'point_perimeters')
        self._ignitePoints(point_perimeters)
        # Update the point geometries to dissolve overlaping perimeters
        point_perimeters_corrected = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'point_perimeters_corrected')
        if point_perimeters.featureCount() > 0:
            self._pointGeometryOperations(point_perimeters, point_perimeters_corrected)
        # Propagate the perimeters
        new_perimeters = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'new_perimeters')
        self._ignitePerimeters(new_perimeters)
        # Update the perimeter geometries to dissolve overlaping perimeters
        new_perimeters_corrected = self._createMemoryLayer('Polygon', QgsProject.instance().crs().authid(), 'new_perimeters_corrected')
        if new_perimeters.featureCount() > 0:
            self._perimeterGeometryOperations(new_perimeters, new_perimeters_corrected)
        resulting_perimeters = self._mergePerimeters(point_perimeters_corrected, new_perimeters_corrected)
        regrided_perimeters = self._regridPerimeters(resulting_perimeters)
        self._updatePerimeterLayer(regrided_perimeters)
        # Delete temporary layers
        del(point_perimeters)
        del(point_perimeters_corrected)
        del(new_perimeters)
        del(new_perimeters_corrected)
        del(resulting_perimeters)
        del(regrided_perimeters)
        # Time increment
        self._tnow += timedelta(seconds=self._timeStep)
