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
from prusa.connect.printer.filesystem import FileSystemNode, NodeType
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
        self.active_rules = [] # Initialize active_rules
        self.last_matched_rule_pattern = None # Initialize last matched rule pattern
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
            rules=[],  # Default empty list for rules
            prusa_connect_sn=None,
            prusa_connect_fingerprint=None,
            prusa_connect_token=None,
            prusa_connect_tmp_code=None,
            prusa_server_url="https://connect.prusa3d.com" # Added
        )

    def on_settings_initialized(self):
        self._logger.info("PrusaConnectBridgePlugin: Settings initialized.")
        self.active_rules = self._settings.get(["rules"])
        if self.active_rules is None:
            self.active_rules = []
        self._logger.info(f"PrusaConnectBridgePlugin: Loaded {len(self.active_rules)} rules.")

        self.prusa_server = self._settings.get(["prusa_server_url"]) # Load server URL
        self.last_status_sent_to_ui = "" # Initialize for status pushing
        # Initial status update can be triggered from on_after_startup or get_template_vars
        # self._get_prusa_connect_status() # Initial status check and push


    def on_settings_save(self, data):
        self._logger.info("PrusaConnectBridgePlugin: on_settings_save called.")
        old_server_url = self._settings.get(["prusa_server_url"])

        # Important: Let OctoPrint save the settings first
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

        # Now retrieve the new value that was just saved by OctoPrint
        self.prusa_server = self._settings.get(["prusa_server_url"])

        self.active_rules = self._settings.get(["rules"]) # Reload rules as well
        if self.active_rules is None:
            self.active_rules = []
        self._logger.info(f"PrusaConnectBridgePlugin: Settings saved, {len(self.active_rules)} rules reloaded.")

        if old_server_url != self.prusa_server:
            self._logger.info(f"Prusa Connect server URL changed. Old: '{old_server_url}', New: '{self.prusa_server}'.")
            self._logger.info("Clearing token and temp code to force re-registration with the new server.")

            self._settings.set(["prusa_connect_token"], None)
            self._settings.set(["prusa_connect_tmp_code"], None)
            # No need to call self._settings.save() here if we are in on_settings_save,
            # OctoPrint handles saving. However, if we want to ensure these specific changes are
            # immediately persisted and events triggered for these specific keys, saving might be desired.
            # For now, rely on OctoPrint's save cycle for the main data object.
            # Re-evaluate if direct save is needed for immediate effect on other components.

            # Update and push status to UI
            self._get_prusa_connect_status()

            self._logger.warning("A manual 'Clear Settings & Re-Register' or an OctoPrint restart is highly recommended to ensure the SDK fully uses the new server URL and re-initializes correctly.")
            # Consider how to gracefully restart the SDK components or prompt user.

    ##~~ StartupPlugin mixin
    def _initialize_identifiers(self):
        self._logger.info("Attempting to initialize Prusa Connect identifiers (SN and Fingerprint)...")
        try:
            sn = self._settings.get(["prusa_connect_sn"])
            if sn is None:
                self._logger.info("SN not found in settings, attempting to generate a new one.")
                if hasattr(self._printer, 'get_firmware_uuid') and self._printer.get_firmware_uuid():
                    sn = self._printer.get_firmware_uuid()
                    self._logger.info(f"Using firmware UUID as SN: {sn}")
                elif self._printer.get_printer_profile().get("serial"):
                    sn = self._printer.get_printer_profile().get("serial")
                    self._logger.info(f"Using printer profile serial as SN: {sn}")
                else:
                    sn = str(uuid.uuid4())
                    self._logger.info(f"Generated new UUID as SN: {sn}")
                self._settings.set(["prusa_connect_sn"], sn)
                self._settings.save() # Persist the new SN

            fingerprint = self._settings.get(["prusa_connect_fingerprint"])
            calculated_fingerprint = hashlib.sha256(sn.encode('utf-8')).hexdigest()

            if fingerprint != calculated_fingerprint:
                self._logger.info(f"Fingerprint mismatch or not set. Current: '{fingerprint}', Calculated: '{calculated_fingerprint}'. Updating fingerprint.")
                self._settings.set(["prusa_connect_fingerprint"], calculated_fingerprint)
                self._settings.save() # Persist the new fingerprint
                fingerprint = calculated_fingerprint

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
            self.prusa_printer = Printer(fingerprint=fingerprint, sn=sn, printer_type=const.PrinterType.I3MK3)
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
            self.prusa_printer.add_handler(const.Command.START_PRINT, self._handle_start_print)
        self.prusa_printer.add_handler(const.Command.STOP_PRINT, self._handle_stop_print)
        self.prusa_printer.add_handler(const.Command.PAUSE_PRINT, self._handle_pause_print)
        self.prusa_printer.add_handler(const.Command.RESUME_PRINT, self._handle_resume_print)
        self.prusa_printer.add_handler(const.Command.SEND_INFO, self._handle_send_info)
            # self.prusa_printer.add_handler(const.Command.SET_TARGET_NOZZLE, self._handle_set_target_nozzle)
            # self.prusa_printer.add_handler(const.Command.SET_TARGET_BED, self._handle_set_target_bed)
            self._logger.info("Successfully registered Prusa Connect SDK command handlers.")
        except Exception as e:
            self._logger.error(f"Error registering SDK command handlers: {e}", exc_info=True)


    # --- Command Handlers ---
    def _handle_send_info(self, args=None):
        self._logger.info(f"Handling SEND_INFO command from Prusa Connect. Args: {args}")
        try:
            if not self.prusa_printer or not self.prusa_printer.fs:
                self._logger.error("Filesystem object (self.prusa_printer.fs) not available.", exc_info=True)
                return {"error": "Filesystem not initialized", "source": const.Source.WUI}

            octoprint_files_data = self._file_manager.list_files(recursive=True, locations=['local'])

            if self.prusa_printer.fs.root:
                self.prusa_printer.fs.root.children.clear()
            else:
                self._logger.error("Prusa printer FS root is None, cannot clear or build tree.", exc_info=True) # Should not happen if fs object exists
                return {"error": "FS root is None", "source": const.Source.WUI}

            def build_fs_tree(octo_files_dict, parent_node):
                for name, item_data in octo_files_dict.items():
                    node_type = None
                    if item_data["type"] == "folder":
                        node_type = NodeType.DIR
                    elif item_data["type"] == "machinecode":
                        node_type = NodeType.FILE
                    else:
                        self._logger.debug(f"Skipping item '{name}' of type '{item_data['type']}'")
                        continue  # Skip other types

                    # Path for FileSystemNode is usually relative to printer's FS root.
                    # For items directly under 'local', their name is their path relative to root.
                    # For items in subfolders, the path needs to be constructed.
                    # The FileSystemNode path should be the full path from the FS root.
                    # Let parent_node.path be the path of the parent.
                    node_path = os.path.join(parent_node.path, name).lstrip("/")
                    if parent_node.path == "/" : # Root node special case
                        node_path = name


                    node = FileSystemNode(
                        name=name,
                        path=node_path, # This path might need adjustment based on SDK expectations for root.
                        type=node_type,
                        size=item_data.get("size", 0) if node_type == NodeType.FILE else 0,
                        m_timestamp=int(item_data.get("date", time.time()))
                    )

                    # Add estimated print time if available (for files)
                    if node_type == NodeType.FILE and item_data.get("gcodeAnalysis"):
                        estimated_print_time = item_data["gcodeAnalysis"].get("estimatedPrintTime")
                        if estimated_print_time:
                            node.print_time = int(estimated_print_time) # Assuming SDK expects int

                    parent_node.add_child(node)

                    if node_type == NodeType.DIR and "children" in item_data:
                        build_fs_tree(item_data.get("children", {}), node)

            if self.prusa_printer and self.prusa_printer.fs and self.prusa_printer.fs.root:
                build_fs_tree(octoprint_files_data.get('local', {}), self.prusa_printer.fs.root)
            else:
                self._logger.error("Prusa printer FS root not available for population.")
                return {"error": "FS root not available for population", "source": const.Source.WUI}


            # Set total and free space
            try:
                actual_uploads_path = self._file_manager.get_basedir("local")
                if actual_uploads_path and os.path.exists(actual_uploads_path):
                    stat = os.statvfs(actual_uploads_path)
                    self.prusa_printer.fs.fs_free_space = stat.f_bavail * stat.f_frsize
                    self.prusa_printer.fs.fs_total_space = stat.f_blocks * stat.f_frsize
                    self._logger.info(f"Disk space for '{actual_uploads_path}': Free: {self.prusa_printer.fs.fs_free_space}, Total: {self.prusa_printer.fs.fs_total_space}")
                else:
                    self._logger.warning(f"Could not determine valid uploads path ('{actual_uploads_path}') for disk space calculation. Path does not exist or is not accessible. Using defaults (0).")
                    self.prusa_printer.fs.fs_free_space = 0
                    self.prusa_printer.fs.fs_total_space = 0
            except Exception as e_stat:
                self._logger.error(f"Error calculating disk space for path '{actual_uploads_path}': {e_stat}", exc_info=True)
                self.prusa_printer.fs.fs_free_space = 0
                self.prusa_printer.fs.fs_total_space = 0

            self._logger.info("File system information updated for Prusa Connect based on SEND_INFO.")
            # The SDK should detect the change in self.prusa_printer.fs and send it.
            # This handler's return value confirms processing.
            return {"message": "File system info processed", "source": const.Source.WUI}

        except Exception as e:
            self._logger.error(f"Error handling SEND_INFO: {e}", exc_info=True)
            return {"error": str(e), "source": const.Source.WUI}

    def _handle_start_print(self, args):
        self._logger.info(f"Handling START_PRINT command with args: {args}")

        filename = None
        if isinstance(args, list) and len(args) > 0:
            filename = args[0]
        elif isinstance(args, str):
            filename = args

        if not filename or not isinstance(filename, str):
            self._logger.error("START_PRINT: Filename not provided or invalid.")
            # self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, command_id=const.Command.START_PRINT, message="Filename missing")
            return {"error": "Filename missing", "source": const.Source.WUI} # SDK expects dict response

        try:
            # Ensure the file exists in OctoPrint's local storage
            # The filename from Prusa Connect might not include the full path or correct origin.
            # We need to find it. This assumes files are in 'local' storage.
            # A more robust solution might involve checking selected_file_path if already selected via another interface.

            # Check if the file exists using OctoPrint's file manager
            if not self._file_manager.file_exists("local", filename):
                self._logger.error(f"START_PRINT: File '{filename}' not found in local storage via file_manager.")
                # Attempt to find the file by iterating if the name is correct but path is not known by PrusaConnect
                # This is a simplified check. A full search might be needed if paths are complex.
                # For now, we require exact name match in 'local'.
                # self.prusa_printer.event_cb(const.Event.COMMAND_FAILED, command_id=const.Command.START_PRINT, message=f"File {filename} not found")
                return {"error": f"File '{filename}' not found", "source": const.Source.WUI}

            # Get the full path on disk for OctoPrint's printer module
            path_to_file = self._file_manager.path_on_disk("local", filename)
            if not path_to_file: # Should be redundant if file_exists passed, but good practice
                 self._logger.error(f"START_PRINT: Could not get disk path for supposedly existing file '{filename}'.")
                 return {"error": f"Could not get disk path for {filename}", "source": const.Source.WUI}

            self._logger.info(f"Attempting to select and print file: {path_to_file}")
            self._printer.select_file(path_to_file, printAfterSelect=True)

            # SDK's set_state is primarily for telemetry. OctoPrint's state will propagate.
            # However, explicitly setting it can make Prusa Connect UI more responsive.
            self.prusa_printer.set_state(const.State.PRINTING)
            self._logger.info(f"Successfully initiated print for {filename}")
            return {"source": const.Source.WUI} # Success
        except Exception as e:
            self._logger.error(f"Error handling START_PRINT for {filename}: {e}", exc_info=True)
            error_msg = f"Error handling START_PRINT for file '{filename}': {e}"
            self._logger.error(error_msg, exc_info=True)
            if self.prusa_printer and self.prusa_printer.token_set:
                try:
                    self.prusa_printer.event_cb(const.Event.PROJECT_FAILED,
                                                message=f"OctoPrint failed to start print: {str(e)[:100]}",
                                                source=const.Source.WUI)
                except Exception as sdk_event_err:
                    self._logger.error(f"Failed to send PROJECT_FAILED event to Prusa Connect: {sdk_event_err}", exc_info=True)
            return {"error": str(e), "source": const.Source.WUI}

    def _handle_stop_print(self, args=None):
        self._logger.info(f"Handling STOP_PRINT command. Args: {args}")
        try:
            self._printer.cancel_print()
            self.prusa_printer.set_state(const.State.READY)
            self._logger.info("Print cancelled successfully via Prusa Connect command.")
            return {"source": const.Source.WUI}
        except Exception as e:
            error_msg = f"Error handling STOP_PRINT: {e}"
            self._logger.error(error_msg, exc_info=True)
            if self.prusa_printer and self.prusa_printer.token_set:
                try:
                    self.prusa_printer.event_cb(const.Event.FAILED, message=f"Failed to stop print: {str(e)[:100]}", source=const.Source.WUI)
                except Exception as sdk_event_err:
                    self._logger.error(f"Failed to send FAILED event for STOP_PRINT: {sdk_event_err}", exc_info=True)
            return {"error": str(e), "source": const.Source.WUI}

    def _handle_pause_print(self, args=None):
        self._logger.info(f"Handling PAUSE_PRINT command. Args: {args}")
        try:
            if self._printer.is_printing() and not self._printer.is_paused():
                self._printer.pause_print()
                self.prusa_printer.set_state(const.State.PAUSED)
                self._logger.info("Print paused successfully via Prusa Connect command.")
            elif self._printer.is_paused():
                self._logger.info("Print is already paused. No action taken.")
            else:
                self._logger.warning("Cannot pause: Printer is not currently printing.")
                return {"error": "Not printing", "source": const.Source.WUI}
            return {"source": const.Source.WUI}
        except Exception as e:
            error_msg = f"Error handling PAUSE_PRINT: {e}"
            self._logger.error(error_msg, exc_info=True)
            if self.prusa_printer and self.prusa_printer.token_set:
                try:
                    self.prusa_printer.event_cb(const.Event.FAILED, message=f"Failed to pause print: {str(e)[:100]}", source=const.Source.WUI)
                except Exception as sdk_event_err:
                    self._logger.error(f"Failed to send FAILED event for PAUSE_PRINT: {sdk_event_err}", exc_info=True)
            return {"error": str(e), "source": const.Source.WUI}

    def _handle_resume_print(self, args=None):
        self._logger.info(f"Handling RESUME_PRINT command. Args: {args}")
        try:
            if self._printer.is_paused():
                self._printer.resume_print()
                self.prusa_printer.set_state(const.State.PRINTING)
                self._logger.info("Print resumed successfully via Prusa Connect command.")
            else:
                self._logger.warning("Cannot resume: Printer is not currently paused.")
                return {"error": "Not paused", "source": const.Source.WUI}
            return {"source": const.Source.WUI}
        except Exception as e:
            error_msg = f"Error handling RESUME_PRINT: {e}"
            self._logger.error(error_msg, exc_info=True)
            if self.prusa_printer and self.prusa_printer.token_set:
                try:
                    self.prusa_printer.event_cb(const.Event.FAILED, message=f"Failed to resume print: {str(e)[:100]}", source=const.Source.WUI)
                except Exception as sdk_event_err:
                    self._logger.error(f"Failed to send FAILED event for RESUME_PRINT: {sdk_event_err}", exc_info=True)
            return {"error": str(e), "source": const.Source.WUI}
    # --- End Command Handlers ---

    def _initiate_registration(self):
        self._logger.info("Initiating Prusa Connect registration process (e.g., via wizard or manual trigger)...")
        if not self.prusa_printer: # Guard against uninitialized printer object
            self._logger.error("Cannot initiate registration: prusa_printer not initialized.", exc_info=True)
            return

        try:
            self.prusa_printer.register() # This call attempts to get tmp_code
            tmp_code = self.prusa_printer.tmp_code

            if tmp_code:
                self._logger.info(f"Successfully received temporary code from Prusa Connect: {tmp_code}")
                self._settings.set(["prusa_connect_tmp_code"], tmp_code)
                self._settings.save()
                self.temp_code_displayed = True # Legacy flag, might not be used by wizard
                self._registration_error_message = None # Clear any previous error
                self._start_token_retrieval_timer(tmp_code)
            else:
                self._logger.error("Failed to retrieve temporary code from Prusa Connect (tmp_code is None after register() call).")
                self._registration_error_message = "Failed to obtain temporary code from Prusa Connect. Server might be busy or unreachable. Please check logs."
        except Exception as e:
            self._logger.error(f"Exception during Prusa Connect self.prusa_printer.register() call: {e}", exc_info=True)
            self._registration_error_message = f"Error obtaining temp code: {str(e)}. Please check logs and network."
        finally:
            # Always update status, whether success or failure, to push error message or new tmp_code
            self._get_prusa_connect_status()


    def _start_token_retrieval_timer(self, tmp_code):
        self._logger.info(f"Starting token retrieval timer with tmp_code: {tmp_code}")
        if self.token_retrieval_timer is not None and self.token_retrieval_timer.is_alive(): # Check if timer is alive
            self.token_retrieval_timer.cancel()
            self._logger.info("Cancelled existing token retrieval timer.")

        self.token_retrieval_timer = RepeatedTimer(
            10.0,
            self._check_for_token,
            run_first=True, # Check immediately then repeat
            condition=lambda: not (self.prusa_printer and self.prusa_printer.token_set), # Continue if no token
            on_condition_false=self._token_retrieved_successfully, # Call when token IS set
            daemon=True
        )
        self.token_retrieval_timer.start()
        self._logger.info("Token retrieval timer started.")


    def _check_for_token(self):
        if not self.prusa_printer: # Guard
            self._logger.warning("Cannot check for token: prusa_printer not initialized. Stopping timer.", exc_info=True)
            if self.token_retrieval_timer: self.token_retrieval_timer.cancel()
            return

        if not self.prusa_printer.tmp_code:
            # Attempt to restore tmp_code if cleared from printer object (e.g. after restart)
            stored_tmp_code = self._settings.get(["prusa_connect_tmp_code"])
            if stored_tmp_code:
                self.prusa_printer.tmp_code = stored_tmp_code
                self._logger.info(f"Restored tmp_code {stored_tmp_code} to printer object for token check.")
            else:
                self._logger.warning("No tmp_code on printer object or in settings. Stopping token retrieval.")
                if self.token_retrieval_timer: self.token_retrieval_timer.cancel()
                self.last_status_sent_to_ui = "" ; self._get_prusa_connect_status() # Update UI
                return

        current_tmp_code = self.prusa_printer.tmp_code # Use current tmp_code for logging
        self._logger.info(f"Checking for token with tmp_code: {current_tmp_code}...")
        try:
            # get_token() returns True if token is obtained, False otherwise.
            # It sets self.prusa_printer.token and self.prusa_printer.token_set internally.
            token_obtained_now = self.prusa_printer.get_token()

            if token_obtained_now:
                # This means the token was just obtained in this call.
                # The RepeatedTimer's condition will cause it to stop, and _token_retrieved_successfully will be called.
                self._logger.info(f"Token appears to have been retrieved successfully for tmp_code: {current_tmp_code} during get_token() call.")
                self._registration_error_message = None # Clear error as we got a token
                # _token_retrieved_successfully will handle saving and further status updates
            elif self.prusa_printer.token_set:
                # Token was already set, but timer is still running (shouldn't happen if condition is correct)
                self._logger.info("Token was already set. Timer should have stopped.")
                self._registration_error_message = None # Clear error
            else:
                # Token not yet available, no exception, this is normal polling
                self._logger.info(f"Token not yet available for tmp_code: {current_tmp_code}. Polling continues.")
                # Don't clear _registration_error_message here, an error might be transient from previous attempt
                # Only clear error on explicit success.
        except Exception as e:
            self._logger.error(f"Error while checking for token with tmp_code {current_tmp_code}: {e}", exc_info=True)
            self._registration_error_message = f"Error polling for token: {str(e)}. Will retry."
            # Update UI to reflect potential issue
            self._get_prusa_connect_status() # Push error to UI

    def _token_retrieved_successfully(self):
        if not self.prusa_printer or not self.prusa_printer.token: # Guard
            self._logger.error("Token retrieved successfully callback, but printer object or token is None. This should not happen.", exc_info=True)
            self._registration_error_message = "Internal error after token retrieval. Please check logs."
            self._get_prusa_connect_status()
            return

        token = self.prusa_printer.token
        self._logger.info(f"Successfully retrieved and confirmed Prusa Connect token: {token[:4]}...{token[-4:]}")
        self._settings.set(["prusa_connect_token"], token)
        self._settings.set(["prusa_connect_tmp_code"], None) # Clear temp code from settings
        self._settings.save()
        self._registration_error_message = None # Clear any errors as we have succeeded

        self.temp_code_displayed = False # Reset flag
        # self.last_status_sent_to_ui = "" # This is implicitly handled by calling _get_prusa_connect_status()
        self._get_prusa_connect_status() # Ensure UI is updated with new token status

        if self.token_retrieval_timer:
            # The timer should have already stopped itself due to the condition.
            # This is an explicit cancel for safety, though normally not needed.
            self.token_retrieval_timer.cancel()
            self.token_retrieval_timer = None # Clear the timer object
            self._logger.info("Token retrieval timer stopped and cleared.")

        # Ensure the printer object is configured with the new token for the SDK loop.
        # The SDK's Printer.token attribute is set by get_token().
        # The Printer.set_connection method also sets this, but it's primarily for initial setup.
        # The loop should pick up the new token automatically.
        # For clarity or if issues arise, one could re-call:
        # self.prusa_printer.set_connection(server_url=self.prusa_server, token=token)
        self._logger.info("Prusa Connect SDK is now configured with the token.")
        self._start_telemetry_timer() # Start telemetry once token is retrieved


    def _start_telemetry_timer(self):
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
                self.prusa_printer = Printer(fingerprint=new_fingerprint, sn=new_sn, printer_type=const.PrinterType.I3MK3)
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


    ##~~ G-code queuing hook
    def hook_gcode_queuing(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        if not gcode:
            return cmd

        # G-code hook logic is related to a different feature (G-code manipulation based on rules)
        # and is assumed to be correct from previous context.
        # For this step, ensure any self.active_rules access is safe if rules can be None initially.
        if not self.active_rules: # Add a guard if active_rules might not be initialized
            return cmd

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

    def on_wizard_finish(self):
        self._logger.info("PrusaConnectBridgePlugin: Wizard finished.")
        self._get_prusa_connect_status() # Update status on settings page etc.

    def on_wizard_proceed(self, current_step_id, next_step_id):
        self._logger.info(f"Wizard proceeding from '{current_step_id}' to '{next_step_id}'.")
        if current_step_id == "introduction" and next_step_id == "register_prusa_connect":
            self._logger.info("Proceeding from introduction to registration step. Initiating Prusa Connect registration.")
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
                    "next_button_label": "Start Registration Process"
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
