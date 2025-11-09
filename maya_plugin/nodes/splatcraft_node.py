"""
SplatCraft Maya Node

Custom Maya node to store and manage 3D Gaussian Splatting data.
This node serves as the single source of truth for all Gaussian parameters.
"""

import sys
import os

# Add user site-packages to path for Maya (in case it's not finding numpy)
user_site = os.path.expanduser('~/Library/Python/3.10/lib/python/site-packages')
if user_site not in sys.path:
    sys.path.insert(0, user_site)

import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaRender as omr
import numpy as np


def maya_useNewAPI():
    """Tell Maya to use Maya Python API 2.0"""
    pass


# Global registry to store node instances for draw override access
# Using both ID-based and name-based lookups for robustness
_NODE_REGISTRY = {}
_NODE_NAME_REGISTRY = {}
_NODE_DATA = {}  # Fallback storage for Gaussian data keyed by node name

# Store a reference to this module's globals for cross-module access
# This allows other modules to access THIS specific _NODE_DATA dict
_THIS_MODULE_GLOBALS = None


class SplatCraftNode(omui.MPxLocatorNode):
    """
    Custom Maya locator node to store 3D Gaussian Splatting data

    Attributes:
        - numGaussians: Number of Gaussians in the scene (int)
        - displayLOD: Level of detail for viewport display 0.0-1.0 (float)
        - pointSize: Display point size (float)
        - enableRender: Toggle rendered panel display (bool)
        - filePath: Source PLY file path (string)
    """

    TYPE_NAME = "splatCraftNode"
    TYPE_ID = om.MTypeId(0x00138200)  # Unique ID - register with Autodesk if publishing
    DRAW_CLASSIFICATION = "drawdb/geometry/splatCraft"
    DRAW_REGISTRANT_ID = "SplatCraftNodePlugin"

    # Attributes
    num_gaussians_attr = None
    display_lod_attr = None
    point_size_attr = None
    enable_render_attr = None
    file_path_attr = None

    # Gaussian parameter arrays (cached in memory)
    positions = None
    opacities = None
    scales = None
    rotations = None
    colors_dc = None
    colors_sh = None

    def __init__(self):
        omui.MPxLocatorNode.__init__(self)
        # Register this instance
        _NODE_REGISTRY[id(self)] = self

    @classmethod
    def creator(cls):
        return cls()

    @classmethod
    def initialize(cls):
        """Define node attributes"""

        # Numeric attributes
        num_attr = om.MFnNumericAttribute()

        cls.num_gaussians_attr = num_attr.create(
            "numGaussians", "ng", om.MFnNumericData.kInt, 0
        )
        num_attr.writable = True
        num_attr.storable = True
        num_attr.readable = True
        num_attr.keyable = False
        cls.addAttribute(cls.num_gaussians_attr)

        cls.display_lod_attr = num_attr.create(
            "displayLOD", "lod", om.MFnNumericData.kFloat, 1.0
        )
        num_attr.writable = True
        num_attr.storable = True
        num_attr.setMin(0.01)
        num_attr.setMax(1.0)
        num_attr.keyable = True
        cls.addAttribute(cls.display_lod_attr)

        cls.point_size_attr = num_attr.create(
            "pointSize", "ps", om.MFnNumericData.kFloat, 2.0
        )
        num_attr.writable = True
        num_attr.storable = True
        num_attr.setMin(0.1)
        num_attr.setMax(20.0)
        num_attr.keyable = True
        cls.addAttribute(cls.point_size_attr)

        cls.enable_render_attr = num_attr.create(
            "enableRender", "er", om.MFnNumericData.kBoolean, True
        )
        num_attr.writable = True
        num_attr.storable = True
        num_attr.keyable = True
        cls.addAttribute(cls.enable_render_attr)

        # String attribute for file path
        typed_attr = om.MFnTypedAttribute()
        cls.file_path_attr = typed_attr.create(
            "filePath", "fp", om.MFnData.kString
        )
        typed_attr.writable = True
        typed_attr.storable = True
        typed_attr.readable = True
        cls.addAttribute(cls.file_path_attr)

    def compute(self, plug, data_block):
        """Compute method (not used for locator node)"""
        # Locator nodes don't compute outputs
        return None

    def postConstructor(self):
        """Called after node construction - setup node for drawing"""
        # Store node handle for draw override access
        self.node_handle = om.MObjectHandle(self.thisMObject())

        # Also register by name for easier lookup
        dep_fn = om.MFnDependencyNode(self.thisMObject())
        node_name = dep_fn.name()
        _NODE_NAME_REGISTRY[node_name] = self

        print(f"   SplatCraft node registered: {node_name}")

    def set_gaussian_data(self, gaussian_dict):
        """
        Store Gaussian data in node

        Args:
            gaussian_dict: Dictionary with keys:
                - positions: [N, 3] numpy array
                - opacities: [N, 1] or [N] numpy array
                - scales: [N, 3] numpy array
                - rotations: [N, 4] numpy array
                - colors_dc: [N, 3] numpy array
                - colors_sh: [N, sh*3] numpy array (optional)
        """
        # Cache numpy arrays
        self.positions = gaussian_dict["positions"]
        self.opacities = gaussian_dict["opacities"]
        self.scales = gaussian_dict["scales"]
        self.rotations = gaussian_dict["rotations"]
        self.colors_dc = gaussian_dict["colors_dc"]
        self.colors_sh = gaussian_dict.get("colors_sh", None)

        # Update num_gaussians attribute
        plug = om.MPlug(self.thisMObject(), self.num_gaussians_attr)
        plug.setInt(self.positions.shape[0])

        print(f"SplatCraft: Loaded {self.positions.shape[0]} Gaussians")

    def get_gaussian_data(self):
        """Retrieve Gaussian data from node"""
        return {
            "positions": self.positions,
            "opacities": self.opacities,
            "scales": self.scales,
            "rotations": self.rotations,
            "colors_dc": self.colors_dc,
            "colors_sh": self.colors_sh,
        }

    def get_decimated_points(self, lod_factor=1.0, max_display_points=20000):
        """
        Get decimated point cloud for viewport display

        SAFETY: Hard cap on point count to prevent Maya crashes with large datasets

        Args:
            lod_factor: 0.01 to 1.0, percentage of points to show
            max_display_points: Hard limit on points to display (default: 20,000)

        Returns:
            tuple: (positions, colors) as numpy arrays
        """
        if self.positions is None or len(self.positions) == 0:
            return None, None

        lod_factor = max(0.01, min(1.0, lod_factor))
        num_points = int(self.positions.shape[0] * lod_factor)

        # SAFETY: Apply hard cap to prevent crashes
        num_points = min(num_points, max_display_points)
        num_points = max(1, num_points)  # At least 1 point

        # Random sampling with fixed seed for consistency
        if num_points >= self.positions.shape[0]:
            positions = self.positions
            colors = self.colors_dc
        else:
            np.random.seed(42)  # Fixed seed for consistent display
            indices = np.random.choice(self.positions.shape[0], num_points, replace=False)
            positions = self.positions[indices]
            colors = self.colors_dc[indices]

        # Convert colors to [0, 1] range for Maya
        # Check if colors are in [-1, 1] or [0, 1] or [0, 255]
        if colors.max() > 1.0:
            # Colors are in [0, 255]
            colors = colors / 255.0
        elif colors.min() < 0:
            # Colors are in [-1, 1]
            colors = np.clip((colors + 1.0) * 0.5, 0, 1)

        return positions, colors


def set_node_data_by_name(node_name, gaussian_data):
    """
    Set Gaussian data for a node by name
    This is a helper function that works around registry issues

    Args:
        node_name: Name of the SplatCraft node
        gaussian_data: Dictionary with Gaussian parameters
    """
    print(f"[DEBUG] set_node_data_by_name called for {node_name}")
    print(f"[DEBUG] _NODE_NAME_REGISTRY has {len(_NODE_NAME_REGISTRY)} items: {list(_NODE_NAME_REGISTRY.keys())}")
    print(f"[DEBUG] _NODE_REGISTRY has {len(_NODE_REGISTRY)} items")

    # First try to get from name registry
    if node_name in _NODE_NAME_REGISTRY:
        print(f"[DEBUG] Found in _NODE_NAME_REGISTRY")
        node_inst = _NODE_NAME_REGISTRY[node_name]
        node_inst.set_gaussian_data(gaussian_data)
        return True

    # Try to get MObject and look up in all registries
    try:
        sel_list = om.MSelectionList()
        sel_list.add(node_name)
        node_obj = sel_list.getDependNode(0)

        print(f"[DEBUG] Got MObject for {node_name}")

        # Try get_node_instance which searches all registries
        node_inst = get_node_instance(node_obj)
        if node_inst:
            print(f"[DEBUG] Found node instance via get_node_instance")
            node_inst.set_gaussian_data(gaussian_data)
            # Also add to name registry for future use
            _NODE_NAME_REGISTRY[node_name] = node_inst
            print(f"[DEBUG] Added to _NODE_NAME_REGISTRY")
            return True
        else:
            print(f"[DEBUG] get_node_instance returned None")
    except Exception as e:
        print(f"[DEBUG] Exception getting node instance: {e}")

    # If all else fails, store in a global data dict
    # The draw override will check this dict as a fallback
    print(f"[DEBUG] Falling back to _NODE_DATA storage")
    global _NODE_DATA
    if '_NODE_DATA' not in globals():
        _NODE_DATA = {}
    _NODE_DATA[node_name] = gaussian_data

    # Set numGaussians attribute manually
    try:
        import maya.cmds as cmds
        cmds.setAttr(f"{node_name}.numGaussians", gaussian_data["positions"].shape[0])
    except:
        pass

    return True


def get_node_data_by_name(node_name):
    """
    Get Gaussian data for a node by name

    Args:
        node_name: Name of the SplatCraft node

    Returns:
        Dictionary with Gaussian parameters or None
    """
    # Try name registry first
    if node_name in _NODE_NAME_REGISTRY:
        return _NODE_NAME_REGISTRY[node_name].get_gaussian_data()

    # Try global data dict
    if '_NODE_DATA' in globals() and node_name in globals()['_NODE_DATA']:
        return globals()['_NODE_DATA'][node_name]

    return None


def get_node_instance(node_obj):
    """
    Get the Python MPxNode instance from MObject
    Uses the global registry to look up node instances
    """
    # Get node name first - this is the most reliable method
    try:
        dep_fn = om.MFnDependencyNode(node_obj)
        node_name = dep_fn.name()

        # Try name-based lookup first
        if node_name in _NODE_NAME_REGISTRY:
            return _NODE_NAME_REGISTRY[node_name]
    except:
        pass

    # Fallback: try direct lookup using MObjectHandle
    for node_id, node_inst in list(_NODE_REGISTRY.items()):
        try:
            if hasattr(node_inst, 'node_handle'):
                if node_inst.node_handle.isValid() and node_inst.node_handle.object() == node_obj:
                    return node_inst
        except:
            continue

    # Last resort: try comparing all registered instances
    for node_id, node_inst in list(_NODE_REGISTRY.items()):
        try:
            if node_inst.thisMObject() == node_obj:
                return node_inst
        except:
            continue

    return None


class SplatCraftDrawOverride(omr.MPxDrawOverride):
    """
    Viewport 2.0 draw override for SplatCraft node
    Renders decimated point cloud for fast viewport interaction
    """

    NAME = "SplatCraftDrawOverride"

    def __init__(self, obj):
        omr.MPxDrawOverride.__init__(self, obj, None, False)
        self.positions_cache = None
        self.colors_cache = None

    @staticmethod
    def creator(obj):
        return SplatCraftDrawOverride(obj)

    @staticmethod
    def draw(context, data):
        return

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        """
        Prepare point cloud data for drawing
        Called before draw()
        """
        # Get node object
        node_obj = obj_path.node()
        dep_fn = om.MFnDependencyNode(node_obj)
        node_name = dep_fn.name()

        # DEBUG
        print(f"[DEBUG] prepareForDraw called for {node_name}")

        # CRITICAL FIX: Access _NODE_DATA through builtins (where plugin stores it)
        import builtins
        if hasattr(builtins, '_SPLATCRAFT_PLUGIN_GLOBALS'):
            print(f"[DEBUG] Using plugin globals from builtins")
            plugin_globals = builtins._SPLATCRAFT_PLUGIN_GLOBALS
            current_node_data = plugin_globals['_NODE_DATA']
            print(f"[DEBUG] _NODE_DATA dict id: {id(current_node_data)}")
            print(f"[DEBUG] _NODE_DATA contents: {list(current_node_data.keys())}")
        else:
            print(f"[DEBUG] WARNING: No plugin globals in builtins, using lexical _NODE_DATA")
            current_node_data = _NODE_DATA
            print(f"[DEBUG] _NODE_DATA dict id: {id(current_node_data)}")
            print(f"[DEBUG] _NODE_DATA contents: {list(current_node_data.keys())}")

        # Get LOD value
        lod_plug = dep_fn.findPlug("displayLOD", False)
        lod_value = lod_plug.asFloat()

        print(f"[DEBUG] LOD: {lod_value}")

        # Use the dynamically found _NODE_DATA
        if node_name in current_node_data:
            print(f"[DEBUG] Using current_node_data (dynamically found)")
            # Use the dynamically found dict, not the lexically captured one
            gaussian_data = current_node_data[node_name]
            positions = gaussian_data.get("positions")
            colors = gaussian_data.get("colors_dc")

            if positions is not None and colors is not None:
                # Apply LOD decimation with SAFETY CAP
                lod_factor = max(0.01, min(1.0, lod_value))
                num_points = int(positions.shape[0] * lod_factor)

                # SAFETY: Apply 20k hard cap (same as node instance method)
                num_points = min(20000, max(1, num_points))

                if num_points >= positions.shape[0]:
                    self.positions_cache = positions
                    self.colors_cache = colors
                else:
                    indices = np.random.choice(positions.shape[0], num_points, replace=False)
                    self.positions_cache = positions[indices]
                    self.colors_cache = colors[indices]

                # Convert colors to [0, 1] range
                if self.colors_cache.max() > 1.0:
                    self.colors_cache = self.colors_cache / 255.0
                elif self.colors_cache.min() < 0:
                    self.colors_cache = np.clip((self.colors_cache + 1.0) * 0.5, 0, 1)

                print(f"[DEBUG] Cached {len(self.positions_cache)} points from _NODE_DATA")
            else:
                print(f"[DEBUG] ERROR: positions or colors is None!")
                self.positions_cache = None
                self.colors_cache = None
        else:
            print(f"[DEBUG] ERROR: No data found for {node_name}!")
            self.positions_cache = None
            self.colors_cache = None

        return old_data

    def hasUIDrawables(self):
        return True

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        """
        Draw point cloud in viewport using optimized batch operations
        """
        # Get node object
        node_obj = obj_path.node()
        dep_fn = om.MFnDependencyNode(node_obj)

        # Get point size
        ps_plug = dep_fn.findPlug("pointSize", False)
        point_size = ps_plug.asFloat()

        print(f"[DEBUG] addUIDrawables called, point_size={point_size}, has_data={self.positions_cache is not None}")

        draw_manager.beginDrawable()

        # Set point size
        draw_manager.setPointSize(point_size)

        # Draw point cloud if we have data
        if self.positions_cache is not None and self.colors_cache is not None:
            print(f"[DEBUG] Drawing {len(self.positions_cache)} points")
            try:
                num_points = len(self.positions_cache)

                # Draw colored points
                # Maya's draw manager requires drawing points individually with colors
                for i in range(num_points):
                    pos = om.MPoint(
                        float(self.positions_cache[i, 0]),
                        float(self.positions_cache[i, 1]),
                        float(self.positions_cache[i, 2])
                    )
                    color = om.MColor([
                        float(self.colors_cache[i, 0]),
                        float(self.colors_cache[i, 1]),
                        float(self.colors_cache[i, 2]),
                        1.0
                    ])

                    draw_manager.setColor(color)
                    draw_manager.point(pos)

            except Exception as e:
                # If drawing fails, show error indicator
                draw_manager.setColor(om.MColor([1.0, 0.0, 0.0]))
                draw_manager.text(om.MPoint(0, 0, 0), f"Error: {str(e)[:50]}", omr.MUIDrawManager.kCenter)
        else:
            # No data - draw placeholder coordinate system
            draw_manager.setColor(om.MColor([1.0, 0.0, 0.0]))
            draw_manager.line(om.MPoint(0, 0, 0), om.MPoint(1, 0, 0))

            draw_manager.setColor(om.MColor([0.0, 1.0, 0.0]))
            draw_manager.line(om.MPoint(0, 0, 0), om.MPoint(0, 1, 0))

            draw_manager.setColor(om.MColor([0.0, 0.0, 1.0]))
            draw_manager.line(om.MPoint(0, 0, 0), om.MPoint(0, 0, 1))

        draw_manager.endDrawable()


def initializePlugin(plugin):
    """Initialize the plugin"""
    vendor = "SplatCraft"
    version = "0.2.0"  # Phase 3: Viewport rendering enabled

    # CRITICAL: Store reference to this module's globals so other modules can find it
    global _THIS_MODULE_GLOBALS
    _THIS_MODULE_GLOBALS = globals()

    # ALSO store in builtins so it's accessible from anywhere
    import builtins
    builtins._SPLATCRAFT_PLUGIN_GLOBALS = globals()

    print(f"[DEBUG] initializePlugin: Set _THIS_MODULE_GLOBALS")
    print(f"[DEBUG] initializePlugin: Stored in builtins._SPLATCRAFT_PLUGIN_GLOBALS")
    print(f"[DEBUG] initializePlugin: _NODE_DATA id = {id(_NODE_DATA)}")
    print(f"[DEBUG] initializePlugin: Module __name__ = {__name__}")

    plugin_fn = om.MFnPlugin(plugin, vendor, version)

    try:
        # Register node as locator node
        # Use omui.MPxLocatorNode (not om.MPxNode.kLocatorNode) for proper DAG node registration
        plugin_fn.registerNode(
            SplatCraftNode.TYPE_NAME,
            SplatCraftNode.TYPE_ID,
            SplatCraftNode.creator,
            SplatCraftNode.initialize,
            omui.MPxLocatorNode.kLocatorNode,  # Correct type for MPxLocatorNode
            SplatCraftNode.DRAW_CLASSIFICATION
        )
        print(f"✓ Registered node: {SplatCraftNode.TYPE_NAME}")
    except Exception as e:
        om.MGlobal.displayError(f"Failed to register node: {SplatCraftNode.TYPE_NAME} - {str(e)}")
        raise

    # Register draw override for viewport rendering
    try:
        omr.MDrawRegistry.registerDrawOverrideCreator(
            SplatCraftNode.DRAW_CLASSIFICATION,
            SplatCraftNode.DRAW_REGISTRANT_ID,
            SplatCraftDrawOverride.creator
        )
        print(f"✓ Registered draw override: {SplatCraftDrawOverride.NAME}")
    except Exception as e:
        om.MGlobal.displayError(f"Failed to register draw override - {str(e)}")
        raise


def uninitializePlugin(plugin):
    """Uninitialize the plugin"""
    plugin_fn = om.MFnPlugin(plugin)

    # Deregister draw override
    try:
        omr.MDrawRegistry.deregisterDrawOverrideCreator(
            SplatCraftNode.DRAW_CLASSIFICATION,
            SplatCraftNode.DRAW_REGISTRANT_ID
        )
        print(f"✓ Deregistered draw override")
    except Exception as e:
        om.MGlobal.displayError(f"Failed to deregister draw override - {str(e)}")
        # Don't raise - continue with node deregistration

    # Deregister node
    try:
        plugin_fn.deregisterNode(SplatCraftNode.TYPE_ID)
        print(f"✓ Deregistered node: {SplatCraftNode.TYPE_NAME}")
    except Exception as e:
        om.MGlobal.displayError(f"Failed to deregister node: {SplatCraftNode.TYPE_NAME} - {str(e)}")
        raise

    # Clear node registries but DON'T clear _NODE_DATA
    # (it needs to persist across module reloads for draw override to work)
    _NODE_REGISTRY.clear()
    _NODE_NAME_REGISTRY.clear()
    # DO NOT CLEAR: _NODE_DATA.clear()  # Keep data for draw override
    print(f"[DEBUG] Registries cleared, but _NODE_DATA preserved ({len(_NODE_DATA)} nodes)")
