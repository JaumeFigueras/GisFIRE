from qgis.core import QgsVectorLayer
from qgis.core import QgsField
from qgis.core import QgsVectorFileWriter
from qgis.core import QgsLayerTreeLayer
from qgis.core import QgsMarkerSymbol

from PyQt5.QtCore import QVariant

from os import path

def CreateLayer(type, name, attributes, crs):
    # create layer
    vl = QgsVectorLayer(type, name, 'memory')
    pr = vl.dataProvider()
    # add fields
    pr.addAttributes(attributes)
    vl.updateFields() # tell the vector layer to fetch changes from the provider
    vl.setCrs(crs, True)
    # update layer's extent when new features have been added
    # because change of extent in provider is not propagated to the layer
    vl.updateExtents()
    return vl

def SaveLayerToGeoPackage(layer, geo_package):
    options = QgsVectorFileWriter.SaveVectorOptions()
    if not path.exists(geo_package):
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    else:
        geo_package_layer = geo_package + "|layername=" + "_".join(layer.name().split(' '))
        vl = QgsVectorLayer(geo_package_layer, layer.name(), "ogr")
        if not vl.isValid():
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        else:
            options.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerNoNewFields
    options.EditionCapability = QgsVectorFileWriter.CanAddNewLayer
    options.layerName = "_".join(layer.name().split(' '))
    writer = QgsVectorFileWriter.writeAsVectorFormat(layer, geo_package, options)

def LoadLayer(layer_name, geo_package):
    geo_package_layer = geo_package + "|layername=" + "_".join(layer_name.split(' '))
    vl = QgsVectorLayer(geo_package_layer, layer_name, "ogr")
    return vl

def AddLayerInPosition(project, layer, position):
    project.addMapLayer(layer, True)
    root = project.layerTreeRoot()
    node_layer = root.findLayer(layer.id())
    node_clone = node_layer.clone()
    parent = node_layer.parent()
    parent.insertChildNode(position, node_clone)
    parent.removeChildNode(node_layer)

def CreateIgnitionPointLayer(iface, project, geo_package):
    attributes = [QgsField('date',  QVariant.String)]
    ignition_layer = CreateLayer('Point', 'Ignition Points', attributes, project.crs())
    SaveLayerToGeoPackage(ignition_layer, geo_package)
    ignition_layer = LoadLayer('Ignition Points', geo_package)
    symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': 'red', 'size_unit': 'MM', 'size':'2'})
    ignition_layer.renderer().setSymbol(symbol)
    AddLayerInPosition(project, ignition_layer, 0)
    return ignition_layer

def CreatePerimeterLayer(iface, project, geo_package):
    attributes = [QgsField('date',  QVariant.String)]
    perimeter_layer = CreateLayer('Multipolygon', 'Fire Perimeter', attributes, project.crs())
    SaveLayerToGeoPackage(perimeter_layer, geo_package)
    perimeter_layer = LoadLayer('Fire Perimeter', geo_package)
    AddLayerInPosition(project, perimeter_layer, 2)
    return perimeter_layer
