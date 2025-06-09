# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import logging # Import the logging module
import re # Import the regular expression module
from prusa.connect.printer import Printer, const
import threading
import uuid
import hashlib
import time
import os
import flask # Added for API command response
# Ensure threading is imported if not already (it was from previous steps)
# import threading
from octoprint.util import RepeatedTimer
### from prusa.connect.printer.filesystem import FileSystemNode, NodeType  # SDK <= 0.7.0
# octoprint.plugin required for SettingsPlugin.on_settings_save
import octoprint.plugin
from octoprint.plugin import WizardPlugin # Import WizardPlugin
from octoprint.events import Events # Added for EventHandlerPlugin


class PrusaConnectBridgePlugin(octoprint.plugin.SettingsPlugin,
                             octoprint.plugin.AssetPlugin,
                             octoprint.plugin.TemplatePlugin,
                             octoprint.plugin.StartupPlugin,
                             octoprint.plugin.SimpleApiPlugin,
                             octoprint.plugin.EventHandlerPlugin, # Added EventHandlerPlugin
                             WizardPlugin): # Add WizardPlugin

    def __init__(self):
        # Initialize the logger
        self._logger = logging.getLogger("octoprint.plugins.PrusaConnectBridge")
        self._logger.info("PrusaConnectBridgePlugin: Initializing...")
        self.prusa_printer = None
        # self.prusa_printer_thread = None # Unused, sdk_thread is used
        self.sdk_thread = None
        self.prusa_server = "https://connect.prusa3d.com" # Default, will be overridden by settings
        self.token_retrieval_timer = None
        self.temp_code_displayed = False
        self.telemetry_timer = None
        self.last_status_sent_to_ui = ""
        self._registration_error_message = None # For wizard error reporting
        self._logger.info("PrusaConnectBridgePlugin initialized.")


    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return dict(
            prusa_connect_sn=None,
            prusa_connect_fingerprint=None,
            prusa_connect_token=None,
            prusa_connect_tmp_code=None,
            prusa_server_url="https://connect.prusa3d.com", # Added
            prusa_connect_manual_sn=None # Add this line
        )

    def on_settings_initialized(self):
        self._logger.info("PrusaConnectBridgePlugin: Settings initialized.")

        self.prusa_server = self._settings.get(["prusa_server_url"]) # Load server URL
        self.last_status_sent_to_ui = "" # Initialize for status pushing
        # Initial status update can be triggered from on_after_startup or get_template_vars
        # self._get_prusa_connect_status() # Initial status check and push


    def on_settings_save(self, data):
        self._logger.info("PrusaConnectBridgePlugin: on_settings_save called.")
        old_server_url = self._settings.get(["prusa_server_url"])
        old_active_sn = self._settings.get(["prusa_connect_sn"]) # Used for registration

        # Important: Let OctoPrint save the settings from 'data' first.
        # This will update prusa_connect_manual_sn and prusa_server_url if they were changed in UI.
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

        # Retrieve the potentially new server URL
        self.prusa_server = self._settings.get(["prusa_server_url"])

        needs_sdk_reinitialization = False
        force_reregistration = False # Implies clearing token and tmp_code

        # Check if server URL changed
        if old_server_url != self.prusa_server:
            self._logger.info(f"Prusa Connect server URL changed. Old: '{old_server_url}', New: '{self.prusa_server}'.")
            needs_sdk_reinitialization = True
            force_reregistration = True # Server change always forces re-registration

        # Now, run _initialize_identifiers(). This will:
        # 1. Consider the new prusa_connect_manual_sn (just saved by OctoPrint).
        # 2. Determine the new active prusa_connect_sn and prusa_connect_fingerprint.
        # 3. Save these new active identifiers to settings.
        new_active_sn, new_fingerprint = self._initialize_identifiers() # This method calls self._settings.save()

        # Check if the active SN changed
        if old_active_sn != new_active_sn:
            self._logger.info(f"Active Serial Number changed. Old: '{old_active_sn}', New: '{new_active_sn}'.")
            needs_sdk_reinitialization = True
            if self._settings.get(["prusa_connect_token"]): # If already registered
                self._logger.warning("SN changed while registered. This requires re-registration with Prusa Connect.")
                force_reregistration = True

        if force_reregistration:
            self._logger.info("Forcing re-registration: Clearing Prusa Connect token and temporary code.")
            self._settings.set(["prusa_connect_token"], None)
            self._settings.set(["prusa_connect_tmp_code"], None)
            self._settings.save() # Persist cleared token/tmp_code immediately

        if needs_sdk_reinitialization:
            self._logger.info("SDK needs re-initialization due to settings changes.")

            if force_reregistration:
                # Stop timers if we are about to clear everything for re-registration
                if self.token_retrieval_timer and self.token_retrieval_timer.is_alive():
                    self.token_retrieval_timer.cancel()
                    self.token_retrieval_timer = None
                    self._logger.info("Token retrieval timer cancelled for SDK re-initialization.")
                if self.telemetry_timer and self.telemetry_timer.is_alive():
                    self.telemetry_timer.cancel()
                    self.telemetry_timer = None
                    self._logger.info("Telemetry timer cancelled for SDK re-initialization.")

            try:
                # Get the final SN and Fingerprint that _initialize_identifiers decided upon and saved
                final_sn_for_sdk = self._settings.get(["prusa_connect_sn"])
                final_fp_for_sdk = self._settings.get(["prusa_connect_fingerprint"])

                if not final_sn_for_sdk or not final_fp_for_sdk:
                    self._logger.error("Cannot re-initialize SDK: SN or Fingerprint is missing after _initialize_identifiers.")
                    raise ValueError("SN or Fingerprint missing, cannot create Printer object.")

                self._logger.info(f"Re-creating Prusa SDK Printer object with SN: {final_sn_for_sdk}, FP: {final_fp_for_sdk[:10]}...")
                self.prusa_printer = Printer(fingerprint=final_fp_for_sdk, sn=final_sn_for_sdk)
                self._logger.info("New Prusa SDK Printer object created.")

                current_token_for_sdk = self._settings.get(["prusa_connect_token"]) # Might be None if force_reregistration
                self.prusa_printer.set_connection(server_url=self.prusa_server, token=current_token_for_sdk)
                self._logger.info(f"SDK connection re-configured. Server: {self.prusa_server}, Token: {'Set' if current_token_for_sdk else 'None'}.")

                self._register_sdk_handlers() # Re-register command handlers for the new printer object

                # SDK Thread Management
                if self.sdk_thread and self.sdk_thread.is_alive():
                    self._logger.info("Previous SDK thread is alive. A new one will be started. The old one should exit as it's a daemon.")
                    # Old thread will eventually terminate as its prusa_printer object is no longer referenced here.

                self._logger.info("Starting new SDK loop thread after settings save.")
                self.sdk_thread = threading.Thread(target=self.prusa_printer.loop, daemon=True, name="PrusaConnectSDKLoop-SettingsSave")
                self.sdk_thread.start()
                self._logger.info("New SDK loop thread started.")

                if force_reregistration:
                    self._logger.info("Re-registration is now required. User may need to use Wizard or 'Clear & Re-register' button if not guided automatically.")
                    # Future: could call self._initiate_registration() if not in wizard context and no token.
                    # For now, rely on wizard or manual action if token was cleared.
                    # Or, if no token, perhaps _initiate_registration could be called here to be more proactive.
                    # Let's check if a token exists. If not, and we forced re-registration, it means we need one.
                    if not current_token_for_sdk:
                        self._logger.info("No token present after forced re-registration, initiating registration process.")
                        self._initiate_registration()


            except Exception as e:
                self._logger.error(f"Error during SDK re-initialization: {e}", exc_info=True)
                self._registration_error_message = f"Failed to re-initialize Prusa Connect SDK: {e}. Check logs."
                # If SDK init fails, it's safer to clear the printer object
                self.prusa_printer = None
                if self.telemetry_timer and self.telemetry_timer.is_alive(): self.telemetry_timer.cancel()


        # Always update the status display
        self._get_prusa_connect_status()

    ##~~ StartupPlugin mixin
    def _initialize_identifiers(self):
        self._logger.info("Attempting to initialize Prusa Connect identifiers (SN and Fingerprint)...")
        try:
            manual_sn = self._settings.get(["prusa_connect_manual_sn"])
            sn = None

            if manual_sn: # Check if manual_sn is not None and not empty
                sn = manual_sn
                self._logger.info(f"Using manual SN from settings: {sn}")
            else:
                sn = self._settings.get(["prusa_connect_sn"])
                if not sn: # Check if sn is None or empty (it will be None if not set)
                    self._logger.info("SN not found in settings or manual SN not provided, attempting to generate a new one.")
                    if hasattr(self._printer, 'get_firmware_uuid') and self._printer.get_firmware_uuid():
                        sn = self._printer.get_firmware_uuid()
                        self._logger.info(f"Using firmware UUID as SN: {sn}")
                    else:
                        sn = str(uuid.uuid4())
                        self._logger.info(f"Generated new UUID as SN: {sn}")
                else:
                    self._logger.info(f"Using existing SN from settings: {sn}")

            # Save the determined SN back to prusa_connect_sn for consistency
            self._settings.set(["prusa_connect_sn"], sn)

            fingerprint = self._settings.get(["prusa_connect_fingerprint"])
            calculated_fingerprint = hashlib.sha256(sn.encode('utf-8')).hexdigest()

            if fingerprint != calculated_fingerprint:
                self._logger.info(f"Fingerprint mismatch or not set. Current: '{fingerprint}', Calculated: '{calculated_fingerprint}'. Updating fingerprint.")
                self._settings.set(["prusa_connect_fingerprint"], calculated_fingerprint)
                fingerprint = calculated_fingerprint

            self._settings.save() # Persist any changes to SN or fingerprint

            self._logger.info(f"Identifiers initialized. SN: {sn}, Fingerprint: {fingerprint[:10]}...")
            return sn, fingerprint
        except Exception as e:
            self._logger.error(f"Error initializing identifiers: {e}", exc_info=True)
            # Fallback to temporary identifiers if generation failed, to allow SDK to potentially start
            # though registration will likely fail or be improper.
            fallback_sn = str(uuid.uuid4())
            fallback_fingerprint = hashlib.sha256(fallback_sn.encode('utf-8')).hexdigest()
            self._logger.warning(f"Using fallback SN: {fallback_sn} and Fingerprint: {fallback_fingerprint[:10]}... due to error.")
            return fallback_sn, fallback_fingerprint


    def on_after_startup(self):
        self._logger.info("PrusaConnectBridgePlugin: on_after_startup initiated.")

        sn, fingerprint = self._initialize_identifiers()

        try:
            self.prusa_printer = Printer(fingerprint=fingerprint, sn=sn)
            self._logger.info(f"Prusa SDK Printer object created. SN: {sn}, Fingerprint: {fingerprint[:10]}...")
        except Exception as e:
            self._logger.error(f"Failed to initialize Prusa SDK Printer object: {e}", exc_info=True)
            self.last_status_sent_to_ui = ""
            self._get_prusa_connect_status()
            self._logger.info("PrusaConnectBridgePlugin on_after_startup finished due to critical SDK error.")
            return

        # Register command handlers
        self._register_sdk_handlers()

        # The actual connection (with server and token) is set conditionally below or during registration.

        token = self._settings.get(["prusa_connect_token"])

        if token:
            self._logger.info("Token found in settings, attempting to connect to Prusa Connect.")
            try:
                self.prusa_printer.set_connection(server_url=self.prusa_server, token=token)
                self._logger.info(f"SDK connection configured with server URL: {self.prusa_server} and existing token: {token[:4]}...{token[-4:]}")
            except Exception as e:
                self._logger.error(f"Error setting SDK connection with existing token: {e}", exc_info=True)

            if not self.sdk_thread or not self.sdk_thread.is_alive():
                self._logger.info("Starting SDK loop thread with existing token.")
                self.sdk_thread = threading.Thread(target=self.prusa_printer.loop, daemon=True, name="PrusaConnectSDKLoop")
                self.sdk_thread.start()
                self._logger.info("SDK loop started with existing token.")
            else:
                self._logger.info("SDK loop thread already running.")
            self._start_telemetry_timer()
        else:
            self._logger.info("No token found in settings. Registration will be handled by the wizard if required.")
            # Ensure SDK loop is running, as printer.register() might need it.
            if not self.sdk_thread or not self.sdk_thread.is_alive():
                self._logger.info("Starting SDK loop thread (no token, for potential wizard registration).")
                self.sdk_thread = threading.Thread(target=self.prusa_printer.loop, daemon=True, name="PrusaConnectSDKLoop-PreToken")
                self.sdk_thread.start()
                self._logger.info("SDK loop thread started for potential wizard-led registration.")
            else:
                self._logger.info("SDK loop thread already running (no token). Wizard will handle registration if needed.")
            # DO NOT call _initiate_registration() here. It will be called by the wizard.
        self._logger.info("PrusaConnectBridgePlugin on_after_startup complete.")

    def _register_sdk_handlers(self):
        if not self.prusa_printer:
            self._logger.error("Cannot register SDK handlers: prusa_printer object is not initialized.", exc_info=True)
            return

        self._logger.info("Registering Prusa Connect SDK command handlers...")
        try:
            @self.prusa_printer.handler(const.Command.START_PRINT)
            def decorated_handle_start_print(args):
                self._logger.info(f"Prusa Connect Command (Decorated): START_PRINT with args: {args}")
                filename = None
                if isinstance(args, list) and len(args) > 0:
                    filename = args[0]
                elif isinstance(args, str):
                    filename = args

                if not filename or not isinstance(filename, str):
                    self._logger.error("START_PRINT: Filename not provided or invalid.")
                    self.prusa_printer.event_cb(const.Event.COMMAND_REJECTED, const.Source.PLUGIN, command=const.Command.START_PRINT, reason="Missing filename")
                    return {"source": const.Source.PLUGIN, "error": "Missing filename"}

                try:
                    if not self._file_manager.file_exists("local", filename):
                        self._logger.error(f"START_PRINT: File '{filename}' not found in local storage via file_manager.")
                        self.prusa_printer.event_cb(const.Event.COMMAND_REJECTED, const.Source.PLUGIN, command=const.Command.START_PRINT, reason=f"File '{filename}' not found")
                        return {"source": const.Source.PLUGIN, "error": f"File '{filename}' not found"}

                    path_to_file = self._file_manager.path_on_disk("local", filename)
                    if not path_to_file:
                        self._logger.error(f"START_PRINT: Could not get disk path for supposedly existing file '{filename}'.")
                        # This case should ideally be caught by file_exists, but as a fallback:
                        self.prusa_printer.event_cb(const.Event.COMMAND_REJECTED, const.Source.PLUGIN, command=const.Command.START_PRINT, reason=f"Could not get disk path for {filename}")
                        return {"source": const.Source.PLUGIN, "error": f"Could not get disk path for {filename}"}

                    self._logger.info(f"Attempting to select and print file: {path_to_file}")
                    self._printer.select_file(path_to_file, printAfterSelect=True)
                    self.prusa_printer.set_state(const.State.PRINTING)
                    self._logger.info(f"Successfully initiated print for {filename}")
                    return {"source": const.Source.PLUGIN}
                except Exception as e:
                    self._logger.error(f"Error handling START_PRINT for {filename}: {e}", exc_info=True)
                    self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, const.Source.PLUGIN, command=const.Command.START_PRINT, reason=str(e))
                    return {"source": const.Source.PLUGIN, "error": str(e)}

            @self.prusa_printer.handler(const.Command.STOP_PRINT)
            def decorated_handle_stop_print(args=None):
                self._logger.info(f"Prusa Connect Command (Decorated): STOP_PRINT. Args: {args}")
                try:
                    self._printer.cancel_print()
                    self.prusa_printer.set_state(const.State.READY)
                    self._logger.info("Print cancelled successfully via Prusa Connect command (Decorated).")
                    return {"source": const.Source.PLUGIN}
                except Exception as e:
                    self._logger.error(f"Error handling STOP_PRINT (Decorated): {e}", exc_info=True)
                    self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, const.Source.PLUGIN, command=const.Command.STOP_PRINT, reason=str(e))
                    return {"source": const.Source.PLUGIN, "error": str(e)}

            @self.prusa_printer.handler(const.Command.PAUSE_PRINT)
            def decorated_handle_pause_print(args=None):
                self._logger.info(f"Prusa Connect Command (Decorated): PAUSE_PRINT. Args: {args}")
                try:
                    if self._printer.is_printing() and not self._printer.is_paused():
                        self._printer.pause_print()
                        self.prusa_printer.set_state(const.State.PAUSED)
                        self._logger.info("Print paused successfully via Prusa Connect command (Decorated).")
                    elif self._printer.is_paused():
                        self._logger.info("Print is already paused. No action taken (Decorated).")
                    else:
                        self._logger.warning("Cannot pause: Printer is not currently printing (Decorated).")
                        self.prusa_printer.event_cb(const.Event.COMMAND_REJECTED, const.Source.PLUGIN, command=const.Command.PAUSE_PRINT, reason="Not printing")
                        return {"source": const.Source.PLUGIN, "error": "Not printing"}
                    return {"source": const.Source.PLUGIN}
                except Exception as e:
                    self._logger.error(f"Error handling PAUSE_PRINT (Decorated): {e}", exc_info=True)
                    self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, const.Source.PLUGIN, command=const.Command.PAUSE_PRINT, reason=str(e))
                    return {"source": const.Source.PLUGIN, "error": str(e)}

            @self.prusa_printer.handler(const.Command.RESUME_PRINT)
            def decorated_handle_resume_print(args=None):
                self._logger.info(f"Prusa Connect Command (Decorated): RESUME_PRINT. Args: {args}")
                try:
                    if self._printer.is_paused():
                        self._printer.resume_print()
                        self.prusa_printer.set_state(const.State.PRINTING)
                        self._logger.info("Print resumed successfully via Prusa Connect command (Decorated).")
                    else:
                        self._logger.warning("Cannot resume: Printer is not currently paused (Decorated).")
                        self.prusa_printer.event_cb(const.Event.COMMAND_REJECTED, const.Source.PLUGIN, command=const.Command.RESUME_PRINT, reason="Not paused")
                        return {"source": const.Source.PLUGIN, "error": "Not paused"}
                    return {"source": const.Source.PLUGIN}
                except Exception as e:
                    self._logger.error(f"Error handling RESUME_PRINT (Decorated): {e}", exc_info=True)
                    self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, const.Source.PLUGIN, command=const.Command.RESUME_PRINT, reason=str(e))
                    return {"source": const.Source.PLUGIN, "error": str(e)}

            @self.prusa_printer.handler(const.Command.SEND_INFO)
            def decorated_handle_send_info(args=None):
                self._logger.info(f"Prusa Connect Command (Decorated): SEND_INFO. Args: {args}")
                try:
                    if not self.prusa_printer or not self.prusa_printer.fs:
                        self._logger.error("Filesystem object (self.prusa_printer.fs) not available (Decorated).")
                        # No specific event_cb for this internal check, but fail the command.
                        # The SDK might retry or handle this. For now, return error.
                        return {"source": const.Source.PLUGIN, "error": "Filesystem not initialized"}

                    octoprint_files_data = self._file_manager.list_files(recursive=True, locations=['local'])

                    # Initialize self.prusa_printer.fs.root as a dictionary
                    self.prusa_printer.fs.root = {
                        'name': '/',
                        'path': '/',
                        'type': 'DIR',
                        'children': [],
                        'size': 0,
                        'm_timestamp': int(time.time())
                    }
                    # Clearing children:
                    # self.prusa_printer.fs.root['children'].clear() # This is already done by re-assigning above essentially

                    def build_fs_tree(octo_files_dict, parent_node_dict):
                        for name, item_data in octo_files_dict.items():
                            node_type_str = None
                            if item_data["type"] == "folder":
                                node_type_str = 'DIR'
                            elif item_data["type"] == "machinecode":
                                node_type_str = 'FILE'
                            else:
                                self._logger.debug(f"Skipping item '{name}' of type '{item_data['type']}' (Decorated)")
                                continue

                            node_path = os.path.join(parent_node_dict['path'], name).lstrip("/")
                            if parent_node_dict['path'] == "/":
                                node_path = name

                            node_dict = {
                                'name': name,
                                'path': node_path,
                                'type': node_type_str,
                                'size': item_data.get("size", 0) if node_type_str == 'FILE' else 0,
                                'm_timestamp': int(item_data.get("date", time.time())),
                            }
                            if node_type_str == 'DIR':
                                node_dict['children'] = []

                            if node_type_str == 'FILE' and item_data.get("gcodeAnalysis"):
                                estimated_print_time = item_data["gcodeAnalysis"].get("estimatedPrintTime")
                                if estimated_print_time:
                                    node_dict['print_time'] = int(estimated_print_time)

                            parent_node_dict['children'].append(node_dict)

                            if node_type_str == 'DIR' and "children" in item_data:
                                build_fs_tree(item_data.get("children", {}), node_dict)

                    if self.prusa_printer and self.prusa_printer.fs and self.prusa_printer.fs.root:
                        # Ensure root children are clear before building, self.prusa_printer.fs.root is now a dict
                        self.prusa_printer.fs.root['children'].clear()
                        build_fs_tree(octoprint_files_data.get('local', {}), self.prusa_printer.fs.root)
                    else:
                        self._logger.error("Prusa printer FS root (dict) not available for population (Decorated).")
                        return {"source": const.Source.PLUGIN, "error": "FS root not available for population"}

                    try:
                        actual_uploads_path = self._file_manager.get_basedir("local")
                        if actual_uploads_path and os.path.exists(actual_uploads_path):
                            stat = os.statvfs(actual_uploads_path)
                            self.prusa_printer.fs.fs_free_space = stat.f_bavail * stat.f_frsize
                            self.prusa_printer.fs.fs_total_space = stat.f_blocks * stat.f_frsize
                            self._logger.info(f"Disk space for '{actual_uploads_path}': Free: {self.prusa_printer.fs.fs_free_space}, Total: {self.prusa_printer.fs.fs_total_space} (Decorated)")
                        else:
                            self._logger.warning(f"Could not determine valid uploads path ('{actual_uploads_path}') for disk space calculation (Decorated). Using defaults (0).")
                            self.prusa_printer.fs.fs_free_space = 0
                            self.prusa_printer.fs.fs_total_space = 0
                    except Exception as e_stat:
                        self._logger.error(f"Error calculating disk space for path '{actual_uploads_path}': {e_stat} (Decorated)", exc_info=True)
                        self.prusa_printer.fs.fs_free_space = 0
                        self.prusa_printer.fs.fs_total_space = 0

                    self._logger.info("File system information updated for Prusa Connect based on SEND_INFO (Decorated).")
                    return {"message": "File system info processed", "source": const.Source.PLUGIN}
                except Exception as e:
                    self._logger.error(f"Error handling SEND_INFO (Decorated): {e}", exc_info=True)
                    self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, const.Source.PLUGIN, command=const.Command.SEND_INFO, reason=str(e))
                    return {"source": const.Source.PLUGIN, "error": str(e)}

            self._logger.info("Successfully registered Prusa Connect SDK command handlers (Decorated).")
        except Exception as e:
            self._logger.error(f"Error registering SDK command handlers (Decorated): {e}", exc_info=True)

    # The old _handle_... methods are now removed as their logic is inside _register_sdk_handlers.

    def _initiate_registration(self):
        if not self.prusa_printer or not self.prusa_printer.token_set:
            self._logger.info("Cannot start telemetry timer: Prusa printer not ready or token not set.")
            return

        if self.telemetry_timer is not None:
            self.telemetry_timer.cancel()
            self.telemetry_timer = None
            self._logger.info("Cancelled existing telemetry timer.")

        self.telemetry_timer = RepeatedTimer(
            1.0,  # Interval in seconds
            self._send_telemetry,
            run_first=False, # Do not run immediately, wait for the first interval
            daemon=True
        )
        self.telemetry_timer.start()
        self._logger.info("Started telemetry transmission (1s interval).")

    def _send_telemetry(self):
        if not self.prusa_printer or not self.prusa_printer.token_set:
            # This check is important because the timer might fire before token is set,
            # or if connection is somehow lost.
            # self._logger.debug("Prusa printer not ready or token not set. Skipping telemetry.")
            return

        try:
            printer_data = self._printer.get_current_data()
            temperature_data = self._printer.get_current_temperatures()

            # State Mapping
            octo_state = printer_data["state"]["flags"]
            prusa_state = const.State.READY  # Default

            if octo_state["printing"]:
                prusa_state = const.State.PRINTING
            elif octo_state["paused"]:
                prusa_state = const.State.PAUSED
            elif octo_state["error"] or octo_state["closedOrError"]:
                prusa_state = const.State.ERROR
            elif not octo_state["operational"]:
                prusa_state = const.State.ATTENTION
            elif octo_state["ready"]:
                 prusa_state = const.State.READY
            # Add other states if necessary, e.g., FINISHING based on OctoPrint events later.

            # Temperature Data
            # Ensure tool0 exists, otherwise default to 0.0
            nozzle_actual = temperature_data.get("tool0", {}).get("actual") if temperature_data.get("tool0") else 0.0
            nozzle_target = temperature_data.get("tool0", {}).get("target") if temperature_data.get("tool0") else 0.0
            # Ensure bed exists, otherwise default to 0.0
            bed_actual = temperature_data.get("bed", {}).get("actual") if temperature_data.get("bed") else 0.0
            bed_target = temperature_data.get("bed", {}).get("target") if temperature_data.get("bed") else 0.0

            # Ensure values are float, default to 0.0 if None
            nozzle_actual = float(nozzle_actual) if nozzle_actual is not None else 0.0
            nozzle_target = float(nozzle_target) if nozzle_target is not None else 0.0
            bed_actual = float(bed_actual) if bed_actual is not None else 0.0
            bed_target = float(bed_target) if bed_target is not None else 0.0


            # Print Progress and File
            progress = None
            filename = None
            if prusa_state == const.State.PRINTING or prusa_state == const.State.PAUSED:
                if printer_data.get("progress") and printer_data["progress"].get("completion") is not None:
                    progress = round(printer_data["progress"]["completion"])  # SDK expects int 0-100
                if printer_data.get("job") and printer_data["job"].get("file") and printer_data["job"]["file"].get("name"):
                    filename = printer_data["job"]["file"]["name"]

            # self._logger.debug(
            #     f"Sending telemetry: State: {prusa_state}, Nozzle: {nozzle_actual}°C (T: {nozzle_target}°C), "
            #     f"Bed: {bed_actual}°C (T: {bed_target}°C), Progress: {progress}%, File: {filename}"
            # )

            self.prusa_printer.telemetry(
                state=prusa_state,
                temp_nozzle=nozzle_actual,
                target_nozzle=nozzle_target,
                temp_bed=bed_actual,
                target_bed=bed_target,
                progress=progress,
                print_file=filename
                # TODO: Consider adding material and time_est if easily available from OctoPrint
            )

        except Exception as e:
            self._logger.error(f"Error sending telemetry: {e}", exc_info=True)


    ##~~ TemplatePlugin mixin
    def get_template_configs(self):
        return [
            dict(type="settings", template="prusaconnectbridge_settings.jinja2", custom_bindings=False),
            dict(type="wizard", name="prusaconnectbridge", template="prusaconnectbridge_wizard.jinja2", custom_bindings=True)
        ]

    def get_template_vars(self):
        current_status_text = self._get_prusa_connect_status() # Ensures status is evaluated and pushed
        return dict(
            prusa_connect_sn=self._settings.get(["prusa_connect_sn"]),
            prusa_connect_manual_sn=self._settings.get(["prusa_connect_manual_sn"]),
            prusa_connect_fingerprint=self._settings.get(["prusa_connect_fingerprint"]),
            prusa_connect_status_text=current_status_text,
            prusa_server_url=self._settings.get(["prusa_server_url"])
        )

    def _get_prusa_connect_status(self):
        token = self._settings.get(["prusa_connect_token"])
        tmp_code = self._settings.get(["prusa_connect_tmp_code"])
        sn = self._settings.get(["prusa_connect_sn"])
        status = "Status Unknown. Please check logs." # Default
        is_token_available = False
        tmp_code_to_send = None
        token_display_partial_val = None

        if self.prusa_printer and self.prusa_printer.token_set and token:
            status_token_display = f"{token[:4]}...{token[-4:]}" if token and len(token) > 8 else "Set"
            status = f"Registered (Token: {status_token_display})"
            is_token_available = True
            if len(token) > 8:
                token_display_partial_val = f"{token[:4]}...{token[-4:]}"
            elif token:
                token_display_partial_val = "Token Set (Short)"
            else:
                token_display_partial_val = "Token Set"
            # If we are registered, there should be no persistent registration error message.
            # self._registration_error_message = None # Cleared in _token_retrieved_successfully

        elif tmp_code and self.token_retrieval_timer and self.token_retrieval_timer.is_alive() and not self._registration_error_message:
            status = f"Awaiting code entry on Prusa Connect: {tmp_code}"
            tmp_code_to_send = tmp_code
        elif tmp_code and not self._registration_error_message: # tmp_code exists, timer might not be active (e.g. restart)
             status = f"Has temporary code {tmp_code}. Registration process may be paused or will resume/restart."
             tmp_code_to_send = tmp_code
        elif self._registration_error_message:
            status = "Registration Error" # General status text for error
            tmp_code_to_send = tmp_code # Still send tmp_code if we have one
            # The specific error is in self._registration_error_message
        elif not token and self.prusa_printer and hasattr(self.prusa_printer, 'tmp_code') and self.prusa_printer.tmp_code and self.sdk_thread and self.sdk_thread.is_alive():
             status = f"Not Registered. SDK active. Temp code from SDK: {self.prusa_printer.tmp_code}. Waiting for user entry."
             tmp_code_to_send = self.prusa_printer.tmp_code
        elif not token and self.sdk_thread and self.sdk_thread.is_alive():
            status = "Not Registered. SDK is active. Wizard will guide registration if needed."
        elif not token:
             status = "Not Registered. SDK may not be active or initialized. Wizard will guide registration if needed."


        current_message_content = dict(
            status_text=status,
            prusa_connect_sn=sn if sn else "Not set",
            tmp_code=tmp_code_to_send,
            token_available=is_token_available,
            token_display_partial=token_display_partial_val,
            registration_error_message=self._registration_error_message # Add the error message
        )

        # Push status updates to UI via plugin message if it has changed.
        # Add self._registration_error_message to the tuple for change detection.
        simplified_current_status_tuple = (status, tmp_code_to_send, is_token_available, token_display_partial_val, self._registration_error_message)
        simplified_last_status_tuple = getattr(self, "_last_simplified_status_pushed", None)

        if simplified_last_status_tuple != simplified_current_status_tuple:
            self._logger.debug(f"Sending PrusaConnectBridge plugin message: {current_message_content}")
            self._plugin_manager.send_plugin_message(self._identifier, current_message_content)
            self.last_status_sent_to_ui = status
            self._last_simplified_status_pushed = simplified_current_status_tuple

        return status

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return dict(
            js=["js/prusaconnectbridge.js"],
            css=["css/prusaconnectbridge.css"],
            less=["less/prusaconnectbridge.less"]
        )

    ##~~ SimpleApiPlugin mixin
    def get_api_commands(self):
        return dict(
            clear_prusa_connect_settings=[]
        )

    def on_api_command(self, command, data):
        if command == "clear_prusa_connect_settings":
            self._logger.info("API command: 'clear_prusa_connect_settings' received.")

            # Stop timers
            if self.token_retrieval_timer and self.token_retrieval_timer.is_alive():
                self.token_retrieval_timer.cancel()
                self.token_retrieval_timer = None
                self._logger.info("Token retrieval timer cancelled.")
            if self.telemetry_timer and self.telemetry_timer.is_alive():
                self.telemetry_timer.cancel()
                self.telemetry_timer = None
                self._logger.info("Telemetry timer cancelled.")

            # Reset SDK printer object attributes safely
            if self.prusa_printer:
                try:
                    # Attempt to stop the SDK loop gracefully if possible
                    # This depends on SDK internals; a direct stop method is often not exposed for the loop thread.
                    # For now, we rely on daemon=True for the thread and re-creating the Printer object.
                    self._logger.info("Resetting Prusa SDK printer object attributes.")
                    self.prusa_printer.token = None
                    self.prusa_printer.tmp_code = None
                    self.prusa_printer.token_set = False
                except Exception as e_sdk_reset:
                    self._logger.error(f"Error resetting SDK printer object attributes: {e_sdk_reset}")


            # Clear settings in OctoPrint's storage
            self._settings.set(["prusa_connect_sn"], None)
            self._settings.set(["prusa_connect_fingerprint"], None)
            self._settings.set(["prusa_connect_token"], None)
            self._settings.set(["prusa_connect_tmp_code"], None)
            self._settings.set(["prusa_connect_manual_sn"], None) # Clear manual SN as well
            # Server URL is kept as it's user-configurable separately.
            self._settings.save(trigger_event=True) # Save changes and trigger event for UI updates

            self.temp_code_displayed = False
            self.last_status_sent_to_ui = ""

            self._logger.info("Prusa Connect settings cleared. Attempting to re-initialize SDK and registration.")
            msg = "Settings cleared. Re-initializing and attempting re-registration..."

            try:
                # Re-initialize identifiers (this will generate new SN if old one was cleared)
                new_sn, new_fingerprint = self._initialize_identifiers()

                # Create a new Printer object for the SDK
                self.prusa_printer = Printer(fingerprint=new_fingerprint, sn=new_sn)
                self._logger.info(f"New Prusa SDK Printer object created. SN: {new_sn}, Fingerprint: {new_fingerprint}")

                # Re-register handlers for the new printer object
                self._register_sdk_handlers()

                # SDK Thread Management
                # The old SDK thread, if running, is a daemon and will exit if its target (old prusa_printer.loop) finishes or errors out.
                # Starting a new thread for the new printer object.
                if self.sdk_thread and self.sdk_thread.is_alive():
                    self._logger.warning("Previous SDK thread might still be running. Starting new SDK thread for re-registration.")
                    # Ideally, we'd signal the old thread to stop, but SDK doesn't expose this easily.
                    # Rely on daemon thread nature and OctoPrint shutdown for cleanup of old threads.

                self.sdk_thread = threading.Thread(target=self.prusa_printer.loop, daemon=True, name="PrusaConnectSDKLoop-Reset")
                self.sdk_thread.start()
                self._logger.info("New SDK thread started for re-registration.")

                self._initiate_registration() # Start registration with the new printer object
                msg = "Settings cleared. Re-registration process initiated with new/regenerated identifiers."
                self._logger.info(msg)

            except Exception as e:
                self._logger.error(f"Critical error during settings clear and re-initialization: {str(e)}", exc_info=True)
                msg = f"Critical error during settings clear: {str(e)}. Check plugin logs for details. You may need to restart OctoPrint."

            self.last_status_sent_to_ui = "" # Force status update after all operations
            self._get_prusa_connect_status()
            return flask.jsonify(message=msg)
        return None

    ##~~ EventHandlerPlugin mixin
    def on_event(self, event, payload):
        # Ensure SDK object is initialized and token is set before trying to use it
        if not hasattr(self, 'prusa_printer') or not self.prusa_printer or not self.prusa_printer.token_set:
            # Only process events if SDK is initialized and token is set (i.e., registered and connected)
            return

        try:
            if event == Events.CONNECTED:
                self._logger.info("OctoPrint connected to printer. Setting Prusa Connect state to READY (if not already printing/paused).")
                current_data = self._printer.get_current_data()
                if not current_data['state']['flags']['printing'] and not current_data['state']['flags']['paused']:
                    self.prusa_printer.set_state(const.State.READY)

            elif event == Events.DISCONNECTED:
                self._logger.info("OctoPrint disconnected from printer. Reporting OFFLINE to Prusa Connect.")
                self.prusa_printer.set_state(const.State.OFFLINE)

            elif event == Events.PRINTER_STATE_CHANGED:
                new_octo_state_id = payload.get("state_id")
                self._logger.debug(f"OctoPrint PRINTER_STATE_CHANGED event: {new_octo_state_id}") # DEBUG level for frequent events
                if new_octo_state_id == "ERROR" or new_octo_state_id == "CLOSED_WITH_ERROR":
                    self._logger.warning(f"OctoPrint reported printer state: {new_octo_state_id}. Setting Prusa Connect state to ERROR.")
                    self.prusa_printer.set_state(const.State.ERROR)
                    # Optionally send a FAILED event to Prusa Connect with more details if available
                    # self.prusa_printer.event_cb(const.Event.FAILED, message=f"Printer error: {new_octo_state_id}")
                elif new_octo_state_id == "OFFLINE": # Should be covered by DISCONNECTED, but good for robustness
                    self._logger.info("OctoPrint reported printer state: OFFLINE. Setting Prusa Connect state to OFFLINE.")
                    self.prusa_printer.set_state(const.State.OFFLINE)
                # Other state changes are typically handled by the periodic telemetry update.
        except AttributeError as ae:
            # This can happen if prusa_printer is None or methods are missing (e.g. token_set before init)
            self._logger.debug(f"SDK attribute error in on_event handling OctoPrint event '{event}': {ae}. SDK might not be fully initialized or printer object changed.", exc_info=False) # Debug, as this might be normal during startup/shutdown
        except Exception as e:
            self._logger.error(f"Error processing OctoPrint event '{event}' for Prusa Connect: {e}", exc_info=True)


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
                repo="PrusaConnect-Bridge",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/VisualBoy/OctoPrint-PrusaConnect-Bridge/archive/{target_version}.zip"
            )
        )

    ##~~ WizardPlugin mixin
    def get_wizard_version(self):
        return 1 # Version of the wizard

    def is_wizard_required(self):
        self._logger.debug("PrusaConnectBridgePlugin: Checking if wizard is required.")
        token = self._settings.get(["prusa_connect_token"])
        if token is None or token == "":
            self._logger.info("PrusaConnectBridgePlugin: Wizard required because Prusa Connect token is missing.")
            return True
        else:
            self._logger.info("PrusaConnectBridgePlugin: Wizard not required, Prusa Connect token exists.")
            return False

    def on_wizard_show(self):
        self._logger.info("PrusaConnectBridgePlugin: Wizard shown.")
        # Optionally, send current status to pre-populate wizard dynamically if needed beyond get_wizard_details
        # self._get_prusa_connect_status() # This will send a plugin message

    def on_wizard_finish(self, handled):
        self._logger.info("PrusaConnectBridgePlugin: Wizard finished.")
        self._get_prusa_connect_status() # Update status on settings page etc.

    def on_wizard_proceed(self, current_step_id, next_step_id, data=None): # Added data=None for safety, though base class provides it
        self._logger.info(f"Wizard proceeding from '{current_step_id}' to '{next_step_id}'.")

        if current_step_id == "introduction" and next_step_id == "collect_sn_input":
            self._logger.info("Proceeding from introduction to SN collection step.")
            # No specific action needed here, wizard will display the next page.
        elif current_step_id == "collect_sn_input" and next_step_id == "register_prusa_connect":
            self._logger.info("Proceeding from SN collection to registration step.")
            manual_sn = data.get("manual_serial_number") if data else None

            if manual_sn: # Check if manual_sn is not None and not an empty string
                self._logger.info(f"User provided manual SN: {manual_sn}")
                self._settings.set(["prusa_connect_manual_sn"], manual_sn)
            else:
                self._logger.info("User did not provide manual SN, or it was empty. Clearing any existing manual SN setting.")
                self._settings.set(["prusa_connect_manual_sn"], None) # Ensure it's None if empty or not provided

            self._settings.save()
            self._logger.info("Manual SN (or lack thereof) saved to settings.")

            self._logger.info("Re-initializing identifiers based on wizard input before Prusa Connect registration.")
            self._initialize_identifiers() # This will use manual_sn if set, or generate/use existing, and save all SN/FP.

            self._logger.info("Identifiers re-initialized. Initiating Prusa Connect registration.")
            self._initiate_registration()
        # Other step transitions can be handled here if needed in the future.

    def get_wizard_details(self):
        self._logger.debug("PrusaConnectBridgePlugin: get_wizard_details called.")
        sn = self._settings.get(["prusa_connect_sn"])
        fingerprint = self._settings.get(["prusa_connect_fingerprint"])
        tmp_code = self._settings.get(["prusa_connect_tmp_code"])
        token = self._settings.get(["prusa_connect_token"])

        token_display = "Not yet available"
        if token and len(token) > 8:
            token_display = f"{token[:4]}...{token[-4:]}"
        elif token:
            token_display = "Token is set (short)"


        return [
            {
                "id": "introduction",
                "title": "Welcome to Prusa Connect Bridge",
                "description": "This wizard will guide you through connecting your OctoPrint instance to Prusa Connect. "
                               "The following identifiers will be used for registration:",
                "template": "prusaconnectbridge_wizard.jinja2",
                "data": {
                    "sn": sn if sn else "Will be generated/retrieved on first run",
                    "fingerprint": fingerprint if fingerprint else "Will be generated/retrieved on first run",
                    "next_button_label": "Configure Serial Number"
                }
            },
            {
                "id": "collect_sn_input",
                "title": "Serial Number Configuration",
                "description": "You can optionally provide a specific Serial Number (SN) for your printer to use with Prusa Connect. This is useful if you have an Original Prusa printer or need to use a pre-assigned SN. If you leave this field blank, a unique ID will be automatically generated.",
                "template": "prusaconnectbridge_wizard.jinja2",
                "data": {
                    "manual_sn_value": self._settings.get(["prusa_connect_manual_sn"]),
                    "next_button_label": "Continue to Registration",
                    "finish_button": False
                }
            },
            {
                "id": "register_prusa_connect",
                "title": "Register with Prusa Connect",
                "description": "When you proceed to this step, the plugin will attempt to obtain a temporary code from Prusa Connect. "
                               "Once displayed, go to <a href='https://connect.prusa3d.com/printers/add' target='_blank'>https://connect.prusa3d.com/printers/add</a> "
                               "and enter the code. The plugin will automatically attempt to retrieve your printer's token in the background.",
                "template": "prusaconnectbridge_wizard.jinja2",
                "data": {
                    "tmp_code": tmp_code if tmp_code else "Awaiting code...", # Updated initial text
                    "registration_url": "https://connect.prusa3d.com/printers/add",
                    "status_message": "Attempting to obtain temporary code...", # This will be updated by plugin messages
                    "next_button_label": "Next", # This might be hidden/disabled initially by JS based on token status
                    "finish_button": False
                }
            },
            {
                "id": "confirmation",
                "title": "Registration Complete",
                "description": "Successfully registered with Prusa Connect!",
                "template": "prusaconnectbridge_wizard.jinja2",
                "data": {
                    "token_display": token_display,
                    "finish_button_label": "Finish",
                    "next_button": False
                }
            }
        ]

# Plugin registration
__plugin_name__ = "PrusaConnect-Bridge"
__plugin_version__ = "0.1.4"
__plugin_description__ = "OctoPrint plugin bridge to Prusa Connect (unofficial)."
__plugin_pythoncompat__ = ">=3,<4" # Python 3 compatibility


def __plugin_load__():
    global __plugin_implementation__
    plugin = PrusaConnectBridgePlugin()
    __plugin_implementation__ = plugin

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.plugin.settings.initialized": __plugin_implementation__.on_settings_initialized # Add this hook
    }
