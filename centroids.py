from generator_types import energy_source_code
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsVectorFileWriter,
    QgsFeatureRequest,
)
from qgis.PyQt.QtCore import QVariant
from collections import defaultdict

states_layer = QgsProject.instance().mapLayersByName("States")[0]
balancing_authorities_layer = QgsProject.instance().mapLayersByName(
    "Balancing_Authorities"
)[0]


# Load generator points layer
points_layer = None
for layer in QgsProject.instance().mapLayers().values():
    if layer.name() == "Generator Points" and layer.crs().authid() == "EPSG:5070":
        points_layer = layer
        break

if not points_layer:
    raise ValueError("Could not find Generator Points layer with CRS EPSG:5070")

# Create centroid layer with additional fields
centroid_layer = QgsVectorLayer("Point?crs=EPSG:5070", "Weighted Centroids", "memory")
centroid_provider = centroid_layer.dataProvider()
centroid_provider.addAttributes(
    [
        QgsField("energy_type", QVariant.String),
        QgsField("year", QVariant.Int),
        QgsField("total_capacity", QVariant.Double),
        QgsField("avg_x", QVariant.Double),
        QgsField("avg_y", QVariant.Double),
        QgsField("group_type", QVariant.String),
        QgsField("group_name", QVariant.String),
    ]
)
centroid_layer.updateFields()

capacity_field = "Nameplate Capacity (MW)"
ba_code_field = "Balancing Authority Code"  # Adjust field name as necessary
state_field = "Plant State"  # Adjust field name as necessary
min_year = 2018
max_year = 2028

with edit(centroid_layer):
    for energy_code in energy_source_code:
        source_filter = energy_code.source_filter()

        for year in range(min_year, max_year + 1):
            # Build the filter
            filter_expr = f"""
                {source_filter}
                AND (
                    coalesce("Operating Year", "Planned Operation Year", {max_year}) <= {year}
                ) AND (
                    coalesce("Retirement Year", "Planned Retirement Year", {year + 1}) > {year}
                )
                {"AND Status != '(OS) Out of service'" if year == 2025 else ""}
            """

            request = QgsFeatureRequest().setFilterExpression(filter_expr)
            features = points_layer.getFeatures(request)

            features_data = []
            for feature in features:
                capacity = feature[capacity_field] or 0
                try:
                    capacity = float(capacity)
                except (TypeError, ValueError):
                    continue

                geom = feature.geometry()
                if geom.isNull():
                    continue

                point = geom.asPoint()
                x = point.x()
                y = point.y()

                # Extract BA code and state
                ba_code = feature[ba_code_field] or ""
                state = feature[state_field] or ""

                features_data.append(
                    {
                        "capacity": capacity,
                        "x": x,
                        "y": y,
                        "ba_code": str(ba_code).strip(),
                        "state": str(state).strip(),
                    }
                )

            if not features_data:
                continue

            # Function to add centroid features
            def add_centroid(group_cap, avg_x, avg_y, group_type, group_name):
                if group_cap <= 0:
                    return
                feat = QgsFeature(centroid_layer.fields())
                feat.setAttributes(
                    [
                        energy_code.name,
                        year,
                        group_cap,
                        avg_x,
                        avg_y,
                        group_type,
                        group_name,
                    ]
                )
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(avg_x, avg_y)))
                centroid_provider.addFeature(feat)

            # Total centroid
            total_cap = sum(f["capacity"] for f in features_data)
            weighted_x_total = sum(f["x"] * f["capacity"] for f in features_data)
            weighted_y_total = sum(f["y"] * f["capacity"] for f in features_data)
            if total_cap > 0:
                avg_x_total = weighted_x_total / total_cap
                avg_y_total = weighted_y_total / total_cap
                add_centroid(total_cap, avg_x_total, avg_y_total, "total", "total")

            # Balancing Authority Groups
            ba_groups = defaultdict(list)
            for data in features_data:
                ba_code = data["ba_code"]
                if ba_code:
                    ba_groups[ba_code].append(data)

            for ba_code, group in ba_groups.items():
                group_cap = sum(f["capacity"] for f in group)
                weighted_x = sum(f["x"] * f["capacity"] for f in group)
                weighted_y = sum(f["y"] * f["capacity"] for f in group)
                avg_x = weighted_x / group_cap if group_cap else 0
                avg_y = weighted_y / group_cap if group_cap else 0
                add_centroid(group_cap, avg_x, avg_y, "balancing_authority", ba_code)

            # State Groups
            state_groups = defaultdict(list)
            for data in features_data:
                state = data["state"]
                if state:
                    state_groups[state].append(data)

            for state, group in state_groups.items():
                group_cap = sum(f["capacity"] for f in group)
                weighted_x = sum(f["x"] * f["capacity"] for f in group)
                weighted_y = sum(f["y"] * f["capacity"] for f in group)
                avg_x = weighted_x / group_cap if group_cap else 0
                avg_y = weighted_y / group_cap if group_cap else 0
                add_centroid(group_cap, avg_x, avg_y, "state", state)

# Save to GeoPackage
gpkg_path = "../hex.gpkg"
options = QgsVectorFileWriter.SaveVectorOptions()
options.layerName = "weighted_centroids"
options.driverName = "GPKG"
options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

QgsVectorFileWriter.writeAsVectorFormatV2(
    centroid_layer, gpkg_path, QgsProject.instance().transformContext(), options
)

# Add to project and configure labeling
uri = f"{gpkg_path}|layername=weighted_centroids"
vlayer = QgsVectorLayer(uri, "Weighted Centroids", "ogr")
QgsProject.instance().addMapLayer(vlayer)

label_settings = QgsPalLayerSettings()
label_settings.fieldName = """format('%1 %2', "energy_type", "year")"""
label_settings.enabled = True
label_settings.isExpression = True
vlayer.setLabelsEnabled(True)
vlayer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))

# Add categorized styling based on energy type's single_color
categories = []
for energy_code in energy_source_code:
    # Create a symbol with the specified color
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": energy_code.single_color, "size": "3.0"}
    )

    # Create category for this energy type
    category = QgsRendererCategory(
        energy_code.name,  # Match value in "energy_type" field
        symbol,
        energy_code.name,  # Label for legend
    )
    categories.append(category)

# Create and apply categorized renderer
renderer = QgsCategorizedSymbolRenderer(
    "energy_type", categories  # Field to categorize on
)
vlayer.setRenderer(renderer)
vlayer.triggerRepaint()
