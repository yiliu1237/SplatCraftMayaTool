# SplatCraft – Maya Authoring & Generation Tool for 3D Gaussian Splatting

SplatCraft is a Maya-based toolkit for **creating, importing, editing, and visualizing 3D Gaussian Splatting (3DGS)** scenes.

SplatCraft lets you **upload a 2D image and automatically generate a 3D Gaussian Splat model** inside Maya.

---

## Key Features

### 3DGS Generation from a Single Image
- Upload an image in the Maya UI
- Background removal (optional)
- Generates a `.ply` Gaussian splat model using **Splatter-Image**
- Automatically imports it into the Maya scene

### 3DGS Scene Authoring in Maya
- Proxy viewport visualization (LOD-controlled, crash-safe)  
- Transform, duplicate, organize splats like normal Maya objects  
- Export edited scenes back to `.ply`  

### Embedded WebGL Viewer
- Gaussian rendering 
- Depth toggle (solid vs blended)  
- camera navigation

---

## Demo

Here's a quick preview of the full workflow — upload an image → generate 3D Gaussian Splats → auto-import into Maya → view/edit in real-time WebGL viewer.

![SplatCraft Demo](./demo.gif)

---

## Project Structure
```
SplatCraft/
├── maya_plugin/ # Main Maya authoring plugin
│ ├── ui/ # Qt-based Maya UI panels
│ │ ├── inference_panel.py # Image → 3DGS UI + progress bar
│ │ └── ...
│ ├── rendering/ (optional) # Maya viewport drawing (if used)
│ ├── nodes/ # Custom Maya nodes (splatCraftNode, etc.)
│ ├── webgl/ # HTML + JS WebGL Gaussian viewer
│ │ ├── viewer.html
│ │ ├── gaussian_viewer.js # Main WebGL rendering logic
│ │ └── ...
│ ├── import_gaussians.py # Loads PLY into Maya + WebGL bridge
│ ├── maya_webgl_panel.py # Embeds WebGL into a Maya dockable panel
│ ├── splatter_subprocess.py # Spawns backend inference in Conda
│ └── start_clean.py # Easy startup script for Maya on Windows + WSL
└── splatter-image/ (or external dependency) # Backend: image → 3D Gaussian Splats
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

## Workflow

1. **Launch Maya**
2. Load plugin:
   ```python
   import sys
   sys.path.insert(0, r'/path/to/SplatMayaTool/maya_plugin')
   import load_splatcraft
   load_splatcraft.load_plugin()
    ```
3. Open the inference UI:
   ```python
    from ui.inference_panel import show_inference_panel
    show_inference_panel(conda_env='splatter-image')
    ```
4. In the UI panel:
- Upload an image
- (Optional) Enable "Remove Background"
- Click Generate 3D Gaussian Splat
- Automatically imports .ply into Maya and opens WebGL preview

5. Quick Start
    ```python
    exec(open(r"/path/to/SplatMayaTool/maya_plugin/start_clean.py").read())
    ```
---

## WebGL Viewer Shortcuts

| Key / Mouse          | Action                               |
|----------------------|----------------------------------------|
| **M**                | Toggle manual camera control           |
| **Left Mouse Drag**  | Rotate camera around the model         |
| **Mouse Scroll**     | Zoom in/out                           |
| **W / A / S / D**    | Move camera forward / left / back / right |
| **Z / X**            | Move camera up / down                  |
| **O**                | Toggle depth write (solid vs. blended splats) |
| **Full 360° Pitch**  | Enabled — camera can look fully up/down |

---

## Backend Overview (Splatter-Image + Maya)

The Maya plugin uses the **splatter-image** backend to generate 3D Gaussian Splat (3DGS) scenes directly from a single 2D image.

### End-to-End Pipeline

```mermaid
graph LR
    A[User uploads image in Maya UI] --> B[Python inference process (splatter-image)]
    B --> C[Single-image → 3D Gaussian Splat reconstruction]
    C --> D[PLY file saved to /splatter_output]
    D --> E[Maya imports PLY as splatCraftNode]
    E --> F[Displayed in WebGL viewer + Maya viewport]
```

---

## Citation

```bibtex
@misc{splatcraft2025,
  title   = {SplatCraft: Maya Authoring and Generation Tool for 3D Gaussian Splatting},
  author  = {Anonymous},
  year    = {2025},
  note    = {Includes image-to-3DGS via Splatter-Image backend}
}
```
---


## License

See individual component licenses in their respective directories.
