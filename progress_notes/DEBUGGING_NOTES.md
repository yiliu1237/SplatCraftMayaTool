# SplatCraft Maya Plugin - Debugging Journey

**Date Solved**:  November 3, 2025

This document chronicles the major bugs encountered during Phase 3 (Viewport Proxy) development and how they were solved.

---

## Bug #1: Maya Crash on Large Files

**Date**: October 25, 2025

### Symptom
Maya crashed when importing truck.ply (1.7M Gaussians) with default 10% LOD setting.

### Root Cause
Attempting to display 169,000 points in the viewport overwhelmed Maya's rendering system, causing a hard crash.

### Solution
Implemented multiple safety layers:
1. **Hard cap**: Maximum 20,000 points displayed regardless of LOD setting
2. **Auto-LOD adjustment**: Automatically set LOD based on file size
   - >2M Gaussians: 1% LOD
   - >500k Gaussians: 2% LOD
   - >100k Gaussians: 5% LOD
3. **Optimized array operations**: Pre-allocate arrays instead of using append in loops

**Files Modified**: `splatcraft_node.py`, `import_gaussians.py`

---

## Bug #2: Module Instance Problem - Points Not Visible

**Date**: November 1, 2025

### Symptom
Import succeeded without crash, debug output showed:
- `[DEBUG] Drawing 20000 points`
- But no points visible in viewport

Then discovered viewport error:
- `Error: 'OpenMayaUI.MUIDrawManager' object has no attribute`

### Root Cause #1: Draw API Issue
The draw code was trying to use `setColorArray()` and batch drawing, which isn't supported for points in Maya's API. Each point must be drawn individually with `setColor()` + `point()`.

**Solution**: Changed from batch drawing to per-point drawing loop.

**Files Modified**: `splatcraft_node.py` (addUIDrawables method)

---

### Root Cause #2: Multiple Module Instances

This was the **major bug** that took extensive debugging.

**The Problem**:
```
When storing:  module_id=16052851696, dict_id=16434214464, contents=['splatCraftNode1']
When drawing:  module_id=16767775360, dict_id=16486024960, contents=[] ← EMPTY!
```

Data was stored in one `_NODE_DATA` dictionary, but the draw override was reading from a DIFFERENT `_NODE_DATA` dictionary in a different module instance!

### Why This Happened

1. **Plugin Load**: Maya's `cmds.loadPlugin()` loads the plugin file directly, creating Module Instance A
2. **Module Reload**: `importlib.reload(splatcraft_node)` creates Module Instance B
3. **Import Statement**: `from nodes import splatcraft_node` might return Instance B
4. **Draw Override**: Created with lexical reference to Instance A's `_NODE_DATA`
5. **Result**: Storage writes to Instance B's dict, draw reads from Instance A's dict → data not found!

### Attempted Solutions (That Didn't Work)

1. **Attempt 1**: Check if plugin already loaded to avoid reload
   - Still failed because import created new instance

2. **Attempt 2**: Use `sys.modules['splatcraft_node']` explicitly
   - Failed because module registered as `'nodes.splatcraft_node'`, not `'splatcraft_node'`

3. **Attempt 3**: Search sys.modules for module with `SplatCraftDrawOverride` class
   - Failed because after clearing module cache, the module wasn't in sys.modules with a predictable name

4. **Attempt 4**: Store reference in `_THIS_MODULE_GLOBALS` and search for it
   - Failed because the plugin module had `__name__ = 'builtins'`, not registered in sys.modules properly!

### Final Solution: Use `builtins` as Global Storage

Since Maya loads the plugin in the `builtins` namespace, we store the plugin's globals dictionary in a truly global location that ALL code can access:

```python
# In initializePlugin():
import builtins
builtins._SPLATCRAFT_PLUGIN_GLOBALS = globals()

# In storage code:
plugin_globals = builtins._SPLATCRAFT_PLUGIN_GLOBALS
node_data_dict = plugin_globals['_NODE_DATA']
node_data_dict[node_name] = gaussian_data

# In draw code:
plugin_globals = builtins._SPLATCRAFT_PLUGIN_GLOBALS
current_node_data = plugin_globals['_NODE_DATA']
gaussian_data = current_node_data[node_name]
```

**Why This Works**:
- `builtins` module is THE SAME instance across all code in Python
- No matter how many times modules are imported/reloaded, `builtins` is always the same
- Both storage and draw code access the EXACT SAME dictionary

**Files Modified**:
- `splatcraft_node.py` (initializePlugin, prepareForDraw)
- `import_gaussians.py` (store_gaussian_data)

---

## Bug #3: Module Cache Conflicts

**Date**: November 3, 2025

### Symptom
Even after implementing module instance fixes, dict IDs still didn't match.

### Root Cause
The workflow was:
1. Reload modules → creates fresh instances
2. Load plugin → Maya loads from file
3. Result: Two instances coexist

### Solution
Clear module cache BEFORE loading plugin, ensuring only ONE instance exists:

```python
# Remove from sys.modules to force fresh load
modules_to_remove = [k for k in sys.modules.keys() if 'splatcraft' in k.lower()]
for key in modules_to_remove:
    del sys.modules[key]

# Now load plugin - creates the ONE and ONLY instance
cmds.loadPlugin(plugin_path)
```

**Files Modified**: `fresh_start.py`

---

## Summary of Key Learnings

1. **Maya's Plugin Loading**: Maya loads plugins in the `builtins` namespace, not as standard Python modules
2. **Module Reloading**: `importlib.reload()` creates NEW module instances with NEW global dictionaries
3. **Lexical Scope**: Draw override captures lexical reference to `_NODE_DATA` at class definition time
4. **Global Storage**: For cross-module communication in Maya plugins, use `builtins` module as truly global storage
5. **Draw API**: Maya's draw manager requires per-point drawing for colored points, not batch operations

---

## Final Working Solution

### Architecture:
1. Plugin loads → stores `globals()` in `builtins._SPLATCRAFT_PLUGIN_GLOBALS`
2. All code accesses data through `builtins._SPLATCRAFT_PLUGIN_GLOBALS['_NODE_DATA']`
3. No reliance on module names, sys.modules, or import statements
4. Guaranteed single source of truth

### Safety Features:
- Hard 20,000 point display cap
- Auto-LOD adjustment based on file size
- Optimized rendering (per-point but efficient)
- Clear module cache to avoid instance conflicts

### Result:
✅ Successfully displays 20,000 colored points from 1.7M Gaussian truck.ply file without crashes!

---

## Files Involved in Final Solution

- `splatcraft_node.py`: Plugin core with node, draw override, and builtins storage
- `import_gaussians.py`: PLY import with builtins-based data storage
- `fresh_start.py`: Clean workflow with module cache clearing
- `test_real_ply_safe.py`: Safe import script with crash prevention

Total debugging time: ~4 hours
Total lines of debug output analyzed: ~500+
Total module instance permutations tested: 7

**Lesson**: Maya's plugin system has unique quirks that require understanding of Python's module system, lexical scope, and global storage mechanisms. When in doubt, use `builtins`! 🎯
