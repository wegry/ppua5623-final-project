# Define the statuses you want to analyze
statuses = [
    "(U) Under construction, less than or equal to 50 percent complete",
    "(V) Under construction, more than 50 percent complete",
    "(TS) Construction complete, but not yet in commercial operation",
    "(OP) Operating",
]

# Get references to your layers with the correct layer names
grid_layer = QgsProject.instance().mapLayersByName("Grid")[0]
points_layer = "battery projects by status (scaled)"

# Field to summarize
capacity_field = "Nameplate Capacity (MW)"

# Keep track of all generated layers and the sum field names
generated_layers = []

# Process each status separately
for status in statuses:
    # Create a filter expression for this status
    exp = f"\"Status\" = '{status}'"

    # Create short status name for field prefix
    trimmed_status = status.split(")")[1].strip()
    filter_expression = f"Status = '{status}' "

    print(f"filtering `{filter_expression}`")

    # Run join attributes by location (summary)
    params = {
        "INPUT": grid_layer,
        "JOIN": QgsProcessingFeatureSourceDefinition(
            points_layer,
            selectedFeaturesOnly=False,
            featureLimit=-1,
            filterExpression=filter_expression,
            geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid,
        ),
        "PREDICATE": [0],  # contains
        "JOIN_FIELDS": [capacity_field],
        "SUMMARIES": [5],  # sum
        "DISCARD_NONMATCHING": True,
        "OUTPUT": f"memory:{trimmed_status}",
    }

    # Run the processing algorithm
    result = processing.run("qgis:joinbylocationsummary", params)

    # Add the temporary result to the map
    temp_layer = result["OUTPUT"]
    QgsProject.instance().addMapLayer(temp_layer)

    # Store the layer and field name for later styling
    generated_layers.append(temp_layer)

    print(f"Completed processing for status: {status}")

# Find the global min and max values across all layers using features
global_min = float("inf")
global_max = float("-inf")
field = "Nameplate Capacity (MW)_sum"

for layer in generated_layers:
    # Get all values from the field
    field_idx = layer.fields().indexOf(field)

    for feature in layer.getFeatures():
        value = feature[field_idx]
        if value is not None:  # Skip NULL values
            if value < global_min:
                global_min = value
            if value > global_max:
                global_max = value

print(f"Global min: {global_min}, Global max: {global_max}")


# Create a graduated renderer
renderer = QgsGraduatedSymbolRenderer(field)

# Define the color ramp (Blues)
color_ramp = QgsStyle.defaultStyle().colorRamp("Viridis")
color_ramp.invert()

# Define the number of classes
num_classes = 5

# Create ranges manually
ranges = []
interval = (global_max - global_min) / num_classes

for i in range(num_classes):
    lower = global_min + (i * interval)
    upper = global_min + ((i + 1) * interval)

    # Create a symbol for this range
    symbol = QgsFillSymbol([])

    # Set color based on position in the color ramp
    color_value = i / (num_classes - 1)
    color = color_ramp.color(color_value)
    symbol.setColor(color)

    # Create the range
    range_label = f"{lower:.2f} - {upper:.2f}"
    range_obj = QgsRendererRange(lower, upper, symbol, range_label)
    renderer.addClassRange(range_obj)

renderer.setSourceColorRamp(color_ramp)


# Create the renderer manually
renderer.setMode(QgsGraduatedSymbolRenderer.EqualInterval)

# Apply consistent graduated symbology to all layers
for layer in generated_layers:
    # Apply the renderer to the layer
    layer.setRenderer(renderer.clone())

    # Refresh the layer
    layer.triggerRepaint()

    print("trying")
    print(layer)
    Fl_ou = f"/Users/zachwegrzyniak/OneDrive - Northeastern University/PPUA5263/grid-batteries/hex/{layer.name()}.shp"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    QgsVectorFileWriter.writeAsVectorFormatV2(
        layer, Fl_ou, QgsCoordinateTransformContext(), options
    )


print("Processing complete. All layers have consistent graduated symbology.")
