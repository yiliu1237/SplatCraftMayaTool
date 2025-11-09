"""
OpenGL-based Gaussian Splat Renderer

This module provides a simplified 3D Gaussian splatting renderer using OpenGL.
It renders Gaussians as point sprites with perspective-aware scaling and
proper alpha blending.

Phase 4: Rendered Panel (3DGS Preview)
"""

import numpy as np
from OpenGL.GL import *
from OpenGL.GL import shaders
import ctypes


# Vertex shader - transforms points and passes data to fragment shader
# Using GLSL 120 for macOS compatibility
VERTEX_SHADER = """
#version 120

attribute vec3 position;
attribute vec3 color;
attribute float opacity;
attribute vec3 scale;

uniform mat4 mvp;
uniform float pointSizeScale;

varying vec3 fragColor;
varying float fragOpacity;

void main() {
    gl_Position = mvp * vec4(position, 1.0);

    // Perspective-aware point size
    // Use average scale as base size, adjust for distance
    float avgScale = (scale.x + scale.y + scale.z) / 3.0;
    float distance = gl_Position.w;
    gl_PointSize = max(1.0, (avgScale * pointSizeScale * 500.0) / distance);

    fragColor = color;
    fragOpacity = opacity;
}
"""

# Fragment shader - renders circular splat with Gaussian falloff
FRAGMENT_SHADER = """
#version 120

varying vec3 fragColor;
varying float fragOpacity;

void main() {
    // Get point coordinate in [0,1] range
    vec2 coord = gl_PointCoord * 2.0 - 1.0;

    // Calculate distance from center
    float dist = length(coord);

    // Discard pixels outside circle
    if (dist > 1.0) {
        discard;
    }

    // Use opacity from vertex shader (even if just for debugging)
    // This prevents the compiler from optimizing away the opacity attribute
    gl_FragColor = vec4(fragColor, fragOpacity);
}
"""


class SplatRenderer:
    """
    OpenGL-based renderer for 3D Gaussian splats

    This is a simplified renderer that displays Gaussians as point sprites
    with perspective-aware scaling and Gaussian falloff for alpha blending.

    Attributes:
        shader_program: Compiled OpenGL shader program
        vao: Vertex Array Object
        vbo_positions: VBO for Gaussian positions
        vbo_colors: VBO for Gaussian colors
        vbo_opacities: VBO for Gaussian opacities
        vbo_scales: VBO for Gaussian scales
        num_gaussians: Number of Gaussians loaded
        point_size_scale: Global scale factor for point sizes
    """

    def __init__(self):
        """Initialize the renderer (call after OpenGL context is created)"""
        self.shader_program = None
        self.vao = None
        self.vbo_positions = None
        self.vbo_colors = None
        self.vbo_opacities = None
        self.vbo_scales = None
        self.num_gaussians = 0
        self.point_size_scale = 1.0

        self.initialized = False

    def initialize(self):
        """
        Initialize OpenGL resources

        Must be called after OpenGL context is created and made current.
        """
        if self.initialized:
            return

        print("[SplatRenderer] Initializing OpenGL resources...")

        # Print OpenGL version for debugging
        gl_version = glGetString(GL_VERSION)
        glsl_version = glGetString(GL_SHADING_LANGUAGE_VERSION)
        print(f"[SplatRenderer] OpenGL Version: {gl_version}")
        print(f"[SplatRenderer] GLSL Version: {glsl_version}")

        # Compile shaders
        try:
            vertex_shader = shaders.compileShader(VERTEX_SHADER, GL_VERTEX_SHADER)
            fragment_shader = shaders.compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER)

            # Link program without validation (macOS compatibility)
            self.shader_program = glCreateProgram()
            glAttachShader(self.shader_program, vertex_shader)
            glAttachShader(self.shader_program, fragment_shader)

            # Bind attribute locations (GLSL 120 doesn't support layout qualifier)
            glBindAttribLocation(self.shader_program, 0, b"position")
            glBindAttribLocation(self.shader_program, 1, b"color")
            glBindAttribLocation(self.shader_program, 2, b"opacity")
            glBindAttribLocation(self.shader_program, 3, b"scale")

            glLinkProgram(self.shader_program)

            # Check link status
            link_status = glGetProgramiv(self.shader_program, GL_LINK_STATUS)
            error_log = glGetProgramInfoLog(self.shader_program)

            if error_log:
                error_str = error_log.decode() if isinstance(error_log, bytes) else str(error_log)
                print(f"[SplatRenderer] Link log: {error_str}")

            if not link_status:
                raise RuntimeError(f"Shader program link failed: {error_str if error_log else 'Unknown error'}")

            # Delete shader objects (no longer needed after linking)
            glDeleteShader(vertex_shader)
            glDeleteShader(fragment_shader)

            print("[SplatRenderer] ✓ Shaders compiled and linked successfully")
        except Exception as e:
            print(f"[SplatRenderer] ✗ Shader compilation failed: {e}")
            raise

        # Create VBOs (no VAO support in OpenGL 2.1)
        # VAOs were introduced in OpenGL 3.0, Maya uses 2.1
        self.vao = None  # Not used in OpenGL 2.1
        self.vbo_positions = glGenBuffers(1)
        self.vbo_colors = glGenBuffers(1)
        self.vbo_opacities = glGenBuffers(1)
        self.vbo_scales = glGenBuffers(1)

        # Enable OpenGL features for proper rendering
        glEnable(GL_PROGRAM_POINT_SIZE)  # Allow shader to set point size
        glEnable(GL_BLEND)  # Enable alpha blending
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)  # Standard alpha blending
        glEnable(GL_DEPTH_TEST)  # Enable depth testing
        glDepthFunc(GL_LESS)

        self.initialized = True
        print("[SplatRenderer] ✓ Initialized successfully")

    def upload_gaussian_data(self, gaussian_data, max_points=None):
        """
        Upload Gaussian data to GPU

        Args:
            gaussian_data: Dictionary with keys:
                - positions: [N, 3] numpy array
                - colors_dc: [N, 3] numpy array (RGB in [0,1])
                - opacities: [N] or [N, 1] numpy array
                - scales: [N, 3] numpy array
            max_points: Optional limit on number of points to upload
        """
        if not self.initialized:
            raise RuntimeError("Renderer not initialized! Call initialize() first.")

        print(f"[SplatRenderer] Uploading Gaussian data...")

        positions = gaussian_data['positions'].astype(np.float32)
        colors = gaussian_data['colors_dc'].astype(np.float32)
        opacities = gaussian_data['opacities'].astype(np.float32)
        scales = gaussian_data['scales'].astype(np.float32)

        # Apply max points limit if specified
        if max_points and positions.shape[0] > max_points:
            print(f"[SplatRenderer] Limiting to {max_points:,} points (from {positions.shape[0]:,})")
            np.random.seed(42)
            indices = np.random.choice(positions.shape[0], max_points, replace=False)
            positions = positions[indices]
            colors = colors[indices]
            opacities = opacities[indices]
            scales = scales[indices]

        # Ensure opacities is 1D
        if opacities.ndim == 2:
            opacities = opacities.reshape(-1)

        # Apply sigmoid to opacities (they're typically stored in logit space)
        # sigmoid(x) = 1 / (1 + exp(-x))
        opacities = 1.0 / (1.0 + np.exp(-opacities))

        # Apply exp to scales (they're typically stored in log space)
        scales = np.exp(scales)

        self.num_gaussians = positions.shape[0]

        # Ensure arrays are C-contiguous for OpenGL
        positions = np.ascontiguousarray(positions)
        colors = np.ascontiguousarray(colors)
        opacities = np.ascontiguousarray(opacities)
        scales = np.ascontiguousarray(scales)

        # Upload to GPU (no VAO binding in OpenGL 2.1)
        # Pass numpy arrays directly to glBufferData (Windows PyOpenGL compatibility)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_positions)
        glBufferData(GL_ARRAY_BUFFER, positions.nbytes, positions, GL_STATIC_DRAW)

        # Upload colors
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_colors)
        glBufferData(GL_ARRAY_BUFFER, colors.nbytes, colors, GL_STATIC_DRAW)

        # Upload opacities
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_opacities)
        glBufferData(GL_ARRAY_BUFFER, opacities.nbytes, opacities, GL_STATIC_DRAW)

        # Upload scales
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_scales)
        glBufferData(GL_ARRAY_BUFFER, scales.nbytes, scales, GL_STATIC_DRAW)

        # Unbind
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        print(f"[SplatRenderer] ✓ Uploaded {self.num_gaussians:,} Gaussians")
        print(f"  Position range: [{positions.min():.3f}, {positions.max():.3f}]")
        print(f"  Color range: [{colors.min():.3f}, {colors.max():.3f}]")
        print(f"  Opacity range: [{opacities.min():.3f}, {opacities.max():.3f}]")
        print(f"  Scale range: [{scales.min():.6f}, {scales.max():.6f}]")

    def render(self, mvp_matrix, clear=True):
        """
        Render the Gaussians

        Args:
            mvp_matrix: Model-View-Projection matrix (4x4 numpy array)
            clear: Whether to clear the framebuffer before rendering
        """
        if not self.initialized or self.num_gaussians == 0:
            return

        if clear:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Use shader program
        glUseProgram(self.shader_program)

        # Set uniforms
        mvp_location = glGetUniformLocation(self.shader_program, "mvp")
        glUniformMatrix4fv(mvp_location, 1, GL_TRUE, mvp_matrix.astype(np.float32))

        point_size_location = glGetUniformLocation(self.shader_program, "pointSizeScale")
        glUniform1f(point_size_location, self.point_size_scale)

        # Bind VBOs and set up vertex attributes (no VAO in OpenGL 2.1)
        # Position attribute (location 0)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_positions)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(0)

        # Color attribute (location 1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_colors)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(1)

        # Opacity attribute (location 2)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_opacities)
        glVertexAttribPointer(2, 1, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(2)

        # Scale attribute (location 3)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_scales)
        glVertexAttribPointer(3, 3, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(3)

        # Draw points
        glDrawArrays(GL_POINTS, 0, self.num_gaussians)

        # Disable vertex attributes
        glDisableVertexAttribArray(0)
        glDisableVertexAttribArray(1)
        glDisableVertexAttribArray(2)
        glDisableVertexAttribArray(3)

        # Unbind
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glUseProgram(0)

        # Ensure rendering is complete before Qt composites (important for QOpenGLWidget on Windows)
        glFlush()

    def set_point_size_scale(self, scale):
        """
        Set global point size scale factor

        Args:
            scale: Multiplier for point sizes (default 1.0)
        """
        self.point_size_scale = max(0.1, scale)

    def cleanup(self):
        """Clean up OpenGL resources"""
        if not self.initialized:
            return

        # No VAO to delete in OpenGL 2.1
        if self.vbo_positions:
            glDeleteBuffers(1, [self.vbo_positions])
        if self.vbo_colors:
            glDeleteBuffers(1, [self.vbo_colors])
        if self.vbo_opacities:
            glDeleteBuffers(1, [self.vbo_opacities])
        if self.vbo_scales:
            glDeleteBuffers(1, [self.vbo_scales])
        if self.shader_program:
            glDeleteProgram(self.shader_program)

        self.initialized = False
        print("[SplatRenderer] Cleaned up OpenGL resources")

    def __del__(self):
        """Destructor - clean up resources"""
        # Note: May not work reliably if OpenGL context is gone
        try:
            self.cleanup()
        except:
            pass


def create_perspective_matrix(fov_y, aspect, near, far):
    """
    Create perspective projection matrix

    Args:
        fov_y: Field of view in Y direction (radians)
        aspect: Aspect ratio (width/height)
        near: Near clipping plane
        far: Far clipping plane

    Returns:
        4x4 perspective projection matrix
    """
    f = 1.0 / np.tan(fov_y / 2.0)

    return np.array([
        [f / aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (far + near) / (near - far), (2 * far * near) / (near - far)],
        [0, 0, -1, 0]
    ], dtype=np.float32)


def create_look_at_matrix(eye, target, up):
    """
    Create view matrix using look-at transformation

    Args:
        eye: Camera position [x, y, z]
        target: Look-at target [x, y, z]
        up: Up vector [x, y, z]

    Returns:
        4x4 view matrix
    """
    eye = np.array(eye, dtype=np.float32)
    target = np.array(target, dtype=np.float32)
    up = np.array(up, dtype=np.float32)

    # Forward vector (camera looks down -Z)
    forward = target - eye
    forward = forward / np.linalg.norm(forward)

    # Right vector
    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)

    # Recompute up vector
    up = np.cross(right, forward)

    # Build view matrix
    view = np.eye(4, dtype=np.float32)
    view[0, :3] = right
    view[1, :3] = up
    view[2, :3] = -forward
    view[:3, 3] = -np.array([np.dot(right, eye), np.dot(up, eye), np.dot(forward, eye)])

    return view


def create_orbit_camera(distance, azimuth, elevation, target=None):
    """
    Create camera position using orbit parameters

    Args:
        distance: Distance from target
        azimuth: Horizontal angle in radians (0 = looking from +X)
        elevation: Vertical angle in radians (0 = horizontal)
        target: Look-at target [x, y, z] (default: origin)

    Returns:
        tuple: (eye_position, target, up_vector)
    """
    if target is None:
        target = np.array([0, 0, 0], dtype=np.float32)
    else:
        target = np.array(target, dtype=np.float32)

    # Compute camera position
    x = distance * np.cos(elevation) * np.cos(azimuth)
    y = distance * np.sin(elevation)
    z = distance * np.cos(elevation) * np.sin(azimuth)

    eye = target + np.array([x, y, z], dtype=np.float32)
    up = np.array([0, 1, 0], dtype=np.float32)

    return eye, target, up
