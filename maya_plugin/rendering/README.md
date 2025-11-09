# Rendering Module

OpenGL-based 3D Gaussian Splatting renderer.

## Overview

This module provides a simplified but effective Gaussian splat renderer using OpenGL shaders. It displays Gaussians as point sprites with perspective-aware scaling and Gaussian falloff for smooth appearance.

## Components

### `splat_renderer.py`

**Main class:** `SplatRenderer`

**Key features:**
- Vertex/fragment shader compilation
- VBO/VAO management for efficient GPU upload
- Perspective-aware point sizing
- Gaussian falloff in fragment shader
- Proper alpha blending and depth testing

**Usage example:**
```python
from rendering.splat_renderer import SplatRenderer, create_perspective_matrix, create_look_at_matrix

# Initialize (after OpenGL context is created)
renderer = SplatRenderer()
renderer.initialize()

# Upload data
renderer.upload_gaussian_data(gaussian_data, max_points=50000)

# Render
view = create_look_at_matrix(eye, target, up)
proj = create_perspective_matrix(fov, aspect, near, far)
mvp = np.dot(proj, view)
renderer.render(mvp)

# Cleanup
renderer.cleanup()
```

## Shader Details

### Vertex Shader
- Input: position, color, opacity, scale (per-vertex)
- Uniforms: MVP matrix, point size scale
- Output: Transformed position with perspective-aware point size

### Fragment Shader
- Input: color, opacity (interpolated)
- Processing:
  - Calculate distance from point center
  - Discard pixels outside circle
  - Apply Gaussian falloff: `exp(-dist² / 2)`
  - Multiply opacity by Gaussian value
- Output: RGBA color with alpha blending

## Helper Functions

- `create_perspective_matrix(fov_y, aspect, near, far)` - Standard perspective projection
- `create_look_at_matrix(eye, target, up)` - Camera view matrix
- `create_orbit_camera(distance, azimuth, elevation, target)` - Orbit camera helper

## Requirements

- PyOpenGL
- NumPy
- OpenGL 3.3+ capable GPU

## Performance

Recommended point limits for 60 FPS:
- Low-end GPU: 20,000 - 50,000 points
- Mid-range GPU: 50,000 - 100,000 points
- High-end GPU: 100,000 - 200,000 points

## Future Improvements

- Tile-based rendering for larger datasets
- Anisotropic splatting (elliptical splats instead of circles)
- Advanced rasterization using `diff-gaussian-rasterization`
- Spherical harmonics for view-dependent colors
- Screen-space ambient occlusion
