<div align="center">

# <img src="https://www.prusa3d.com/wp-content/themes/prusa3d/assets/images/prusa-logo.svg" height="50"> OctoPrint-PrusaConnect-Bridge (Unofficial)

A bridge plugin to connect <strong>OctoPrint</strong> with <strong>Prusa Connect</strong>, enabling seamless remote monitoring and control of your printer.

<br>

![OctoPrint](https://img.shields.io/badge/Platform-OctoPrint-orange?style=for-the-badge\&logo=octoprint\&logoColor=white)
![Prusa Connect](https://img.shields.io/badge/Bridge-Prusa%20Connect-ff6f00?style=for-the-badge\&logo=3d\&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-ff6f00.svg?style=for-the-badge)

</div>

---

## 🔧 Features

* ⏳ Real-time printer status monitoring via Prusa Connect (temperatures, progress, etc.).
* ✈️ Remote print control: start, stop, pause, resume.
* 📽️ Webcam stream viewable in Prusa Connect.
* 📂 Browse and print files from OctoPrint through Prusa Connect.
* 🔐 Secure communication with Prusa servers.
* 🔧 Easy setup directly within OctoPrint.

---

## 🚀 Quick Setup

### 🔍 Prerequisites

* OctoPrint (version X.Y.Z or later)
* Valid Prusa Account (for Prusa Connect)

### 🚚 Installation

#### ✅ Plugin Manager (Recommended)

1. Open OctoPrint Settings
2. Navigate to "Plugin Manager"
3. Click on **Get More...**
4. Search for `PrusaConnect Bridge`
5. Click **Install**

#### 📁 Manual Installation

```bash
cd ~/.octoprint/plugins
git clone https://github.com/VisualBoy/PrusaConnect-Bridge.git OctoPrint-PrusaConnect-Bridge
```

Or download the ZIP and install via Plugin Manager:

* Open OctoPrint Settings > Plugin Manager
* Click **Get More...** > **Upload from file** > Browse to the ZIP
* Click **Install**, then restart OctoPrint

---

## 🔄 Usage Guide

### 🔢 Configuration

1. Go to **OctoPrint Settings > PrusaConnect Bridge**
2. Follow the registration wizard to link your OctoPrint instance to your Prusa Connect account
3. Enter the temporary code on [connect.prusa3d.com](https://connect.prusa3d.com)
4. Save configuration settings

### 📊 Monitoring & Control

* Once connected, your printer will show up in your Prusa Connect dashboard
* Monitor temperatures, control print jobs, and access webcam
* Fully functional from both web and mobile Prusa Connect interfaces

---

## ⚠️ Troubleshooting

| Issue                                | Solution                                                  |
| ------------------------------------ | --------------------------------------------------------- |
| Printer not visible in Prusa Connect | Ensure registration is complete and the plugin is enabled |
| Webcam not showing                   | Check OctoPrint webcam settings and network access        |

> For more help, check the [Issues](https://github.com/VisualBoy/PrusaConnect-Bridge/issues) tab or join the community.

---

## 🎨 Contributing

Contributions are welcome! To get started:

1. Fork the repository
2. Create a new branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes and commit:

   ```bash
   git commit -am 'Add some feature'
   ```
4. Push and open a Pull Request

> Please follow the existing code style and add tests when relevant.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">
  <sub>Unofficial community project | Not affiliated with Prusa Research</sub>
</div>
