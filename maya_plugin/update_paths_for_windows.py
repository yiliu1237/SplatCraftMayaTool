"""
Quick script to update all macOS paths to Windows paths
Run this once to update all files

Usage:
    python update_paths_for_windows.py
"""
import os
import re

# Path mapping
OLD_PATH = '/Users/yiliu/Documents/GitHub/flash3d'
NEW_PATH = r'C:\Users\thero\OneDrive\Documents\GitHub\flash3d'

# Files to update (Python scripts only - documentation is optional)
files_to_update = [
    'fresh_start.py',
    'test_phase4_in_maya.py',
    'test_real_ply_safe.py',
    'reload_plugin.py',
    'load_splatcraft.py',
    'verify_ply.py',
    'PHASE3_CLEAN.py',
    'PHASE3_DEMO.py',
    'TEST_SIMPLE.py',
    'examples/basic_usage.py'
]

def update_file_paths(filepath, old_path, new_path):
    """Update paths in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"Error reading: {e}"

    # Replace paths
    original = content
    content = content.replace(old_path, new_path)

    # Fix: Ensure we use raw strings (r'...') or forward slashes
    # Replace mixed slash patterns from the replacement
    content = content.replace(new_path + '/maya_plugin', new_path + r'\maya_plugin')
    content = content.replace(new_path + '/flash3d', new_path + r'\flash3d')

    # Add raw string prefix if path assignment doesn't have it
    import re
    # Match: variable = 'C:\path' and replace with r'C:\path'
    content = re.sub(
        r"([_a-zA-Z][_a-zA-Z0-9]*\s*=\s*)'(C:\\[^']*)'",
        r"\1r'\2'",
        content
    )

    if content != original:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "Updated"
        except Exception as e:
            return False, f"Error writing: {e}"
    else:
        return False, "No changes needed"


if __name__ == "__main__":
    print("="*70)
    print("SplatCraft - Windows Path Update Utility")
    print("="*70)
    print(f"\nUpdating paths from:")
    print(f"  OLD: {OLD_PATH}")
    print(f"  NEW: {NEW_PATH}")
    print()

    maya_plugin_root = os.path.dirname(os.path.abspath(__file__))
    print(f"Plugin root: {maya_plugin_root}\n")

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for file in files_to_update:
        filepath = os.path.join(maya_plugin_root, file)

        if not os.path.exists(filepath):
            print(f"[SKIP] Not found: {file}")
            skipped_count += 1
            continue

        success, message = update_file_paths(filepath, OLD_PATH, NEW_PATH)

        if success:
            print(f"[OK] Updated: {file}")
            updated_count += 1
        elif "Error" in message:
            print(f"[ERROR] {message}: {file}")
            error_count += 1
        else:
            print(f"[INFO] {message}: {file}")
            skipped_count += 1

    print("\n" + "="*70)
    print("Summary:")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors: {error_count}")
    print("="*70)

    if updated_count > 0:
        print("\nPath update complete!")
        print("\nNext steps:")
        print("  1. Open Maya")
        print("  2. Run in Script Editor (Python):")
        print(f"     exec(open(r'{NEW_PATH}\\maya_plugin\\test_phase4_in_maya.py').read())")
    else:
        print("\nNo files were updated. Paths may already be correct.")
