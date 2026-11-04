# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Fixed resource-request contract and 17 synthetic cases for dependency
  order, shared-state suppression and conditional check-context behavior.
- Standard-pair lower-span arithmetic and 27 synthetic cases for explicit
  byte-argument transfers into the memory-bank serializer.
- Freestanding memory-bank serializer with bounded output, explicit host
  validation and 44 complete synthetic fixture comparisons.
- Memory-bank serialization contract and 48 synthetic cases for ordered
  big-endian cells, numeric range selection and bounded caller stores.
- Freestanding memory-capacity helper with ordered byte callbacks, separate
  MiB/class outputs and 24 complete synthetic fixture comparisons.
- Memory-capacity calculation contract and 28 synthetic cases, with separate
  MiB/class observations and explicit instruction preparation for replay.
- BCM2711 PLLB register addresses and fields from pinned public sources,
  with explicit applicability and clock-state limits.
- Freestanding ARM configuration-request and software start-request helpers,
  with 40 synthetic fixture comparisons and separate host validation results.
- ARM service and mutex return-word checks, with 17 synthetic vectors
  for ignored replies and preserved resource results.
- ARM configuration-request routing and software start-request gates,
  with 24 synthetic vectors and explicit service boundaries.
- Ordinary ELF feature-word requirements, 35 synthetic compatibility
  vectors and conditional observations for the open VPU image.
- Freestanding boot-information parser, cache lookup, zeroing allocator,
  bounded revision fallback and metadata-pointer preparation, with 126
  synthetic fixture comparisons and host bounds checks.
- Boot-information record layouts, copy bounds, allocation zeroing and
  state-pointer execution vectors.
- Pinned VPU bring-up build with ELF bounds checks and a separate BCM2711
  ARM entry stub build; ARM handoff and Linux loading remain unimplemented.
- Freestanding ARM stub metadata preparation with five synthetic fixture
  comparisons and host buffer bounds checks.
- Repeatable headless Ghidra imports and metadata exports for four BCM2711 firmware stages.
- Scalar calling-convention observations and library entry points for the pinned firmware.
- Boot-flow documentation and synthetic execution vectors for resource loading,
  digest checks, SDRAM selection, configuration, boot modes and firmware loading.
- Scalar fixture capture with explicit memory and device-call boundaries.
- Filename override and zero-length fixup checks for replacement firmware loading.
- ARM stub metadata format and five scalar execution vectors for buffer preparation.

### Changed

- Reserve LR in the isolated boot-information VPU compilation target.

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
