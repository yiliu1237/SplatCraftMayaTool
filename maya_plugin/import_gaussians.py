"""
Import Gaussian Splat Data into Maya

This module provides utilities to import PLY files containing
3D Gaussian splatting data into Maya as SplatCraft nodes.
"""

import numpy as np
import maya.cmds as cmds
import maya.api.OpenMaya as om
from plyfile import PlyData
from pathlib import Path


# Global dictionary to store node references
# This is a workaround to access MPxNode instances from Python
SPLATCRAFT_NODES = {}


def read_ply_gaussians(ply_path):
    """
    Read Gaussian splat data from PLY file

    Args:
        ply_path: Path to PLY file

    Returns:
        dict: Gaussian parameters with keys:
            - positions: [N, 3] numpy array
            - opacities: [N] numpy array
            - scales: [N, 3] numpy array
            - rotations: [N, 4] numpy array
            - colors_dc: [N, 3] numpy array
            - colors_sh: None or [N, sh*3] numpy array
    """
    ply_path = Path(ply_path)
    if not ply_path.exists():
        raise FileNotFoundError(f"PLY file not found: {ply_path}")

    print(f"Reading PLY file: {ply_path}")
    ply_data = PlyData.read(str(ply_path))
    vertex = ply_data['vertex']

    # Check available fields
    available_fields = [prop.name for prop in vertex.properties]

    # Detect format - supports two formats:
    # Format 1: Standard 3DGS format (red/green/blue, scale_x/y/z)
    # Format 2: SH format (f_dc_0/1/2, scale_0/1/2)

    has_rgb = 'red' in available_fields
    has_sh = 'f_dc_0' in available_fields
    has_scale_xyz = 'scale_x' in available_fields
    has_scale_012 = 'scale_0' in available_fields

    # Check if this is a valid Gaussian splat file
    required_base = ['x', 'y', 'z', 'opacity', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    missing_base = [f for f in required_base if f not in available_fields]

    if missing_base or (not has_rgb and not has_sh) or (not has_scale_xyz and not has_scale_012):
        print(f"\n✗ ERROR: This PLY file does not appear to be a valid Gaussian splatting file!")
        if missing_base:
            print(f"  Missing required fields: {', '.join(missing_base)}")
        if not has_rgb and not has_sh:
            print(f"  Missing color data (expected 'red/green/blue' or 'f_dc_0/1/2')")
        if not has_scale_xyz and not has_scale_012:
            print(f"  Missing scale data (expected 'scale_x/y/z' or 'scale_0/1/2')")
        print(f"\n  Available fields in this file: {', '.join(available_fields[:20])}...")
        raise ValueError(f"Invalid PLY file format for Gaussian splatting")

    # Extract positions
    positions = np.stack([vertex['x'], vertex['y'], vertex['z']], axis=1)

    # Extract colors based on format
    if has_rgb:
        # Format 1: RGB uint8 colors
        colors_uint8 = np.stack([vertex['red'], vertex['green'], vertex['blue']], axis=1)
        colors_dc = colors_uint8.astype(np.float32) / 255.0
    else:
        # SH DC → RGB
        fdc = np.stack([vertex['f_dc_0'], vertex['f_dc_1'], vertex['f_dc_2']], axis=1).astype(np.float32)
        SH_C0 = 0.28209479177387814
        colors_dc = np.clip(fdc * SH_C0 + 0.5, 0.0, 1.0)

    # Extract scales based on format
    if has_scale_xyz:
        scales = np.stack([vertex['scale_x'], vertex['scale_y'], vertex['scale_z']], axis=1).astype(np.float32)
    else:
        scales_raw = np.stack([vertex['scale_0'], vertex['scale_1'], vertex['scale_2']], axis=1).astype(np.float32)
        scales = np.exp(scales_raw)

    # Extract rotations (quaternions) - same for both formats
    rotations = np.stack([vertex['rot_0'], vertex['rot_1'], vertex['rot_2'], vertex['rot_3']], axis=1)

    # heuristic reorder: if col0 looks like w, move it to the end
    if np.mean(np.abs(rotations[:, 0])) > np.mean(np.abs(rotations[:, 3])) * 1.5:
        rotations = rotations[:, [1, 2, 3, 0]]
    
    # normalize
    rotations /= (np.linalg.norm(rotations, axis=1, keepdims=True) + 1e-8)

    # Extract opacity
    opacities_logit = np.asarray(vertex['opacity'], dtype=np.float32)
    opacities = 1.0 / (1.0 + np.exp(-opacities_logit))
    opacities = opacities.reshape(-1)  # 1-D


    gaussian_data = {
        "positions": positions.astype(np.float32),
        "opacities": opacities.astype(np.float32),
        "scales": scales.astype(np.float32),
        "rotations": rotations.astype(np.float32),
        "colors_dc": colors_dc.astype(np.float32),
        "colors_sh": None,
    }

    print(f"  Scales range: [{scales.min():.3e}, {scales.max():.3e}]  (linear)")    
    w_mean = float(np.mean(np.abs(rotations[:, 3])))
    print(f"  mean |quat.w|: {w_mean:.3f}")

    print(f"✓ Read {positions.shape[0]} Gaussians")
    print(f"  Position range: [{positions.min():.3f}, {positions.max():.3f}]")
    print(f"  Color range: [{colors_dc.min():.3f}, {colors_dc.max():.3f}]")

    return gaussian_data


def read_metadata(npz_path):
    """
    Read camera metadata from NPZ file

    Args:
        npz_path: Path to NPZ metadata file

    Returns:
        dict: Metadata dictionary or None if file doesn't exist
    """
    npz_path = Path(npz_path)
    if not npz_path.exists():
        print(f"Note: No metadata file found at {npz_path}")
        return None

    metadata = np.load(str(npz_path))
    return {k: metadata[k] for k in metadata.files}


def import_gaussian_scene(ply_path, node_name=None, open_webgl=True):
    """
    Import Gaussian splat scene into Maya

    Args:
        ply_path: Path to .ply file
        node_name: Optional custom name for the node (default: auto-generated)
        open_webgl: Whether to automatically open WebGL viewer panel (default: True)

    Returns:
        tuple: (node_name, gaussian_data) - Name of created SplatCraft node and the data
    """
    # Read Gaussian data
    gaussian_data = read_ply_gaussians(ply_path)

    # Read metadata if available
    npz_path = Path(ply_path).with_suffix('.npz')
    metadata = read_metadata(npz_path)

    # Create SplatCraft node
    if node_name is None:
        node_name = "splatCraftNode#"

    node_name = cmds.createNode("splatCraftNode", name=node_name)
    print(f"✓ Created node: {node_name}")

    # Set file path attribute
    cmds.setAttr(f"{node_name}.filePath", str(ply_path), type="string")

    # Set initial display attributes with auto-LOD based on file size
    num_gaussians = gaussian_data["positions"].shape[0]
    cmds.setAttr(f"{node_name}.numGaussians", num_gaussians)

    # SAFETY: Auto-adjust LOD based on Gaussian count to prevent crashes
    # Max safe display: 20,000 points (hardcoded in splatcraft_node.py)
    if num_gaussians > 2000000:  # > 2M Gaussians
        initial_lod = 0.01  # 1% (will be capped at 20k points)
        print(f"  Large file detected ({num_gaussians:,} Gaussians)")
        print(f"   Setting initial LOD to 1% for stability (max 20k points displayed)")
    elif num_gaussians > 500000:  # > 500k Gaussians
        initial_lod = 0.02  # 2%
        print(f"   Auto-adjusted LOD to 2% for large file ({num_gaussians:,} Gaussians)")
    elif num_gaussians < 10000:  # > 100k Gaussians
        initial_lod = 1.0  # 5%
    else:
        initial_lod = 0.1  # 10% for small files

    cmds.setAttr(f"{node_name}.displayLOD", initial_lod)
    cmds.setAttr(f"{node_name}.pointSize", 2.0)
    cmds.setAttr(f"{node_name}.enableRender", True)

    # Store Gaussian data in the node
    # We need to access the MPxNode instance to call set_gaussian_data()
    # This requires getting the MObject and then the node instance
    store_gaussian_data(node_name, gaussian_data)

    # Store reference in global dict for later access
    SPLATCRAFT_NODES[node_name] = gaussian_data

    print(f"✓ Successfully imported {gaussian_data['positions'].shape[0]} Gaussians")
    print(f"  Node: {node_name}")
    print(f"  Source: {ply_path}")
    print(f"  Viewport: {int(num_gaussians * initial_lod):,} points @ {initial_lod:.1%} LOD")

    # Automatically open WebGL viewer panel
    if open_webgl:
        try:
            print("\n✓ Opening WebGL Gaussian viewer...")
            import sys
            maya_plugin_path = Path(__file__).parent
            if str(maya_plugin_path) not in sys.path:
                sys.path.insert(0, str(maya_plugin_path))

            # Reload module to pick up any changes
            if 'maya_webgl_panel' in sys.modules:
                import importlib
                importlib.reload(sys.modules['maya_webgl_panel'])

            import maya_webgl_panel
            panel = maya_webgl_panel.show_webgl_panel(ply_path=str(ply_path))

            print("✓ WebGL panel opened!")
            print(f"  Viewport: {int(num_gaussians * initial_lod):,} sampled points")
            print(f"  WebGL: {num_gaussians:,} full Gaussians")
            print("\n🎮 Camera sync enabled - rotate viewport to see synchronized movement!")

        except Exception as e:
            print(f"⚠️  Warning: Could not open WebGL panel: {e}")
            print("   (You can still view point cloud in viewport)")

    return node_name, gaussian_data


def store_gaussian_data(node_name, gaussian_data):
    """
    Store Gaussian data in the SplatCraft node

    This calls the helper function from splatcraft_node module to properly
    store data in the node instance.

    Args:
        node_name: Name of the SplatCraft node
        gaussian_data: Dictionary of Gaussian parameters
    """
    try:
        # CRITICAL: Access plugin globals from builtins (where plugin stores it)
        import builtins

        if hasattr(builtins, '_SPLATCRAFT_PLUGIN_GLOBALS'):
            print(f"[DEBUG] Found plugin globals in builtins")
            plugin_globals = builtins._SPLATCRAFT_PLUGIN_GLOBALS
        else:
            print(f"[DEBUG] ERROR: No _SPLATCRAFT_PLUGIN_GLOBALS in builtins!")
            raise Exception("Cannot store data: plugin not initialized")

        node_data_dict = plugin_globals['_NODE_DATA']

        # Debug
        print(f"[DEBUG] Plugin globals id: {id(plugin_globals)}")
        print(f"[DEBUG] Plugin _NODE_DATA dict id: {id(node_data_dict)}")
        print(f"[DEBUG] _NODE_DATA contents before store: {list(node_data_dict.keys())}")

        # Store directly in the plugin's _NODE_DATA dict
        node_data_dict[node_name] = gaussian_data

        # Debug: Check after store
        print(f"[DEBUG] _NODE_DATA contents after store: {list(node_data_dict.keys())}")
        print(f"✓ Gaussian data stored in node: {node_name}")

    except Exception as e:
        print(f"Warning: Error storing data in node: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: just store in SPLATCRAFT_NODES dict
        SPLATCRAFT_NODES[node_name] = gaussian_data


def get_gaussian_data(node_name):
    """
    Retrieve Gaussian data for a given node

    Args:
        node_name: Name of the SplatCraft node

    Returns:
        dict: Gaussian data dictionary or None if not found
    """
    return SPLATCRAFT_NODES.get(node_name, None)


def update_lod(node_name, lod_factor):
    """
    Update the LOD (Level of Detail) for a SplatCraft node

    Args:
        node_name: Name of the SplatCraft node
        lod_factor: LOD value between 0.01 and 1.0
    """
    lod_factor = max(0.01, min(1.0, lod_factor))
    cmds.setAttr(f"{node_name}.displayLOD", lod_factor)
    print(f"Updated LOD for {node_name}: {lod_factor:.2%}")


def batch_import_gaussians(ply_files):
    """
    Import multiple PLY files as separate SplatCraft nodes

    Args:
        ply_files: List of paths to PLY files

    Returns:
        list: List of created node names
    """
    node_names = []

    for ply_path in ply_files:
        try:
            node_name, _ = import_gaussian_scene(ply_path)
            node_names.append(node_name)
        except Exception as e:
            print(f"Error importing {ply_path}: {e}")

    print(f"\n✓ Imported {len(node_names)}/{len(ply_files)} files successfully")
    return node_names


def refresh_node(node_name):
    """
    Refresh/reload Gaussian data from the source file

    Args:
        node_name: Name of the SplatCraft node
    """
    # Get file path from node
    file_path = cmds.getAttr(f"{node_name}.filePath")

    if not file_path:
        print(f"Error: No file path set for {node_name}")
        return

    # Re-import the data
    gaussian_data = read_ply_gaussians(file_path)
    store_gaussian_data(node_name, gaussian_data)
    SPLATCRAFT_NODES[node_name] = gaussian_data

    # Update num gaussians
    cmds.setAttr(f"{node_name}.numGaussians", gaussian_data["positions"].shape[0])

    print(f"✓ Refreshed {node_name} from {file_path}")


# Example usage functions for Maya Script Editor:

def example_import():
    """
    Example: Import a single PLY file
    """
    print("SplatCraft Import Example")
    print("=" * 50)
    print("\nTo import a Gaussian PLY file, use:")
    print("\n  import import_gaussians")
    print("  node, data = import_gaussians.import_gaussian_scene('/path/to/file.ply')")
    print("\nTo adjust LOD:")
    print("  import_gaussians.update_lod('splatCraftNode1', 0.5)  # 50% of points")


if __name__ == "__main__":
    example_import()
