from generator_types import *
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsVectorFileWriter,
    QgsField,
    QgsFeature,
    QgsSpatialIndex,
    QgsVectorLayerTemporalProperties,
    QgsExpression,
)
from PyQt5.QtCore import QVariant, QDate, QDateTime
import os
from collections import defaultdict

# Get references to your layers
grid_layer = next(
    (
        x
        for x in QgsProject.instance().mapLayersByName("Grid")
        if x.crs().authid() == "EPSG:5070" and x.featureCount() > 0
    ),
    None,
)
points_layer = next(
    (
        x
        for x in QgsProject.instance().mapLayersByName("Generator Points")
        if x.crs().authid() == "EPSG:5070"
    ),
    None,
)
print((grid_layer.featureCount()))

if not grid_layer or not points_layer:
    raise ValueError("Required layers not found")

capacity_field = "Nameplate Capacity (MW)"
GPKG_PATH = "../hex.gpkg"


def first(list):
    for item in list:
        if item is not None:
            if isinstance(item, QVariant):
                if item.isNull():
                    continue
                return item.toInt()
            elif isinstance(item, float):
                return int(item)
            elif isinstance(item, int):
                return item
    return None


def first_float(list):
    for item in list:
        if item is not None:
            if isinstance(item, QVariant):
                if item.isNull():
                    continue
                return item.toDouble()
            elif isinstance(item, float):
                return item
            elif isinstance(item, int):
                return item
    return None


def create_temporal_hex_layer():
    layer_name = "generator_capacity_temporal"
    fields = [
        QgsField("cell_id", QVariant.Int),
        QgsField("start_date", QVariant.Date),
        QgsField("end_date", QVariant.Date),
        QgsField("energy_source", QVariant.String),
        QgsField("capacity_mw", QVariant.Double),
    ]

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.layerName = layer_name
    options.driverName = "GPKG"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteLayer
        if os.path.exists(GPKG_PATH)
        else QgsVectorFileWriter.CreateOrOverwriteFile
    )

    grid_index = QgsSpatialIndex()
    grid_features = {f.id(): f for f in grid_layer.getFeatures()}
    for f in grid_features.values():
        grid_index.insertFeature(f)

    generators = []
    for gen in energy_source_code:
        if not gen.source_filter:
            continue
        filter_expr = (
            gen.source_filter() if callable(gen.source_filter) else gen.source_filter
        )
        expr = QgsExpression(filter_expr)
        context = QgsExpressionContext()
        context.setFields(points_layer.fields())
        expr.prepare(context)
        generators.append((gen, expr, context))

    min_year = 2017
    max_year = 2028
    interval_accumulator = defaultdict(list)

    for point_feat in points_layer.getFeatures():
        matched_gen = None
        for gen, expr, context in generators:
            context.setFeature(point_feat)
            if expr.evaluate(context):
                matched_gen = gen
                break
        if not matched_gen:
            continue

        status = point_feat["Status"]
        op_year = first(
            [point_feat["Operating Year"], point_feat["Planned Operation Year"]]
        )
        op_month = first(
            [
                point_feat["Operating Month"],
                point_feat["Planned Operation Month"],
            ]
        )
        start_date = None
        if (
            op_year >= 2025
            and status
            == "(OS) Out of service and NOT expected to return to service in next calendar year"
        ):
            continue
        elif op_year is None or op_month is None:
            print(f"feat: {point_feat['Planned Operation Year']}")
            print(f"missing either {op_year} or {op_month}")
            continue

        start_date = QDate(op_year, op_month, 1)

        retire_year = first(
            [
                point_feat["Retirement Year"],
                point_feat["Planned Retirement Year"],
            ]
        )
        retire_month = first(
            [
                point_feat["Retirement Month"],
                point_feat["Planned Retirement Month"],
            ]
        )
        end_date = (
            QDate(retire_year, retire_month, 1)
            if retire_year and retire_month
            else QDate(max_year, 12, 1)
        )

        start_date = max(start_date, QDate(min_year, 1, 1))
        end_date = min(end_date, QDate(max_year, 12, 1))

        raw_field = point_feat[capacity_field]
        capacity = first_float([raw_field, 0.0])

        cell_id = grid_index.nearestNeighbor(point_feat.geometry())[0]
        if cell_id is None:
            print(
                f"{point_feat['Plant Name']} feat: {point_feat['Planned Operation Year']} {point_feat['Planned Operation Month']}"
            )
            raise ValueError("Cell not found")

        key = (cell_id, matched_gen.name)
        interval_accumulator[key].append((start_date, end_date, capacity))

    merged_intervals = []
    for key in interval_accumulator:
        cell_id, energy_source = key
        events = []
        for start, end, cap in interval_accumulator[key]:
            events.append((start, cap))
            end_event = end.addMonths(1)
            events.append((end_event, -cap))

        events.sort(key=lambda e: e[0])
        current_cap = 0
        prev_date = None
        merged = []

        for date, delta in events:
            if prev_date is not None and date > prev_date and current_cap > 0:
                merged.append((prev_date, date.addMonths(-1), current_cap))
            current_cap += delta
            prev_date = date

        for start, end, cap in merged:
            merged_intervals.append((cell_id, energy_source, start, end, cap))

    temp_layer = QgsVectorLayer("Polygon?crs=EPSG:5070", "temp", "memory")
    temp_provider = temp_layer.dataProvider()
    temp_provider.addAttributes(fields)
    temp_layer.updateFields()

    features = []
    for cell_id, energy_source, start_date, end_date, capacity in merged_intervals:
        if capacity <= 0:
            continue
        feat = QgsFeature()
        feat.setGeometry(grid_features[cell_id].geometry())
        feat.setAttributes([cell_id, start_date, end_date, energy_source, capacity])
        features.append(feat)

    temp_provider.addFeatures(features)

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        temp_layer, GPKG_PATH, QgsProject.instance().transformContext(), options
    )

    if error[0] != QgsVectorFileWriter.NoError:
        print(f"Error saving layer: {error[1]}")
        return None

    uri = f"{GPKG_PATH}|layername={layer_name}"
    saved_layer = QgsVectorLayer(uri, "Generator Capacity (Temporal)", "ogr")
    if saved_layer.isValid():
        tprops = saved_layer.temporalProperties()
        tprops.setIsActive(True)
        tprops.setMode(
            QgsVectorLayerTemporalProperties.ModeFeatureDateTimeStartAndEndFromFields
        )
        tprops.setStartField("start_date")
        tprops.setEndField("end_date")
        return saved_layer
    return None


temporal_layer = create_temporal_hex_layer()
if temporal_layer and temporal_layer.isValid():
    QgsProject.instance().addMapLayer(temporal_layer)
    print("Temporal layer created successfully")
