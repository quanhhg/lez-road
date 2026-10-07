"""PyQGIS helpers imported only by the registered GIS worker."""
from __future__ import annotations

import os
import atexit
from contextlib import contextmanager
from pathlib import Path

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsFeature, QgsFields, QgsField, QgsGeometry, QgsProject,
                       QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes)
from qgis.PyQt.QtCore import QVariant

APP = None


def initialize(work):
    global APP
    if QgsApplication.instance() is None:
        profile = Path(work) / "data/interim/qgis_profile_lez"
        profile.mkdir(parents=True, exist_ok=True)
        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
        APP = QgsApplication([], False, str(profile))
        APP.initQgis()
        atexit.register(shutdown)
    return QgsProject.instance().transformContext()


def shutdown():
    global APP
    if APP is not None:
        QgsProject.instance().clear()
        APP.exitQgis()
        APP = None


def read_polygon(path, target_crs, context, layer_name=None, selector_field=None, values=None):
    uri = str(path) + ("|layername=" + layer_name if layer_name else "")
    layer = QgsVectorLayer(uri, "polygon_input", "ogr")
    if not layer.isValid() or not layer.crs().isValid():
        raise ValueError("Cannot load polygon layer with a valid CRS: " + uri)
    geometries, selected = [], set()
    transform = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem(target_crs), context)
    if selector_field and selector_field not in layer.fields().names():
        raise ValueError("Missing polygon selector field: " + selector_field)
    requested = None if values is None else {str(v) for v in values}
    for feature in layer.getFeatures():
        value = str(feature[selector_field]) if selector_field else None
        if requested is not None and value not in requested:
            continue
        if value is not None:
            selected.add(value)
        geometry = QgsGeometry(feature.geometry())
        if geometry.isEmpty() or geometry.type() != QgsWkbTypes.PolygonGeometry or not geometry.isGeosValid():
            raise ValueError("Empty/invalid/non-polygon source geometry: " + uri)
        geometry.transform(transform)
        if not geometry.isGeosValid():
            raise ValueError("Invalid polygon after CRS transform: " + uri)
        geometries.append(geometry)
    if requested is not None and requested != selected:
        raise ValueError("Polygon IDs not found: " + ",".join(sorted(requested-selected)))
    if not geometries:
        raise ValueError("No polygons selected: " + uri)
    result = QgsGeometry.unaryUnion(geometries)
    if result.isNull() or result.isEmpty() or not result.isGeosValid():
        raise ValueError("Polygon union is empty or invalid: " + uri)
    return result


class Sink:
    def __init__(self, path, layer_name, columns, geometry_type, crs, context):
        self.fields = QgsFields()
        self.names = [c[0] for c in columns]
        types = {"str": QVariant.String, "int": QVariant.LongLong, "float": QVariant.Double, "bool": QVariant.Bool}
        for name, kind in columns:
            self.fields.append(QgsField(name, types[kind]))
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName, options.layerName = "GPKG", layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if Path(path).exists() else QgsVectorFileWriter.CreateOrOverwriteFile
        options.layerOptions = ["SPATIAL_INDEX=YES"] if geometry_type != QgsWkbTypes.NoGeometry else []
        self.writer = QgsVectorFileWriter.create(str(path), self.fields, geometry_type,
                                                QgsCoordinateReferenceSystem(crs), context, options)
        if self.writer.hasError() != QgsVectorFileWriter.NoError:
            raise RuntimeError(self.writer.errorMessage())
        self.count = 0

    def add(self, row, geometry=None):
        feature = QgsFeature(self.fields)
        feature.setAttributes([row.get(k) for k in self.names])
        if geometry is not None:
            feature.setGeometry(geometry)
        if not self.writer.addFeature(feature):
            raise RuntimeError(self.writer.lastError())
        self.count += 1

    def close(self):
        if self.writer:
            if not self.writer.flushBuffer():
                raise RuntimeError(self.writer.lastError())
            self.writer = None


@contextmanager
def sink(*args, **kwargs):
    output = Sink(*args, **kwargs)
    try:
        yield output
    finally:
        output.close()


def check_layers(path, expected, crs):
    actual = {}
    for name, count in expected.items():
        layer = QgsVectorLayer(str(path) + "|layername=" + name, name, "ogr")
        if not layer.isValid() or layer.featureCount() != count:
            raise RuntimeError(f"GeoPackage readback failed: {name}")
        if layer.isSpatial() and layer.crs().authid() != crs:
            raise RuntimeError(f"Unexpected layer CRS: {name}")
        actual[name] = count
    return actual
