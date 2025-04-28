import os

OUT_PATH = "../Grid.gpkg"
run = processing.run(
    "native:creategrid",
    {
        "TYPE": 4,
        "EXTENT": "-3599775.515500000,3627909.786400000,88872.426600000,3332064.549200000 [EPSG:5070]",
        "HSPACING": 40000,
        "VSPACING": 40000,
        "HOVERLAY": 0,
        "VOVERLAY": 0,
        "CRS": QgsCoordinateReferenceSystem("EPSG:5070"),
        "OUTPUT": "memory:Grid",
    },
)

grid_layer = run["OUTPUT"]

generators = "../data/current and planned generators.gpkg"

# Retrieve all sublayers from the GPKG
sublayers = (
    QgsProviderRegistry.instance().providerMetadata("ogr").querySublayers(generators)
)

for sublayer in sublayers:
    # Construct layer URI with proper syntax
    uri = f"{generators}|layername={sublayer.name()}"

    # Create the layer using QgsVectorLayer
    layer = QgsVectorLayer(uri, "Generator Points", "ogr")

    if layer.isValid():
        # QgsProject.instance().addMapLayer(layer, false)
        print(f"Loaded layer: {sublayer.name()}")
        points_layer = layer
        break
    else:
        print(f"Failed to load layer: {sublayer.name()}")

# Use GeoPackage instead of shapefile to preserve field names
points_path = "Users/zachwegrzyniak/Library/CloudStorage/OneDrive-NortheasternUniversity/PPUA5263/grid-batteries/generator_points.gpkg"

# Reproject points
params = {
    "INPUT": points_layer,
    "TARGET_CRS": "EPSG:5070",
    "OUTPUT": points_path,
}

processing.run("qgis:reprojectlayer", params)
points_reprojected = QgsVectorLayer(
    points_path,
    "Generator Points",
    "ogr",
)
points_reprojected.dataProvider().createSpatialIndex()

QgsProject.instance().addMapLayer(points_reprojected)
points_layer = points_reprojected

QgsProject.instance().addMapLayer(grid_layer, False)

# Extract only the grid cells that contain points
params = {
    "INPUT": grid_layer.id(),
    # Get references to your layers with the correct layer names
    "PREDICATE": [0],  # Contains
    "INTERSECT": points_layer.id(),
    "OUTPUT": OUT_PATH,
}
processing.run("native:extractbylocation", params)
grid_layer = QgsVectorLayer(
    OUT_PATH,
    "Grid",
    "ogr",
)

# Add spatial index to improve performance
grid_layer.dataProvider().createSpatialIndex()

if grid_layer.isValid():
    # Add the layer to the project
    QgsProject.instance().addMapLayer(grid_layer)

    # Optional: Style the grid with a light border
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "transparent",
            "outline_width": "0.25",
            "outline_width_unit": "Point",
            "name": "hexagon",
        }
    )

    grid_layer.renderer().setSymbol(symbol)
    grid_layer.triggerRepaint()

    print("Grid successfully added to the map")
else:
    print("Failed to load the grid layer")
