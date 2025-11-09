"""
Live camera monitor - prints camera info as you move the viewport

Run this in Maya's Script Editor:
exec(open('C:/Users/thero/OneDrive/Desktop/SplatMayaTool/maya_plugin/monitor_camera_live.py').read())

Then rotate/pan/zoom the Maya viewport and watch the console for updates.
Press ESC or run again to stop monitoring.
"""

import maya.cmds as cmds
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore
import numpy as np

# Global reference to timer
_monitor_timer = None

class CameraMonitor(QtCore.QObject):
    def __init__(self):
        super(CameraMonitor, self).__init__()
        self.last_state = None
        self.update_count = 0

    def check_camera(self):
        """Check camera state and print if changed"""
        try:
            # Get active panel
            active_panel = cmds.getPanel(withFocus=True)
            if not active_panel or cmds.getPanel(typeOf=active_panel) != 'modelPanel':
                model_panels = cmds.getPanel(type='modelPanel')
                if not model_panels:
                    return
                active_panel = model_panels[0]

            # Get camera
            camera = cmds.modelPanel(active_panel, query=True, camera=True)
            if not camera:
                return

            # Get camera transform
            camera_shapes = cmds.ls(camera, type='camera')
            if camera_shapes:
                camera_transform = cmds.listRelatives(camera_shapes[0], parent=True)[0]
            else:
                camera_transform = camera

            # Get position and matrix
            cam_pos = cmds.xform(camera_transform, query=True, translation=True, worldSpace=True)
            world_matrix = cmds.xform(camera_transform, query=True, matrix=True, worldSpace=True)

            # Check if changed
            current_state = (tuple(cam_pos), tuple(world_matrix))
            if current_state != self.last_state:
                self.last_state = current_state
                self.update_count += 1

                # Print update
                world_matrix_np = np.array(world_matrix, dtype=np.float32).reshape(4, 4)
                forward = -world_matrix_np[:3, 2]

                print(f"\n[Update #{self.update_count}] Camera moved!")
                print(f"  Panel: {active_panel}")
                print(f"  Camera: {camera}")
                print(f"  Position: [{cam_pos[0]:.2f}, {cam_pos[1]:.2f}, {cam_pos[2]:.2f}]")
                print(f"  Looking: [{forward[0]:.2f}, {forward[1]:.2f}, {forward[2]:.2f}]")

        except Exception as e:
            print(f"[Monitor Error] {e}")

# Stop existing monitor if running
if _monitor_timer is not None:
    try:
        _monitor_timer.stop()
        _monitor_timer.deleteLater()
        print("Stopped previous camera monitor")
    except:
        pass

# Create new monitor
print("\n" + "="*80)
print("CAMERA MONITOR - Starting...")
print("="*80)
print("Now rotate/pan/zoom the Maya viewport")
print("You should see camera updates printed below")
print("Run this script again to stop monitoring")
print("="*80 + "\n")

monitor = CameraMonitor()
_monitor_timer = QtCore.QTimer()
_monitor_timer.timeout.connect(monitor.check_camera)
_monitor_timer.start(100)  # Check every 100ms

print("[Monitor] Running... (checking every 100ms)")
