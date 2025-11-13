"""
Maya UI panel for image-to-3D inference using subprocess approach.
"""

try:
    from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                                  QLabel, QFileDialog, QCheckBox, QSlider, QProgressBar,
                                  QGroupBox)
    from PySide2.QtCore import Qt, QThread, Signal
    from PySide2.QtGui import QPixmap
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                                  QLabel, QFileDialog, QCheckBox, QSlider, QProgressBar,
                                  QGroupBox)
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QPixmap
    from shiboken6 import wrapInstance

import maya.cmds as cmds
import maya.OpenMayaUI as omui
import os
import sys

# Add plugin path
plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)


class InferenceThread(QThread):
    """Background thread for running inference"""
    progress = Signal(int, str)  # progress%, status_message
    finished = Signal(str)  # ply_path
    error = Signal(str)  # error_message

    def __init__(self, inference_engine, image_path, output_path, remove_bg, fg_ratio):
        super().__init__()
        self.inference_engine = inference_engine
        self.image_path = image_path
        self.output_path = output_path
        self.remove_bg = remove_bg
        self.fg_ratio = fg_ratio

    def run(self):
        try:
            ply_path = self.inference_engine.run_inference(
                self.image_path,
                self.output_path,
                remove_bg=self.remove_bg,
                fg_ratio=self.fg_ratio,
                progress_callback=self.on_progress
            )
            self.finished.emit(ply_path)
        except Exception as e:
            self.error.emit(str(e))

    def on_progress(self, progress, message):
        self.progress.emit(progress, message)


class SplatCraftInferencePanel(QWidget):
    """Main inference panel widget"""

    def __init__(self, parent=None, conda_env='splatter-image'):
        super().__init__(parent)
        self.conda_env = conda_env
        self.inference_engine = None
        self.current_image_path = None
        self.cached_ply_path = None  # Track if PLY exists for current image
        self.setup_ui()

    def setup_ui(self):
        """Build the UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # ===== Title =====
        title = QLabel("SplatCraft - Image to 3DGS")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # ===== Image Upload Section =====
        upload_group = QGroupBox("1. Upload Image")
        upload_layout = QVBoxLayout()

        self.upload_btn = QPushButton("📁 Browse Image...")
        self.upload_btn.clicked.connect(self.on_upload_image)
        self.upload_btn.setMinimumHeight(35)
        upload_layout.addWidget(self.upload_btn)

        # Image preview
        self.image_preview = QLabel()
        self.image_preview.setFixedSize(280, 280)
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setStyleSheet("border: 2px dashed #999; background: #2b2b2b;")
        self.image_preview.setText("No image selected")
        upload_layout.addWidget(self.image_preview)

        self.image_label = QLabel("")
        self.image_label.setWordWrap(True)
        self.image_label.setStyleSheet("color: #888; font-size: 10px;")
        upload_layout.addWidget(self.image_label)

        upload_group.setLayout(upload_layout)
        main_layout.addWidget(upload_group)

        # ===== Preprocessing Options =====
        preprocess_group = QGroupBox("2. Preprocessing")
        preprocess_layout = QVBoxLayout()

        self.remove_bg_checkbox = QCheckBox("Remove Background")
        self.remove_bg_checkbox.setChecked(True)
        preprocess_layout.addWidget(self.remove_bg_checkbox)

        fg_layout = QHBoxLayout()
        fg_layout.addWidget(QLabel("Foreground Ratio:"))
        self.fg_slider = QSlider(Qt.Horizontal)
        self.fg_slider.setRange(50, 85)
        self.fg_slider.setValue(65)
        self.fg_label = QLabel("0.65")
        self.fg_slider.valueChanged.connect(lambda v: self.fg_label.setText(f"{v/100:.2f}"))
        fg_layout.addWidget(self.fg_slider)
        fg_layout.addWidget(self.fg_label)
        preprocess_layout.addLayout(fg_layout)

        preprocess_group.setLayout(preprocess_layout)
        main_layout.addWidget(preprocess_group)

        # ===== Generate Section =====
        generate_group = QGroupBox("3. Generate 3D Model")
        generate_layout = QVBoxLayout()

        self.generate_btn = QPushButton("▶ Generate 3D Gaussian Splat")
        self.generate_btn.clicked.connect(self.on_generate_clicked)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setMinimumHeight(45)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #555;
            }
        """)
        generate_layout.addWidget(self.generate_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        generate_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #aaa; padding: 5px;")
        generate_layout.addWidget(self.status_label)

        generate_group.setLayout(generate_layout)
        main_layout.addWidget(generate_group)

        # ===== Additional Controls =====
        controls_group = QGroupBox("4. View Controls")
        controls_layout = QVBoxLayout()

        # Node selector dropdown (populated when nodes exist)
        from PySide6.QtWidgets import QComboBox
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Model:"))
        self.node_selector = QComboBox()
        self.node_selector.setMinimumHeight(25)
        selector_layout.addWidget(self.node_selector)

        # Refresh button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMaximumWidth(30)
        refresh_btn.clicked.connect(self.refresh_node_list)
        refresh_btn.setToolTip("Refresh model list")
        selector_layout.addWidget(refresh_btn)
        controls_layout.addLayout(selector_layout)

        # Show WebGL Viewer button
        self.show_panel_btn = QPushButton("👁 Show 3DGS Viewer")
        self.show_panel_btn.clicked.connect(self.on_show_webgl_viewer)
        self.show_panel_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.show_panel_btn.setMinimumHeight(35)
        controls_layout.addWidget(self.show_panel_btn)

        controls_group.setLayout(controls_layout)
        main_layout.addWidget(controls_group)

        # Populate node list initially
        self.refresh_node_list()

        # ===== Test Connection Button =====
        self.test_btn = QPushButton("🔧 Test Conda Environment")
        self.test_btn.clicked.connect(self.on_test_connection)
        self.test_btn.setStyleSheet("background-color: #555; color: white;")
        main_layout.addWidget(self.test_btn)

        main_layout.addStretch()

    def initialize_inference_engine(self):
        """Initialize the subprocess-based inference engine"""
        if self.inference_engine is None:
            self.status_label.setText("Initializing inference engine...")
            try:
                from splatter_subprocess import create_inference_engine
                self.inference_engine = create_inference_engine(conda_env=self.conda_env)
                self.status_label.setText("✓ Engine ready")
                return True
            except Exception as e:
                self.status_label.setText(f" Error: {str(e)}")
                print(f"[InferencePanel] Failed to initialize: {e}")
                import traceback
                traceback.print_exc()
                return False
        return True

    def on_test_connection(self):
        """Test connection to conda environment"""
        self.status_label.setText("Testing conda environment...")
        self.test_btn.setEnabled(False)

        if self.initialize_inference_engine():
            if self.inference_engine.test_connection():
                self.status_label.setText("✓ Conda environment working!")
            else:
                self.status_label.setText(" Conda environment test failed")

        self.test_btn.setEnabled(True)

    def reset_progress(self, msg="Ready"):
        self.progress_bar.setValue(0)
        self.status_label.setText(msg)


    def on_upload_image(self):
        """Handle image upload"""
        self.reset_progress("Ready")

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff)"
        )

        if file_path:
            self.current_image_path = file_path

            # Show preview
            pixmap = QPixmap(file_path)
            scaled = pixmap.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_preview.setPixmap(scaled)

            # Update label
            filename = os.path.basename(file_path)
            self.image_label.setText(f"✓ {filename}")

            # Check if we already have a cached PLY for this image
            workspace = cmds.workspace(q=True, rd=True)
            output_dir = os.path.join(workspace, "splatter_output")

            # Generate expected PLY filename from image name
            image_basename = os.path.splitext(filename)[0]  # e.g., "cow" from "cow.png"
            expected_ply = os.path.join(output_dir, f"{image_basename}.ply")

            if os.path.exists(expected_ply):
                self.cached_ply_path = expected_ply
                self.status_label.setText(f"Found cached result! Click viewer to see it, or generate new.")
                # Enable the show viewer button since we have cached data
                self.show_panel_btn.setEnabled(True)
            else:
                self.cached_ply_path = None
                self.status_label.setText("No cached model for this image - generate to create 3DGS")
                # Check if we should enable viewer button based on nodes in scene
                nodes = cmds.ls(type='splatCraftNode')
                self.show_panel_btn.setEnabled(bool(nodes))

            # Enable generate button
            self.generate_btn.setEnabled(True)

    def on_generate_clicked(self):
        """Start the inference process"""
        if not self.current_image_path:
            return

        # Initialize engine
        if not self.initialize_inference_engine():
            return

        # Prepare output path - use image basename for consistent naming
        workspace = cmds.workspace(q=True, rd=True)
        output_dir = os.path.join(workspace, "splatter_output")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Generate PLY filename from input image name (e.g., cow.png → cow.ply)
        image_basename = os.path.splitext(os.path.basename(self.current_image_path))[0]
        output_path = os.path.join(output_dir, f"{image_basename}.ply")

        # Disable UI
        self.generate_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        self.test_btn.setEnabled(False)

        # Start inference thread
        self.inference_thread = InferenceThread(
            self.inference_engine,
            self.current_image_path,
            output_path,
            self.remove_bg_checkbox.isChecked(),
            self.fg_slider.value() / 100.0
        )

        self.inference_thread.progress.connect(self.on_progress)
        self.inference_thread.finished.connect(self.on_inference_finished)
        self.inference_thread.error.connect(self.on_inference_error)

        self.inference_thread.start()

    def on_progress(self, progress, message):
        """Update progress UI"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)

    def on_inference_finished(self, ply_path):
        """Handle successful inference"""
        self.status_label.setText("Importing into Maya...")

        try:
            # Update cached PLY path for this image
            self.cached_ply_path = ply_path

            # Import PLY into Maya
            # Note: open_webgl=True automatically opens the WebGL viewer
            import import_gaussians
            node_name, data = import_gaussians.import_gaussian_scene(ply_path, open_webgl=True)

            # Frame the camera
            cmds.select(node_name)
            cmds.viewFit()

            # WebGL viewer already opened by import_gaussians, no need to open again

            # Refresh the node list to include the new model
            self.refresh_node_list()

            self.status_label.setText(f"✓ Success! Created {node_name}")
            self.progress_bar.setValue(100)

        except Exception as e:
            self.on_inference_error(f"Import failed: {str(e)}")
            import traceback
            traceback.print_exc()

        # Re-enable UI
        self.generate_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
        self.test_btn.setEnabled(True)

    def on_inference_error(self, error_message):
        """Handle inference errors"""
        self.status_label.setText(f" Error: {error_message}")
        self.progress_bar.setValue(0)

        # Re-enable UI
        self.generate_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
        self.test_btn.setEnabled(True)

    def refresh_node_list(self):
        """Refresh the dropdown list of SplatCraft nodes"""
        self.node_selector.clear()

        nodes = cmds.ls(type='splatCraftNode')
        if nodes:
            for node in nodes:
                num_gaussians = cmds.getAttr(f"{node}.numGaussians")
                display_text = f"{node} ({num_gaussians:,} Gaussians)"
                self.node_selector.addItem(display_text, node)  # text, user data

            # Select the most recent (last) node by default
            self.node_selector.setCurrentIndex(len(nodes) - 1)
            self.show_panel_btn.setEnabled(True)
        else:
            self.node_selector.addItem("(No models in scene)")
            self.show_panel_btn.setEnabled(False)

    def on_show_webgl_viewer(self):
        """Open the WebGL viewer for the selected SplatCraft node or cached PLY"""
        try:
            # Priority 1: If we have a cached PLY path from image upload, use it directly
            if self.cached_ply_path and os.path.exists(self.cached_ply_path):
                print(f"[InferencePanel] Opening viewer for cached PLY: {self.cached_ply_path}")
                self.status_label.setText("Opening cached 3DGS viewer...")

                import maya_webgl_panel
                # Note: Opening from cached PLY without node_name - rotation sync won't work
                # User should import to scene first for rotation sync
                maya_webgl_panel.show_webgl_panel(ply_path=self.cached_ply_path)

                filename = os.path.basename(self.cached_ply_path)
                self.status_label.setText(f"✓ 3DGS viewer opened (cached: {filename})")
                print("[InferencePanel] NOTE: Import to Maya scene to enable rotation sync")
                return

            # Priority 2: Get the selected node from dropdown
            node = self.node_selector.currentData()

            if not node:
                self.status_label.setText("No model selected and no cached PLY available!")
                return

            # Get transform node (parent of splatCraftNode shape)
            transform_node = node
            if cmds.nodeType(node) == 'splatCraftNode':
                # If it's the shape node, get its parent transform
                parents = cmds.listRelatives(node, parent=True, type='transform')
                if parents:
                    transform_node = parents[0]

            num_gaussians = cmds.getAttr(f"{node}.numGaussians")
            print(f"[InferencePanel] Opening viewer for node: {transform_node}")

            # Get the PLY file path from the node (this is what the viewer needs)
            ply_path = cmds.getAttr(f"{node}.filePath")

            if not ply_path:
                self.status_label.setText("No PLY file associated with this node!")
                return

            self.status_label.setText(f"Opening 3DGS viewer for {transform_node}...")

            # Import and show the WebGL viewer with BOTH ply_path AND node_name
            import maya_webgl_panel
            maya_webgl_panel.show_webgl_panel(node_name=transform_node, ply_path=ply_path)

            self.status_label.setText(f"✓ 3DGS viewer opened ({num_gaussians:,} Gaussians)")

        except Exception as e:
            self.status_label.setText(f" Failed to open viewer: {str(e)}")
            print(f"[InferencePanel] Error opening WebGL viewer: {e}")
            import traceback
            traceback.print_exc()


# ===== Maya Integration =====

def show_inference_panel(conda_env='splatter-image'):
    """
    Show the inference panel as a docked Maya window.

    Args:
        conda_env: Name of conda environment with splatter-image installed

    Usage in Maya:
        import sys
        sys.path.insert(0, '/root/SplatMayaTool/maya_plugin')

        from ui.inference_panel import show_inference_panel
        show_inference_panel(conda_env='splatter-image')
    """
    panel_name = 'SplatCraftInferencePanel'

    # Close existing
    if cmds.workspaceControl(panel_name, exists=True):
        cmds.deleteUI(panel_name)

    # Create workspace control
    cmds.workspaceControl(
        panel_name,
        label='SplatCraft Inference',
        retain=False,
        floating=False,
        dockToControl=('ToolBox', 'right'),
        widthProperty='free',
        initialWidth=320
    )

    # Get Qt widget
    ptr = omui.MQtUtil.findControl(panel_name)
    widget = wrapInstance(int(ptr), QWidget)

    # Add our panel
    panel = SplatCraftInferencePanel(conda_env=conda_env)

    # Get or create layout
    layout = widget.layout()
    if layout is None:
        layout = QVBoxLayout(widget)

    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(panel)

    print(f"[SplatCraft] Inference panel opened (conda env: {conda_env})")
    return panel


def close_inference_panel():
    """Close the inference panel"""
    panel_name = 'SplatCraftInferencePanel'
    if cmds.workspaceControl(panel_name, exists=True):
        cmds.deleteUI(panel_name)
