from qgis.core import QgsFeature
from qgis.core import QgsPointXY
from qgis.core import QgsGeometry

from .ROS import ros
from .Ellipse import Alexander

from datetime import datetime
from datetime import timedelta
from numpy import arange
from numpy import sin, cos
import numpy

def ceilToTimeStep(dt, delta):
    return dt + (datetime.min - dt) % timedelta(seconds=delta)

class IgnitionPoint:

    def __init__(self, x, y, dt):
        self._x = x
        self._y = y
        self._dt = dt

    def __lt__(self, other):
        return self._dt < other._dt

    def __gt__(self, other):
        return self._dt > other._dt

    def __le__(self, other):
        return self._dt <= other._dt

    def __ge__(self, other):
        return self._dt >= other._dt

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

class SpreadSimulator:

    def __init__(self):
        self._timeStep = 30
        self._initialSampling = 400
        self._ignition_layer = None
        self._perimeter_layer = None
        self._ignition_points = []
        self._fire_perimeters = []
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

    def initilizeSimulation(self):
        # get points from layer
        points = list(self._ignition_layer.getFeatures())
        # Convert points to Ignition Point, ceil time to interval and then sort
        self._ignition_points = [IgnitionPoint(feat.geometry().asPoint().x(), feat.geometry().asPoint().y(), ceilToTimeStep(datetime.strptime(feat.attributes()[1], '%Y-%m-%dT%H:%M:%S'), self._timeStep)) for feat in points]
        self._ignition_points.sort()
        # Initialize simulation time
        self._tnow = self._ignition_points[0].dt

    def ignitePoints(self):
        # get ignition points to ignite now and udtae list
        points_to_ignite = [pt for pt in self._ignition_points if pt.dt = self._tnow]
        self._ignition_points = [pt for pt in self._ignition_points if pt.dt > self._tnow]
        for pt in points_to_ignite:
            perimeter = self.computeElipseFromPoint(pt)
            self.addPerimeterToLayer(perimeter)

    def addPerimeterToLayer(self, perimeter):
        feat = QgsFeature(self._perimeter_layer.fields())
        feat.setAttribute('date', (self._tnow + timedelta(seconds=self._timeStep)).strftime('%Y-%m-%dT%H:%M:%S'))
        points = [QgsPointXY(pt[0], pt[1]) for pt in perimeter]
        feat.setGeometry(QgsGeometry.fromPolygonXY([points]))
        (res, outFeats) = self._perimeter_layer.dataProvider().addFeatures([feat])
        self._perimeter_layer.updateExtents()
        self._perimeter_layer.triggerRepaint()


    def computeElipseFromPoint(self, pt):
        (rate, alpha, Ue) = ros(1, [[0.03,0.03,0.03],[0.45,0.82]], [1, numpy.radians(-30)], 0)
        (a, b, c) = Alexander(rate / 60, Ue)
        dt = self._timeStep
        ds = numpy.pi / self._initialSampling
        ids = arange(0, 2 * numpy.pi, ds)
        points = [(dt * a * cos(ids), dt * b * sin(ids) + dt * c) for ids in arange(0, 2 * numpy.pi, ds)]
        points = [(p[0] * cos(alpha) - p[1] * sin(alpha), p[0] * sin(alpha) + p[1] * cos(alpha)) for p in points]
        points = [(p[0] + pt.x, p[1] + pt.y) for p in points]
        return points

    def ignitePerimeter(self):
        perimeters = self._perimeter_layer.getFeatures()
        perimeter_features = [f for f in perimeters if f.attributes()[1] == self._tnow.strftime('%Y-%m-%dT%H:%M:%S')]
        for perimeter_feature in perimeter_features:
            geom = perimeter_feature.geomety()
            #TODO

    def step(self):
        self.ignitePoints()
        self.ignitePerimeter()
        #Time increment
        self._tnow += timedelta(seconds=self._timeStep)
