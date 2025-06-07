---
layout: plugin
id: PrusaConnect-Bridge
title:  PrusaConnect Bridge
description: Integrates OctoPrint with Prusa Connect, allowing you to monitor and control your printer via the Prusa Connect interface.

authors:
- GlitchLab.xyz

license: MIT License

date: 2025-06-07 #

homepage: https://github.com/VisualBoy/PrusaConnect-Bridge
source: https://github.com/VisualBoy/PrusaConnect-Bridge
archive: https://github.com/VisualBoy/PrusaConnect-Bridge/archive/main.zip

# Set this if your plugin heavily interacts with any kind of cloud services.
# privacypolicy: your plugin's privacy policy URL

# Set this to true if your plugin uses the dependency_links setup parameter to include
# library versions not yet published on pypi. SHOULD ONLY BE USED IF THERE IS NO OTHER OPTION!
follow_dependency_links: false

tags: [prusa connect, cloud, monitoring, remote control]

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

**PrusaConnect Bridge** is an 🐙 **OctoPrint** plugin that seamlessly integrates your printer with Prusa Connect. This allows for remote monitoring and control through the official Prusa Connect cloud interface.

### ✨ Features

*   **Remote Monitoring:** Keep an eye on your printer's temperatures, progress, and status from anywhere via Prusa Connect.
*   **Remote Control:** Start, stop, pause, and resume prints directly from the Prusa Connect interface.
*   **Webcam Streaming:** View your OctoPrint webcam feed within Prusa Connect.
*   **File Management:** List G-code files stored in OctoPrint and initiate prints from them via Prusa Connect.
*   **Secure Connection:** Uses the official Prusa Connect SDK for communication.
*   **Easy Setup:** Configuration wizard to guide you through the Prusa Connect registration process.


### 🧪 Example Use Cases

*   Check on your print's progress while you are away from home.
*   Start a pre-sliced print job remotely.
*   Pause a print if you notice an issue via webcam and then resume it after fixing.
*   Manage multiple printers linked to your Prusa Connect account, including those running OctoPrint with this bridge.

### ⚙️ Configuration

Configuration is handled via a setup wizard that launches after plugin installation. You will be guided through the process of linking your OctoPrint instance to your Prusa Connect account. Key settings include:
*   **Prusa Connect Server URL:** Defaults to the official Prusa Connect server, but can be changed if needed (e.g., for testing).
*   **Registration:** The wizard helps generate a temporary code to register your printer with Prusa Connect.
Once registered, the plugin handles communication in the background. You can access most controls and monitoring features directly through the Prusa Connect web portal or mobile apps.
You can re-run the wizard or adjust settings by navigating to "Settings" > "PrusaConnect Bridge" in OctoPrint.

### 📌 Important Notes

*   This is an unofficial bridge and is not directly supported by Prusa Research.
*   Ensure your OctoPrint instance has stable internet connectivity for reliable communication with Prusa Connect.
*   For troubleshooting, check the plugin's logs within OctoPrint under "Settings" > "Logging".
