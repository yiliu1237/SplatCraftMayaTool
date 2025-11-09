# UI Module

PySide2/PyQt-based user interface components for SplatCraft.

## Overview

This module provides Qt-based UI widgets for displaying and interacting with 3D Gaussian splat data.

## Components

### `rendered_panel.py`

Two main classes:

#### `SplatGLWidget`
**Base:** `QGLWidget`

OpenGL widget that handles:
- OpenGL context and rendering loop
- Mouse-based camera controls (orbit, pan, zoom)
- Continuous rendering at ~60 FPS
- Integration with `SplatRenderer`

**Camera controls:**
- Left mouse drag: Orbit (rotate camera around target)
- Middle mouse drag: Pan (move target)
- Mouse wheel: Zoom (adjust distance)

**API:**
```python
gl_widget = SplatGLWidget()
gl_widget.upload_gaussian_data(gaussian_data, max_points=50000)
gl_widget.set_point_size_scale(1.5)
gl_widget.set_auto_rotate(True)
gl_widget.reset_camera()
```

#### `RenderedPanel`
**Base:** `QWidget`

Complete panel with controls:
- OpenGL viewport (`SplatGLWidget`)
- Reset camera button
- Auto-rotate toggle button
- Point size slider (0.1x - 3.0x)
- Status label

**API:**
```python
panel = RenderedPanel()
panel.upload_gaussian_data(gaussian_data, max_points=50000)
panel.set_status("Loaded 50,000 Gaussians")
panel.show()
```

## Standalone Usage

Both widgets can run as standalone Qt applications:

```python
from ui.rendered_panel import test_rendered_panel
test_rendered_panel()  # Opens test window with random data
```

## Maya Integration

The widgets are compatible with Maya's Qt environment:

```python
# In Maya
from ui.rendered_panel import RenderedPanel

panel = RenderedPanel()
panel.show()
# Window opens and stays open (Qt is managed by Maya)
```

## Camera System

Uses an **orbit camera** model:
- **Distance**: How far from target (zoom)
- **Azimuth**: Horizontal rotation angle
- **Elevation**: Vertical rotation angle (clamped to ±89° to avoid gimbal lock)
- **Target**: Point to orbit around (defaults to data centroid)

Camera is automatically framed when data is uploaded:
```python
# Auto-framing algorithm
bounding_box = calculate_bounds(positions)
center = bounding_box.center
size = bounding_box.diagonal_length
camera_distance = size * 1.5  # 1.5x for good framing
```

## Rendering Loop

Continuous rendering at ~60 FPS:
```python
QTimer -> update() -> paintGL() -> renderer.render()
   |                                      |
   +-- every 16ms (60 FPS) ---------------+
```

## Qt Compatibility

Supports both PySide2 and PyQt5 with automatic fallback:
```python
try:
    from PySide2.QtWidgets import ...
except ImportError:
    from PyQt5.QtWidgets import ...
```

## Dependencies

- PySide2 (or PyQt5)
- PyOpenGL
- NumPy
- Maya (optional, only for Maya integration)

## Example: Custom Window

```python
from ui.rendered_panel import RenderedPanel
from import_gaussians import read_ply_gaussians
from PySide2.QtWidgets import QApplication

# Create app
app = QApplication.instance() or QApplication([])

# Create panel
panel = RenderedPanel()
panel.setWindowTitle("My Custom Viewer")
panel.resize(1024, 768)

# Load data
data = read_ply_gaussians("path/to/file.ply")
panel.upload_gaussian_data(data, max_points=100000)

# Show
panel.show()
app.exec_()
```

## Future Enhancements

- Dockable Maya panel (integrate into Maya UI)
- Save/load camera presets
- Turntable animation export
- Screenshot/render export
- Multi-viewport support
- Gizmos for parameter editing
