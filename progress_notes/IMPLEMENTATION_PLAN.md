# SplatCraft Implementation Plan

**Maya Authoring Tool for 3D Gaussian Splatting**

Version: Alpha → Beta
Target: Maya 2022+ on Windows 11 / Linux
Backend: Flash3D/Splatter-Image inference engine

---

## Table of Contents

1. [Project Architecture](#project-architecture)
2. [Development Phases](#development-phases)
3. [Phase 0: Environment Setup](#phase-0-environment-setup)
4. [Phase 1: Flash3D/Splatter-Image Export Bridge](#phase-1-flash3d-export-bridge)
5. [Phase 2: Maya Scene Node Foundation](#phase-2-maya-scene-node-foundation)
6. [Phase 3: Viewport Proxy (VP2)](#phase-3-viewport-proxy-vp2)
7. [Phase 4: Rendered Panel (3DGS Preview)](#phase-4-rendered-panel-3dgs-preview)
8. [Phase 5: Transform Synchronization](#phase-5-transform-synchronization)
9. [Phase 6: Display Controls & LOD](#phase-6-display-controls--lod)
10. [Phase 7: Export System](#phase-7-export-system)
11. [Phase 8: UI Panel Integration](#phase-8-ui-panel-integration)
12. [Beta Features](#beta-features)
13. [Testing Strategy](#testing-strategy)
14. [Performance Targets](#performance-targets)

---

## Project Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      SplatCraft Pipeline                     │
└─────────────────────────────────────────────────────────────┘

[Input Images]
      ↓
[Flash3D/Splatter-Image Inference] (Python/PyTorch)
      ↓
[Gaussian Data Export] (.ply / .splatcraft format)
      ↓
[Maya Import] (Python API)
      ↓
┌─────────────────┐
│ SplatCraft Node │ (Single Source of Truth)
└────────┬────────┘
         │
    ┌────┴────┐
    ↓         ↓
[VP2 Proxy]  [Rendered Panel]
(Fast)       (Accurate)
    │         │
    └────┬────┘
         ↓
[Export System] (.ply / .abc / custom)
```

### Core Components

| Component | Technology | Location | Purpose |
|-----------|-----------|----------|---------|
| **Flash3D/Splatter-Image Bridge** | Python | `/Splatter-Image/export_to_maya.py` | Extract Gaussian data from inference |
| **Maya Importer** | Python (Maya API) | `maya_plugin/import_gaussians.py` | Load data into Maya scene |
| **Scene Node** | Python (MPxNode) | `maya_plugin/nodes/splatcraft_node.py` | Store Gaussian parameters |
| **VP2 Proxy** | Python/C++ (VP2 Override) | `maya_plugin/viewport/proxy_drawable.py` | Fast point cloud display |
| **Rendered Panel** | Python/OpenGL | `maya_plugin/ui/rendered_panel.py` | True 3DGS preview |
| **UI Panel** | PySide2 | `maya_plugin/ui/main_panel.py` | Control interface |
| **Export System** | Python | `maya_plugin/export_gaussians.py` | Write authored scenes |

### Data Flow

```python
# Gaussian Splat Data Structure
{
    "positions": np.ndarray,      # [N, 3] xyz coordinates
    "opacities": np.ndarray,      # [N, 1] alpha values
    "scales": np.ndarray,         # [N, 3] Gaussian radii
    "rotations": np.ndarray,      # [N, 4] quaternions
    "colors_dc": np.ndarray,      # [N, 3] RGB (SH degree 0)
    "colors_sh": np.ndarray,      # [N, sh_degree*3] optional SH
    "camera_params": {
        "intrinsics": np.ndarray, # [3, 3] K matrix
        "fov": tuple,             # (fovX, fovY)
        "transform": np.ndarray   # [4, 4] world-to-camera
    }
}
```

---

## Development Phases

### Timeline Overview

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 0** | 1-2 days | Development environment ready |
| **Phase 1** | 3-4 days | Flash3D exports Gaussian data |
| **Phase 2** | 2-3 days | Maya scene node stores data |
| **Phase 3** | 3-4 days | Point cloud proxy renders in viewport |
| **Phase 4** | 5-6 days | Rendered panel shows true 3DGS |
| **Phase 5** | 2-3 days | Transform sync between views |
| **Phase 6** | 2-3 days | LOD controls and decimation |
| **Phase 7** | 2-3 days | Export system functional |
| **Phase 8** | 2-3 days | Complete UI panel |
| **Total Alpha** | ~23-31 days | End-to-end working prototype |

---

## Phase 0: Environment Setup

**Duration:** 1-2 days
**Goal:** Prepare development environment with Flash3D and Maya

### Tasks

#### 0.1 Flash3D Environment

### Validation Checklist
- [ ] Flash3D environment activates successfully
- [ ] Pretrained model downloads without errors
- [ ] Maya 2022+ installed and accessible
- [ ] Directory structure created
- [ ] Test images prepared

---

## Phase 1: Flash3D Export Bridge

**Duration:** 3-4 days
**Goal:** Extract Gaussian data from Flash3D inference and save to file

### 1.1 Create Export Script

**File:** `flash3d/export_to_maya.py`

### 1.2 Integration Script

**File:** `flash3d/inference_and_export.py`

### 1.3 Testing

### Validation Checklist
- [ ] Export script creates .ply file
- [ ] Metadata .npz file created
- [ ] Gaussian count matches expected range
- [ ] PLY file opens in MeshLab/CloudCompare
- [ ] Colors visible in point cloud viewer

---

## Phase 2: Maya Scene Node Foundation

**Duration:** 2-3 days
**Goal:** Create custom Maya node to store Gaussian data

### 2.1 Scene Node Implementation

**File:** `maya_plugin/nodes/splatcraft_node.py`


### 2.3 Testing in Maya

### Validation Checklist
- [ ] Plugin loads in Maya without errors
- [ ] SplatCraft node appears in Node Editor
- [ ] Import script reads PLY file correctly
- [ ] Node stores Gaussian count attribute
- [ ] Transform node created and linked

---

## Phase 3: Viewport Proxy (VP2)

**Duration:** 3-4 days
**Goal:** Display point cloud proxy in Maya viewport

### 3.1 Viewport 2.0 Override (Python)

**File:** `maya_plugin/viewport/proxy_drawable.py`


### Validation Checklist
- [ ] Point cloud visible in viewport
- [ ] Points have correct colors
- [ ] Can select and transform node
- [ ] Performance acceptable (>30 FPS for 10k points)
- [ ] LOD slider reduces point count

---

## Phase 4: Rendered Panel (3DGS Preview)

**Duration:** 5-6 days
**Goal:** Display true 3DGS rendering in separate panel

**Note:** This is the most complex phase. We'll start with a simplified OpenGL renderer.

### 4.1 Simplified Splat Renderer

**File:** `maya_plugin/rendering/splat_renderer.py`

### 4.2 Rendered Panel Widget

**File:** `maya_plugin/ui/rendered_panel.py`

### 4.3 Testing

### Validation Checklist
- [ ] Rendered panel opens without errors
- [ ] Gaussians visible as colored points
- [ ] Mouse drag rotates camera
- [ ] Mouse wheel zooms
- [ ] Alpha blending works correctly

---

## Phase 5: Transform Synchronization

**Duration:** 2-3 days
**Goal:** Keep viewport proxy and rendered panel synchronized

### 5.1 Transform Monitor

**File:** `maya_plugin/utils/transform_monitor.py`

### 5.2 Update Rendered Panel

**File:** `maya_plugin/ui/rendered_panel.py` (add method)

### Validation Checklist
- [ ] Moving viewport object updates rendered panel
- [ ] Rotation synchronized
- [ ] Scale synchronized
- [ ] No lag or flicker during transform

---

## Phase 6: Display Controls & LOD

**Duration:** 2-3 days
**Goal:** Add LOD slider and display controls

### 6.1 Control Panel

**File:** `maya_plugin/ui/control_panel.py`

### Validation Checklist
- [ ] Control panel displays correctly
- [ ] LOD slider changes viewport density
- [ ] Point size affects both views
- [ ] Import/export dialogs open
- [ ] Status updates correctly

---

## Phase 7: Export System

**Duration:** 2-3 days
**Goal:** Export authored Gaussian scenes

### 7.1 Export Implementation

**File:** `maya_plugin/export_gaussians.py`


### Validation Checklist
- [ ] Export creates valid PLY file
- [ ] Transform applied correctly
- [ ] Re-import matches original
- [ ] Metadata preserved

---

## Phase 8: UI Panel Integration

**Duration:** 2-3 days
**Goal:** Integrate all components into Maya UI

### 8.1 Main Panel

**File:** `maya_plugin/ui/main_panel.py`

### Validation Checklist
- [ ] Panel docks in Maya UI
- [ ] All controls functional
- [ ] Rendered panel integrated
- [ ] Panel persists across Maya sessions


---

## Testing Strategy

### Unit Tests
- Gaussian data I/O
- Transform math
- LOD decimation

### Integration Tests
- Full pipeline (image → inference → import → export)
- Transform synchronization
- Multi-scene handling

### Performance Tests
- 10k, 100k, 1M Gaussian benchmarks
- Frame rate targets (>30 FPS viewport, >15 FPS rendered)
- Memory profiling

### User Acceptance Tests
- End-to-end workflow tests
- Usability evaluation
- Bug tracking

---

## Performance Targets

| Metric | Alpha Target | Beta Target |
|--------|-------------|-------------|
| **Viewport FPS** (100k points) | >30 FPS | >60 FPS |
| **Rendered FPS** (100k points) | >15 FPS | >30 FPS |
| **Import time** (100k points) | <5 sec | <2 sec |
| **Export time** (100k points) | <5 sec | <2 sec |
| **Memory usage** (100k points) | <500 MB | <300 MB |
| **Max Gaussians** | 1M | 10M |

---

## Dependencies

### Python Packages
```
numpy>=1.26.4
PySide2>=5.15
PyOpenGL>=3.1.5
plyfile>=0.7.4
```

### Maya Requirements
- Maya 2022 or later
- Viewport 2.0 enabled
- Python 3.x support

---

## Resources

- [Flash3D Paper](https://arxiv.org/abs/2406.04343)
- [3D Gaussian Splatting](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)
- [Maya Python API 2.0](https://help.autodesk.com/view/MAYAUL/2022/ENU/?guid=Maya_SDK_py_ref_index_html)
- [Viewport 2.0 Override](https://help.autodesk.com/view/MAYAUL/2022/ENU/?guid=Maya_SDK_Viewport_2_0_API_index_html)

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21