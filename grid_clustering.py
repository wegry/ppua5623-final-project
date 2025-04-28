from generator_types import *
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsVectorFileWriter,
    QgsProcessingFeatureSourceDefinition,
)

import os

# Define the statuses you want to analyze
statuses = [
    "(U) Under construction, less than or equal to 50 percent complete",
    "(V) Under construction, more than 50 percent complete",
    "(TS) Construction complete, but not yet in commercial operation",
    "(OP) Operating",
    "(SB) Standby/Backup: available for service but not normally used",
]

# Get references to your layers with the correct layer names

for x in QgsProject.instance().mapLayersByName("Grid"):
    root = QgsProject.instance().layerTreeRoot()
    layer_node = root.findLayer(x)
    if layer_node:
        grid_layer = x

for x in QgsProject.instance().mapLayersByName("Generator Points"):
    if x.crs().authid() == "EPSG:5070":
        points_layer = x


def ramps_by_energy_source(source: str):
    return (
        {
            "Conventional Hydro": "Blues",
            "Pumped Storage": "Blues",
            "MWH": "Reds",
            "NUC": "Purples",
            "Renewables": "Greens",
        }
    ).get(source, "Greys")


# Field to summarize
capacity_field = "Nameplate Capacity (MW)"
field = f"{capacity_field}_sum"
GPKG_PATH = f"../hex.gpkg"


def create_hex_layer(fname: str, display_name: str, filter_expression: str):
    # Run join attributes by location (summary)
    params = {
        "INPUT": grid_layer,
        "JOIN": QgsProcessingFeatureSourceDefinition(
            points_layer.id(),
            selectedFeaturesOnly=False,
            featureLimit=-1,
            filterExpression=filter_expression,
            geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid,
        ),
        "PREDICATE": [0],  # contains
        "JOIN_FIELDS": [capacity_field],
        "SUMMARIES": [0, 4, 5],  # count, range, sum
        "DISCARD_NONMATCHING": True,
        "OUTPUT": "memory:",
    }

    # Run the processing algorithm
    result = processing.run("qgis:joinbylocationsummary", params)

    memory_layer = result["OUTPUT"]

    # Check if the memory layer has features
    feature_count = memory_layer.featureCount()

    if feature_count == 0:
        # print(f"Memory layer has {feature_count} features")
        return

    # Prepare the GeoPackage path
    layer_name = fname.replace(" ", "_").lower()

    # Save the memory layer to GeoPackage
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.layerName = layer_name
    options.driverName = "GPKG"

    # Determine action based on whether GPKG exists
    if not os.path.exists(GPKG_PATH):
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        memory_layer, GPKG_PATH, QgsProject.instance().transformContext(), options
    )

    if error[0] != QgsVectorFileWriter.NoError:
        print(f"Error saving layer: {error[1]}")
        return None

    # Load the permanent layer from GeoPackage
    uri = f"{GPKG_PATH}|layername={layer_name}"
    saved_layer = QgsVectorLayer(uri, display_name, "ogr")

    if not saved_layer.isValid():
        print(f"Failed to load layer '{display_name}' from GeoPackage")
        return None

    return saved_layer  # Returns the permanent layer object


# Keep track of all generated layers and the sum field names
generated_layers = []

summed_layer = create_hex_layer(
    "sums",
    "All Generation Capacity",
    #     f"""array_contains(array({
    #     ', '.join([f"'{x}'" for x in statuses])
    # }), Status)""",
    None,
)

QgsProject.instance().addMapLayer(summed_layer, False)

# Create a graduated renderer
renderer = QgsGraduatedSymbolRenderer(field)

# Define the number of classes
num_classes = 7

# Create the renderer manually
classifier = QgsClassificationLogarithmic()
hexagon_symbol = QgsFillSymbol.createSimple(
    {"outline_width": "0.25", "outline_width_unit": "Point"}
)
renderer.setSourceSymbol(hexagon_symbol)
renderer.setClassificationMethod(classifier)
renderer.updateClasses(summed_layer, num_classes)

for i, symbol_range in enumerate(renderer.ranges()):
    lower_value = symbol_range.lowerValue()
    upper_value = symbol_range.upperValue()

    # Format the label as desired, e.g., "min - max unit"
    unit = "MW"
    if upper_value >= 1000:
        unit = "GW"
        lower_value /= 1000
        upper_value /= 1000

    new_label = f"{lower_value:g} - {upper_value:g} {unit}"
    # Set the new label
    renderer.updateRangeLabel(i, new_label)

root = QgsProject.instance().layerTreeRoot()
parent_group = root.insertGroup(3, "Generators")

# Pre-create renderer copies for each energy code to avoid recreation in loops
renderer_copies = {}
for energy_code in energy_source_code:
    name = energy_code.name
    color_scheme = energy_code.color_ramp
    color_ramp = QgsStyle.defaultStyle().colorRamp(color_scheme)
    renderer_copies[name] = QgsGraduatedSymbolRenderer.clone(renderer)
    renderer_copies[name].updateColorRamp(color_ramp.clone())


# Process each status separately
# https://www.eia.gov/electricity/monthly/pdf/AppendixC.pdf
for energy_code in energy_source_code:
    code = energy_code.name
    source_filter = energy_code.source_filter()

    group = parent_group.addGroup(code)

    for status in statuses:
        short_status = status.split("(")[1].split(")")[0]
        trimmed_status = status.split(")")[1].strip()
        # Create a filter expression for this status
        filter_expression = f"{source_filter} AND \"Status\" = '{status}'"

        result_layer = create_hex_layer(
            f"{code}_{short_status}",
            trimmed_status,
            filter_expression,
        )

        if result_layer and result_layer.isValid():
            QgsProject.instance().addMapLayer(result_layer, False)
            layer_node = group.addLayer(result_layer)
            layer_node.setItemVisibilityChecked(False)

            renderer_copy = renderer_copies[code].clone()
            result_layer.setRenderer(renderer_copy)
            result_layer.commitChanges()


print("Processing complete. All layers have consistent graduated symbology.")
