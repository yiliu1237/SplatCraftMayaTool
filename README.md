# SplatCraft – Maya Authoring & Generation Tool for 3D Gaussian Splatting

SplatCraft is a Maya-based toolkit for **creating, importing, editing, and visualizing 3D Gaussian Splatting (3DGS)** scenes. Upload a 2D image and automatically generate a 3D Gaussian Splat model inside Maya, then author complex multi-object scenes with real-time WebGL visualization.

---

## Key Features

### 3DGS Generation from a Single Image
- Upload an image in the Maya UI
- Background removal (optional)
- Generates a `.ply` Gaussian splat model using **Splatter-Image**
- Automatically imports it into the Maya scene

### 3DGS Scene Authoring in Maya
- **Multi-object scene management** – Manage multiple 3DGS objects simultaneously
- **Maya viewport proxy** – LOD-controlled point cloud visualization (crash-safe)
- **Transform and organize** – Move, rotate, scale, duplicate splats like normal Maya objects
- **Real-time synchronization** – Object transforms automatically sync with WebGL viewer
- **Automatic deletion detection** – Remove objects from Maya, they disappear from viewer instantly
- Export edited scenes back to `.ply`  

### Real-Time WebGL Viewer
- **Multi-object rendering** – View entire scene with all 3DGS objects simultaneously
- **Bidirectional synchronization:**
  - WebGL → Maya: Camera movements update Maya viewport in real-time
  - Maya → WebGL: Object transforms sync automatically (100ms polling)
- **Interactive navigation** – Manual camera controls (WASD/ZX movement, mouse rotation, scroll zoom)
- **Visual aids** – Toggle XZ ground plane grid, XYZ reference axes, and depth rendering modes
- **Integrated controls** – All features accessible via in-viewer button panel
- **Reset view** – Instantly return to initial camera position

---

## Demo

Here's a quick preview of the full workflow — upload an image → generate 3D Gaussian Splats → auto-import into Maya → view/edit in real-time WebGL viewer.

![SplatCraft Demo](./demo.gif)

---

## Project Structure
```
SplatCraft/
├── maya_plugin/                    # Main Maya authoring plugin
│   ├── ui/                         # Qt-based Maya UI panels
│   │   ├── inference_panel.py      # Image → 3DGS UI + progress bar
│   │   └── ...
│   ├── webgl_viewer/               # WebGL Gaussian viewer (embedded in Maya)
│   │   ├── gaussian_viewer.html    # Main HTML viewer interface
│   │   ├── gaussian_renderer.js    # WebGL rendering engine (multi-object)
│   │   └── ...
│   ├── splatcraft_node.py          # Custom Maya node for 3DGS data
│   ├── splatcraft_plugin.py        # Maya plugin loader
│   ├── import_gaussians.py         # PLY importer + scene loader
│   ├── maya_webgl_panel.py         # Embeds WebGL into Maya dockable panel
│   │                               # Handles multi-object sync & deletion detection
│   ├── splatter_subprocess.py      # Spawns backend inference in Conda
│   ├── load_splatcraft.py          # Plugin initialization helper
│   └── start_clean.py              # Quick startup script (Windows + WSL)
└── splatter-image/                 # Backend: image → 3D Gaussian Splats
```

---

## System Requirements

| Component | Requirement |
|-----------|-------------|
| OS        | Windows 10/11 with WSL Ubuntu **or** native Linux |
| GPU       | NVIDIA GPU with CUDA 12.x (for splatter-image) |
| Maya      | Autodesk Maya 2022–2025 (Python 3.9–3.10) |
| Python    | Maya-side: Python 3.9 / Backend: Python 3.10 |
| Backend   | Conda env with PyTorch + CUDA |
| Viewer    | PySide2 or PySide6 + WebGL-enabled Qt |

### Required Components

- **Autodesk Maya** 
- **WSL Ubuntu (if on Windows)**  
  ```powershell
  wsl --install -d Ubuntu
  ```
- **Conda for backend**  
- **NVIDIA CUDA drivers (Windows or WSL)**
- **PySide2 / PySide6 available in Maya's Python**

---

## Quick Start

**One-line command** (Windows + WSL):
```python
exec(open(r'\\wsl$\Ubuntu\root\SplatMayaTool\maya_plugin\start_clean.py').read())
```

Or **step-by-step**:
```python
# 1. Add plugin to path
import sys
sys.path.insert(0, r'/path/to/SplatMayaTool/maya_plugin')

# 2. Load plugin
import load_splatcraft
load_splatcraft.load_plugin()

# 3. Open inference UI
from ui.inference_panel import show_inference_panel
show_inference_panel(conda_env='splatter-image')
```

---

## Workflow

### Generating 3DGS from Images
1. Launch Maya and run the quick start command
2. In the inference panel:
   - Click **"Browse Image..."** to select an input image
   - (Optional) Enable **"Remove Background"** for cleaner results
   - Click **"Generate 3D Gaussian Splat"**
3. The generated `.ply` file automatically imports into Maya
4. WebGL viewer opens automatically showing the full-resolution Gaussian splat

### Working with Multi-Object Scenes
Import multiple objects into your scene:
```python
import import_gaussians

# Import multiple PLY files
node1, _ = import_gaussians.import_gaussian_scene('/path/to/object1.ply')
node2, _ = import_gaussians.import_gaussian_scene('/path/to/object2.ply')
node3, _ = import_gaussians.import_gaussian_scene('/path/to/object3.ply')
```

**Scene management:**
- WebGL viewer displays **all objects** simultaneously
- **Transform objects** in Maya → Changes sync to WebGL in real-time
- **Delete objects** in Maya → They disappear from WebGL automatically
- **Navigate in WebGL** → Maya camera follows your movements
- Info panel shows: `Objects: 3 | Gaussians: 500,000`

---

## WebGL Viewer Reference

### Control Panel Buttons
| Button | Function |
|--------|----------|
| **Manual Control** | Toggle manual camera navigation (default: ON) |
| **Grid** | Show/hide XZ ground plane grid and XYZ reference axes |
| **Reset View** | Return camera to initial position |
| **Camera Sync** | Toggle WebGL → Maya camera synchronization (default: ON) |
| **Object Sync** | Toggle Maya → WebGL object transform sync (default: ON) |

### Navigation Controls
| Input | Action |
|-------|--------|
| **Mouse Drag** | Rotate camera (orbit around target) |
| **Mouse Wheel** | Zoom in/out |
| **W / A / S / D** | Move forward / left / back / right |
| **Z / X** | Move up / down |
| **O** | Toggle depth write (solid vs. alpha-blended rendering) |

### Info Display
- **Objects:** 3DGS object count in scene
- **Gaussians:** Total splat count across all objects
- **FPS:** Rendering frame rate
- **Camera:** Current mode (Manual / Synced)

---

## Backend

SplatCraft uses the **[Splatter Image](https://arxiv.org/abs/2312.13150)** model as its core backend for **single-image to 3D Gaussian Splat (3DGS)** generation.  
This feed-forward network enables fast, one-shot reconstruction of 3D splats directly from a single RGB input, allowing seamless integration with the Maya authoring pipeline.

---


## License

See individual component licenses in their respective directories.
