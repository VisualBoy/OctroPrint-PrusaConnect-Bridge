---
layout: plugin
id: PrusaConnect-Bridge
title:  PrusaConnect Bridge
description: Allows real-time G-code stream manipulation by matching user-defined patterns (e.g., regex) against outgoing commands to conditionally modify, skip, or inject G-code.

authors:
- GlitchLab.xyz

license: MIT License

date: 2025-06-07 #

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
- // TO-DO

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

**PrusaConnect Bridge** is an 🐙 **OctoPrint** plugin designed to... // TO-DO

### ✨ Features

// TO-DO


### 🧪 Example Use Cases

// TO-DO

### ⚙️ Configuration

The plugin provides a settings interface within OctoPrint where you can:

// TO-DO

> ⚠️ It is recommended to have a basic understanding of G-code and regular expressions to use this plugin effectively. Test rules in a safe environment before relying on them for critical prints.

### 📌 Important Notes

// TO-DO
