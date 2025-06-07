# OctoPrint-PrusaConnect-Bridge (Unofficial)

An OctoPrint plugin that acts as a bridge to Prusa Connect, allowing you to monitor and control your ika via the Prusa Connect interface.

## Features

*   Real-time printer status monitoring via Prusa Connect (e.g., temperatures, print progress).
*   Remote print control (start, stop, pause, resume) from the Prusa Connect interface.
*   View printer webcam stream in Prusa Connect.
*   File listing and print initiation from files stored in OctoPrint, accessible via Prusa Connect.
*   Secure communication with Prusa Connect servers.
*   Easy setup and configuration within OctoPrint.

## Setup

### Prerequisites

*   OctoPrint (version X.Y.Z or later)
*   [Any other prerequisites, e.g., A Prusa Account]

### Installation

1.  **Via Plugin Manager (Recommended)**
    *   Open OctoPrint settings.
    *   Go to the "Plugin Manager".
    *   Click "Get More...".
    *   Search for "PrusaConnect Bridge".
    *   Click "Install".
2.  **Manual Installation**
    *   Download the plugin repository as a ZIP file.
    *   In OctoPrint settings, go to "Plugin Manager".
    *   Click "Get More...".
    *   Under "...or upload a file from your computer", click "Browse..." and select the downloaded ZIP file.
    *   Click "Install".
    *   Alternatively, clone the repository into your OctoPrint plugins directory:
        ```bash
        cd ~/.octoprint/plugins
        git clone https://github.com/VisualBoy/PrusaConnect-Bridge.git OctoPrint-PrusaConnect-Bridge
        ```
    *   Restart OctoPrint.

## Usage

1.  **Configuration**
    *   After installation, open OctoPrint settings.
    *   Navigate to "PrusaConnect Bridge" under the "Plugins" section.
    *   Follow the on-screen wizard after installation to register your OctoPrint instance with Prusa Connect. This will involve obtaining a temporary code from the plugin and entering it on the Prusa Connect website.
    *   Save settings.
2.  **Monitoring and Control**
    *   Once configured, your printer will appear in your Prusa Connect account (web or app). You can monitor its status, control prints, and view its webcam stream directly from the Prusa Connect interface.

## Troubleshooting

*   [Common issue 1 and its solution]
*   [Common issue 2 and its solution]

## Contributing

Contributions are welcome! If you'd like to contribute, please:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix (`git checkout -b feature/your-feature-name` or `bugfix/your-bug-fix`).
3.  Make your changes.
4.  Add tests for your changes (if applicable).
5.  Ensure your code follows the project's coding style.
6.  Commit your changes (`git commit -am 'Add some feature'`).
7.  Push to the branch (`git push origin feature/your-feature-name`).
8.  Create a new Pull Request.

## License

This project is licensed under the terms of the [MIT License](LICENSE).
