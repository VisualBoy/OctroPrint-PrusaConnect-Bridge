# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import logging # Import the logging module
import re # Import the regular expression module

class PrusaConnectBridgePlugin(octoprint.plugin.SettingsPlugin,
                             octoprint.plugin.AssetPlugin,
                             octoprint.plugin.TemplatePlugin):

    def __init__(self):
        # Initialize the logger
        self._logger = logging.getLogger("octoprint.plugins.PrusaConnectBridge")
        self._logger.info("PrusaConnectBridgePlugin: Initializing...")
        self.active_rules = [] # Initialize active_rules
        self.last_matched_rule_pattern = None # Initialize last matched rule pattern

    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return dict(
            rules=[]  # Default empty list for rules
        )

    def on_settings_initialized(self):
        self._logger.info("PrusaConnectBridgePlugin: Settings initialized.")
        self.active_rules = self._settings.get(["rules"])
        if self.active_rules is None:
            self.active_rules = []
        self._logger.info(f"PrusaConnectBridgePlugin: Loaded {len(self.active_rules)} rules.")

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.active_rules = self._settings.get(["rules"])
        if self.active_rules is None:
            self.active_rules = []
        self._logger.info(f"PrusaConnectBridgePlugin: Settings saved, {len(self.active_rules)} rules reloaded.")


    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return dict(
            js=["js/prusaconnectbridge.js"],
            css=["css/prusaconnectbridge.css"],
            less=["less/prusaconnectbridge.less"]
        )

    ##~~ G-code queuing hook
    def hook_gcode_queuing(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        if not gcode:  # Check if gcode is None or empty
            return cmd

        # self._logger.info(f"PrusaConnectBridgePlugin: Processing G-code: {cmd}") # DEBUG

        for rule in self.active_rules:
            if not rule.get("enabled"):
                continue

            pattern_str = rule.get("pattern")
            if not pattern_str:
                continue

            try:
                regex = re.compile(pattern_str)
                match = regex.search(gcode)

                if match:
                    self._logger.info(f"PrusaConnectBridgePlugin: Rule '{pattern_str}' matched G-code: {gcode}")
                    action_type = rule.get("actionType", "").lower()
                    action_gcode_str = rule.get("actionGcode", "")

                    # Split action_gcode_str into individual commands, filtering out empty lines
                    action_gcode_lines = [line for line in action_gcode_str.splitlines() if line.strip()]

                    self._logger.info(f"PrusaConnectBridgePlugin: Action '{action_type}' with G-code(s): {action_gcode_lines}")

                    # Store the pattern of the matched rule
                    self.last_matched_rule_pattern = pattern_str

                    if action_type == "skip" or action_type == "skip/suppress":
                        self._logger.info(f"PrusaConnectBridgePlugin: Suppressing G-code: {gcode}")
                        return None  # Suppress the command

                    elif action_type == "inject_before":
                        commands_to_send = action_gcode_lines + [cmd]
                        self._logger.info(f"PrusaConnectBridgePlugin: Injecting before, sending: {commands_to_send}")
                        return commands_to_send

                    elif action_type == "inject_after":
                        commands_to_send = [cmd] + action_gcode_lines
                        self._logger.info(f"PrusaConnectBridgePlugin: Injecting after, sending: {commands_to_send}")
                        return commands_to_send

                    elif action_type == "replace" or action_type == "modify": # Modify treated as Replace for now
                        if not action_gcode_lines: # If action G-code is empty, effectively skip
                            self._logger.info(f"PrusaConnectBridgePlugin: Replacing with empty, effectively suppressing G-code: {gcode}")
                            return None
                        self._logger.info(f"PrusaConnectBridgePlugin: Replacing G-code '{gcode}' with: {action_gcode_lines}")
                        return action_gcode_lines

                    else:
                        self._logger.warning(f"PrusaConnectBridgePlugin: Unknown action type '{action_type}' for rule '{pattern_str}'. Passing original command.")
                        # Even if action is unknown, a rule matched. Storing its pattern.
                        # self.last_matched_rule_pattern is already set above.
                        return cmd

                    # If a rule matched and an action was taken (or attempted), stop processing further rules for this G-code line.
                    # The return statements above handle this for specific actions.
                    # If an unknown action type occurs, we fall through and return original cmd, but ideally, we should break here too.
                    # However, since all known actions return, this break is implicitly handled for them.
                    # break # This break is now effectively handled by returns in each action block

            except re.error as e:
                self._logger.error(f"PrusaConnectBridgePlugin: Invalid regex pattern '{pattern_str}': {e}")
            except Exception as e_gen:
                self._logger.error(f"PrusaConnectBridgePlugin: Error processing rule '{pattern_str}' for G-code '{gcode}': {e_gen}")

        return cmd # Return the original command if no rules matched or no action taken


    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return dict(
            PrusaConnectBridge=dict(
                displayName="PrusaConnect Bridge", # Updated display name
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="VisualBoy", # Update with your GitHub username
                repo="OctoPrint-PrusaConnect-Bridge",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/VisualBoy/OctoPrint-PrusaConnect-Bridge/archive/{target_version}.zip"
            )
        )

# Plugin registration
__plugin_name__ = "PrusaConnect-Bridge"
__plugin_version__ = "0.1.0"
__plugin_description__ = "OctoPrint plugin bridge to Prusa Connect (unofficial)."
__plugin_pythoncompat__ = ">=3,<4" # Python 3 compatibility


def __plugin_load__():
    global __plugin_implementation__
    plugin = PrusaConnectBridgePlugin()
    __plugin_implementation__ = plugin

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.hook_gcode_queuing,
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.plugin.settings.initialized": __plugin_implementation__.on_settings_initialized # Add this hook
    }
