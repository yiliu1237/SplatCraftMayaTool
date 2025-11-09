# """
# Maya-Integrated Rendered Panel with Camera Sync

# Creates a dockable Maya panel showing 3DGS rendering that stays synchronized
# with Maya's viewport camera. When you tumble/pan/zoom in Maya, the rendered
# panel updates to match.

# Usage in Maya:
#     import maya_rendered_panel
#     maya_rendered_panel.show_panel()
# """

# import maya.cmds as cmds
# import maya.OpenMaya as om
# import maya.OpenMayaUI as omui
# import sys
# import os
# import numpy as np

# # Add plugin path
# maya_plugin_path = os.path.dirname(os.path.abspath(__file__))
# if maya_plugin_path not in sys.path:
#     sys.path.insert(0, maya_plugin_path)

# try:
#     from PySide2.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton
#     from PySide2.QtCore import Qt, QTimer
#     from PySide2.QtOpenGL import QGLWidget as GLWidgetBase
#     from shiboken2 import wrapInstance
#     USING_PYSIDE6 = False
# except ImportError:
#     from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton
#     from PySide6.QtCore import Qt, QTimer
#     from PySide6.QtOpenGLWidgets import QOpenGLWidget as GLWidgetBase
#     from shiboken6 import wrapInstance
#     USING_PYSIDE6 = True

# from OpenGL.GL import *
# from OpenGL.GL import glBindFramebuffer, GL_FRAMEBUFFER
# from rendering.splat_renderer import SplatRenderer, create_perspective_matrix, create_look_at_matrix

# # Global reference
# _MAYA_RENDERED_PANEL = None


# class MayaSyncedGLWidget(GLWidgetBase):
#     """
#     OpenGL widget that syncs with Maya's active camera

#     This widget queries Maya's camera transform every frame and uses
#     it to render the 3DGS data, keeping the view synchronized.
#     """

#     def __init__(self, parent=None):
#         super(MayaSyncedGLWidget, self).__init__(parent)

#         # For QOpenGLWidget (PySide6), set explicit update behavior
#         if USING_PYSIDE6:
#             # This is critical for Windows - forces the widget to actually display rendered content
#             try:
#                 from PySide6.QtOpenGLWidgets import QOpenGLWidget
#                 self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.PartialUpdate)
#             except:
#                 pass

#         # Renderer
#         self.renderer = SplatRenderer()
#         self.pending_data = None

#         # Point size scale
#         self.point_size_scale = 1.0

#         # Set up continuous rendering (sync with Maya)
#         self.render_timer = QTimer()
#         self.render_timer.timeout.connect(self.update)
#         self.render_timer.start(16)  # ~60 FPS

#     def initializeGL(self):
#         """Initialize OpenGL context"""
#         glClearColor(0.1, 0.1, 0.1, 1.0)
#         self.renderer.initialize()
#         print("[MayaSyncedGLWidget] OpenGL initialized")

#         # Upload pending data if any
#         if self.pending_data is not None:
#             data, max_points = self.pending_data
#             self.pending_data = None
#             self._do_upload(data, max_points)

#     def resizeGL(self, width, height):
#         """Handle window resize"""
#         glViewport(0, 0, width, height)
#         self.width = width
#         self.height = height

#     def paintGL(self):
#         """Render using Maya's current camera"""
#         # For QOpenGLWidget (PySide6), ensure we're rendering to the correct framebuffer
#         if USING_PYSIDE6:
#             try:
#                 # Bind to the widget's default framebuffer object
#                 fbo_id = self.defaultFramebufferObject()
#                 glBindFramebuffer(GL_FRAMEBUFFER, fbo_id)
#             except:
#                 pass  # Fallback if defaultFramebufferObject() not available

#         if not self.renderer.initialized or self.renderer.num_gaussians == 0:
#             glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
#             return

#         # Get Maya's active camera matrix
#         mvp = self.get_maya_camera_mvp()
#         if mvp is None:
#             glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
#             return

#         # Render with Maya's camera
#         self.renderer.render(mvp, clear=True)

#     def get_maya_camera_mvp(self):
#         """
#         Get model-view-projection matrix from Maya's active viewport camera

#         Returns:
#             np.ndarray: 4x4 MVP matrix, or None if failed
#         """
#         try:
#             # Get active viewport
#             active_view = omui.M3dView.active3dView()

#             # Get camera
#             camera_dag = om.MDagPath()
#             active_view.getCamera(camera_dag)

#             # Get camera transform matrix (world space)
#             camera_fn = om.MFnCamera(camera_dag)

#             # Get view matrix (inverse of camera transform)
#             camera_matrix = camera_dag.inclusiveMatrix()
#             view_matrix = camera_matrix.inverse()

#             # Convert to numpy (row-major to column-major)
#             view = np.array([
#                 [view_matrix(0, 0), view_matrix(1, 0), view_matrix(2, 0), view_matrix(3, 0)],
#                 [view_matrix(0, 1), view_matrix(1, 1), view_matrix(2, 1), view_matrix(3, 1)],
#                 [view_matrix(0, 2), view_matrix(1, 2), view_matrix(2, 2), view_matrix(3, 2)],
#                 [view_matrix(0, 3), view_matrix(1, 3), view_matrix(2, 3), view_matrix(3, 3)]
#             ], dtype=np.float32)

#             # Get projection matrix from camera
#             # Maya uses horizontal FOV, we need vertical FOV
#             h_fov = camera_fn.horizontalFieldOfView()  # radians
#             aspect = self.width / max(1.0, self.height)
#             v_fov = 2.0 * np.arctan(np.tan(h_fov / 2.0) / aspect)

#             near = camera_fn.nearClippingPlane()
#             far = camera_fn.farClippingPlane()

#             # Create projection matrix
#             proj = create_perspective_matrix(v_fov, aspect, near, far)

#             # Combine view and projection
#             mvp = np.dot(proj, view)

#             return mvp

#         except Exception as e:
#             # Silently fail (camera might not be ready yet)
#             return None

#     def upload_gaussian_data(self, gaussian_data, max_points=None):
#         """Upload Gaussian data to renderer"""
#         if not self.renderer.initialized:
#             print("[MayaSyncedGLWidget] Deferring data upload until OpenGL is initialized")
#             self.pending_data = (gaussian_data, max_points)
#             return

#         self._do_upload(gaussian_data, max_points)

#     def _do_upload(self, gaussian_data, max_points):
#         """Internal method to upload data"""
#         self.renderer.upload_gaussian_data(gaussian_data, max_points)
#         print(f"[MayaSyncedGLWidget] ✓ Uploaded {self.renderer.num_gaussians:,} Gaussians")

#     def set_point_size_scale(self, scale):
#         """Set point size scale"""
#         self.point_size_scale = scale
#         self.renderer.set_point_size_scale(scale)


# class MayaRenderedPanel(QWidget):
#     """
#     Maya-integrated rendered panel with camera sync

#     This panel shows 3DGS rendering synchronized with Maya's viewport.
#     """

#     def __init__(self, parent=None):
#         super(MayaRenderedPanel, self).__init__(parent)
#         self.setup_ui()

#     def setup_ui(self):
#         """Set up the user interface"""
#         layout = QVBoxLayout(self)

#         # OpenGL viewport (synced with Maya camera)
#         self.gl_widget = MayaSyncedGLWidget()
#         layout.addWidget(self.gl_widget, stretch=1)

#         # Control panel
#         controls_layout = QHBoxLayout()

#         # Point size slider
#         controls_layout.addWidget(QLabel("Point Size:"))
#         self.point_size_slider = QSlider(Qt.Horizontal)
#         self.point_size_slider.setMinimum(10)
#         self.point_size_slider.setMaximum(300)
#         self.point_size_slider.setValue(100)
#         self.point_size_slider.valueChanged.connect(self.update_point_size)
#         controls_layout.addWidget(self.point_size_slider)

#         self.point_size_label = QLabel("1.0x")
#         controls_layout.addWidget(self.point_size_label)

#         layout.addLayout(controls_layout)

#         # Status label
#         self.status_label = QLabel("Ready - Camera synced with Maya viewport")
#         layout.addWidget(self.status_label)

#         self.setLayout(layout)

#     def update_point_size(self, value):
#         """Update point size scale"""
#         scale = value / 100.0
#         self.gl_widget.set_point_size_scale(scale)
#         self.point_size_label.setText(f"{scale:.1f}x")

#     def upload_gaussian_data(self, gaussian_data, max_points=None):
#         """Upload Gaussian data to renderer"""
#         self.gl_widget.upload_gaussian_data(gaussian_data, max_points)

#         num_points = gaussian_data['positions'].shape[0]
#         if max_points and num_points > max_points:
#             self.status_label.setText(f"Rendering {max_points:,} / {num_points:,} Gaussians - Camera synced")
#         else:
#             self.status_label.setText(f"Rendering {num_points:,} Gaussians - Camera synced")


# def get_maya_main_window():
#     """Get Maya's main window as Qt widget"""
#     main_window_ptr = omui.MQtUtil.mainWindow()
#     return wrapInstance(int(main_window_ptr), QWidget)


# def get_gaussian_data_from_node(node_name):
#     """Retrieve Gaussian data from SplatCraft node"""
#     try:
#         import builtins

#         if hasattr(builtins, '_SPLATCRAFT_PLUGIN_GLOBALS'):
#             plugin_globals = builtins._SPLATCRAFT_PLUGIN_GLOBALS
#             node_data = plugin_globals['_NODE_DATA']

#             if node_name in node_data:
#                 return node_data[node_name]
#             else:
#                 print(f"✗ No data found for node: {node_name}")
#                 print(f"  Available nodes: {list(node_data.keys())}")
#                 return None
#         else:
#             print("✗ Plugin not initialized")
#             return None

#     except Exception as e:
#         print(f"✗ Error retrieving data: {e}")
#         import traceback
#         traceback.print_exc()
#         return None


# def show_panel(node_name=None):
#     """
#     Show the rendered panel docked in Maya, synced with viewport camera

#     Args:
#         node_name: Optional SplatCraft node name. If None, uses selected node.

#     Returns:
#         MayaRenderedPanel instance
#     """
#     global _MAYA_RENDERED_PANEL

#     print("\n" + "="*70)
#     print("SplatCraft - Maya Rendered Panel (Camera Synced)")
#     print("="*70)

#     # Get node name
#     if node_name is None:
#         selection = cmds.ls(selection=True, type='splatCraftNode')
#         if not selection:
#             print("\n✗ No SplatCraft node selected")
#             print("\nPlease select a SplatCraft node and try again.")
#             all_nodes = cmds.ls(type='splatCraftNode')
#             if all_nodes:
#                 print("\nAvailable nodes:")
#                 for node in all_nodes:
#                     print(f"  - {node}")
#             return None
#         node_name = selection[0]

#     # Check if node exists
#     if not cmds.objExists(node_name):
#         print(f"✗ Node does not exist: {node_name}")
#         return None

#     # Get Gaussian data
#     print(f"\n1. Retrieving data from node: {node_name}")
#     gaussian_data = get_gaussian_data_from_node(node_name)

#     if gaussian_data is None:
#         print("✗ Failed to retrieve Gaussian data")
#         return None

#     num_gaussians = gaussian_data['positions'].shape[0]
#     print(f"   ✓ Found {num_gaussians:,} Gaussians")

#     # Determine max points
#     # OPTION 1: No limits - render ALL Gaussians (may be slow for huge models)
#     max_points = None

#     # OPTION 2: Set your own limit (uncomment and adjust if needed)
#     # max_points = 500000  # Render up to 500k Gaussians

#     # OPTION 3: Original adaptive limits (commented out)
#     # if num_gaussians > 1000000:
#     #     max_points = 50000
#     # elif num_gaussians > 500000:
#     #     max_points = 100000
#     # elif num_gaussians > 100000:
#     #     max_points = 200000
#     # else:
#     #     max_points = None

#     # Create workspace control
#     workspace_control_name = "SplatCraftRenderedPanel"

#     if cmds.workspaceControl(workspace_control_name, exists=True):
#         cmds.deleteUI(workspace_control_name)

#     print("\n2. Creating Maya-docked panel...")
#     workspace_control = cmds.workspaceControl(
#         workspace_control_name,
#         label="SplatCraft 3DGS Renderer",
#         retain=False,
#         floating=False,  # Dock by default
#         dockToMainWindow=('right', 1),  # Dock to right side
#         widthProperty="free",
#         heightProperty="free",
#         initialWidth=600,
#         initialHeight=800
#     )

#     # Get Qt widget for workspace control
#     workspace_control_ptr = omui.MQtUtil.findControl(workspace_control_name)
#     workspace_control_widget = wrapInstance(int(workspace_control_ptr), QWidget)

#     # Create rendered panel
#     panel = MayaRenderedPanel(parent=workspace_control_widget)
#     workspace_control_widget.layout().addWidget(panel)

#     # Upload data
#     print(f"\n3. Uploading Gaussians to GPU...")
#     if max_points:
#         print(f"   Limiting to {max_points:,} points (from {num_gaussians:,})")

#     try:
#         panel.upload_gaussian_data(gaussian_data, max_points=max_points)
#         print("   ✓ Data uploaded successfully")
#     except Exception as e:
#         print(f"   ✗ Error uploading data: {e}")
#         import traceback
#         traceback.print_exc()
#         return None

#     # Store reference
#     _MAYA_RENDERED_PANEL = panel

#     # Get file info
#     file_path = cmds.getAttr(f"{node_name}.filePath")
#     file_name = os.path.basename(file_path) if file_path else node_name

#     print("\n" + "="*70)
#     print("✓ RENDERED PANEL CREATED - CAMERA SYNCED")
#     print("="*70)
#     print(f"\nNode: {node_name}")
#     print(f"File: {file_name}")
#     print(f"Rendering: {max_points or num_gaussians:,} / {num_gaussians:,} Gaussians")
#     print("\n📷 Camera Synchronization:")
#     print("  The rendered panel uses Maya's active viewport camera")
#     print("  When you tumble/pan/zoom in Maya, the panel updates automatically")
#     print("\n🎮 Controls:")
#     print("  - Use Maya's normal viewport navigation (Alt+LMB, Alt+MMB, etc.)")
#     print("  - The rendered panel will follow your camera movements")
#     print("  - Adjust point size with the slider in the panel")
#     print("\n💡 Tip: Dock the panel next to your viewport for dual-view!")
#     print("="*70 + "\n")

#     return panel


# def close_panel():
#     """Close the rendered panel"""
#     workspace_control_name = "SplatCraftRenderedPanel"

#     if cmds.workspaceControl(workspace_control_name, exists=True):
#         cmds.deleteUI(workspace_control_name)
#         print("✓ Rendered panel closed")
#     else:
#         print("No rendered panel open")


# if __name__ == "__main__":
#     print("\nSplatCraft - Maya Rendered Panel")
#     print("\nUsage:")
#     print("  1. Select a SplatCraft node")
#     print("  2. import maya_rendered_panel")
#     print("  3. maya_rendered_panel.show_panel()")
#     print("\nThe panel will sync with Maya's camera automatically!")
