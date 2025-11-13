"""
Maya Panel with Embedded WebGL Gaussian Splat Viewer

This uses QWebEngineView to embed a Chromium browser that renders
Gaussians using WebGL, completely bypassing Maya's OpenGL limitations.
"""

import os
import json
import numpy as np
from PySide6 import QtWidgets, QtCore, QtWebEngineWidgets, QtWebChannel
from PySide6.QtCore import QUrl, QTimer, Slot
import maya.cmds as cmds
import maya.OpenMayaUI as omui
from shiboken6 import wrapInstance


# Global reference to the panel
_WEBGL_PANEL = None


class MayaToPy(QtCore.QObject):
    """
    Qt object for JavaScript to Python communication bridge
    """
    def __init__(self, parent_panel=None):
        super().__init__()
        self.parent_panel = parent_panel

    @Slot(str)
    def log(self, message):
        """Called from JavaScript to log messages to Python console"""
        print(f"[WebGL] {message}")

    @Slot(result=str)
    def test(self):
        """Test method to verify WebChannel connection"""
        print("[MayaToPy Bridge] test() called - WebChannel is working!")
        return "Connection OK"

    @Slot(str)
    def updateMayaCamera(self, camera_json):
        """Called from JavaScript to update Maya camera from WebGL viewer"""
        try:
            camera_data = json.loads(camera_json)
            if self.parent_panel:
                self.parent_panel.applyCameraToMaya(camera_data)
        except Exception as e:
            print(f"[WebGL→Maya] Error updating camera: {e}")

    @Slot()
    def requestMayaCamera(self):
        """Called from JavaScript to request current Maya camera state"""
        print("[MayaToPy Bridge] requestMayaCamera() called from JavaScript")
        try:
            if self.parent_panel:
                print("[MayaToPy Bridge] Calling parent_panel.sendMayaCameraToWebGL()...")
                self.parent_panel.sendMayaCameraToWebGL()
            else:
                print("[MayaToPy Bridge] ERROR: No parent_panel set!")
        except Exception as e:
            print(f"[Maya→WebGL] Error sending camera: {e}")
            import traceback
            traceback.print_exc()


class WebGLGaussianPanel(QtWidgets.QDialog):
    """
    Maya-integrated panel with WebGL Gaussian splat viewer
    """

    def __init__(self, node_name=None, ply_path=None, parent=None):
        if parent is None:
            # Get Maya main window as parent
            maya_main_window_ptr = omui.MQtUtil.mainWindow()
            parent = wrapInstance(int(maya_main_window_ptr), QtWidgets.QWidget)

        super(WebGLGaussianPanel, self).__init__(parent)

        self.node_name = node_name
        self.ply_path = ply_path
        self.gaussian_data = None
        self.data_loaded = False
        self.camera_sync_enabled = False  # Camera view synchronization toggle
        self.object_sync_enabled = False  # Object transformation synchronization toggle

        # Transform monitoring
        self.last_transform_matrix = None
        self.transform_update_count = 0
        self.transform_monitor_timer = None

        # Setup UI
        self.setWindowTitle("SplatCraft - WebGL Viewer")
        self.setWindowFlags(QtCore.Qt.Window)
        self.resize(1200, 800)

        self.setupUI()
        self.loadGaussianData()

        print("[WebGLPanel] Panel initialized")

    def setupUI(self):
        """Create the UI layout"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add sync control bar
        control_layout = QtWidgets.QHBoxLayout()

        # Camera sync checkbox
        self.sync_checkbox = QtWidgets.QCheckBox("Sync Camera View with Maya")
        self.sync_checkbox.setChecked(False)
        self.sync_checkbox.setToolTip("Rotate view in WebGL → Maya camera orbits (object stays still)")
        self.sync_checkbox.toggled.connect(self.toggleCameraSync)
        control_layout.addWidget(self.sync_checkbox)

        # Object transform sync checkbox
        self.object_sync_checkbox = QtWidgets.QCheckBox("Sync Object Transform")
        self.object_sync_checkbox.setChecked(False)
        self.object_sync_checkbox.setToolTip("Rotate Maya object → Gaussians rotate in WebGL viewer")
        self.object_sync_checkbox.toggled.connect(self.toggleObjectSync)
        control_layout.addWidget(self.object_sync_checkbox)

        control_layout.addStretch()
        layout.addLayout(control_layout)

        # WebGL viewer (embedded browser) - takes full window
        self.web_view = QtWebEngineWidgets.QWebEngineView()

        # Load the HTML file
        html_path = os.path.join(
            os.path.dirname(__file__),
            'webgl_viewer',
            'gaussian_viewer.html'
        )

        if not os.path.exists(html_path):
            print(f"[ERROR] HTML file not found: {html_path}")
            # No info_label anymore
            return

        # Convert to file URL
        file_url = QUrl.fromLocalFile(html_path)
        print(f"[WebGLPanel] Loading: {file_url.toString()}")

        self.web_view.setUrl(file_url)
        layout.addWidget(self.web_view)

        # Setup web channel for Python ↔ JavaScript communication
        self.channel = QtWebChannel.QWebChannel()
        self.bridge = MayaToPy(parent_panel=self)
        self.channel.registerObject('pybridge', self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        # Wait for page to load before sending data
        self.web_view.loadFinished.connect(self.onPageLoaded)

    def onPageLoaded(self, success):
        """Called when the web page finishes loading"""
        if success:
            print("[WebGLPanel] WebGL viewer loaded successfully")
            # Removed info_label - WebGL has its own overlay


            # Send Gaussian data if we have it
            if self.gaussian_data and not self.data_loaded:
                self.sendGaussianDataToViewer()

                # WebGL will use manual control mode for navigation
                print("[WebGLPanel] WebGL viewer has initial centered view")
                print("[WebGLPanel] Use 'Manual Control' button to navigate")
        else:
            print("[WebGLPanel] ERROR: Failed to load web page")
            # No info_label anymore

    def loadGaussianData(self):
        """Load Gaussian data from PLY file or SplatCraft node"""

        # Option 1: Load from PLY file directly
        if self.ply_path:
            self.loadFromPLY(self.ply_path)
            return

        # Option 2: Load from SplatCraft node (via pickle)
        if self.node_name and cmds.objExists(self.node_name):
            self.loadFromNode(self.node_name)
            return

        print("[WebGLPanel] No data source specified (need ply_path or node_name)")

    def loadFromPLY(self, ply_path):
        """Load Gaussian data directly from PLY file"""
        if not os.path.exists(ply_path):
            print(f"[WebGLPanel] PLY file not found: {ply_path}")
            return

        print(f"[WebGLPanel] Loading from PLY: {ply_path}")

        try:
            from plyfile import PlyData

            plydata = PlyData.read(ply_path)
            vertices = plydata['vertex']

            # Extract data
            positions = np.vstack([vertices['x'], vertices['y'], vertices['z']]).T.astype(np.float32)

            # Colors (SH coefficients)
            colors_dc = np.vstack([
                vertices['f_dc_0'],
                vertices['f_dc_1'],
                vertices['f_dc_2']
            ]).T.astype(np.float32)

            opacities_raw = vertices['opacity'].astype(np.float32)
            scales_raw = np.vstack([
                vertices['scale_0'],
                vertices['scale_1'],
                vertices['scale_2']
            ]).T.astype(np.float32)

            rotations = np.vstack([
                vertices['rot_0'], vertices['rot_1'],
                vertices['rot_2'], vertices['rot_3']
            ]).T.astype(np.float32)

            # If file is (w,x,y,z), reorder to (x,y,z,w)
            # Heuristic: if column 0 looks like w (bigger magnitude than col 3), swap.
            if np.mean(np.abs(rotations[:, 0])) > np.mean(np.abs(rotations[:, 3])) * 1.5:
                rotations = rotations[:, [1, 2, 3, 0]]

            # normalize
            rotations /= (np.linalg.norm(rotations, axis=1, keepdims=True) + 1e-8)


            # Process colors (RGB in [0, 1])
            SH_C0 = 0.28209479177387814
            colors = (colors_dc * SH_C0 + 0.5).clip(0, 1)

            # Process opacities (apply sigmoid)
            opacities = 1.0 / (1.0 + np.exp(-opacities_raw))

            # Process scales (apply exp)
            scales = np.exp(scales_raw)

            # avoid paper-thin or monster splats
            scales = np.clip(scales, 1e-3, 1e3)

            # Calculate model bounds for camera positioning
            self.model_center = positions.mean(axis=0)
            self.model_min = positions.min(axis=0)
            self.model_max = positions.max(axis=0)
            self.model_size = np.linalg.norm(self.model_max - self.model_min)

            # Store data
            self.gaussian_data = {
                'positions': positions.flatten().tolist(),
                'colors': colors.flatten().tolist(),
                'opacities': opacities.tolist(),
                'scales': scales.flatten().tolist(),
                'rotations': rotations.flatten().tolist(),
                'count': len(positions)
            }

            print(f"[WebGLPanel] Loaded {self.gaussian_data['count']:,} Gaussians from PLY")
            print(f"  Position range: [{positions.min():.3f}, {positions.max():.3f}]")
            print(f"  Color range: [{colors.min():.3f}, {colors.max():.3f}]")
            print(f"  Model center: {self.model_center}")
            print(f"  Model size: {self.model_size:.1f}")

        except Exception as e:
            print(f"[WebGLPanel] Error loading PLY: {e}")
            import traceback
            traceback.print_exc()

    def loadFromNode(self, node_name):
        """Load Gaussian data from SplatCraft node (via pickle)"""
        print(f"[WebGLPanel] Loading from node: {node_name}")

        try:
            # Get pickle file path
            pickle_path = cmds.getAttr(f"{node_name}.pickleFilePath")

            if not pickle_path or not os.path.exists(pickle_path):
                print(f"[WebGLPanel] No pickle file found: {pickle_path}")
                return

            # Load pickle data
            import pickle
            with open(pickle_path, 'rb') as f:
                data = pickle.load(f)

            # Extract Gaussian parameters
            positions = data['xyz'].astype(np.float32)
            colors_dc = data['f_dc'].astype(np.float32)
            opacities_raw = data['opacity'].astype(np.float32)
            scales_raw = data['scaling'].astype(np.float32)


            # --- rotations ---
            rotations = None
            # common keys in our pickles
            for k in ('rotation', 'rotations', 'quat', 'quaternion'):
                if k in data:
                    rotations = data[k].astype(np.float32)
                    break

            # last resort: separate fields
            if rotations is None and all(k in data for k in ('rot_0','rot_1','rot_2','rot_3')):
                rotations = np.stack([data['rot_0'], data['rot_1'], data['rot_2'], data['rot_3']], axis=1).astype(np.float32)

            # if still None, make identities
            if rotations is None:
                rotations = np.zeros((positions.shape[0], 4), dtype=np.float32)
                rotations[:, 3] = 1.0

            # normalize
            rotations /= (np.linalg.norm(rotations, axis=1, keepdims=True) + 1e-8)

            # IMPORTANT: reorder to (x,y,z,w) if your source is (w,x,y,z)
            # simple heuristic: if |w| is often much larger in column 0 than column 3, swap
            if np.mean(np.abs(rotations[:, 0])) > np.mean(np.abs(rotations[:, 3]))*1.5:
                rotations = rotations[:, [1,2,3,0]]


            # Process colors (RGB in [0, 1])
            SH_C0 = 0.28209479177387814
            colors = (colors_dc * SH_C0 + 0.5).clip(0, 1)

            # Process opacities (apply sigmoid)
            opacities = 1.0 / (1.0 + np.exp(-opacities_raw))
            if opacities.ndim == 2:
                opacities = opacities.reshape(-1)

            # Process scales (apply exp)
            scales = np.exp(scales_raw)

            # Calculate model bounds for camera positioning
            self.model_center = positions.mean(axis=0)
            self.model_min = positions.min(axis=0)
            self.model_max = positions.max(axis=0)
            self.model_size = np.linalg.norm(self.model_max - self.model_min)

            # Store data
            self.gaussian_data = {
                'positions': positions.flatten().tolist(),
                'colors': colors.flatten().tolist(),
                'opacities': opacities.tolist(),
                'scales': scales.flatten().tolist(),
                'rotations': rotations.flatten().tolist(),
                'count': len(positions)
            }

            print(f"[WebGLPanel] Loaded {self.gaussian_data['count']:,} Gaussians from node")
            print(f"  Position range: [{positions.min():.3f}, {positions.max():.3f}]")
            print(f"  Color range: [{colors.min():.3f}, {colors.max():.3f}]")
            print(f"  Model center: {self.model_center}")
            print(f"  Model size: {self.model_size:.1f}")

        except Exception as e:
            print(f"[WebGLPanel] Error loading from node: {e}")
            import traceback
            traceback.print_exc()

    def sendGaussianDataToViewer(self):
        """Send Gaussian data to the WebGL viewer via JavaScript"""
        if not self.gaussian_data:
            print("[WebGLPanel] No Gaussian data to send")
            return

        original_count = self.gaussian_data['count']
        print(f"[WebGLPanel] Sending ALL {original_count:,} Gaussians to WebGL (no downsampling)...")

        # Send all data without downsampling
        data_to_send = self.gaussian_data

        # Convert to JSON
        data_json = json.dumps(data_to_send)
        json_size_mb = len(data_json) / (1024 * 1024)
        print(f"[WebGLPanel] JSON payload size: {json_size_mb:.2f} MB")

        # Call JavaScript function (no callback in PySide6)
        js_code = f"window.setGaussianData({data_json});"
        self.web_view.page().runJavaScript(js_code)

        # Set initial far camera - looking at scene from far away
        if hasattr(self, 'model_center') and hasattr(self, 'model_size'):
            # Position camera very far back
            far_distance = self.model_size * 5.0  # 5x the model size
            initial_camera = {
                'position': [0, 0, far_distance],
                'target': self.model_center.tolist(),
                'up': [0, 1, 0],
                'distance': far_distance
            }
            camera_json = json.dumps(initial_camera)
            js_code = f"window.setInitialFarCamera({camera_json});"
            self.web_view.page().runJavaScript(js_code)
            print(f"[WebGLPanel] Set initial camera distance: {far_distance:.1f}")

        # Mark as loaded
        self.data_loaded = True
        print("[WebGLPanel] Gaussian data sent to WebGL viewer")
        # Removed info_label update


    def toggleCameraSync(self, enabled):
        """Toggle camera synchronization between Maya and WebGL"""
        self.camera_sync_enabled = enabled

        if enabled:
            print("\n" + "="*60)
            print(f"[CameraSync] ENABLED - WebGL camera → Maya camera")
            print("  • Rotate view in WebGL → Maya camera orbits")
            print("  • Object stays still (just like Alt+drag in Maya)")
            print("="*60 + "\n")

            # Notify JavaScript to enable sync mode
            js_code = """
                if (window.viewer) {
                    window.viewer.syncEnabled = true;
                    console.log('[CameraSync] Sync mode ENABLED from Python');
                }
            """
            self.web_view.page().runJavaScript(js_code)
        else:
            print("[CameraSync] DISABLED - Camera sync off\n")

            # Notify JavaScript to disable sync mode
            js_code = """
                if (window.viewer) {
                    window.viewer.syncEnabled = false;
                    console.log('[CameraSync] Sync mode DISABLED from Python');
                }
            """
            self.web_view.page().runJavaScript(js_code)

    def createPerspectiveMatrix(self, fov_deg, aspect, near, far):
        """Create a perspective projection matrix"""
        import numpy as np
        fov_rad = np.radians(fov_deg)
        f = 1.0 / np.tan(fov_rad / 2.0)
        nf = 1.0 / (near - far)

        return np.array([
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (far + near) * nf, -1],
            [0, 0, 2 * far * near * nf, 0]
        ])

    def applyCameraToMaya(self, camera_data):
        """Apply WebGL camera position to Maya camera (orbit camera around object)"""
        if not self.camera_sync_enabled:
            return

        try:
            # Extract camera position and target from WebGL
            position = camera_data.get('position')
            target = camera_data.get('target')

            if not position or not target:
                return

            # Get Maya perspective camera
            camera_transform = 'persp'
            if not cmds.objExists(camera_transform):
                return

            # Set camera position to match WebGL camera
            cmds.xform(camera_transform, translation=position, worldSpace=True)

            # Use aim constraint to point camera at target (most reliable method)
            # Check if aim constraint already exists
            constraints = cmds.listConnections(f"{camera_transform}.rotateX", type='aimConstraint')
            if constraints:
                # Delete old constraint
                cmds.delete(constraints)

            # Create temporary locator at target position
            temp_locator = cmds.spaceLocator(name='temp_camera_target')[0]
            cmds.xform(temp_locator, translation=target, worldSpace=True)

            # Create aim constraint
            cmds.aimConstraint(temp_locator, camera_transform,
                             worldUpType='vector',
                             worldUpVector=[0, 1, 0],
                             aimVector=[0, 0, -1],  # Maya camera looks down -Z
                             upVector=[0, 1, 0])

            # Bake the constraint and delete it
            cmds.delete(cmds.listConnections(f"{camera_transform}.rotateX", type='aimConstraint'))
            cmds.delete(temp_locator)

            # Debug: print first few updates
            if not hasattr(self, '_camera_update_count'):
                self._camera_update_count = 0
            self._camera_update_count += 1
            if self._camera_update_count <= 3:
                print(f"[WebGL→Maya] Camera orbit #{self._camera_update_count}: pos={position}, target={target}")

        except Exception as e:
            print(f"[WebGL→Maya] Error updating camera: {e}")
            import traceback
            traceback.print_exc()

    def sendMayaCameraToWebGL(self):
        """Send current Maya camera state to WebGL viewer (one-time snapshot)"""
        try:
            print("[Maya→WebGL] Capturing Maya camera state...")

            # Find the perspective camera
            all_panels = cmds.getPanel(type='modelPanel')
            camera_transform = None
            camera_shape = None

            for panel in all_panels:
                cam = cmds.modelPanel(panel, query=True, camera=True)
                if cam and 'persp' in cam.lower():
                    # Maya can return either transform or shape node
                    if cmds.nodeType(cam) == 'camera':
                        # It's the shape node
                        camera_shape = cam
                        parents = cmds.listRelatives(cam, parent=True)
                        if parents:
                            camera_transform = parents[0]
                    else:
                        # It's the transform node
                        camera_transform = cam
                        shapes = cmds.listRelatives(cam, children=True, type='camera')
                        if shapes:
                            camera_shape = shapes[0]
                    break

            # Fallback to persp camera if not found
            if not camera_transform or not camera_shape:
                if cmds.objExists('persp'):
                    camera_transform = 'persp'
                    shapes = cmds.listRelatives('persp', children=True, type='camera')
                    if shapes:
                        camera_shape = shapes[0]
                    else:
                        print("[Maya→WebGL] No camera shape found for persp")
                        return
                else:
                    print("[Maya→WebGL] No perspective camera found")
                    return

            print(f"[Maya→WebGL] Found camera: transform='{camera_transform}', shape='{camera_shape}'")

            # Get camera world matrix
            import numpy as np
            matrix = cmds.xform(camera_transform, query=True, matrix=True, worldSpace=True)
            maya_matrix = np.array(matrix).reshape(4, 4)

            # Invert to get view matrix
            view_matrix = np.linalg.inv(maya_matrix)

            # Get camera position and target
            cam_pos = cmds.xform(camera_transform, query=True, translation=True, worldSpace=True)

            # Calculate target using camera's look direction
            # Maya camera looks down -Z in its local space
            look_dir = maya_matrix[:3, 2]  # Third column is Z axis (forward direction)
            look_distance = 100.0  # Default look distance

            # Try to get center of interest if available
            if cmds.objExists(f"{camera_transform}.centerOfInterest"):
                look_distance = cmds.getAttr(f"{camera_transform}.centerOfInterest")

            target = [
                cam_pos[0] - look_dir[0] * look_distance,
                cam_pos[1] - look_dir[1] * look_distance,
                cam_pos[2] - look_dir[2] * look_distance
            ]

            # Get projection parameters
            # Calculate aspect ratio from film aperture (Maya doesn't have aspectRatio attribute)
            h_aperture = cmds.getAttr(f"{camera_shape}.horizontalFilmAperture")
            v_aperture = cmds.getAttr(f"{camera_shape}.verticalFilmAperture")
            aspect = h_aperture / v_aperture if v_aperture > 0 else 1.0

            near_clip = cmds.getAttr(f"{camera_shape}.nearClipPlane")
            far_clip = cmds.getAttr(f"{camera_shape}.farClipPlane")
            focal_length = cmds.getAttr(f"{camera_shape}.focalLength")

            # Convert focal length to vertical FOV
            # Maya: focalLength is in mm, verticalFilmAperture is in inches
            # Convert aperture to mm: 1 inch = 25.4mm
            v_aperture_mm = v_aperture * 25.4
            fov_rad = 2 * np.arctan(v_aperture_mm / (2 * focal_length))
            fov_deg = np.degrees(fov_rad)

            print(f"[Maya→WebGL] Camera params: FOV={fov_deg:.1f}°, aspect={aspect:.2f}, near={near_clip:.2f}, far={far_clip:.1f}")

            # Create perspective projection matrix
            proj_matrix = self.createPerspectiveMatrix(fov_deg, aspect, near_clip, far_clip)

            # Calculate distance
            distance = np.linalg.norm(np.array(cam_pos) - np.array(target))

            # Prepare camera data
            camera_data = {
                'viewMatrix': view_matrix.flatten().tolist(),
                'projectionMatrix': proj_matrix.flatten().tolist(),
                'position': cam_pos,
                'target': target,
                'distance': float(distance)
            }

            # Send to WebGL
            camera_json = json.dumps(camera_data)
            js_code = f"if (window.applyMayaCameraView) {{ window.applyMayaCameraView({camera_json}); }}"
            self.web_view.page().runJavaScript(js_code)

            print(f"[Maya→WebGL] Camera sent: pos={cam_pos}, target={target}, distance={distance:.1f}")

        except Exception as e:
            print(f"[Maya→WebGL] Error capturing camera: {e}")
            import traceback
            traceback.print_exc()

    def toggleObjectSync(self, enabled):
        """Toggle object transformation synchronization"""
        self.object_sync_enabled = enabled

        if enabled:
            if not self.node_name or not cmds.objExists(self.node_name):
                print("[ObjectSync] ERROR: No valid node to monitor!")
                self.object_sync_checkbox.setChecked(False)
                return

            print("\n" + "="*60)
            print(f"[ObjectSync] ENABLED - Maya object → WebGL Gaussians")
            print(f"  • Monitoring node: {self.node_name}")
            print("  • Rotate/move Maya object → Gaussians transform in WebGL")
            print("="*60 + "\n")

            # Start monitoring transform
            self.startTransformMonitoring()
        else:
            print("[ObjectSync] DISABLED - Object sync off\n")
            self.stopTransformMonitoring()

    def startTransformMonitoring(self):
        """Start monitoring the Maya transform node"""
        if self.transform_monitor_timer is not None:
            # Already monitoring
            return

        # Create timer to check transform every 100ms
        self.transform_monitor_timer = QTimer(self)
        self.transform_monitor_timer.timeout.connect(self.checkTransformUpdate)
        self.transform_monitor_timer.start(100)  # Check every 100ms

        # Get initial transform state
        if cmds.objExists(self.node_name):
            matrix = cmds.xform(self.node_name, query=True, matrix=True, worldSpace=True)
            self.last_transform_matrix = tuple(matrix)

        print(f"[ObjectSync] Started monitoring '{self.node_name}'")

    def stopTransformMonitoring(self):
        """Stop monitoring the Maya transform node"""
        if self.transform_monitor_timer is not None:
            self.transform_monitor_timer.stop()
            self.transform_monitor_timer.deleteLater()
            self.transform_monitor_timer = None
            print("[ObjectSync] Stopped transform monitoring")

    def checkTransformUpdate(self):
        """Check if transform has changed and send update to WebGL"""
        if not self.object_sync_enabled or not self.node_name:
            return

        try:
            if not cmds.objExists(self.node_name):
                print(f"[ObjectSync] ERROR: Node '{self.node_name}' no longer exists!")
                self.stopTransformMonitoring()
                self.object_sync_checkbox.setChecked(False)
                return

            # Get current world matrix
            matrix = cmds.xform(self.node_name, query=True, matrix=True, worldSpace=True)
            current_matrix = tuple(matrix)

            # Check if changed
            if current_matrix != self.last_transform_matrix:
                self.last_transform_matrix = current_matrix
                self.transform_update_count += 1

                # Send transform to WebGL
                self.sendTransformToWebGL(matrix)

                # Debug: Log first few updates
                if self.transform_update_count <= 3:
                    print(f"[ObjectSync] Transform update #{self.transform_update_count}")

        except Exception as e:
            print(f"[ObjectSync] Error checking transform: {e}")

    def sendTransformToWebGL(self, matrix):
        """Send transform matrix to WebGL viewer"""
        try:
            # Maya matrix is 4x4 row-major
            matrix_array = list(matrix)

            # Send to JavaScript
            matrix_json = json.dumps(matrix_array)
            js_code = f"if (window.viewer && window.viewer.applyObjectTransform) {{ window.viewer.applyObjectTransform({matrix_json}); }}"
            self.web_view.page().runJavaScript(js_code)

        except Exception as e:
            print(f"[ObjectSync] Error sending transform: {e}")
            import traceback
            traceback.print_exc()

    def closeEvent(self, event):
        """Clean up when closing"""
        # Stop transform monitoring
        self.stopTransformMonitoring()

        print("[WebGLPanel] Panel closed")
        super().closeEvent(event)


def show_webgl_panel(node_name=None, ply_path=None):
    """
    Show the WebGL Gaussian panel

    Args:
        node_name: Name of the SplatCraft node (optional)
        ply_path: Path to PLY file to load directly (optional)
    """
    global _WEBGL_PANEL

    # Close existing panel
    if _WEBGL_PANEL:
        try:
            _WEBGL_PANEL.close()
            _WEBGL_PANEL.deleteLater()
        except:
            pass
        _WEBGL_PANEL = None

    # Create new panel
    print("\n" + "="*70)
    print("SplatCraft - WebGL Gaussian Viewer")
    print("="*70)

    panel = WebGLGaussianPanel(node_name=node_name, ply_path=ply_path)
    panel.show()

    _WEBGL_PANEL = panel

    return panel


def close_webgl_panel():
    """Close the WebGL panel"""
    global _WEBGL_PANEL

    if _WEBGL_PANEL:
        _WEBGL_PANEL.close()
        _WEBGL_PANEL = None
        print("[WebGLPanel] Panel closed")
    else:
        print("[WebGLPanel] No panel open")
