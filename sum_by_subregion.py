from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsVectorFileWriter,
)
import os

# Set the output path for the GPKG file
GPKG_PATH = "../sums.gpkg"

# Get references to the input layers
states_layer = QgsProject.instance().mapLayersByName("States")[0]
generator_points_layer = QgsProject.instance().mapLayersByName("Generator Points")[0]
balancing_authorities_layer = QgsProject.instance().mapLayersByName(
    "World Grid Subdivisions"
)[0]

shared_filters = f"""
"Status" NOT IN (
        '(P) Planned for installation, but regulatory approvals not initiated',
        '(L) Regulatory approvals pending. Not under construction',
        '(OS) Out of service and NOT expected to return to service in next calendar year'
    ) AND ("Retirement Year" IS NULL OR "Retirement Year" < 2026)
"""

battery_by_state_query = f"""
WITH pre_aggregated AS (
    SELECT
        "Plant State" AS state_code,
        SUM(CASE WHEN "Energy Source Code" = 'MWH' THEN "Nameplate Capacity (MW)" ELSE 0 END) AS total_battery_capacity
    FROM "{generator_points_layer.name()}"
    WHERE {shared_filters}
    GROUP BY "Plant State"
)
SELECT
    s.*,
    COALESCE(p.total_battery_capacity, 0) AS total_battery_capacity
FROM "{states_layer.name()}" AS s
LEFT JOIN pre_aggregated p ON s."STUSPS" = p.state_code
"""

# Battery capacity by balancing authority - optimized
battery_by_ba_query = f"""
WITH pre_aggregated AS (
    SELECT
        "Balancing Authority Code" AS ba_code,
        SUM(CASE WHEN "Energy Source Code" = 'MWH' THEN "Nameplate Capacity (MW)" ELSE 0 END) AS total_battery_capacity
    FROM "{generator_points_layer.name()}"
    WHERE {shared_filters}
    GROUP BY "Balancing Authority Code"
)
SELECT
    ba.*,
    COALESCE(p.total_battery_capacity, 0) AS total_battery_capacity
FROM "{balancing_authorities_layer.name()}" AS ba
LEFT JOIN pre_aggregated p ON ba."EIACode" = p.ba_code
"""

# Battery fraction by state - optimized
battery_fraction_by_state_query = f"""
WITH aggregated AS (
    SELECT
        "Plant State" AS state_code,
        SUM(CASE WHEN "Energy Source Code" = 'MWH' THEN "Nameplate Capacity (MW)" ELSE 0.0 END) AS battery_capacity,
        SUM("Nameplate Capacity (MW)") AS total_capacity
    FROM "{generator_points_layer.name()}"
    WHERE {shared_filters}
    GROUP BY "Plant State"
)
SELECT
    s.*,
    COALESCE(a.battery_capacity, 0.0) AS total_battery_capacity,
    COALESCE(a.total_capacity, 0.0) AS total_capacity,
    CASE
        WHEN COALESCE(a.total_capacity, 0.0) > 0
        THEN COALESCE(a.battery_capacity, 0.0) / a.total_capacity * 100
        ELSE 0.0
    END AS battery_fraction
FROM "{states_layer.name()}" AS s
LEFT JOIN aggregated a ON s."STUSPS" = a.state_code
"""

# Battery fraction by balancing authority - optimized
battery_fraction_by_ba_query = f"""
WITH aggregated AS (
    SELECT
        "Balancing Authority Code" AS ba_code,
        SUM(CASE WHEN "Energy Source Code" = 'MWH' THEN "Nameplate Capacity (MW)" ELSE 0.0 END) AS battery_capacity,
        SUM("Nameplate Capacity (MW)") AS total_capacity
    FROM "{generator_points_layer.name()}"
    WHERE {shared_filters}
    GROUP BY "Balancing Authority Code"
)
SELECT
    ba.*,
    COALESCE(a.battery_capacity, 0.0) AS total_battery_capacity,
    COALESCE(a.total_capacity, 0.0) AS total_capacity,
    CASE
        WHEN COALESCE(a.total_capacity, 0.0) > 0
        THEN COALESCE(a.battery_capacity, 0.0) / a.total_capacity * 100
        ELSE 0
    END AS battery_fraction
FROM "{balancing_authorities_layer.name()}" AS ba
LEFT JOIN aggregated a ON ba."EIACode" = a.ba_code
"""

bivariate_by_ba_query = f"""
WITH pre_aggregated AS (
    SELECT
        "Balancing Authority Code" AS ba_code,
        SUM(CASE WHEN "Energy Source Code" = 'MWH' THEN "Nameplate Capacity (MW)" ELSE 0.0 END) AS total_battery_capacity,
        SUM(CASE WHEN "Energy Source Code" IN ('SUN', 'WND') THEN "Nameplate Capacity (MW)" ELSE 0.0 END) AS total_renewable_capacity,
        SUM(CASE WHEN "Energy Source Code" = 'WAT' and "Prime Mover Code" = 'HY' THEN "Nameplate Capacity (MW)" ELSE 0.0 END) AS total_hydro_capacity,
        SUM(CASE WHEN "Status" = '(SB) Standby/Backup: available for service but not normally used' THEN "Nameplate Capacity (MW)" ELSE 0.0 END) AS total_peaker_capacity,
        SUM("Nameplate Capacity (MW)") AS total_capacity
    FROM "{generator_points_layer.name()}"
    WHERE {shared_filters}
    GROUP BY "Balancing Authority Code"
)
SELECT
    ba.*,
    COALESCE(p.total_battery_capacity, 0.0) AS total_battery_capacity,
    COALESCE(p.total_renewable_capacity, 0.0) AS total_renewable_capacity,
    COALESCE(p.total_hydro_capacity, 0.0) AS total_hydro_capacity,
    COALESCE(p.total_peaker_capacity, 0.0) AS total_peaker_capacity,
    COALESCE(p.total_capacity, 0.0) AS total_capacity
FROM "{balancing_authorities_layer.name()}" AS ba
LEFT JOIN pre_aggregated p ON ba."EIACode" = p.ba_code
"""

# Process and save all queries
queries = [
    {
        "query": battery_by_state_query,
        "name": "battery_by_state",
        "display": "Battery Capacity by State",
        "field_expr": """format('%1MW', format_number(total_battery_capacity))""",
    },
    {
        "query": battery_by_ba_query,
        "name": "battery_by_ba",
        "display": "Battery Capacity by Balancing Authority",
        "field_expr": """format('%1\n%2MW', EIAcode, format_number(total_battery_capacity))""",
    },
    {
        "field": "battery_fraction",
        "query": battery_fraction_by_state_query,
        "name": "battery_fraction_by_state",
        "display": "Battery Fraction by State",
        "field_expr": """format('%1%', format_number(battery_fraction, 1))""",
        "graduated": True,
    },
    {
        "field": "battery_fraction",
        "query": battery_fraction_by_ba_query,
        "name": "battery_fraction_by_ba",
        "display": "Battery Fraction by Balancing Authority",
        "field_expr": """format('%1\n%2%', EIAcode, format_number(battery_fraction, 1))""",
        "graduated": True,
    },
    {
        "field": "renewables_fraction",
        "query": bivariate_by_ba_query,
        "name": "bivariate_fraction_by_ba",
        "display": "Renewables Fraction by Balancing Authority",
        "field_expr": """format('%1\n%2%', EIAcode, format_number(renewables_fraction, 1))""",
        "graduated": True,
    },
]


root = QgsProject.instance().layerTreeRoot()
group = root.insertGroup(3, "Capacity By Subregion")


for query_info in queries:
    # Create virtual layer
    virtual_layer = QgsVectorLayer(
        "?query={}".format(query_info["query"]),
        "virtual_{}".format(query_info["name"]),
        "virtual",
    )

    if not virtual_layer.isValid():
        print(query_info["query"])
        print("Invalid virtual layer for {}!".format(query_info["name"]))
        continue

    display_name = query_info["display"]

    # Save the memory layer to GeoPackage
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.layerName = query_info["name"]
    options.driverName = "GPKG"

    # Determine action based on whether GPKG exists
    if not os.path.exists(GPKG_PATH):
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        virtual_layer, GPKG_PATH, QgsProject.instance().transformContext(), options
    )

    if error[0] != QgsVectorFileWriter.NoError:
        print(f"Error saving layer: {error[1]}")
        continue

    uri = f"{GPKG_PATH}|layername={query_info['name']}"
    permanent_layer = QgsVectorLayer(uri, display_name, "ogr")

    if not permanent_layer.isValid():
        print(f"Failed to load layer '{display_name}' from GeoPackage")
        continue

    # Configure labeling for the capacity field
    label_settings = QgsPalLayerSettings()
    label_settings.fieldName = query_info["field_expr"]
    label_settings.enabled = True
    label_settings.isExpression = True

    text_format = QgsTextFormat()

    # Add label mask (background)
    background_settings = QgsTextBackgroundSettings()
    background_settings.setEnabled(True)
    background_settings.setType(QgsTextBackgroundSettings.ShapeRectangle)
    background_settings.setSizeType(QgsTextBackgroundSettings.SizeBuffer)
    background_settings.setSize(QSizeF(1.5, 1.5))  # Buffer size (mm)
    background_settings.setFillColor(
        QColor(255, 255, 255, 200)
    )  # White with 80% opacity
    background_settings.setStrokeColor(
        QColor(0, 0, 0, 100)
    )  # Black outline with 40% opacity
    background_settings.setStrokeWidth(0.2)  # Thin outline (mm)

    # Apply background settings to the text format
    text_format.setBackground(background_settings)

    # Set the text format for the label settings
    label_settings.setFormat(text_format)

    # Apply labeling to the layer
    permanent_layer.setLabelsEnabled(True)
    permanent_layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))

    if query_info.get("graduated", False):
        renderer = QgsGraduatedSymbolRenderer(query_info["field"])
        classifier = QgsClassificationJenks()
        renderer.setClassificationMethod(classifier)
        renderer.updateClasses(permanent_layer, 8)
        color_ramp = QgsStyle.defaultStyle().colorRamp("Greens")
        color_ramp.invert()
        renderer.updateColorRamp(color_ramp)

        permanent_layer.setRenderer(renderer)

    # Add layer to the project
    QgsProject.instance().addMapLayer(permanent_layer, False)
    layer_node = group.addLayer(permanent_layer)
    layer_node.setItemVisibilityChecked(False)

    print("{} layer created and labeled".format(query_info["display"]))

print("All layers saved to", GPKG_PATH)
