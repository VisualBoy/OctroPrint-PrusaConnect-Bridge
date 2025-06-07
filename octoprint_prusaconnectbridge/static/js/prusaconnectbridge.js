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
});
