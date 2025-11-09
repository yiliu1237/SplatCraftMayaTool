"""
SplatCraft Quick Loader Script for Maya

Run this script in Maya's Script Editor to set up SplatCraft quickly.
This handles all the imports and provides convenient shortcuts.

Usage in Maya Script Editor (Python tab):
    import sys
    sys.path.insert(0, '/root/SplatMayaTool/maya_plugin')
    import load_splatcraft
    load_splatcraft.load_plugin()
"""

import sys
import os
import maya.cmds as cmds

# ============================================================================
# Setup
# ============================================================================

# Auto-detect plugin path (works on Windows, macOS, Linux/WSL)
PLUGIN_PATH = os.path.dirname(os.path.abspath(__file__))
PLUGIN_FILE = os.path.join(PLUGIN_PATH, 'nodes', 'splatcraft_node.py')

print("\n" + "=" * 70)
print("SplatCraft Maya Plugin - Quick Loader")
print("=" * 70)

# Add to Python path
if PLUGIN_PATH not in sys.path:
    sys.path.insert(0, PLUGIN_PATH)
    print(f"✓ Added to Python path: {PLUGIN_PATH}")

# Load plugin
try:
    if cmds.pluginInfo('splatcraft_node.py', query=True, loaded=True):
        print("✓ Plugin already loaded")
    else:
        cmds.loadPlugin(PLUGIN_FILE)
        print("✓ Loaded SplatCraft plugin")
except Exception as e:
    print(f"✗ Error loading plugin: {e}")

# Force fresh import of utilities
if 'import_gaussians' in sys.modules:
    del sys.modules['import_gaussians']

import import_gaussians

print("✓ Imported utilities")

# ============================================================================
# Convenience Functions
# ============================================================================

def import_ply(ply_path, lod=None, open_webgl=True):
    """
    Import a Gaussian PLY file

    Args:
        ply_path: Path to PLY file
        lod: Level of detail (0.001 to 1.0), default None (auto-adjust based on file size)
        open_webgl: Whether to automatically open WebGL viewer (default: True)

    Returns:
        str: Name of created node
    """
    print(f"\nImporting: {ply_path}")
    node_name, data = import_gaussians.import_gaussian_scene(ply_path, open_webgl=open_webgl)

    # Set LOD if specified (otherwise use auto-adjusted value from import)
    if lod is not None:
        cmds.setAttr(f"{node_name}.displayLOD", lod)
        print(f"✓ LOD adjusted to {lod:.1%}")

    # Select the node
    cmds.select(node_name)

    return node_name


def node_info(node_name):
    """Print detailed information about a SplatCraft node"""
    num = cmds.getAttr(f"{node_name}.numGaussians")
    lod = cmds.getAttr(f"{node_name}.displayLOD")
    ps = cmds.getAttr(f"{node_name}.pointSize")
    fp = cmds.getAttr(f"{node_name}.filePath")

    print(f"\nSplatCraft Node: {node_name}")
    print("=" * 50)
    print(f"  Gaussians: {num:,}")
    print(f"  LOD: {lod:.2%} ({int(num * lod):,} points displayed)")
    print(f"  Point Size: {ps}")
    print(f"  Source File: {fp}")
    print("=" * 50 + "\n")


def set_lod(node_name, lod):
    """Set LOD for a node"""
    cmds.setAttr(f"{node_name}.displayLOD", lod)
    num = cmds.getAttr(f"{node_name}.numGaussians")
    print(f"✓ Set LOD to {lod:.1%} ({int(num * lod):,} points)")


def list_nodes():
    """List all SplatCraft nodes in the scene"""
    nodes = cmds.ls(type='splatCraftNode')

    if not nodes:
        print("No SplatCraft nodes in scene")
        return []

    print(f"\nFound {len(nodes)} SplatCraft node(s):")
    print("=" * 50)
    for node in nodes:
        num = cmds.getAttr(f"{node}.numGaussians")
        lod = cmds.getAttr(f"{node}.displayLOD")
        print(f"  {node}: {num:,} Gaussians @ {lod:.1%} LOD")
    print("=" * 50 + "\n")

    return nodes


def delete_all():
    """Delete all SplatCraft nodes"""
    nodes = cmds.ls(type='splatCraftNode')

    if not nodes:
        print("No SplatCraft nodes to delete")
        return

    for node in nodes:
        # Get parent transform if it exists
        parents = cmds.listRelatives(node, parent=True, type='transform')
        if parents:
            cmds.delete(parents[0])
        else:
            cmds.delete(node)

    print(f"✓ Deleted {len(nodes)} SplatCraft node(s)")


# ============================================================================
# Quick Examples
# ============================================================================

print("\n" + "=" * 70)
print("Available Functions:")
print("=" * 70)
print("  import_ply(path, lod=None, open_webgl=True)")
print("      - Import a Gaussian PLY file with auto WebGL panel")
print("  node_info(node_name)")
print("      - Show node information")
print("  set_lod(node_name, lod)")
print("      - Set LOD (0.001 to 1.0)")
print("  list_nodes()")
print("      - List all SplatCraft nodes")
print("  delete_all()")
print("      - Delete all SplatCraft nodes")
print("=" * 70)

print("\nQuick Examples:")
print("-" * 70)
print("# Import truck.ply - auto-opens WebGL viewer!")
print("node = import_ply(r'C:\\Users\\thero\\OneDrive\\Documents\\GitHub\\flash3d\\flash3d\\example\\truck.ply')")
print()
print("# Import without WebGL panel")
print("node = import_ply('path/to/file.ply', open_webgl=False)")
print()
print("# Import with specific LOD")
print("node = import_ply('path/to/file.ply', lod=0.05)")
print()
print("# Show node info")
print("node_info('splatCraftNode1')")
print()
print("# Adjust LOD after import")
print("set_lod('splatCraftNode1', 0.02)  # 2%")
print("-" * 70)

# Show existing nodes if any
existing = cmds.ls(type='splatCraftNode')
if existing:
    print(f"\n✓ Found {len(existing)} existing SplatCraft node(s) in scene")
    list_nodes()

print("\n✓ SplatCraft ready!\n")


# ============================================================================
# NEW: Plugin Loading and UI Functions
# ============================================================================

def load_plugin(fix_paths=True):
    """
    Load the SplatCraft plugin (with WSL/Linux compatibility fixes)

    Args:
        fix_paths: If True, fixes macOS-specific paths for WSL/Linux

    Returns:
        bool: True if loaded successfully
    """
    print("\n" + "=" * 70)
    print("LOADING SPLATCRAFT PLUGIN")
    print("=" * 70)

    # Check if plugin file exists
    if not os.path.exists(PLUGIN_FILE):
        print(f"Plugin file not found: {PLUGIN_FILE}")
        return False

    # Fix macOS paths for WSL/Linux if needed
    plugin_to_load = PLUGIN_FILE
    if fix_paths and sys.platform.startswith('linux'):
        print("⚠ Detected Linux/WSL - checking for platform compatibility...")

        # Read plugin to check for macOS paths
        with open(PLUGIN_FILE, 'r') as f:
            content = f.read()

        if '~/Library/Python' in content:
            print("⚠ Found macOS-specific paths, creating WSL-compatible version...")

            # Create fixed version
            fixed_content = content.replace(
                "user_site = os.path.expanduser('~/Library/Python/3.10/lib/python/site-packages')\n"
                "if user_site not in sys.path:\n"
                "    sys.path.insert(0, user_site)",
                "# Platform-agnostic path detection\n"
                "import platform\n"
                "if platform.system() == 'Darwin':  # macOS\n"
                "    user_site = os.path.expanduser('~/Library/Python/3.10/lib/python/site-packages')\n"
                "elif platform.system() == 'Linux':  # Linux/WSL\n"
                "    user_site = os.path.expanduser('~/.local/lib/python3.10/site-packages')\n"
                "else:  # Windows\n"
                "    user_site = None\n"
                "if user_site and os.path.exists(user_site) and user_site not in sys.path:\n"
                "    sys.path.insert(0, user_site)"
            )

            # Write to temporary file
            plugin_to_load = os.path.join(PLUGIN_PATH, 'nodes', 'splatcraft_node_wsl.py')
            with open(plugin_to_load, 'w') as f:
                f.write(fixed_content)

            plugin_name = 'splatcraft_node_wsl.py'
            print(f"✓ Created WSL-compatible plugin: {plugin_name}")
        else:
            plugin_name = 'splatcraft_node.py'
    else:
        plugin_name = 'splatcraft_node.py'

    # Unload if already loaded
    if cmds.pluginInfo(plugin_name, query=True, loaded=True):
        print(f"Plugin already loaded, unloading first...")
        try:
            cmds.unloadPlugin(plugin_name)
        except:
            pass

    # Load plugin
    try:
        cmds.loadPlugin(plugin_to_load)

        if cmds.pluginInfo(plugin_name, query=True, loaded=True):
            version = cmds.pluginInfo(plugin_name, query=True, version=True)
            print(f"✓ Plugin loaded successfully!")
            print(f"  Name: {plugin_name}")
            print(f"  Version: {version}")
            print("=" * 70)
            return True
        else:
            print(f"Plugin loaded but not registered properly")
            return False

    except Exception as e:
        print(f"Failed to load plugin: {e}")
        import traceback
        traceback.print_exc()
        return False


def open_inference_ui(conda_env='splatter-image'):
    """
    Open the inference UI panel

    Args:
        conda_env: Name of conda environment with splatter-image

    Returns:
        UI panel instance or None
    """
    try:
        print(f"\nOpening inference UI panel (conda env: {conda_env})...")
        from ui.inference_panel import show_inference_panel
        panel = show_inference_panel(conda_env=conda_env)
        print("✓ Inference UI panel opened!")
        print("\nYou can now:")
        print("  1. Click '🔧 Test Conda Environment'")
        print("  2. Upload an image")
        print("  3. Click 'Generate 3D Gaussian Splat'")
        return panel
    except Exception as e:
        print(f"Failed to open UI panel: {e}")
        import traceback
        traceback.print_exc()
        return None


def quick_start(conda_env='splatter-image'):
    """
    Quick start: Load plugin and open UI in one command

    Args:
        conda_env: Name of conda environment with splatter-image
    """
    if load_plugin():
        return open_inference_ui(conda_env=conda_env)
    else:
        print("\nCannot open UI - plugin failed to load")
        return None
