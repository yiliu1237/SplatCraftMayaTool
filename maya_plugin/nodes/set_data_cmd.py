"""
Maya command to set Gaussian data on a SplatCraft node
This bypasses the registry issues
"""

import maya.api.OpenMaya as om
import numpy as np


def maya_useNewAPI():
    """Tell Maya to use API 2.0"""
    pass


class SetSplatDataCmd(om.MPxCommand):
    """
    Command to set Gaussian data on a SplatCraft node
    Usage: setSplatData -node "nodeName" -positions <array> -colors <array> ...
    """

    kPluginCmdName = "setSplatData"

    def __init__(self):
        om.MPxCommand.__init__(self)
        self.node_name = None
        self.gaussian_data = None

    @staticmethod
    def creator():
        return SetSplatDataCmd()

    @staticmethod
    def newSyntax():
        syntax = om.MSyntax()
        syntax.addFlag("-n", "-node", om.MSyntax.kString)
        return syntax

    def doIt(self, args):
        """Execute the command"""
        # This will be called from Python with the data
        # For now, just use the global _NODE_DATA as before
        pass


def initializePlugin(plugin):
    """Initialize the command plugin"""
    plugin_fn = om.MFnPlugin(plugin)
    try:
        plugin_fn.registerCommand(
            SetSplatDataCmd.kPluginCmdName,
            SetSplatDataCmd.creator,
            SetSplatDataCmd.newSyntax
        )
    except:
        om.MGlobal.displayError(f"Failed to register command: {SetSplatDataCmd.kPluginCmdName}")


def uninitializePlugin(plugin):
    """Uninitialize the command plugin"""
    plugin_fn = om.MFnPlugin(plugin)
    try:
        plugin_fn.deregisterCommand(SetSplatDataCmd.kPluginCmdName)
    except:
        om.MGlobal.displayError(f"Failed to deregister command: {SetSplatDataCmd.kPluginCmdName}")
