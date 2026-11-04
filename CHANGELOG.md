# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repeatable headless Ghidra imports and metadata exports for four BCM2711 firmware stages.
- Scalar calling-convention observations and library entry points for the pinned firmware.
- Boot-flow documentation and synthetic execution vectors for resource loading,
  digest checks, SDRAM selection, configuration, boot modes and firmware loading.
- Scalar fixture capture with explicit memory and device-call boundaries.
- Filename override and zero-length fixup checks for replacement firmware loading.

## [0.1.1] - 2026-11-04

### Fixed

- Use LZSS history snapshots for references and reject unwritten history.
- Limit LZSS encoder matches to bytes initialized before each reference.

## [0.1.0] - 2026-11-04

### Added

- `tools/eeprom.py`: list, extract, verify and rebuild BCM2711 SPI EEPROM images.
- Lossless EEPROM image serialization and LZSS/LZ4 section encoders, with
  regression tests across the pinned image catalog.
- Scripts to fetch and verify the pinned vendor firmware.
- Documentation of the BCM2711 boot chain and EEPROM image format.
- Continuous integration: license compliance, lint and tests.

### Changed

- Tie BCM2711 firmware observations to pinned files, hashes and offsets; separate unverified behavior from format evidence.
- Reject existing output files and unsafe or duplicate extraction filenames.
