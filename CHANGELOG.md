# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2025-06-07
### Fixed
- Resolved a `SyntaxError` in command handler registration to ensure compatibility with Python 3.7.9 when using `prusa-connect-sdk-printer` v0.7.0. Refactored to use decorator-based handlers.
### Changed
- Updated `prusa-connect-sdk-printer` dependency to `==0.7.0` in `setup.py`.

## [0.1.1] - 2025-06-04
### Added
- Initial integration with Prusa Connect SDK.
- Functionality to monitor printer status (temperatures, print progress) via Prusa Connect.
- Remote print control (start, stop, pause, resume) from the Prusa Connect interface.
- Webcam stream view in Prusa Connect.
- File listing and print initiation from files stored in OctoPrint, accessible via Prusa Connect.
- Setup wizard for easy registration with Prusa Connect.
- Settings option to clear credentials and re-register.
- Plugin status display in settings.

### Changed
- Updated plugin version to 0.1.1.
- Revised README.md with accurate features, setup instructions, and new repository URL.
- Updated plugin marketplace file (`_plugins/PrusaConnect-Bridge.md`) with new description, features, URLs, and tags; removed obsolete G-code related content and screenshots.
- Corrected repository URL in software update configuration.

### Fixed
- Ensured `requirements.txt` includes `prusa-connect-sdk`.
