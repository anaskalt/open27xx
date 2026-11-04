# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `tools/eeprom.py`: list, extract and verify BCM2711 SPI EEPROM images.
- Scripts to fetch and verify the pinned vendor firmware.
- Documentation of the BCM2711 boot chain and EEPROM image format.
- Continuous integration: license compliance, lint and tests.

### Changed

- Tie BCM2711 firmware observations to pinned files, hashes and offsets; separate unverified behavior from format evidence.
