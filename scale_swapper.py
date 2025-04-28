# Python script to change all scalebar backgrounds to dark gray in QGIS layout
from qgis.core import QgsProject
from PyQt5.QtGui import QColor

# Get the current project
project = QgsProject.instance()

# Get all print layouts in the project
manager = project.layoutManager()
layouts = manager.printLayouts()

dark_gray = QColor(80, 80, 80)  # RGB dark gray


# Loop through all layouts
for layout in layouts:
    print(f"Processing layout: {layout.name()}")
    
    # Find all scalebar items in each layout
    for item in layout.items():
        if item.type() == 65646:  # Scale bar item type
            print(f"  - Found scale bar: {item.id()}")
            
            # Change the fill color (the actual bar color)
            item.setFillColor(dark_gray)
            
            # Change the line color (the outline of segments)
            item.setLineColor(dark_gray)
            
            # If you want to change the text color as well
            item.setFontColor(dark_gray)
            # Enable the background (in case it was disabled)
            item.setBackgroundEnabled(False)
            # Get current font
            font = item.font()
            
            # Reduce font size (adjust the value as needed)
            current_size = font.pointSize()
            new_size = current_size * 0.8  # Reduce to 80% of current size
            # Or set a specific size:
            # new_size = 8  # Set to 8pt
            
            font.setPointSize(new_size)
            
            # Apply the new font
            item.setFont(font)
            
            print(f"  - Changed background to dark gray for scale bar: {item.id()}")

print("Script completed. All scale bars now have dark gray backgrounds.")