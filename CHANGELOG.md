# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ARM mapping-table contract with twelve complete synthetic calls,
  actual repeated state and retained writes on a wrapped-index failure.
- Freestanding ARM object registration and repeated-open helpers with exact
  profile validation, ordered observations and six complete fixture comparisons.
- ARM object registration and repeated-open contracts with six complete
  synthetic calls, one first-open prefix and explicit retained-record fields.
- Owned fixed ARM start composition with whole-path validation, retained
  nested results, ordered active-state storage and complete fixture comparisons.
- Fixed ARM start composition with explicit resource-object binding,
  two complete synthetic calls and two lower-return checkpoints.
- Owned fixed resource composition with shared clock state, algorithmic
  control requests, whole-path preflight and complete fixture comparisons.
- Fixed resource composition with two state-sharing clock requests,
  ordered control-register operations and two complete synthetic calls.
- Owned first clock composition with complete nested programming, whole-path
  preflight, two complete fixture comparisons and source-return order checks.
- Cold clock-request composition and completed-cache repeated requests with
  full provider preflight and four additional synthetic fixture comparisons.
- First fixed clock-composition contract with two complete synthetic calls,
  two source-return prefixes and explicit nested state ownership.
- Freestanding fixed source, native-word and divider clock helpers with
  complete read-plan preflight and 22 synthetic fixture comparisons.
- Fixed clock-request state contracts and four synthetic cases for cold
  initialization, the first request and completed-cache repeated requests.
- Freestanding fixed clock-request and cold-initializer helpers with declared
  replies, bounded profiles and 12 complete synthetic fixture comparisons.
- Fixed source, selected-word and divider clock contracts with 22 synthetic
  cases and a strict public recorder for finite MMIO replies and one RAM cell.
- Fixed clock-request contract and 12 synthetic cases for planning,
  cache order, notification replies and separate lazy initialization, with
  lookup-miss ordering at diagnostic and notification boundaries and
  explicit diagnostic argument words.
- Freestanding fixed resource-request helper with literal boundary replies,
  tagged return/stop outcomes and 16 synthetic fixture comparisons.
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

### Fixed

- Run macOS CI on Intel runners to avoid ARM64 allocation failures.
- Initialize clock and resource composition validation buffers so optimized
  GCC builds pass with uninitialized-value warnings treated as errors.

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
