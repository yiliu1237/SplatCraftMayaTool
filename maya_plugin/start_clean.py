"""
SplatCraft Quick Start for Windows Maya + WSL (ASCII-only version)

Usage in Maya Script Editor (Python):
    exec(open('\\\\wsl$\\Ubuntu\\root\\SplatMayaTool\\maya_plugin\\start_clean.py').read())
"""

import sys
import os
import maya.cmds as cmds

print("\n" + "=" * 70)
print("  SPLATCRAFT - WINDOWS + WSL START")
print("=" * 70)

# Step 1: Unload old plugins
print("\n[1/4] Cleaning up old plugins...")
for plugin_name in ['splatcraft_node.py', 'splatcraft_node_wsl.py']:
    try:
        if cmds.pluginInfo(plugin_name, query=True, loaded=True):
            cmds.unloadPlugin(plugin_name)
            print("  [OK] Unloaded " + plugin_name)
    except:
        pass

# Step 2: Clear Python module cache
print("\n[2/4] Clearing Python module cache...")
modules_to_clear = [
    'load_splatcraft',
    'splatter_subprocess',
    'import_gaussians',
    'ui.inference_panel',
    'rendering.splat_renderer',
    'maya_rendered_panel'
]

for module in modules_to_clear:
    if module in sys.modules:
        del sys.modules[module]
        print("  [OK] Cleared " + module)

# Step 3: Add WSL path
print("\n[3/4] Setting up Python path...")

wsl_paths = [
    '\\\\wsl$\\Ubuntu\\root\\SplatMayaTool\\maya_plugin',
    '\\\\wsl.localhost\\Ubuntu\\root\\SplatMayaTool\\maya_plugin',
]

plugin_path = None
for path in wsl_paths:
    if os.path.exists(path):
        plugin_path = path
        print("  [OK] Found WSL path: " + plugin_path)
        break

if not plugin_path:
    print("  [ERROR] Could not find WSL plugin path!")
    print("  Tried:")
    for p in wsl_paths:
        print("    - " + p)
    raise FileNotFoundError("WSL plugin path not found")

if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)
    print("  [OK] Added to Python path")

# Step 4: Import and run
print("\n[4/4] Loading SplatCraft...")

try:
    import load_splatcraft
    result = load_splatcraft.quick_start(conda_env='splatter')

    if result:
        print("\n" + "=" * 70)
        print("  SUCCESS - SPLATCRAFT READY (Windows + WSL Mode)")
        print("=" * 70)
        print("\nThe inference UI panel is now open on the right side.")
        print("\nNext steps:")
        print("  1. Click 'Test Conda Environment' button")
        print("  2. Click 'Browse Image...' - select a Windows image")
        print("  3. Click 'Generate 3D Gaussian Splat'")
        print("=" * 70 + "\n")
    else:
        print("\n[WARNING] UI panel did not open - check errors above")

except Exception as e:
    print("\n[ERROR] Startup failed: " + str(e))
    import traceback
    traceback.print_exc()
