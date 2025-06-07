$(function() {
    function PrusaConnectBridgeViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0]; // OctoPrint Settings ViewModel

        // Observables for the new rule input fields
        self.newRulePattern = ko.observable("");
        self.newRuleActionType = ko.observable("modify"); // Default action type
        self.newRuleActionGcode = ko.observable("");

        // Observable array to store the rules
        self.rules = ko.observableArray([]);
        self.editingRule = ko.observable(null); // Holds the rule being edited

        // Observable for the Add/Update button text
        self.addOrUpdateRuleButtonText = ko.pureComputed(function() {
            return self.editingRule() ? "Update Rule" : "Add Rule";
        });

        // --- Helper function to create a new rule object ---
        function createRule(enabled, pattern, actionType, actionGcode) {
            return {
                enabled: ko.observable(enabled !== undefined ? enabled : true),
                pattern: ko.observable(pattern || ""),
                actionType: ko.observable(actionType || "modify"),
                actionGcode: ko.observable(actionGcode || "")
            };
        }

        // --- Functions for rule management ---
        self.addRule = function() {
            if (!self.newRulePattern()) {
                // Optionally, add some validation feedback to the user
                // e.g., using PNotify or highlighting the input field
                self._logger.warn("PrusaConnectBridge: Pattern is required to add/update a rule.");
                return;
            }

            if (self.editingRule()) {
                // Update existing rule
                var ruleToUpdate = self.editingRule();
                ruleToUpdate.pattern(self.newRulePattern());
                ruleToUpdate.actionType(self.newRuleActionType());
                ruleToUpdate.actionGcode(self.newRuleActionGcode());
                // 'enabled' state is managed by its own checkbox, no need to set here explicitly
                // unless the design requires re-enabling on edit, which is not typical.
            } else {
                // Add new rule
                var newRule = createRule(
                    true, // New rules are enabled by default
                    self.newRulePattern(),
                    self.newRuleActionType(),
                    self.newRuleActionGcode()
                );
                self.rules.push(newRule);
            }

            // Clear input fields and reset editing state
            self.newRulePattern("");
            self.newRuleActionType("modify"); // Reset to default action type
            self.newRuleActionGcode("");
            self.editingRule(null); // Exit edit mode
        };

        self.removeRule = function(rule) {
            self.rules.remove(rule);
            if (self.editingRule() === rule) { // If deleting the rule being edited
                self.cancelEdit(); // Clear fields and reset editing state
            }
        };

        self.editRule = function(rule) {
            self.editingRule(rule);
            self.newRulePattern(rule.pattern());
            self.newRuleActionType(rule.actionType());
            self.newRuleActionGcode(rule.actionGcode());
        };

        self.cancelEdit = function() {
            self.newRulePattern("");
            self.newRuleActionType("modify");
            self.newRuleActionGcode("");
            self.editingRule(null);
        };

        // --- OctoPrint Settings Plugin Hooks ---
        self.onBeforeBinding = function() {
            // Load existing rules from settings
            var savedRulesData = self.settingsViewModel.settings.plugins.PrusaConnectBridge.rules();
            if (savedRulesData) {
                var mappedRules = $.map(savedRulesData, function(ruleData) {
                    // Ensure ruleData itself isn't observable if settings are ever passed as such
                    var rd = ko.toJS(ruleData);
                    return createRule(rd.enabled, rd.pattern, rd.actionType, rd.actionGcode);
                });
                self.rules(mappedRules);
            }
        };

        self.onSettingsShown = function() {
            // Could refresh data from server if necessary, but usually onBeforeBinding is enough for settings
            // Ensure editing state is clear when settings are reshown
            self.cancelEdit();
        };

        self.onSettingsHidden = function() {
            // Could perform cleanup
            // Ensure editing state is clear when settings are hidden
            self.cancelEdit();
        };

        self.onSettingsSave = function() {
            // Convert observable rules to plain JS objects for saving
            var rulesToSave = $.map(self.rules(), function(rule) {
                return { // Convert each rule (which has observable properties) to a plain object
                    enabled: ko.toJS(rule.enabled), // or rule.enabled()
                    pattern: ko.toJS(rule.pattern),
                    actionType: ko.toJS(rule.actionType),
                    actionGcode: ko.toJS(rule.actionGcode)
                };
            });
            self.settingsViewModel.settings.plugins.PrusaConnectBridge.rules(rulesToSave);
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: PrusaConnectBridgeViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_PrusaConnectBridge"]
    });

    // --- Prusa Connect Bridge Wizard ViewModel ---
    function PrusaConnectBridgeWizardViewModel(parameters) {
        var self = this;
        // parameters[0] is wizardViewModel, parameters[1] is the payload from get_wizard_details
        self.wizard = parameters[0];


        // Observables for wizard data
        self.sn_display = ko.observable("");
        self.fingerprint_display = ko.observable("");
        self.tmp_code_display = ko.observable("Awaiting code...");
        self.registration_url_text = ko.observable("https://connect.prusa3d.com/printers/add");
        self.registration_url_href = ko.observable("https://connect.prusa3d.com/printers/add");
        self.wizard_status_message_display = ko.observable("Initializing...");
        self.token_partial_display = ko.observable("");
        self.is_token_available = ko.observable(false);
        self.current_step_id = ko.observable("");

        // This is called by the wizard framework for each step.
        // wizard: the wizard instance
        // step_id: id of the current step
        // step_payload: the 'data' dict from get_wizard_details for the current step
        self.onWizardBeforeBinding = function(wizard, step_id, step_payload) {
            self.current_step_id(step_id);
            // console.log("PrusaConnectBridgeWizardViewModel: onWizardBeforeBinding for step_id:", step_id, "Payload:", step_payload);

            if (step_payload) { // Check if step_payload exists
                if (step_id === 'introduction') {
                    self.sn_display(step_payload.sn); // Corrected: data is directly in step_payload here
                    self.fingerprint_display(step_payload.fingerprint); // Corrected
                } else if (step_id === 'register_prusa_connect') {
                    self.tmp_code_display(step_payload.tmp_code || 'Awaiting code from server...');
                    self.wizard_status_message_display(step_payload.status_message || 'Follow instructions above.');
                    if (step_payload.registration_url) {
                        self.registration_url_text(step_payload.registration_url);
                        self.registration_url_href(step_payload.registration_url);
                    }
                } else if (step_id === 'confirmation') {
                    self.token_partial_display(step_payload.token_display || 'Token not yet available.');
                    if (step_payload.token_display && step_payload.token_display !== 'Not yet available' && step_payload.token_display.includes("...")) {
                        self.is_token_available(true);
                    }
                }
            } else {
                // console.warn("PrusaConnectBridgeWizardViewModel: step_payload is undefined for step_id:", step_id);
            }
        };

        self.onWizardTabChange = function(next_step_id, current_step_id) {
            self.current_step_id(next_step_id);
            // console.log("PrusaConnectBridgeWizardViewModel: onWizardTabChange to step_id:", next_step_id);
        };

        // Computed observable to control the "Next" button on the registration step
        self.isNextButtonEnabled = ko.pureComputed(function() {
            if (self.current_step_id() === 'register_prusa_connect') {
                return self.is_token_available();
            }
            return true; // Enabled for other steps by default
        });

        // Override for the wizard's "next" button for the registration step
        // This ensures "Next" is only enabled when token is available.
        // Note: OctoPrint's wizard framework should pick up button labels from get_wizard_details.
        // This is more about controlling enabled state.
        self.wizard.isNextEnabled = ko.pureComputed(function() {
            return self.isNextButtonEnabled();
        }, self);

        self.onDataUpdaterPluginMessage = function(plugin, message) {
            if (plugin !== "PrusaConnectBridge") {
                return;
            }
            // console.log("PrusaConnectBridgeWizardViewModel: Received plugin message:", message);

            var statusMessageSet = false; // Flag to see if a specific status message has been set

            // Priority 1: Display registration error message if present
            if (message.registration_error_message && message.registration_error_message.length > 0) {
                self.wizard_status_message_display(message.registration_error_message);
                statusMessageSet = true;
            }

            // Update observables for tmp_code and token_partial_display regardless of status message
            if (message.hasOwnProperty('tmp_code')) {
                self.tmp_code_display(message.tmp_code || 'Awaiting code...');
            }
            if (message.hasOwnProperty('token_display_partial')) {
                self.token_partial_display(message.token_display_partial || '');
            }

            // Handle token availability and associated status messages if no error message was set
            if (message.hasOwnProperty('token_available')) {
                var old_token_state = self.is_token_available();
                self.is_token_available(message.token_available);

                if (message.token_available) {
                    if (!statusMessageSet) { // Only set status if no error message took precedence
                        if (!old_token_state) { // Token *just* became available
                            self.wizard_status_message_display('Token successfully retrieved! Proceeding to confirmation.');
                            statusMessageSet = true;
                        } else if (self.current_step_id() === 'register_prusa_connect') {
                            // Token was already available, user might have navigated back.
                            self.wizard_status_message_display('Token is available. You can proceed to confirmation.');
                            statusMessageSet = true;
                        }
                    }
                    // Auto-advance if token just became available
                    if (!old_token_state && self.current_step_id() === 'register_prusa_connect') {
                        self.wizard.gotoStep('confirmation');
                    }
                } else { // Token not available
                    // Potentially set a status message if no error and not handled by tmp_code logic below
                    if (!statusMessageSet && self.current_step_id() === 'register_prusa_connect') {
                        if (message.hasOwnProperty('tmp_code') && !message.tmp_code) {
                           // self.wizard_status_message_display('Registration may have been reset or failed. Waiting for new code or instructions.');
                           // statusMessageSet = true; // This might be too specific, let general status_text handle
                        }
                    }
                }
            }

            // Handle tmp_code specific message, if no error and no token message has been set
            if (!statusMessageSet && message.hasOwnProperty('tmp_code') && message.tmp_code) {
                self.wizard_status_message_display('Temporary code received. Please enter it on the Prusa Connect website.');
                statusMessageSet = true;
            }

            // Fallback to general status_text if no more specific message has been set
            if (!statusMessageSet && message.status_text) {
                self.wizard_status_message_display(message.status_text);
                statusMessageSet = true;
            }

            // Final check if tmp_code is cleared AND no token AND no error, might need a default message for register step
            if (self.current_step_id() === 'register_prusa_connect' &&
                !message.hasOwnProperty('tmp_code') && // if message does not have tmp_code, means it was not changed by this message
                !self.tmp_code_display() && // but it's currently empty
                !self.is_token_available() &&
                (!message.registration_error_message || message.registration_error_message.length === 0) &&
                !statusMessageSet) {
                // self.wizard_status_message_display('Awaiting code or further instructions...');
            }
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: PrusaConnectBridgeWizardViewModel,
        dependencies: ["wizardViewModel"], // Standard wizard view model
        elements: ["#wizard_plugin_prusaconnectbridge"] // Selector for the wizard dialog body
    });
});
