# SplatCraft Maya Plugin

Maya authoring tool for 3D Gaussian Splatting, powered by Flash3D inference engine.

## Overview

SplatCraft allows you to import, visualize, and manipulate 3D Gaussian Splatting data in Autodesk Maya. The plugin provides:

- **Custom Maya Node**: Store and manage Gaussian splat parameters
- **Viewport Display**: Fast point cloud proxy for scene interaction
- **Import/Export**: PLY format support with metadata
- **LOD Controls**: Adjust display density for performance

## Directory Structure

```
maya_plugin/
├── README.md                    # This file
├── __init__.py                  # Package initialization
├── nodes/
│   ├── __init__.py
│   └── splatcraft_node.py      # Main SplatCraft Maya node
├── viewport/
│   ├── __init__.py
│   └── proxy_drawable.py       # Viewport 2.0 draw override (future)
├── ui/
│   ├── __init__.py
│   ├── main_panel.py           # Main UI panel (future)
│   ├── control_panel.py        # Control widgets (future)
│   └── rendered_panel.py       # OpenGL rendered panel (future)
├── rendering/
│   ├── __init__.py
│   └── splat_renderer.py       # OpenGL Gaussian renderer (future)
├── utils/
│   ├── __init__.py
│   └── transform_monitor.py    # Transform sync utilities (future)
├── import_gaussians.py         # PLY import utilities
└── examples/
    └── basic_usage.py          # Usage examples
```

## Requirements

### Software
- **Autodesk Maya** 2022 or later
- **Python** 3.7+ (comes with Maya)
- **Viewport 2.0** enabled in Maya

### Python Dependencies
```bash
pip install numpy plyfile
```

Install these in Maya's Python environment:
```bash
# macOS example (adjust path for your Maya version)
/Applications/Autodesk/maya2024/Maya.app/Contents/bin/mayapy -m pip install numpy plyfile

# Windows example
"C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" -m pip install numpy plyfile

# Linux example
/usr/autodesk/maya2024/bin/mayapy -m pip install numpy plyfile
```

## Installation

1. **Clone/Download** this repository to your computer

2. **Add to Maya Python Path** - Open Maya and run in Script Editor (Python):

```python
import sys
sys.path.append('/Users/yiliu/Documents/GitHub/flash3d/maya_plugin')
```

3. **Load the Plugin**:

```python
import maya.cmds as cmds
plugin_path = '/Users/yiliu/Documents/GitHub/flash3d/maya_plugin/nodes/splatcraft_node.py'
cmds.loadPlugin(plugin_path)
```

## Quick Start

### 1. Export Gaussians from Flash3D

First, run Flash3D inference and export to PLY format (on your GPU machine):

```python
# In your Flash3D environment
from export_to_maya import GaussianExporter

# After running inference...
exporter = GaussianExporter(cfg)
gaussian_data = exporter.extract_gaussians(outputs, inputs)
exporter.save_as_ply(gaussian_data, 'output/gaussians.ply')
exporter.save_metadata(gaussian_data, 'output/gaussians.ply')
```

### 2. Import into Maya

Open Maya and run:

```python
import sys
sys.path.append('/Users/yiliu/Documents/GitHub/flash3d/maya_plugin')

# Load plugin
import maya.cmds as cmds
cmds.loadPlugin('/Users/yiliu/Documents/GitHub/flash3d/maya_plugin/nodes/splatcraft_node.py')

# Import Gaussian PLY
import import_gaussians
node_name, data = import_gaussians.import_gaussian_scene('/path/to/gaussians.ply')

# The node is now in your scene and selected
```

### 3. Adjust Display Settings

```python
# Set LOD (Level of Detail) to 50%
cmds.setAttr(f"{node_name}.displayLOD", 0.5)

# Set point size
cmds.setAttr(f"{node_name}.pointSize", 3.0)

# Get node info
import import_gaussians
import_gaussians.get_node_info(node_name)
```

## Usage Examples

### Import a Single PLY File

```python
import import_gaussians

# Import file
node, data = import_gaussians.import_gaussian_scene('/path/to/gaussians.ply')

# Check number of Gaussians
num_gaussians = data['positions'].shape[0]
print(f"Loaded {num_gaussians:,} Gaussians")
```

### Batch Import Multiple Files

```python
import import_gaussians

ply_files = [
    '/path/to/scene1.ply',
    '/path/to/scene2.ply',
    '/path/to/scene3.ply',
]

nodes = import_gaussians.batch_import_gaussians(ply_files)
print(f"Imported {len(nodes)} scenes")
```

### Adjust LOD for Performance

```python
import import_gaussians

# List all SplatCraft nodes
nodes = cmds.ls(type='splatCraftNode')

# Set all to 20% LOD for better performance
for node in nodes:
    import_gaussians.update_lod(node, 0.2)
```

### Get Node Information

```python
import import_gaussians

# Get info about a specific node
import_gaussians.get_node_info('splatCraftNode1')

# Output:
# SplatCraft Node: splatCraftNode1
# ==================================================
#   Gaussians: 196,608
#   LOD: 10.00%
#   Point Size: 2.0
#   Source File: /path/to/gaussians.ply
```

## Node Attributes

The `splatCraftNode` has the following attributes:

| Attribute | Type | Range | Description |
|-----------|------|-------|-------------|
| `numGaussians` | int | - | Total number of Gaussians (read-only) |
| `displayLOD` | float | 0.01-1.0 | Percentage of points to display |
| `pointSize` | float | 0.1-20.0 | Size of points in viewport |
| `enableRender` | bool | - | Enable/disable rendered panel |
| `filePath` | string | - | Path to source PLY file |

## Data Format

### PLY File Structure

The PLY files should contain the following per-vertex properties:

```
x, y, z              # Position
nx, ny, nz           # Normals (unused, can be 0)
red, green, blue     # Color (uint8, 0-255)
scale_x, scale_y, scale_z   # Gaussian scale
rot_0, rot_1, rot_2, rot_3  # Quaternion rotation
opacity              # Opacity (float, 0-1)
```

### Metadata NPZ File

Optional metadata file (same name as PLY with .npz extension):

```python
{
    'num_gaussians': int,
    'intrinsics': np.ndarray,      # [3, 3] camera intrinsics
    'inv_intrinsics': np.ndarray,  # [3, 3] inverse intrinsics
    'camera_to_world': np.ndarray, # [4, 4] transform (optional)
}
```

## Troubleshooting

### Plugin Won't Load

**Problem**: `Error: Could not load plugin`

**Solutions**:
1. Check Maya version (2022+)
2. Verify Python path is correct
3. Check dependencies are installed:
   ```python
   import numpy  # Should work
   import plyfile  # Should work
   ```

### No Points Visible in Viewport

**Problem**: Node created but nothing visible

**Solutions**:
1. Check LOD is not too low: `cmds.setAttr(f"{node}.displayLOD", 1.0)`
2. Verify Viewport 2.0 is enabled: `Viewport → Renderer → Viewport 2.0`
3. Check Gaussian data was loaded: `import_gaussians.get_node_info(node)`
4. Frame the object: Select node and press `F` key

### Import Errors

**Problem**: `FileNotFoundError` or `plyfile` errors

**Solutions**:
1. Verify PLY file path is correct
2. Check file exists and is readable
3. Ensure `plyfile` is installed in Maya's Python
4. Try reading file manually:
   ```python
   from plyfile import PlyData
   data = PlyData.read('/path/to/file.ply')
   ```

### Performance Issues

**Problem**: Viewport is slow/laggy

**Solutions**:
1. Reduce LOD: `cmds.setAttr(f"{node}.displayLOD", 0.1)` (10%)
2. Reduce point size: `cmds.setAttr(f"{node}.pointSize", 1.0)`
3. Disable other heavy viewports
4. Use Maya's Viewport 2.0 for better performance

## Current Status

**Implemented** (Phase 0-3):
- ✅ Maya node infrastructure
- ✅ PLY import/export utilities
- ✅ Viewport 2.0 point cloud rendering (Phase 3 COMPLETE)
- ✅ Full draw override implementation with LOD
- ✅ Per-vertex colored points in viewport
- ✅ LOD and display controls
- ✅ Example scripts and test suite

**Planned** (Future Phases):
- ⏳ OpenGL rendered panel (true 3DGS preview) - Phase 4
- ⏳ Transform synchronization - Phase 5
- ⏳ UI control panel - Phase 6-8
- ⏳ Advanced export options
- ⏳ Multi-scene support

## Development

### Running Examples

```python
# In Maya Script Editor (Python tab)
import sys
sys.path.append('/Users/yiliu/Documents/GitHub/flash3d/maya_plugin')

# Run examples
import examples.basic_usage as examples
examples.example_1_load_plugin()
examples.example_4_complete_workflow()
```

### Testing

```python
# Create a test node
import maya.cmds as cmds
node = cmds.createNode('splatCraftNode')
cmds.setAttr(f"{node}.numGaussians", 1000)
cmds.setAttr(f"{node}.displayLOD", 0.5)

# Query attributes
num = cmds.getAttr(f"{node}.numGaussians")
lod = cmds.getAttr(f"{node}.displayLOD")
print(f"Node has {num} Gaussians at {lod:.1%} LOD")
```

## Contributing

This is part of the SplatCraft project. See `IMPLEMENTATION_PLAN.md` for development roadmap.

## License

See main repository LICENSE file.

## Support

For issues and questions, refer to the main Flash3D repository or the implementation plan.

---

**Version**: 0.2.0 (Phase 3 Complete)
**Last Updated**: 2025-01-28

## Phase 3 Documentation

For detailed information about Phase 3 (Viewport Proxy) implementation, see [PHASE3_README.md](PHASE3_README.md)

To test Phase 3 features:
```python
import sys
sys.path.append('/Users/yiliu/Documents/GitHub/flash3d/maya_plugin')
import test_phase3
test_phase3.test_phase3_viewport()
```
