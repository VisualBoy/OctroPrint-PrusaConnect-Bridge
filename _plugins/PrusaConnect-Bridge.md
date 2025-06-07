---
layout: plugin
id: PrusaConnect-Bridge
title:  Live G-Code Control
description: Allows real-time G-code stream manipulation by matching user-defined patterns (e.g., regex) against outgoing commands to conditionally modify, skip, or inject G-code.

authors:
- GlitchLab.xyz

license: MIT License

date: 2025-06-03 #

homepage: https://github.com/VisualBoy/OctoPrint-PrusaConnect-Bridge
source: https://github.com/VisualBoy/OctoPrint-PrusaConnect-Bridge
archive: https://github.com/VisualBoy/OctoPrint-PrusaConnect-Bridge/archive/main.zip

# Set this if your plugin heavily interacts with any kind of cloud services.
# privacypolicy: your plugin's privacy policy URL

# Set this to true if your plugin uses the dependency_links setup parameter to include
# library versions not yet published on pypi. SHOULD ONLY BE USED IF THERE IS NO OTHER OPTION!
follow_dependency_links: false

tags:
- gcode
- control
- regex
- live control
- automation
- gcode manipulation
- interface
- tool
- live
- override

screenshots:
- url: /assets/img/plugins/PrusaConnect-Bridge/screenshot1.png
  alt: Main settings interface for PrusaConnect-Bridge
  caption: Configuring rules in PrusaConnect-Bridge
- url: /assets/img/plugins/PrusaConnect-Bridge/screenshot2.png
  alt: Example of a rule in action
  caption: Rule example for G-code modification
# - ... add more screenshots if needed

featuredimage: /assets/img/plugins/PrusaConnect-Bridge/featured.png

compatibility:
  # OctoPrint versions. >=1.3.0 is a common baseline. Adjust if your plugin needs newer features.
  # OctoPrint 1.8.0+ is Python 3 only.
  octoprint:
  - ">=1.8.0"

  # Operating systems. Should be OS-independent.
  os:
  - linux
  - windows
  - macos
  - freebsd

  # Compatible Python version. OctoPrint 1.8.0+ requires Python 3.7+.
  # New plugins should target Python 3 only.
  python: ">=3.7,<4" # Python 3 only (specifically 3.7+)

# Attributes - uncomment if they apply
# attributes:
#  - cloud  # if your plugin requires access to a cloud to function
#  - commercial  # if your plugin has a commercial aspect to it
#  - free-tier  # if your plugin has a free tier
---

## 🔧 OctoPrint-PrusaConnect-Bridge

**Live G-Code Control** is an 🐙 **OctoPrint** plugin designed to provide fine-grained, real-time control over the G-code stream sent to your 3D printer.

### ✨ Features

Users can define a set of rules, each consisting of a **pattern (regular expression)** and an **action**. As each G-code command is processed, the plugin matches it against your defined patterns. If a pattern matches, the plugin can perform one of the following actions:

- 🔄 **Modify:** Alter the current G-code command (e.g., change a parameter's value).
- 🚫 **Skip/Suppress:** Prevent the current G-code command from being sent.
- ➕ **Inject Before:** Insert custom G-code commands immediately before the matched command.
- ➕ **Inject After:** Insert custom G-code commands immediately after the matched command.
- 🔁 **Replace:** Substitute the current G-code command with custom G-code commands.

This enables dynamic and conditional manipulation of the G-code stream based on its content, including slicer-generated comments (e.g., `;TYPE:Bridge`, `;LAYER_CHANGE`).

### 🧪 Example Use Cases

- 🌬️ **Dynamic Fan Control:** Automatically set fan speed to 100% when a line containing `;TYPE:Bridge` is detected, and revert to a lower speed when the bridge section is complete.
- 🧼 **Conditional G-code Injection:** Inject custom G-code commands before or after specific standard commands (e.g., add a custom nozzle wipe routine before `M600` filament change).
- 🔄 **Command Remapping/Filtering:** Change or filter out specific G-code commands on the fly.
- 🧪 **Experimentation:** Test G-code variations or inject diagnostic commands without re-slicing your model.

### ⚙️ Configuration

The plugin provides a settings interface within OctoPrint where you can:
* Create, edit, and delete rules.
* Define the regex pattern for each rule. This uses standard Python regex syntax.
* Select the action type (Modify, Skip, Inject Before/After, Replace).
* Specify the G-code command(s) for actions that involve injection or replacement.
* Enable or disable individual rules.
* Control the order of rule evaluation.

> ⚠️ It is recommended to have a basic understanding of G-code and regular expressions to use this plugin effectively. Test rules in a safe environment before relying on them for critical prints.

### 📌 Important Notes

* 🧩 This plugin works by intercepting G-code commands via OctoPrint's `octoprint.comm.protocol.gcode.queuing` hook. This allows for robust modification of the command stream before it is sent to the printer.
* ⚠️  While powerful, misconfiguration of rules could lead to unexpected printer behavior. Please use with caution and test your rules thoroughly.
* ⚠️  The effectiveness of matching comments depends on your slicer generating those comments in the G-code file.
* ➕  This plugin adds a new tab to the OctoPrint interface for managing rules. Screenshots provided showcase this interface.
```
