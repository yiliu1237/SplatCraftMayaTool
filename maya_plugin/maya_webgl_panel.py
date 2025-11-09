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
    @Slot(str)
    def log(self, message):
        """Called from JavaScript to log messages to Python console"""
        print(f"[WebGL] {message}")


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

        # Setup UI
        self.setWindowTitle("SplatCraft - WebGL Viewer")
        self.setWindowFlags(QtCore.Qt.Window)
        self.resize(1200, 800)

        self.setupUI()
        self.loadGaussianData()
        # Camera sync removed - using manual control only

        print("[WebGLPanel] Panel initialized")

    def setupUI(self):
        """Create the UI layout"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # REMOVED: Info bar (takes too much space)
        # The WebGL viewer has its own info overlay in the canvas

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
        self.bridge = MayaToPy()
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


    def closeEvent(self, event):
        """Clean up when closing"""
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
