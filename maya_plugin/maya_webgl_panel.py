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

    @Slot(bool)
    def toggleCameraSync(self, enabled):
        """Called from JavaScript to toggle camera sync"""
        print(f"[MayaToPy Bridge] toggleCameraSync({enabled}) called from JavaScript")
        if self.parent_panel:
            self.parent_panel.setCameraSyncFromJS(enabled)

    @Slot(bool)
    def toggleObjectSync(self, enabled):
        """Called from JavaScript to toggle object sync"""
        print(f"[MayaToPy Bridge] toggleObjectSync({enabled}) called from JavaScript")
        if self.parent_panel:
            self.parent_panel.setObjectSyncFromJS(enabled)



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

        # Multi-object support: track all SplatCraft nodes in scene
        self.scene_objects = {}  # {node_name: {'data': gaussian_data, 'ply_path': path, 'last_matrix': matrix}}
        self.data_loaded = False
        self.camera_sync_enabled = True  # Camera view synchronization toggle (enabled by default)
        self.object_sync_enabled = True  # Object transformation synchronization toggle (enabled by default)

        # Transform and deletion monitoring
        self.transform_update_count = 0
        self.monitor_timer = None  # Combined timer for transform updates and deletion detection

        # If specific node provided, use it; otherwise find all SplatCraft nodes
        if node_name:
            self.initial_node = node_name
            self.initial_ply_path = ply_path
        else:
            self.initial_node = None
            self.initial_ply_path = None

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
        layout.setSpacing(0)

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
            if self.scene_objects and not self.data_loaded:
                self.sendAllGaussiansToViewer()

                # WebGL will use manual control mode for navigation
                print("[WebGLPanel] WebGL viewer has initial centered view")
                print("[WebGLPanel] Use 'Manual Control' button to navigate")

            # Enable sync features by default (they're already enabled in __init__)
            # Notify JavaScript
            self.enableCameraSyncInJS()
            self.enableObjectSyncInJS()
        else:
            print("[WebGLPanel] ERROR: Failed to load web page")
            # No info_label anymore

    def loadGaussianData(self):
        """Load Gaussian data from all SplatCraft nodes in scene"""

        # Find all SplatCraft nodes in the scene
        all_splat_nodes = cmds.ls(type='splatCraftNode') or []

        if not all_splat_nodes:
            print("[WebGLPanel] No SplatCraft nodes found in scene")
            return

        print(f"\n[WebGLPanel] Found {len(all_splat_nodes)} SplatCraft node(s) in scene")

        # Load data for each node
        for node in all_splat_nodes:
            # Get parent transform node
            parents = cmds.listRelatives(node, parent=True, type='transform')
            if not parents:
                print(f"[WebGLPanel] Warning: No parent transform for {node}, skipping")
                continue

            transform_node = parents[0]

            # Get PLY file path
            file_path = cmds.getAttr(f"{node}.filePath")
            if not file_path or not os.path.exists(file_path):
                print(f"[WebGLPanel] Warning: No valid file path for {node}, skipping")
                continue

            print(f"  Loading: {transform_node} from {os.path.basename(file_path)}")

            # Load the PLY data
            gaussian_data = self.loadPLYFile(file_path)
            if gaussian_data:
                # Get initial transform matrix
                matrix = cmds.xform(transform_node, query=True, matrix=True, worldSpace=True)

                # Store in scene_objects dict
                self.scene_objects[transform_node] = {
                    'data': gaussian_data,
                    'ply_path': file_path,
                    'shape_node': node,
                    'last_matrix': tuple(matrix)
                }

        if self.scene_objects:
            print(f"[WebGLPanel] Successfully loaded {len(self.scene_objects)} object(s)")
        else:
            print("[WebGLPanel] No objects loaded")

    def loadPLYFile(self, ply_path):
        """Load Gaussian data from PLY file and return it"""
        if not os.path.exists(ply_path):
            print(f"[WebGLPanel] PLY file not found: {ply_path}")
            return None

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

            # Return data as dictionary
            gaussian_data = {
                'positions': positions.flatten().tolist(),
                'colors': colors.flatten().tolist(),
                'opacities': opacities.tolist(),
                'scales': scales.flatten().tolist(),
                'rotations': rotations.flatten().tolist(),
                'count': len(positions)
            }

            return gaussian_data

        except Exception as e:
            print(f"[WebGLPanel] Error loading PLY {ply_path}: {e}")
            import traceback
            traceback.print_exc()
            return None

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

    def sendAllGaussiansToViewer(self):
        """Send all Gaussian objects to the WebGL viewer via JavaScript"""
        if not self.scene_objects:
            print("[WebGLPanel] No Gaussian objects to send")
            return

        print(f"\n[WebGLPanel] Sending {len(self.scene_objects)} object(s) to WebGL...")

        # Prepare array of objects
        objects_data = []
        total_gaussians = 0

        for node_name, obj_info in self.scene_objects.items():
            gaussian_data = obj_info['data']
            matrix = list(obj_info['last_matrix'])

            # Package each object with its data and transform
            obj_package = {
                'node_name': node_name,
                'data': gaussian_data,
                'transform': matrix
            }
            objects_data.append(obj_package)
            total_gaussians += gaussian_data['count']

            print(f"  • {node_name}: {gaussian_data['count']:,} Gaussians")

        # Convert to JSON
        scene_json = json.dumps(objects_data)
        json_size_mb = len(scene_json) / (1024 * 1024)
        print(f"[WebGLPanel] Total: {total_gaussians:,} Gaussians ({json_size_mb:.2f} MB)")

        # Call JavaScript function to load all objects
        js_code = f"window.setSceneData({scene_json});"
        self.web_view.page().runJavaScript(js_code)

        # Set initial camera to view entire scene
        # Calculate scene bounding box from all objects
        all_positions = []
        for obj_info in self.scene_objects.values():
            data = obj_info['data']
            positions_flat = data['positions']
            # Reshape and collect
            positions = np.array(positions_flat).reshape(-1, 3)
            all_positions.append(positions)

        if all_positions:
            all_positions_array = np.vstack(all_positions)
            scene_center = all_positions_array.mean(axis=0)
            scene_min = all_positions_array.min(axis=0)
            scene_max = all_positions_array.max(axis=0)
            scene_size = np.linalg.norm(scene_max - scene_min)

            far_distance = scene_size * 2.5
            initial_camera = {
                'position': [0, 0, far_distance],
                'target': scene_center.tolist(),
                'up': [0, 1, 0],
                'distance': far_distance
            }
            camera_json = json.dumps(initial_camera)
            js_code = f"window.setInitialFarCamera({camera_json});"
            self.web_view.page().runJavaScript(js_code)
            print(f"[WebGLPanel] Set initial camera distance: {far_distance:.1f}")

        # Mark as loaded
        self.data_loaded = True
        print("[WebGLPanel] All Gaussian objects sent to WebGL viewer\n")


    def setCameraSyncFromJS(self, enabled):
        """Set camera sync state from JavaScript button click"""
        self.camera_sync_enabled = enabled
        if enabled:
            print("\n" + "="*60)
            print(f"[CameraSync] ENABLED - WebGL camera → Maya camera")
            print("  • Rotate view in WebGL → Maya camera orbits")
            print("  • Object stays still (just like Alt+drag in Maya)")
            print("="*60 + "\n")
        else:
            print("[CameraSync] DISABLED - Camera sync off\n")

    def enableCameraSyncInJS(self):
        """Enable camera sync in JavaScript"""
        js_code = """
            if (window.viewer) {
                window.viewer.syncEnabled = true;
                console.log('[CameraSync] Sync mode ENABLED from Python');
            }
        """
        self.web_view.page().runJavaScript(js_code)

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

    def setObjectSyncFromJS(self, enabled):
        """Set object sync state from JavaScript button click"""
        self.object_sync_enabled = enabled

        if enabled:
            if not self.scene_objects:
                print("[ObjectSync] ERROR: No objects to monitor!")
                self.object_sync_enabled = False
                # Update button state in JS to reflect failure
                js_code = """
                    if (window.objectSyncBtn) {
                        objectSyncEnabled = false;
                        objectSyncBtn.textContent = '🔄 Object (OFF)';
                        objectSyncBtn.className = 'btn-gray';
                    }
                """
                self.web_view.page().runJavaScript(js_code)
                return

            print("\n" + "="*60)
            print(f"[ObjectSync] ENABLED - Maya objects → WebGL Gaussians")
            print(f"  • Monitoring {len(self.scene_objects)} object(s)")
            print("  • Rotate/move Maya objects → Gaussians transform in WebGL")
            print("  • Delete Maya objects → Removed from WebGL")
            print("="*60 + "\n")

            # Start monitoring transforms and deletions
            self.startMonitoring()
        else:
            print("[ObjectSync] DISABLED - Object sync off\n")
            self.stopMonitoring()

    def enableObjectSyncInJS(self):
        """Enable object sync - start monitoring all nodes"""
        if self.scene_objects:
            print(f"[ObjectSync] Starting monitoring for {len(self.scene_objects)} object(s)")
            self.startMonitoring()
        else:
            print("[ObjectSync] No objects to monitor")

    def startMonitoring(self):
        """Start monitoring all Maya transform nodes (transforms + deletions)"""
        if self.monitor_timer is not None:
            # Already monitoring
            return

        # Create timer to check transforms and deletions every 100ms
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.checkSceneUpdates)
        self.monitor_timer.start(100)  # Check every 100ms

        print(f"[ObjectSync] Started monitoring {len(self.scene_objects)} object(s)")

    def stopMonitoring(self):
        """Stop monitoring all Maya transform nodes"""
        if self.monitor_timer is not None:
            self.monitor_timer.stop()
            self.monitor_timer.deleteLater()
            self.monitor_timer = None
            print("[ObjectSync] Stopped monitoring")

    def checkSceneUpdates(self):
        """Check for transform changes and deletions for all objects"""
        if not self.object_sync_enabled:
            return

        try:
            # Check for deletions first
            deleted_nodes = []
            for node_name in list(self.scene_objects.keys()):
                if not cmds.objExists(node_name):
                    deleted_nodes.append(node_name)

            # Remove deleted objects
            for node_name in deleted_nodes:
                print(f"[ObjectSync] Object '{node_name}' was deleted!")
                del self.scene_objects[node_name]

                # Notify WebGL to remove the object
                js_code = f"if (window.viewer && window.viewer.removeObject) {{ window.viewer.removeObject('{node_name}'); }}"
                self.web_view.page().runJavaScript(js_code)

            # Check for transform updates on remaining objects
            for node_name, obj_info in self.scene_objects.items():
                if not cmds.objExists(node_name):
                    continue

                # Get current world matrix
                matrix = cmds.xform(node_name, query=True, matrix=True, worldSpace=True)
                current_matrix = tuple(matrix)

                # Check if changed
                if current_matrix != obj_info['last_matrix']:
                    obj_info['last_matrix'] = current_matrix
                    self.transform_update_count += 1

                    # Send transform to WebGL
                    self.sendObjectTransformToWebGL(node_name, matrix)

                    # Debug: Log first few updates
                    if self.transform_update_count <= 3:
                        print(f"[ObjectSync] Transform update #{self.transform_update_count}: {node_name}")

        except Exception as e:
            print(f"[ObjectSync] Error checking scene updates: {e}")

    def sendObjectTransformToWebGL(self, node_name, matrix):
        """Send transform matrix for a specific object to WebGL viewer"""
        try:
            # Maya matrix is 4x4 row-major
            matrix_array = list(matrix)

            # Send to JavaScript with node name
            matrix_json = json.dumps(matrix_array)
            js_code = f"if (window.viewer && window.viewer.updateObjectTransform) {{ window.viewer.updateObjectTransform('{node_name}', {matrix_json}); }}"
            self.web_view.page().runJavaScript(js_code)

        except Exception as e:
            print(f"[ObjectSync] Error sending transform for {node_name}: {e}")
            import traceback
            traceback.print_exc()

    def closeEvent(self, event):
        """Clean up when closing"""
        # Stop monitoring
        self.stopMonitoring()

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
